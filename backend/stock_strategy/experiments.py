from __future__ import annotations

import asyncio
from datetime import datetime
from itertools import product
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Protocol, Sequence
import uuid

from .event_stream import EventBroker
from .run_manifest import StrategySnapshot, atomic_write_json, atomic_write_text


EXPERIMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")
MAX_EXPERIMENT_RUNS = 36
EXPERIMENT_OBJECTIVES = frozenset(
    {"total_return_pct", "sharpe_ratio", "max_drawdown_pct"}
)


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
    ) -> dict[str, Any]:
        if objective not in EXPERIMENT_OBJECTIVES:
            raise ValueError(f"unsupported experiment objective: {objective}")
        combinations = expand_parameter_grid(parameter_grid)
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
            "base_request": dict(base_request),
            "validation_window": (
                dict(validation_window) if validation_window else None
            ),
            "test_window": dict(test_window) if test_window else None,
            "parameter_grid": {key: list(values) for key, values in parameter_grid.items()},
            "strategy_path": snapshot.source_path,
            "strategy_revision": snapshot.revision,
            "strategy_snapshot_path": str(snapshot_path.relative_to(self.project_root)),
            "progress": {"completed": 0, "total": len(combinations)},
            "runs": [
                {
                    "index": index + 1,
                    "parameters": parameters,
                    "job_id": None,
                    "status": "queued",
                    "metrics": None,
                    "score": None,
                    "rank": None,
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
                request["parameters"] = {
                    **dict(request.get("parameters") or {}),
                    **dict(run["parameters"]),
                }
                request["refresh_cache"] = False
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
                    scoring_phase.get("metrics", {}).get(experiment["objective"])
                    if scoring_phase["status"] == "succeeded"
                    else None
                )
                run["error"] = scoring_phase.get("error")
            except Exception as error:
                run.update(status="failed", error=str(error))
            experiment["progress"]["completed"] += 1
            self._rank(experiment)
            self._write(experiment)

        self._rank(experiment)
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
        self._rank(experiment)
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
        if selected is None:
            return {
                "mode": "in_sample",
                "selected_parameters": None,
                "out_of_sample": False,
            }
        phases = selected.get("phases", {})
        validation = phases.get("validation")
        test = phases.get("test")
        observed = [
            phase
            for phase in phases.values()
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
        return {
            "mode": (
                "train_validation_test"
                if experiment.get("validation_window")
                else "in_sample"
            ),
            "selected_parameters": dict(selected["parameters"]),
            "out_of_sample": validation is not None,
            "validation_metrics": (
                validation.get("metrics") if validation is not None else None
            ),
            "test_metrics": test.get("metrics") if test is not None else None,
            "positive_window_ratio": (
                sum(value > 0 for value in returns) / len(returns)
                if returns
                else None
            ),
            "worst_window_drawdown_pct": min(drawdowns) if drawdowns else None,
        }

    def list(self) -> list[dict[str, Any]]:
        experiments: list[dict[str, Any]] = []
        for path in self.root.glob("*/experiment.json"):
            try:
                experiments.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(
            experiments, key=lambda item: item.get("created_at", ""), reverse=True
        )

    def get(self, experiment_id: str) -> dict[str, Any]:
        path = self._directory(experiment_id) / "experiment.json"
        if not path.is_file():
            raise KeyError(experiment_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _rank(self, experiment: dict[str, Any]) -> None:
        succeeded = [
            run
            for run in experiment["runs"]
            if run.get("status") == "succeeded" and run.get("score") is not None
        ]
        succeeded.sort(key=lambda run: float(run["score"]), reverse=True)
        for run in experiment["runs"]:
            run["rank"] = None
        for rank, run in enumerate(succeeded, start=1):
            run["rank"] = rank

    def _directory(self, experiment_id: str) -> Path:
        if not EXPERIMENT_ID_PATTERN.fullmatch(experiment_id):
            raise KeyError(experiment_id)
        path = (self.root / experiment_id).resolve()
        if path.parent != self.root:
            raise KeyError(experiment_id)
        return path

    def _write(self, payload: Mapping[str, Any]) -> None:
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
