from __future__ import annotations

import asyncio
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping
import uuid

from pydantic import BaseModel

from .market_cache import MarketDataCache
from .paths import BACKEND_ROOT, PROJECT_ROOT
from .result_reader import (
    load_price_window_payload,
    load_result_payload,
    validated_run_dir,
)
from .web_models import BacktestRequest


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
        self, request: BacktestRequest | Mapping[str, Any], strategy_path: Path
    ) -> dict[str, Any]:
        job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "id": job_id,
            "status": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "request": (
                request.model_dump(mode="json")
                if isinstance(request, BaseModel)
                else dict(request)
            ),
            "strategy_path": str(strategy_path.resolve().relative_to(self.project_root)),
            "run_dir": None,
            "stdout": "",
            "stderr": "",
            "error": None,
        }
        self._write_job(payload)
        return payload

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
        try:
            self.cache.record(job["request"])
        except (OSError, ValueError, csv.Error):
            pass
        if process.returncode != 0:
            job.update(status="failed", error=last_error(stderr, stdout))
            self._write_job(job)
            return

        output_root = self._job_dir(job_id) / "output"
        summaries = sorted(output_root.glob("*/summary.json"))
        if not summaries:
            job.update(status="failed", error="回测结束但没有生成 summary.json。")
            self._write_job(job)
            return
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
            str((self.project_root / job["strategy_path"]).resolve()),
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
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

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
