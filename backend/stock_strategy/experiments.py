from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from itertools import product
from pathlib import Path
import re
import shutil
from statistics import fmean, median, pstdev
from typing import Any, Mapping, Protocol, Sequence
import uuid

from .event_stream import EventBroker
from .run_manifest import StrategySnapshot, atomic_write_json, atomic_write_text
from .state_repository import SqliteExperimentRepository


EXPERIMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")
MAX_EXPERIMENT_RUNS = 36
MAX_EXPERIMENT_JOBS = 72
EXPERIMENT_OBJECTIVES = frozenset(
    {"total_return_pct", "sharpe_ratio", "max_drawdown_pct"}
)
CONSTRAINT_METRICS = frozenset(
    {
        "total_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "total_trades",
        "total_fees",
        "exposure_pct",
    }
)
PARETO_OBJECTIVES = {
    "total_return_pct": "maximize",
    "sharpe_ratio": "maximize",
    "max_drawdown_pct": "maximize",
    "total_fees": "minimize",
}


class JobStoreProtocol(Protocol):
    def create_job(
        self,
        request: Mapping[str, Any],
        strategy_path: Path,
        *,
        strategy_source: str | None = None,
        strategy_revision: str | None = None,
    ) -> dict[str, Any]: ...

    async def run_job(self, job_id: str) -> None: ...

    def get_job(self, job_id: str) -> dict[str, Any]: ...

    def load_result(self, job_id: str) -> dict[str, Any]: ...


def expand_parameter_grid(
    parameter_grid: Mapping[str, Sequence[Any]],
) -> list[dict[str, Any]]:
    if not parameter_grid:
        raise ValueError("parameter_grid cannot be empty")
    names = list(parameter_grid)
    value_lists: list[list[Any]] = []
    for name in names:
        values = list(parameter_grid[name])
        if not values:
            raise ValueError(f"parameter_grid {name!r} cannot be empty")
        deduplicated: list[Any] = []
        for value in values:
            if value not in deduplicated:
                deduplicated.append(value)
        value_lists.append(deduplicated)
    combinations = [dict(zip(names, values)) for values in product(*value_lists)]
    if len(combinations) > MAX_EXPERIMENT_RUNS:
        raise ValueError(
            f"experiment expands to {len(combinations)} runs; maximum is {MAX_EXPERIMENT_RUNS}"
        )
    return combinations


class ExperimentStore:
    def __init__(self, project_root: Path, job_store: JobStoreProtocol):
        self.project_root = project_root.resolve()
        self.root = (self.project_root / "runs" / "experiments").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.repository = SqliteExperimentRepository(
            self.project_root / "runs" / "state.sqlite3",
            self.root,
        )
        self.job_store = job_store
        self.events = getattr(job_store, "events", EventBroker())
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._reconcile_interrupted()

    def create(
        self,
        *,
        name: str,
        base_request: Mapping[str, Any],
        parameter_grid: Mapping[str, Sequence[Any]],
        strategy_path: Path,
        strategy_source: str | None = None,
        strategy_revision: str | None = None,
        objective: str,
        validation_window: Mapping[str, str] | None = None,
        test_window: Mapping[str, str] | None = None,
        walk_forward_folds: int = 0,
        constraints: Sequence[Mapping[str, Any]] = (),
        symbols: Sequence[str] = (),
    ) -> dict[str, Any]:
        if objective not in EXPERIMENT_OBJECTIVES:
            raise ValueError(f"unsupported experiment objective: {objective}")
        normalized_symbols = list(dict.fromkeys(symbols))
        combinations = (
            [{} for _symbol in normalized_symbols]
            if normalized_symbols
            else expand_parameter_grid(parameter_grid)
        )
        normalized_constraints = _validate_constraints(constraints)
        walk_forward_windows = (
            build_walk_forward_windows(base_request, walk_forward_folds)
            if walk_forward_folds
            else []
        )
        planned_jobs = len(combinations) * (
            len(walk_forward_windows) * 2 if walk_forward_windows else 1
        )
        if planned_jobs > MAX_EXPERIMENT_JOBS:
            raise ValueError(
                f"experiment plans {planned_jobs} jobs; maximum is "
                f"{MAX_EXPERIMENT_JOBS}"
            )
        experiment_id = (
            f"exp-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )
        directory = self._directory(experiment_id)
        directory.mkdir(parents=True, exist_ok=False)
        try:
            snapshot = StrategySnapshot.create(
                source_path=str(strategy_path.resolve().relative_to(self.project_root)),
                content=(
                    strategy_source
                    if strategy_source is not None
                    else strategy_path.read_text(encoding="utf-8")
                ),
                revision=strategy_revision,
            )
            snapshot_path = directory / "strategy.py"
            atomic_write_text(snapshot_path, snapshot.content)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        payload = {
            "id": experiment_id,
            "name": name.strip() or f"参数实验 {datetime.now().strftime('%m-%d %H:%M')}",
            "status": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "objective": objective,
            "kind": "batch_validation" if normalized_symbols else "parameter_search",
            "constraints": normalized_constraints,
            "symbols": normalized_symbols,
            "base_request": dict(base_request),
            "validation_window": (
                dict(validation_window) if validation_window else None
            ),
            "test_window": dict(test_window) if test_window else None,
            "walk_forward_folds": walk_forward_folds,
            "walk_forward_windows": walk_forward_windows,
            "parameter_grid": {key: list(values) for key, values in parameter_grid.items()},
            "strategy_path": snapshot.source_path,
            "strategy_revision": snapshot.revision,
            "strategy_snapshot_path": str(snapshot_path.relative_to(self.project_root)),
            "progress": {"completed": 0, "total": len(combinations)},
            "runs": [
                {
                    "index": index + 1,
                    "symbol": (
                        normalized_symbols[index] if normalized_symbols else None
                    ),
                    "parameters": parameters,
                    "job_id": None,
                    "status": "queued",
                    "metrics": None,
                    "score": None,
                    "rank": None,
                    "constraints_satisfied": None,
                    "constraint_violations": [],
                    "pareto_optimal": False,
                    "error": None,
                    "phases": {},
                }
                for index, parameters in enumerate(combinations)
            ],
        }
        self._write(payload)
        return payload

    def launch(self, experiment_id: str) -> None:
        task = asyncio.create_task(self._run(experiment_id))
        self._tasks[experiment_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(experiment_id, None))

    async def _run(self, experiment_id: str) -> None:
        experiment = self.get(experiment_id)
        experiment.update(status="running", started_at=_now())
        self._write(experiment)
        strategy_path = self.project_root / experiment["strategy_path"]
        snapshot_value = experiment.get("strategy_snapshot_path")
        snapshot_path = (
            self.project_root / snapshot_value
            if snapshot_value
            else strategy_path
        )
        strategy_source = snapshot_path.read_text(encoding="utf-8")
        strategy_revision = experiment.get("strategy_revision")
        for run in experiment["runs"]:
            try:
                request = dict(experiment["base_request"])
                if run.get("symbol"):
                    request["symbol"] = run["symbol"]
                request["parameters"] = {
                    **dict(request.get("parameters") or {}),
                    **dict(run["parameters"]),
                }
                request["refresh_cache"] = False
                walk_forward_windows = experiment.get("walk_forward_windows") or []
                if walk_forward_windows:
                    validation_phases: list[dict[str, Any]] = []
                    for fold_index, fold in enumerate(
                        walk_forward_windows,
                        start=1,
                    ):
                        train_request = {
                            **request,
                            **fold["train"],
                        }
                        train = await self._run_phase(
                            experiment,
                            run,
                            f"fold_{fold_index}_train",
                            train_request,
                            strategy_path,
                            strategy_source,
                            strategy_revision,
                        )
                        if train["status"] != "succeeded":
                            break
                        validation_request = {
                            **request,
                            **fold["validation"],
                        }
                        validation = await self._run_phase(
                            experiment,
                            run,
                            f"fold_{fold_index}_validation",
                            validation_request,
                            strategy_path,
                            strategy_source,
                            strategy_revision,
                        )
                        validation_phases.append(validation)
                        if validation["status"] != "succeeded":
                            break
                    successful = (
                        len(validation_phases) == len(walk_forward_windows)
                        and all(
                            phase["status"] == "succeeded"
                            for phase in validation_phases
                        )
                    )
                    last_phase = (
                        validation_phases[-1]
                        if validation_phases
                        else train
                    )
                    run["job_id"] = last_phase.get("job_id")
                    run["status"] = "succeeded" if successful else "failed"
                    run["metrics"] = (
                        _aggregate_metrics(validation_phases)
                        if successful
                        else None
                    )
                    run["score"] = (
                        run["metrics"].get(experiment["objective"])
                        if run["metrics"]
                        else None
                    )
                    run["error"] = (
                        None if successful else last_phase.get("error")
                    )
                else:
                    train = await self._run_phase(
                        experiment,
                        run,
                        "train",
                        request,
                        strategy_path,
                        strategy_source,
                        strategy_revision,
                    )
                    scoring_phase = train
                    validation_window = experiment.get("validation_window")
                    if train["status"] == "succeeded" and validation_window:
                        validation_request = {
                            **request,
                            "start": validation_window["start"],
                            "end": validation_window["end"],
                        }
                        scoring_phase = await self._run_phase(
                            experiment,
                            run,
                            "validation",
                            validation_request,
                            strategy_path,
                            strategy_source,
                            strategy_revision,
                        )
                    run["job_id"] = scoring_phase.get("job_id")
                    run["status"] = scoring_phase["status"]
                    run["metrics"] = scoring_phase.get("metrics")
                    run["score"] = (
                        scoring_phase.get("metrics", {}).get(
                            experiment["objective"]
                        )
                        if scoring_phase["status"] == "succeeded"
                        else None
                    )
                    run["error"] = scoring_phase.get("error")
            except Exception as error:
                run.update(status="failed", error=str(error))
            experiment["progress"]["completed"] += 1
            self._evaluate_candidates(experiment)
            self._write(experiment)

        self._evaluate_candidates(experiment)
        selected = next(
            (run for run in experiment["runs"] if run.get("rank") == 1),
            None,
        )
        test_status: str | None = None
        if selected is not None and experiment.get("test_window"):
            test_window = experiment["test_window"]
            test_request = {
                **dict(experiment["base_request"]),
                "start": test_window["start"],
                "end": test_window["end"],
                "parameters": {
                    **dict(experiment["base_request"].get("parameters") or {}),
                    **dict(selected["parameters"]),
                },
                "refresh_cache": False,
            }
            test_phase = await self._run_phase(
                experiment,
                selected,
                "test",
                test_request,
                strategy_path,
                strategy_source,
                strategy_revision,
            )
            test_status = test_phase["status"]

        succeeded_count = sum(
            run["status"] == "succeeded" for run in experiment["runs"]
        )
        if succeeded_count == len(experiment["runs"]) and test_status in {
            None,
            "succeeded",
        }:
            final_status = "succeeded"
        elif succeeded_count:
            final_status = "completed_with_errors"
        else:
            final_status = "failed"
        experiment.update(
            status=final_status,
            finished_at=_now(),
            research_summary=self._research_summary(experiment, selected),
        )
        self._evaluate_candidates(experiment)
        self._write(experiment)

    async def _run_phase(
        self,
        experiment: dict[str, Any],
        run: dict[str, Any],
        phase_name: str,
        request: Mapping[str, Any],
        strategy_path: Path,
        strategy_source: str,
        strategy_revision: str | None,
    ) -> dict[str, Any]:
        phase = {
            "job_id": None,
            "status": "queued",
            "metrics": None,
            "error": None,
            "window": {
                "start": str(request.get("start") or ""),
                "end": str(request.get("end") or ""),
            },
        }
        run["phases"][phase_name] = phase
        try:
            job = self.job_store.create_job(
                request,
                strategy_path,
                strategy_source=strategy_source,
                strategy_revision=strategy_revision,
            )
            phase.update(job_id=job["id"], status="running")
            if phase_name != "test":
                run["status"] = "running"
            self._write(experiment)
            await self.job_store.run_job(job["id"])
            completed_job = self.job_store.get_job(job["id"])
            phase["status"] = completed_job["status"]
            if completed_job["status"] == "succeeded":
                result = self.job_store.load_result(job["id"])
                phase["metrics"] = result["summary"]["metrics"]
            else:
                phase["error"] = completed_job.get("error") or "回测失败"
        except Exception as error:
            phase.update(status="failed", error=str(error))
        self._write(experiment)
        return phase

    @staticmethod
    def _research_summary(
        experiment: Mapping[str, Any],
        selected: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if experiment.get("kind") == "batch_validation":
            return _batch_research_summary(experiment)
        if selected is None:
            return {
                "mode": "in_sample",
                "selected_parameters": None,
                "out_of_sample": False,
            }
        phases = selected.get("phases", {})
        validation = phases.get("validation")
        test = phases.get("test")
        validation_phases = [
            phase
            for name, phase in phases.items()
            if name == "validation" or name.endswith("_validation")
        ]
        robustness_phases = [
            phase
            for phase in [*validation_phases, test]
            if phase is not None
        ]
        observed = [
            phase
            for phase in (robustness_phases or phases.values())
            if phase.get("status") == "succeeded" and phase.get("metrics")
        ]
        returns = [
            float(phase["metrics"]["total_return_pct"])
            for phase in observed
            if phase["metrics"].get("total_return_pct") is not None
        ]
        drawdowns = [
            float(phase["metrics"]["max_drawdown_pct"])
            for phase in observed
            if phase["metrics"].get("max_drawdown_pct") is not None
        ]
        scores = [
            float(phase["metrics"][experiment["objective"]])
            for phase in observed
            if phase["metrics"].get(experiment["objective"]) is not None
        ]
        score_mean = fmean(scores) if scores else None
        score_stability = (
            max(
                0.0,
                1.0 - pstdev(scores) / (abs(score_mean) + 1e-12),
            )
            if len(scores) > 1 and score_mean is not None
            else (1.0 if scores else None)
        )
        walk_forward = bool(experiment.get("walk_forward_windows"))
        return {
            "mode": (
                "walk_forward"
                if walk_forward
                else (
                "train_validation_test"
                if experiment.get("validation_window")
                else "in_sample"
                )
            ),
            "selected_parameters": dict(selected["parameters"]),
            "out_of_sample": bool(validation_phases),
            "validation_metrics": (
                selected.get("metrics")
                if walk_forward
                else (
                    validation.get("metrics")
                    if validation is not None
                    else None
                )
            ),
            "test_metrics": test.get("metrics") if test is not None else None,
            "walk_forward_windows": (
                experiment.get("walk_forward_windows") if walk_forward else []
            ),
            "window_results": [
                {
                    "window": phase["window"],
                    "metrics": phase["metrics"],
                }
                for phase in observed
            ],
            "parameter_stability": score_stability,
            "positive_window_ratio": (
                sum(value > 0 for value in returns) / len(returns)
                if returns
                else None
            ),
            "worst_window_drawdown_pct": min(drawdowns) if drawdowns else None,
        }

    def list(self) -> list[dict[str, Any]]:
        return self.repository.list()

    def get(self, experiment_id: str) -> dict[str, Any]:
        if not EXPERIMENT_ID_PATTERN.fullmatch(experiment_id):
            raise KeyError(experiment_id)
        return self.repository.get(experiment_id)

    def _evaluate_candidates(self, experiment: dict[str, Any]) -> None:
        constraints = experiment.get("constraints") or []
        for run in experiment["runs"]:
            if run.get("status") != "succeeded" or not run.get("metrics"):
                run["constraints_satisfied"] = None
                run["constraint_violations"] = []
                run["pareto_optimal"] = False
                continue
            violations = _constraint_violations(run["metrics"], constraints)
            run["constraint_violations"] = violations
            run["constraints_satisfied"] = not violations

        succeeded = [
            run
            for run in experiment["runs"]
            if (
                run.get("status") == "succeeded"
                and run.get("score") is not None
                and run.get("constraints_satisfied") is not False
            )
        ]
        succeeded.sort(key=lambda run: float(run["score"]), reverse=True)
        for run in experiment["runs"]:
            run["rank"] = None
        for rank, run in enumerate(succeeded, start=1):
            run["rank"] = rank
        _mark_pareto_frontier(succeeded)

    def _directory(self, experiment_id: str) -> Path:
        if not EXPERIMENT_ID_PATTERN.fullmatch(experiment_id):
            raise KeyError(experiment_id)
        path = (self.root / experiment_id).resolve()
        if path.parent != self.root:
            raise KeyError(experiment_id)
        return path

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.repository.upsert(payload)
        path = self._directory(str(payload["id"])) / "experiment.json"
        atomic_write_json(path, payload)
        self.events.publish(
            "experiment.updated",
            {
                "id": str(payload["id"]),
                "status": str(payload["status"]),
                "completed": int(payload.get("progress", {}).get("completed", 0)),
                "total": int(payload.get("progress", {}).get("total", 0)),
                "updated_at": _now(),
            },
        )

    def _reconcile_interrupted(self) -> None:
        for experiment in self.list():
            if experiment.get("status") in {"queued", "running"}:
                experiment.update(
                    status="failed",
                    finished_at=_now(),
                )
                for run in experiment.get("runs", []):
                    if run.get("status") in {"queued", "running"}:
                        run.update(status="failed", error="Web 服务重启，实验已中断。")
                self._write(experiment)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_walk_forward_windows(
    base_request: Mapping[str, Any],
    folds: int,
) -> list[dict[str, dict[str, str]]]:
    if folds < 2 or folds > 5:
        raise ValueError("walk_forward_folds must be between 2 and 5")
    start = date.fromisoformat(str(base_request["start"]))
    end = date.fromisoformat(str(base_request["end"]))
    total_days = (end - start).days + 1
    segment_count = folds + 1
    if total_days < segment_count:
        raise ValueError("backtest period is too short for walk-forward folds")

    segments: list[dict[str, str]] = []
    for index in range(segment_count):
        segment_start = start + timedelta(days=total_days * index // segment_count)
        segment_end = (
            start
            + timedelta(days=total_days * (index + 1) // segment_count)
            - timedelta(days=1)
        )
        segments.append(
            {
                "start": segment_start.isoformat(),
                "end": segment_end.isoformat(),
            }
        )
    return [
        {
            "train": {
                "start": segments[0]["start"],
                "end": segments[index]["end"],
            },
            "validation": segments[index + 1],
        }
        for index in range(folds)
    ]


def _aggregate_metrics(phases: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    metrics = [
        phase["metrics"]
        for phase in phases
        if phase.get("status") == "succeeded" and phase.get("metrics")
    ]
    names = {
        name
        for phase_metrics in metrics
        for name, value in phase_metrics.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    return {
        name: fmean(
            float(phase_metrics[name])
            for phase_metrics in metrics
            if isinstance(phase_metrics.get(name), (int, float))
        )
        for name in names
    }


def _validate_constraints(
    constraints: Sequence[Mapping[str, Any]],
) -> list[dict[str, str | float]]:
    normalized: list[dict[str, str | float]] = []
    for constraint in constraints:
        metric = str(constraint.get("metric") or "")
        op = str(constraint.get("op") or "")
        if metric not in CONSTRAINT_METRICS:
            raise ValueError(f"unsupported constraint metric: {metric}")
        if op not in {">=", "<="}:
            raise ValueError(f"unsupported constraint operator: {op}")
        try:
            value = float(constraint["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("constraint value must be numeric") from error
        normalized.append({"metric": metric, "op": op, "value": value})
    return normalized


def _constraint_violations(
    metrics: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for constraint in constraints:
        metric = str(constraint["metric"])
        actual = metrics.get(metric)
        expected = float(constraint["value"])
        op = str(constraint["op"])
        satisfied = isinstance(actual, (int, float)) and (
            float(actual) >= expected if op == ">=" else float(actual) <= expected
        )
        if not satisfied:
            violations.append(
                {
                    "metric": metric,
                    "op": op,
                    "value": expected,
                    "actual": actual,
                }
            )
    return violations


def _mark_pareto_frontier(runs: Sequence[dict[str, Any]]) -> None:
    complete = [
        run
        for run in runs
        if all(
            isinstance(run.get("metrics", {}).get(metric), (int, float))
            for metric in PARETO_OBJECTIVES
        )
    ]
    for run in runs:
        run["pareto_optimal"] = False
    for candidate in complete:
        candidate["pareto_optimal"] = not any(
            _dominates(other["metrics"], candidate["metrics"])
            for other in complete
            if other is not candidate
        )


def _dominates(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    at_least_as_good = True
    strictly_better = False
    for metric, direction in PARETO_OBJECTIVES.items():
        left_value = float(left[metric])
        right_value = float(right[metric])
        if direction == "maximize":
            at_least_as_good &= left_value >= right_value
            strictly_better |= left_value > right_value
        else:
            at_least_as_good &= left_value <= right_value
            strictly_better |= left_value < right_value
    return at_least_as_good and strictly_better


def _batch_research_summary(
    experiment: Mapping[str, Any],
) -> dict[str, Any]:
    successful = [
        run
        for run in experiment.get("runs", [])
        if run.get("status") == "succeeded" and run.get("metrics")
    ]
    returns = [
        float(run["metrics"]["total_return_pct"])
        for run in successful
        if isinstance(run["metrics"].get("total_return_pct"), (int, float))
    ]
    sharpes = [
        float(run["metrics"]["sharpe_ratio"])
        for run in successful
        if isinstance(run["metrics"].get("sharpe_ratio"), (int, float))
    ]
    worst = min(
        successful,
        key=lambda run: float(run["metrics"].get("total_return_pct", float("inf"))),
        default=None,
    )
    return {
        "mode": "batch_validation",
        "selected_parameters": None,
        "out_of_sample": True,
        "symbol_count": len(experiment.get("symbols") or []),
        "successful_symbol_count": len(successful),
        "positive_symbol_ratio": (
            sum(value > 0 for value in returns) / len(returns) if returns else None
        ),
        "median_return_pct": median(returns) if returns else None,
        "median_sharpe_ratio": median(sharpes) if sharpes else None,
        "worst_symbol": worst.get("symbol") if worst else None,
        "worst_symbol_return_pct": (
            worst["metrics"].get("total_return_pct") if worst else None
        ),
    }
