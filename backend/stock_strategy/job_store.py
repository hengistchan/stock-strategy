from __future__ import annotations

import asyncio
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Mapping
import uuid

from .market_cache import MarketDataCache
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


JOB_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")


class JobStore:
    """Persist and serialize local backtest subprocess execution."""

    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        timeout_seconds: int = 300,
        opend_host: str | None = None,
        opend_port: int | None = None,
    ):
        self.project_root = project_root.resolve()
        self.root = (self.project_root / "runs" / "web").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.opend_host = opend_host or os.environ.get("OPEND_HOST", "127.0.0.1")
        self.opend_port = opend_port or int(os.environ.get("OPEND_PORT", "11111"))
        self.cache = MarketDataCache(self.project_root)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._execution_lock = asyncio.Lock()
        self._reconcile_interrupted_jobs()

    def create_job(
        self,
        request: Mapping[str, Any],
        strategy_path: Path,
        *,
        strategy_source: str | None = None,
        strategy_revision: str | None = None,
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
                "run_dir": None,
                "stdout": "",
                "stderr": "",
                "error": None,
            }
            self._write_job(payload)
            return payload
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise

    def launch(self, job_id: str) -> None:
        task = asyncio.create_task(self._run_job(job_id))
        self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(job_id, None))

    async def run_job(self, job_id: str) -> None:
        await self._run_job(job_id)

    async def _run_job(self, job_id: str) -> None:
        async with self._execution_lock:
            await self._execute_job(job_id)

    async def _execute_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job.update(status="running", started_at=_now())
        self._write_job(job)
        command = self.build_command(job)
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(BACKEND_ROOT)
            if not existing_pythonpath
            else str(BACKEND_ROOT) + os.pathsep + existing_pythonpath
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.project_root),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            job.update(
                status="failed",
                finished_at=_now(),
                error=f"回测超过 {self.timeout_seconds} 秒，已终止。",
            )
            self._write_job(job)
            return
        except Exception as error:
            job.update(status="failed", finished_at=_now(), error=str(error))
            self._write_job(job)
            return

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        job.update(stdout=stdout[-12_000:], stderr=stderr[-12_000:], finished_at=_now())
        cache_error: Exception | None = None
        try:
            cache_entry = self.cache.record(job["request"])
            if cache_entry:
                self._snapshot_market_data(job, cache_entry)
        except (OSError, ValueError, csv.Error) as error:
            cache_error = error
        if process.returncode != 0:
            job.update(status="failed", error=last_error(stderr, stdout))
            self._write_job(job)
            return
        if not job.get("market_data_path"):
            detail = str(cache_error) if cache_error else "OpenD 缓存不存在"
            job.update(
                status="failed",
                error=f"回测完成但无法冻结 OpenD 行情快照：{detail}",
            )
            self._write_job(job)
            return

        output_root = self._job_dir(job_id) / "output"
        summaries = sorted(output_root.glob("*/summary.json"))
        if not summaries:
            job.update(status="failed", error="回测结束但没有生成 summary.json。")
            self._write_job(job)
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
            job.update(
                status="failed",
                error="回测结果缺少审计产物：" + ", ".join(missing_artifacts),
            )
            self._write_job(job)
            return
        update_run_manifest(
            self._job_dir(job_id) / "manifest.json",
            artifacts=artifact_inventory(run_dir, self._job_dir(job_id)),
        )
        job.update(status="succeeded", run_dir=str(summaries[-1].parent.resolve()))
        self._write_job(job)

    def build_command(self, job: dict[str, Any]) -> list[str]:
        request = job["request"]
        session = request.get("session") or "ALL"
        job_dir = self._job_dir(job["id"])
        cache_path = self.cache.descriptor(request)["path"]
        command = [
            sys.executable,
            "-m",
            "stock_strategy",
            "--strategy",
            str(self._strategy_execution_path(job)),
            "--opend",
            "--symbol",
            request["symbol"],
            "--start",
            request["start"],
            "--end",
            request["end"],
            "--ktype",
            request["ktype"],
            "--autype",
            request["autype"],
            "--session",
            session,
            "--initial-cash",
            str(request["initial_cash"]),
            "--commission-bps",
            str(request["commission_bps"]),
            "--min-commission",
            str(request["min_commission"]),
            "--slippage-bps",
            str(request["slippage_bps"]),
            "--warmup-bars",
            str(request["warmup_bars"]),
            "--opend-cache",
            str(cache_path),
            "--opend-host",
            self.opend_host,
            "--opend-port",
            str(self.opend_port),
            "--output",
            str(job_dir / "output"),
        ]
        for name, value in sorted((request.get("parameters") or {}).items()):
            command.extend(
                ["--parameter", f"{name}={json.dumps(value, ensure_ascii=False)}"]
            )
        if request.get("refresh_cache", False):
            command.append("--refresh-opend-cache")
        if request["allow_short"]:
            command.append("--allow-short")
        if request.get("liquidate_on_end", False):
            command.append("--liquidate-on-end")
        return command

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = []
        for path in self.root.glob("*/job.json"):
            try:
                jobs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(jobs, key=lambda job: job.get("created_at", ""), reverse=True)

    def get_job(self, job_id: str) -> dict[str, Any]:
        path = self._job_dir(job_id) / "job.json"
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

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
        atomic_write_json(path, payload)
        manifest_path = path.parent / "manifest.json"
        if manifest_path.is_file():
            update_run_manifest(
                manifest_path,
                status=str(payload["status"]),
                started_at=payload.get("started_at"),
                finished_at=payload.get("finished_at"),
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
                job.update(
                    status="failed",
                    finished_at=_now(),
                    error="Web 服务重启，上一轮回测已中断。",
                )
                self._write_job(job)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def last_error(stderr: str, stdout: str) -> str:
    stderr_lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if stderr_lines:
        return stderr_lines[-1]
    stdout_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return stdout_lines[-1] if stdout_lines else "回测进程失败，未返回错误信息。"
