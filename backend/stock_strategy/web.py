from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any, Callable, Literal
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .strategy_repository import (
    MAX_STRATEGY_BYTES,
    StrategyConflictError,
    StrategyNotFoundError,
    StrategyPermissionError,
    StrategyRepository,
    StrategyRepositoryError,
    StrategyValidationError,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _discover_project_root() -> Path:
    configured = os.environ.get("STOCK_STRATEGY_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = (BACKEND_ROOT.parent, Path.cwd(), *Path.cwd().parents)
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "examples").is_dir() and (resolved / "strategies").is_dir():
            return resolved
    return Path.cwd().resolve()


PROJECT_ROOT = _discover_project_root()
FRONTEND_ROOT = Path(__file__).resolve().parent / "web_dist"
JOB_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")
SYMBOL_PATTERN = r"^[A-Z]{2,8}\.[A-Z0-9.-]{1,24}$"
KLINE_TYPES = (
    "K_DAY",
    "K_WEEK",
    "K_1M",
    "K_3M",
    "K_5M",
    "K_10M",
    "K_15M",
    "K_30M",
    "K_60M",
    "K_120M",
    "K_180M",
    "K_240M",
)
SESSION_TYPES = ("ALL", "RTH", "ETH")


class BacktestRequest(BaseModel):
    strategy: str = "examples/ma_cross.py"
    symbol: str = Field(default="US.AAPL", pattern=SYMBOL_PATTERN)
    start: date
    end: date
    ktype: Literal[
        "K_DAY",
        "K_WEEK",
        "K_1M",
        "K_3M",
        "K_5M",
        "K_10M",
        "K_15M",
        "K_30M",
        "K_60M",
        "K_120M",
        "K_180M",
        "K_240M",
    ] = "K_DAY"
    autype: Literal["QFQ", "HFQ", "NONE"] = "QFQ"
    session: Literal["ALL", "RTH", "ETH"] = "ALL"
    initial_cash: float = Field(default=100_000, gt=0)
    commission_bps: float = Field(default=3, ge=0, le=1_000)
    min_commission: float = Field(default=1, ge=0)
    slippage_bps: float = Field(default=5, ge=0, le=1_000)
    warmup_bars: int = Field(default=0, ge=0, le=100_000)
    allow_short: bool = False
    liquidate_on_end: bool = False


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=67)
    content: str | None = Field(default=None, max_length=MAX_STRATEGY_BYTES)
    template_path: str | None = Field(default=None, max_length=200)


class StrategySaveRequest(BaseModel):
    content: str = Field(max_length=MAX_STRATEGY_BYTES)
    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)


class JobStore:
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
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._reconcile_interrupted_jobs()

    def create_job(self, request: BacktestRequest, strategy_path: Path) -> dict[str, Any]:
        job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "id": job_id,
            "status": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "request": request.model_dump(mode="json"),
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

    async def _run_job(self, job_id: str) -> None:
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
        if process.returncode != 0:
            job.update(status="failed", error=_last_error(stderr, stdout))
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
        cache_name = (
            f"{job['id']}-{request['symbol'].replace('.', '_')}-"
            f"{request['ktype']}-{session}-"
            f"{request['start']}-{request['end']}.csv"
        )
        cache_path = self.project_root / "data" / "opend" / "web" / cache_name
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
        job = self.get_job(job_id)
        if job["status"] != "succeeded" or not job.get("run_dir"):
            raise RuntimeError("回测结果尚未可用。")
        run_dir = Path(job["run_dir"]).resolve()
        if self.root not in run_dir.parents:
            raise RuntimeError("运行目录超出 Web 工作区。")
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        return {
            "job": job,
            "summary": summary,
            "price_series": _load_opend_price_series(self.project_root, summary),
            "trades": _read_csv(run_dir / "trades.csv"),
            "equity_curve": _read_csv(run_dir / "equity_curve.csv"),
            "report_url": f"/api/jobs/{job_id}/report.svg",
        }

    def report_path(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        if not job.get("run_dir"):
            raise RuntimeError("回测图表尚未可用。")
        path = Path(job["run_dir"]).resolve() / "report.svg"
        if self.root not in path.parents or not path.is_file():
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


def create_app(
    project_root: Path = PROJECT_ROOT,
    job_store: JobStore | None = None,
    opend_probe: Callable[[str, int], bool] | None = None,
    frontend_root: Path | None = None,
) -> FastAPI:
    root = project_root.resolve()
    store = job_store or JobStore(root)
    strategy_repository = StrategyRepository(root)
    web_root = (frontend_root or FRONTEND_ROOT).resolve()
    probe = opend_probe or is_opend_available
    app = FastAPI(title="Strategy Lab", docs_url=None, redoc_url=None)
    app.state.job_store = store
    app.state.strategy_repository = strategy_repository
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    assets_root = web_root / "assets"
    if assets_root.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_root), name="assets")

    @app.get("/")
    async def index():
        index_path = web_root / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        return HTMLResponse(
            "<h1>Strategy Lab frontend is not built</h1>"
            "<p>Run <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>.</p>",
            status_code=503,
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "opend": {
                "connected": probe(store.opend_host, store.opend_port),
                "host": store.opend_host,
                "port": store.opend_port,
            },
        }

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "strategies": strategy_repository.list(),
            "kline_types": list(KLINE_TYPES),
            "adjustment_types": ["QFQ", "HFQ", "NONE"],
            "session_types": list(SESSION_TYPES),
        }

    @app.get("/api/strategies")
    async def strategies() -> dict[str, Any]:
        return {"strategies": strategy_repository.list()}

    @app.post("/api/strategies", status_code=201)
    async def create_strategy(request: StrategyCreateRequest) -> dict[str, Any]:
        try:
            return strategy_repository.create(
                request.name,
                content=request.content,
                template_path=request.template_path,
            )
        except StrategyRepositoryError as error:
            raise _strategy_http_error(error) from error

    @app.get("/api/strategies/{strategy_path:path}")
    async def read_strategy(strategy_path: str) -> dict[str, Any]:
        try:
            return strategy_repository.read(strategy_path)
        except StrategyRepositoryError as error:
            raise _strategy_http_error(error) from error

    @app.put("/api/strategies/{strategy_path:path}")
    async def save_strategy(
        strategy_path: str, request: StrategySaveRequest
    ) -> dict[str, Any]:
        try:
            return strategy_repository.save(
                strategy_path,
                request.content,
                expected_revision=request.expected_revision,
            )
        except StrategyRepositoryError as error:
            raise _strategy_http_error(error) from error

    @app.get("/api/jobs")
    async def jobs() -> dict[str, Any]:
        return {"jobs": store.list_jobs()[:50]}

    @app.post("/api/jobs", status_code=202)
    async def create_job(request: BacktestRequest) -> dict[str, Any]:
        if request.end < request.start:
            raise HTTPException(status_code=422, detail="结束日期不能早于开始日期。")
        try:
            strategy_path = strategy_repository.resolve_for_backtest(request.strategy)
        except StrategyRepositoryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        job = store.create_job(request, strategy_path)
        store.launch(job["id"])
        return job

    @app.get("/api/jobs/{job_id}")
    async def job(job_id: str) -> dict[str, Any]:
        try:
            return store.get_job(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error

    @app.get("/api/jobs/{job_id}/result")
    async def result(job_id: str) -> dict[str, Any]:
        try:
            return store.load_result(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/jobs/{job_id}/report.svg")
    async def report(job_id: str) -> FileResponse:
        try:
            return FileResponse(store.report_path(job_id), media_type="image/svg+xml")
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/{frontend_path:path}")
    async def frontend_fallback(frontend_path: str):
        candidate = (web_root / frontend_path).resolve()
        if web_root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return await index()

    return app


def list_strategies(project_root: Path) -> list[dict[str, Any]]:
    return StrategyRepository(project_root).list()


def resolve_strategy(project_root: Path, value: str) -> Path:
    try:
        return StrategyRepository(project_root).resolve_for_backtest(value)
    except StrategyRepositoryError as error:
        raise ValueError(str(error)) from error


def _strategy_http_error(error: StrategyRepositoryError) -> HTTPException:
    if isinstance(error, StrategyNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, StrategyConflictError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, StrategyPermissionError):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, StrategyValidationError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


def is_opend_available(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {key: _coerce(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _load_opend_price_series(
    project_root: Path, summary: dict[str, Any]
) -> list[dict[str, float | str]]:
    """Return the exact OHLCV rows cached by OpenD for this backtest."""
    opend = summary.get("settings", {}).get("opend", {})
    cache_value = opend.get("cache_path")
    if not cache_value:
        return []

    cache_path = Path(cache_value).resolve()
    allowed_root = (project_root / "data" / "opend").resolve()
    if allowed_root not in cache_path.parents or not cache_path.is_file():
        raise RuntimeError("OpenD 行情缓存不存在或超出项目数据目录。")

    symbol = str(summary.get("symbol", ""))
    points: list[dict[str, float | str]] = []
    with cache_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if symbol and row.get("code") != symbol:
                continue
            try:
                point: dict[str, float | str] = {
                    "date": str(row["time_key"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
            points.append(point)
    return sorted(points, key=lambda point: str(point["date"]))


def _coerce(value: str | None) -> Any:
    if value is None or value == "":
        return value
    try:
        return float(value)
    except ValueError:
        return value


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _last_error(stderr: str, stdout: str) -> str:
    lines = [line.strip() for line in (stderr + "\n" + stdout).splitlines() if line.strip()]
    return lines[-1] if lines else "回测进程失败，未返回错误信息。"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Strategy Lab web app.")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        choices=("127.0.0.1", "localhost", "0.0.0.0"),
        help="Bind locally by default; use 0.0.0.0 only behind an explicit host firewall.",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--opend-host", default=os.environ.get("OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(os.environ.get("OPEND_PORT", "11111")))
    args = parser.parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        print(
            "Web dependencies missing; install with: pip install -e './backend[web]'",
            file=sys.stderr,
        )
        return 1
    store = JobStore(PROJECT_ROOT, opend_host=args.opend_host, opend_port=args.opend_port)
    uvicorn.run(create_app(job_store=store), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
