from __future__ import annotations

import asyncio
from datetime import datetime
from itertools import product
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import uuid


EXPERIMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")
MAX_EXPERIMENT_RUNS = 36
EXPERIMENT_OBJECTIVES = frozenset(
    {"total_return_pct", "sharpe_ratio", "max_drawdown_pct"}
)


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
    def __init__(self, project_root: Path, job_store: Any):
        self.project_root = project_root.resolve()
        self.root = (self.project_root / "runs" / "experiments").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.job_store = job_store
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._reconcile_interrupted()

    def create(
        self,
        *,
        name: str,
        base_request: Mapping[str, Any],
        parameter_grid: Mapping[str, Sequence[Any]],
        strategy_path: Path,
        objective: str,
    ) -> dict[str, Any]:
        if objective not in EXPERIMENT_OBJECTIVES:
            raise ValueError(f"unsupported experiment objective: {objective}")
        combinations = expand_parameter_grid(parameter_grid)
        experiment_id = (
            f"exp-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )
        directory = self._directory(experiment_id)
        directory.mkdir(parents=True, exist_ok=False)
        payload = {
            "id": experiment_id,
            "name": name.strip() or f"参数实验 {datetime.now().strftime('%m-%d %H:%M')}",
            "status": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "objective": objective,
            "base_request": dict(base_request),
            "parameter_grid": {key: list(values) for key, values in parameter_grid.items()},
            "strategy_path": str(strategy_path.resolve().relative_to(self.project_root)),
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
        for run_index, run in enumerate(experiment["runs"]):
            try:
                request = dict(experiment["base_request"])
                request["parameters"] = {
                    **dict(request.get("parameters") or {}),
                    **dict(run["parameters"]),
                }
                if run_index > 0:
                    request["refresh_cache"] = False
                job = self.job_store.create_job(request, strategy_path)
                run.update(job_id=job["id"], status="running")
                self._write(experiment)
                await self.job_store.run_job(job["id"])
                completed_job = self.job_store.get_job(job["id"])
                run["status"] = completed_job["status"]
                if completed_job["status"] == "succeeded":
                    result = self.job_store.load_result(job["id"])
                    metrics = result["summary"]["metrics"]
                    run["metrics"] = metrics
                    run["score"] = metrics.get(experiment["objective"])
                else:
                    run["error"] = completed_job.get("error") or "回测失败"
            except Exception as error:
                run.update(status="failed", error=str(error))
            experiment["progress"]["completed"] += 1
            self._rank(experiment)
            self._write(experiment)

        succeeded = any(run["status"] == "succeeded" for run in experiment["runs"])
        experiment.update(
            status="succeeded" if succeeded else "failed",
            finished_at=_now(),
        )
        self._rank(experiment)
        self._write(experiment)

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
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

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
