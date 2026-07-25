from __future__ import annotations

import asyncio
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping
import uuid

from .backtest_command import build_backtest_command
from .event_stream import EventBroker
from .market_cache import MarketDataCache
from .job_lifecycle import InvalidJobTransition, JobStatus, TERMINAL_JOB_STATUSES
from .paths import BACKEND_ROOT, PROJECT_ROOT
from .result_reader import (
    load_price_window_payload,
    load_result_payload,
    validated_run_dir,
)
from .run_manifest import (
    StrategySnapshot,
    artifact_inventory,
    atomic_write_json,
    atomic_write_text,
    create_run_manifest,
    sha256_file,
    update_run_manifest,
)
from .strategy_process import (
    StrategyProcessRunner,
    StrategyProcessTimeout,
    TRUSTED_EXECUTION_PROFILE,
)
from .state_repository import SqliteJobRepository


JOB_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")


class JobStore:
    """Persist and serialize local backtest subprocess execution."""

    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        timeout_seconds: int = 300,
        opend_host: str | None = None,
        opend_port: int | None = None,
        event_broker: EventBroker | None = None,
    ):
        self.project_root = project_root.resolve()
        self.root = (self.project_root / "runs" / "web").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.repository = SqliteJobRepository(
            self.project_root / "runs" / "state.sqlite3",
            self.root,
        )
        self.timeout_seconds = timeout_seconds
        self.opend_host = opend_host or os.environ.get("OPEND_HOST", "127.0.0.1")
        self.opend_port = opend_port or int(os.environ.get("OPEND_PORT", "11111"))
        self.cache = MarketDataCache(self.project_root)
        self.events = event_broker or EventBroker()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.process_runner = StrategyProcessRunner(
            backend_root=BACKEND_ROOT,
            working_directory=self.project_root,
            timeout_seconds=timeout_seconds,
        )
        self._execution_lock = asyncio.Lock()
        self._reconcile_interrupted_jobs()

    def create_job(
        self,
        request: Mapping[str, Any],
        strategy_path: Path,
        *,
        strategy_source: str | None = None,
        strategy_revision: str | None = None,
        retry_of: str | None = None,
    ) -> dict[str, Any]:
        job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        source_path = str(strategy_path.resolve().relative_to(self.project_root))
        try:
            snapshot = StrategySnapshot.create(
                source_path=source_path,
                content=(
                    strategy_source
                    if strategy_source is not None
                    else strategy_path.read_text(encoding="utf-8")
                ),
                revision=strategy_revision,
            )
            created_at = _now()
            serialized_request = dict(request)
            atomic_write_text(job_dir / "strategy.py", snapshot.content)
            atomic_write_json(job_dir / "request.json", serialized_request)
            atomic_write_json(
                job_dir / "manifest.json",
                create_run_manifest(
                    job_id=job_id,
                    created_at=created_at,
                    request=serialized_request,
                    strategy=snapshot,
                    futu_sdk_version=self.cache.futu_sdk_version,
                ),
            )
            payload = {
                "id": job_id,
                "status": "queued",
                "created_at": created_at,
                "started_at": None,
                "finished_at": None,
                "request": serialized_request,
                "strategy_path": source_path,
                "strategy_revision": snapshot.revision,
                "strategy_snapshot_path": str(
                    (job_dir / "strategy.py").relative_to(self.project_root)
                ),
                "market_data_path": None,
                "execution_profile": TRUSTED_EXECUTION_PROFILE,
                "retry_of": retry_of,
                "run_dir": None,
                "stdout": "",
                "stderr": "",
                "error": None,
            }
            self._write_job(payload)
            return payload
        except Exception:
            self.repository.delete(job_id)
            shutil.rmtree(job_dir, ignore_errors=True)
            raise

    def launch(self, job_id: str) -> None:
        task = asyncio.create_task(self._run_job(job_id))
        self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(job_id, None))

    async def run_job(self, job_id: str) -> None:
        await self._run_job(job_id)

    async def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        status = JobStatus(str(job["status"]))
        if status in TERMINAL_JOB_STATUSES:
            return job
        if status == JobStatus.QUEUED:
            task = self._tasks.get(job_id)
            if task is not None:
                task.cancel()
            try:
                return self._transition_job(
                    job_id,
                    JobStatus.CANCELLED,
                    finished_at=_now(),
                    error="回测已在执行前取消。",
                )
            except InvalidJobTransition:
                return await self.cancel(job_id)
        if status == JobStatus.RUNNING:
            job = self._transition_job(job_id, JobStatus.CANCELLING)
            self.process_runner.cancel(job_id)
            return job
        return job

    def retry(self, job_id: str) -> dict[str, Any]:
        original = self.get_job(job_id)
        if JobStatus(str(original["status"])) not in {
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            raise InvalidJobTransition("only failed or cancelled jobs can be retried")
        snapshot_value = original.get("strategy_snapshot_path")
        strategy_snapshot = (
            self.project_root / str(snapshot_value or original["strategy_path"])
        ).resolve()
        source = strategy_snapshot.read_text(encoding="utf-8")
        request = dict(original["request"])
        request["refresh_cache"] = False
        retried = self.create_job(
            request,
            self.project_root / str(original["strategy_path"]),
            strategy_source=source,
            strategy_revision=original.get("strategy_revision"),
            retry_of=job_id,
        )
        self.launch(retried["id"])
        return retried

    async def _run_job(self, job_id: str) -> None:
        async with self._execution_lock:
            await self._execute_job(job_id)

    async def _execute_job(self, job_id: str) -> None:
        job = self._transition_job(
            job_id,
            JobStatus.RUNNING,
            started_at=_now(),
        )
        command = self.build_command(job)
        try:
            outcome = await self.process_runner.run(job_id, command)
        except StrategyProcessTimeout as error:
            self._transition_job(
                job_id,
                JobStatus.FAILED,
                finished_at=_now(),
                error=str(error),
            )
            return
        except Exception as error:
            self._transition_job(
                job_id,
                JobStatus.FAILED,
                finished_at=_now(),
                error=str(error),
            )
            return

        stdout = outcome.stdout
        stderr = outcome.stderr
        job.update(stdout=stdout, stderr=stderr, finished_at=_now())
        if self.get_job(job_id)["status"] == JobStatus.CANCELLING.value:
            self._transition_job(
                job_id,
                JobStatus.CANCELLED,
                stdout=job["stdout"],
                stderr=job["stderr"],
                finished_at=job["finished_at"],
                error="回测已由用户取消。",
            )
            return
        cache_error: Exception | None = None
        try:
            cache_entry = self.cache.record(job["request"])
            if cache_entry:
                self._snapshot_market_data(job, cache_entry)
        except (OSError, ValueError, csv.Error) as error:
            cache_error = error
        if outcome.returncode != 0:
            self._transition_job(
                job_id,
                JobStatus.FAILED,
                stdout=job["stdout"],
                stderr=job["stderr"],
                finished_at=job["finished_at"],
                market_data_path=job.get("market_data_path"),
                error=last_error(stderr, stdout),
            )
            return
        if not job.get("market_data_path"):
            detail = str(cache_error) if cache_error else "OpenD 缓存不存在"
            self._transition_job(
                job_id,
                JobStatus.FAILED,
                stdout=job["stdout"],
                stderr=job["stderr"],
                finished_at=job["finished_at"],
                market_data_path=job.get("market_data_path"),
                error=f"回测完成但无法冻结 OpenD 行情快照：{detail}",
            )
            return

        output_root = self._job_dir(job_id) / "output"
        summaries = sorted(output_root.glob("*/summary.json"))
        if not summaries:
            self._transition_job(
                job_id,
                JobStatus.FAILED,
                stdout=job["stdout"],
                stderr=job["stderr"],
                finished_at=job["finished_at"],
                market_data_path=job.get("market_data_path"),
                error="回测结束但没有生成 summary.json。",
            )
            return
        if job.get("market_data_path"):
            self._bind_summary_to_market_snapshot(
                summaries[-1],
                (self.project_root / job["market_data_path"]).resolve(),
            )
        run_dir = summaries[-1].parent
        required_artifacts = {
            "summary.json",
            "orders.csv",
            "fills.csv",
            "trades.csv",
            "equity_curve.csv",
            "daily_returns.csv",
            "logs.csv",
            "report.svg",
        }
        missing_artifacts = sorted(
            name for name in required_artifacts if not (run_dir / name).is_file()
        )
        if missing_artifacts:
            self._transition_job(
                job_id,
                JobStatus.FAILED,
                stdout=job["stdout"],
                stderr=job["stderr"],
                finished_at=job["finished_at"],
                market_data_path=job.get("market_data_path"),
                error="回测结果缺少审计产物：" + ", ".join(missing_artifacts),
            )
            return
        update_run_manifest(
            self._job_dir(job_id) / "manifest.json",
            artifacts=artifact_inventory(run_dir, self._job_dir(job_id)),
        )
        self._transition_job(
            job_id,
            JobStatus.SUCCEEDED,
            stdout=job["stdout"],
            stderr=job["stderr"],
            finished_at=job["finished_at"],
            market_data_path=job["market_data_path"],
            run_dir=str(summaries[-1].parent.resolve()),
        )

    def build_command(self, job: dict[str, Any]) -> list[str]:
        request = job["request"]
        job_dir = self._job_dir(job["id"])
        cache_path = self.cache.descriptor(request)["path"]
        return build_backtest_command(
            job,
            strategy_path=self._strategy_execution_path(job),
            cache_path=cache_path,
            output_path=job_dir / "output",
            opend_host=self.opend_host,
            opend_port=self.opend_port,
        )

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.repository.list()

    def get_job(self, job_id: str) -> dict[str, Any]:
        self._job_dir(job_id)
        return self.repository.get(job_id)

    def load_result(self, job_id: str) -> dict[str, Any]:
        return load_result_payload(
            project_root=self.project_root,
            jobs_root=self.root,
            job=self.get_job(job_id),
        )

    def load_price_window(
        self, job_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        return load_price_window_payload(
            project_root=self.project_root,
            jobs_root=self.root,
            job=self.get_job(job_id),
            offset=offset,
            limit=limit,
        )

    def report_path(self, job_id: str) -> Path:
        run_dir = validated_run_dir(self.root, self.get_job(job_id))
        path = run_dir / "report.svg"
        if not path.is_file():
            raise RuntimeError("找不到回测图表。")
        return path

    def _job_dir(self, job_id: str) -> Path:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise KeyError(job_id)
        path = (self.root / job_id).resolve()
        if self.root not in path.parents:
            raise KeyError(job_id)
        return path

    def _write_job(self, payload: dict[str, Any]) -> None:
        path = self._job_dir(payload["id"]) / "job.json"
        self.repository.upsert(payload)
        atomic_write_json(path, payload)
        manifest_path = path.parent / "manifest.json"
        if manifest_path.is_file():
            update_run_manifest(
                manifest_path,
                status=str(payload["status"]),
                started_at=payload.get("started_at"),
                finished_at=payload.get("finished_at"),
            )
        self._publish_job(payload)

    def _transition_job(
        self,
        job_id: str,
        target_status: JobStatus,
        **updates: Any,
    ) -> dict[str, Any]:
        payload = self.repository.transition(job_id, target_status.value, updates)
        path = self._job_dir(job_id) / "job.json"
        atomic_write_json(path, payload)
        manifest_path = path.parent / "manifest.json"
        if manifest_path.is_file():
            update_run_manifest(
                manifest_path,
                status=target_status.value,
                started_at=payload.get("started_at"),
                finished_at=payload.get("finished_at"),
            )
        self._publish_job(payload)
        return payload

    def _publish_job(self, payload: Mapping[str, Any]) -> None:
        self.events.publish(
            "job.updated",
            {
                "id": str(payload["id"]),
                "status": str(payload["status"]),
                "updated_at": _now(),
            },
        )

    def _strategy_execution_path(self, job: Mapping[str, Any]) -> Path:
        snapshot_value = job.get("strategy_snapshot_path")
        if snapshot_value:
            snapshot_path = (self.project_root / str(snapshot_value)).resolve()
            job_dir = self._job_dir(str(job["id"]))
            if snapshot_path.parent == job_dir and snapshot_path.name == "strategy.py":
                return snapshot_path
        return (self.project_root / str(job["strategy_path"])).resolve()

    def _snapshot_market_data(
        self,
        job: dict[str, Any],
        cache_entry: Mapping[str, Any],
    ) -> None:
        source = (self.project_root / str(cache_entry["path"])).resolve()
        destination = self._job_dir(str(job["id"])) / "market-data.csv"
        temporary = destination.with_suffix(".csv.tmp")
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        snapshot_sha256 = sha256_file(destination)
        if snapshot_sha256 != cache_entry["content_sha256"]:
            destination.unlink(missing_ok=True)
            raise OSError("OpenD 行情在生成任务快照时发生变化")
        job["market_data_path"] = str(destination.relative_to(self.project_root))
        update_run_manifest(
            self._job_dir(str(job["id"])) / "manifest.json",
            market_data={**cache_entry, "content_sha256": snapshot_sha256},
        )

    @staticmethod
    def _bind_summary_to_market_snapshot(
        summary_path: Path,
        snapshot_path: Path,
    ) -> None:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        opend = summary.setdefault("settings", {}).setdefault("opend", {})
        shared_cache_path = opend.get("cache_path")
        if shared_cache_path:
            opend["shared_cache_path"] = shared_cache_path
        opend["cache_path"] = str(snapshot_path)
        atomic_write_json(summary_path, summary)

    def _reconcile_interrupted_jobs(self) -> None:
        for job in self.list_jobs():
            if job.get("status") in {"queued", "running"}:
                self._transition_job(
                    str(job["id"]),
                    JobStatus.FAILED,
                    finished_at=_now(),
                    error="Web 服务重启，上一轮回测已中断。",
                )


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def last_error(stderr: str, stdout: str) -> str:
    stderr_lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if stderr_lines:
        return stderr_lines[-1]
    stdout_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return stdout_lines[-1] if stdout_lines else "回测进程失败，未返回错误信息。"
