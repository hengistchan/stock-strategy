from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .execution_service import ExecutionService
from .diagnostics import DiagnosticsService, is_opend_available
from .experiments import ExperimentStore
from .job_store import JobStore, last_error as _last_error
from .opend import OpenDRequestError, OpenDSymbolDirectory, OpenDUnavailableError
from .paths import FRONTEND_ROOT, PROJECT_ROOT
from .result_reader import (
    INITIAL_PRICE_WINDOW,
    MAX_PRICE_WINDOW,
    read_downsampled_equity_curve as _read_downsampled_equity_curve,
)
from .strategy_parameters import StrategyParameterError
from .strategy_repository import (
    StrategyConflictError,
    StrategyNotFoundError,
    StrategyPermissionError,
    StrategyRepository,
    StrategyRepositoryError,
    StrategyValidationError,
)
from .web_models import (
    KLINE_TYPES,
    SESSION_TYPES,
    SYMBOL_PATTERN,
    BacktestRequest,
    ExperimentRequest,
    StrategyCreateRequest,
    StrategySaveRequest,
)


def create_app(
    project_root: Path = PROJECT_ROOT,
    job_store: JobStore | None = None,
    experiment_store: ExperimentStore | None = None,
    opend_probe: Callable[[str, int], bool] | None = None,
    symbol_directory: OpenDSymbolDirectory | None = None,
    diagnostics_service: DiagnosticsService | None = None,
    frontend_root: Path | None = None,
) -> FastAPI:
    root = project_root.resolve()
    store = job_store or JobStore(root)
    experiments = experiment_store or ExperimentStore(root, store)
    strategies = StrategyRepository(root)
    execution = ExecutionService(strategies, store, experiments)
    web_root = (frontend_root or FRONTEND_ROOT).resolve()
    probe = opend_probe or is_opend_available
    directory = symbol_directory or OpenDSymbolDirectory(
        host=store.opend_host,
        port=store.opend_port,
    )
    diagnostics = diagnostics_service or DiagnosticsService(
        root,
        host=store.opend_host,
        port=store.opend_port,
        connection_probe=probe,
        quote_probe=lambda: _probe_quote_directory(directory),
    )

    app = FastAPI(title="Strategy Lab", docs_url=None, redoc_url=None)
    app.state.job_store = store
    app.state.experiment_store = experiments
    app.state.strategy_repository = strategies
    app.state.execution_service = execution
    app.state.symbol_directory = directory
    app.state.diagnostics_service = diagnostics
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    assets_root = web_root / "assets"
    if assets_root.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_root), name="assets")

    @app.get("/")
    async def index():
        index_path = web_root / "index.html"
        if index_path.is_file():
            return FileResponse(index_path, headers={"Cache-Control": "no-cache"})
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

    @app.get("/api/diagnostics")
    def diagnostics_report() -> dict[str, object]:
        return diagnostics.run().to_dict()

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "strategies": strategies.list(),
            "kline_types": list(KLINE_TYPES),
            "adjustment_types": ["QFQ", "HFQ", "NONE"],
            "session_types": list(SESSION_TYPES),
        }

    @app.get("/api/symbols")
    def search_symbols(
        q: str = Query(min_length=1, max_length=80),
        limit: int = Query(default=8, ge=1, le=20),
    ) -> dict[str, Any]:
        try:
            return {"query": q, "symbols": directory.search(q, limit)}
        except (OpenDUnavailableError, OpenDRequestError, OSError) as error:
            raise HTTPException(
                status_code=503,
                detail=f"OpenD 标的搜索暂不可用：{error}",
            ) from error

    @app.get("/api/symbols/resolve")
    def resolve_symbols(codes: list[str] = Query()) -> dict[str, Any]:
        normalized = list(
            dict.fromkeys(code.strip().upper() for code in codes if code.strip())
        )
        if not normalized:
            raise HTTPException(status_code=422, detail="至少需要一个标的代码。")
        if len(normalized) > 100:
            raise HTTPException(status_code=422, detail="单次最多解析 100 个标的代码。")
        invalid = [
            code for code in normalized if re.fullmatch(SYMBOL_PATTERN, code) is None
        ]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"无效的 Futu 标的代码：{', '.join(invalid)}",
            )
        try:
            return {"symbols": directory.resolve(normalized)}
        except (OpenDUnavailableError, OpenDRequestError, OSError) as error:
            raise HTTPException(
                status_code=503,
                detail=f"OpenD 标的名称暂不可用：{error}",
            ) from error

    @app.get("/api/strategies")
    async def list_strategy_documents() -> dict[str, Any]:
        return {"strategies": strategies.list()}

    @app.post("/api/strategies", status_code=201)
    async def create_strategy(request: StrategyCreateRequest) -> dict[str, Any]:
        try:
            return strategies.create(
                request.name,
                content=request.content,
                template_path=request.template_path,
            )
        except StrategyRepositoryError as error:
            raise _strategy_http_error(error) from error

    @app.get("/api/strategies/{strategy_path:path}")
    async def read_strategy(strategy_path: str) -> dict[str, Any]:
        try:
            return strategies.read(strategy_path)
        except StrategyRepositoryError as error:
            raise _strategy_http_error(error) from error

    @app.put("/api/strategies/{strategy_path:path}")
    async def save_strategy(
        strategy_path: str, request: StrategySaveRequest
    ) -> dict[str, Any]:
        try:
            return strategies.save(
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
        try:
            return execution.create_backtest(request)
        except (StrategyRepositoryError, StrategyParameterError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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

    @app.get("/api/jobs/{job_id}/prices")
    async def prices(
        job_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=INITIAL_PRICE_WINDOW, ge=1, le=MAX_PRICE_WINDOW),
    ) -> dict[str, Any]:
        try:
            return store.load_price_window(job_id, offset, limit)
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

    @app.get("/api/experiments")
    async def list_experiments() -> dict[str, Any]:
        return {"experiments": experiments.list()[:50]}

    @app.post("/api/experiments", status_code=202)
    async def create_experiment(request: ExperimentRequest) -> dict[str, Any]:
        try:
            return execution.create_experiment(request)
        except (StrategyRepositoryError, StrategyParameterError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/experiments/{experiment_id}")
    async def get_experiment(experiment_id: str) -> dict[str, Any]:
        try:
            return experiments.get(experiment_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次参数实验。") from error

    @app.get("/api/cache")
    async def list_cache() -> dict[str, Any]:
        entries = store.cache.list()
        return {
            "entries": entries,
            "total_bytes": sum(entry.get("bytes", 0) for entry in entries),
        }

    @app.delete("/api/cache/{cache_id}")
    async def delete_cache(cache_id: str) -> dict[str, Any]:
        try:
            deleted = store.cache.delete(cache_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这份 OpenD 缓存。") from error
        if not deleted:
            raise HTTPException(status_code=404, detail="找不到这份 OpenD 缓存。")
        return {"deleted": cache_id}

    @app.get("/{frontend_path:path}")
    async def frontend_fallback(frontend_path: str):
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
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


def _probe_quote_directory(directory: OpenDSymbolDirectory) -> str:
    matches = directory.search("AAPL", 1)
    return f"OpenD stock directory readable · {len(matches)} probe result(s)"


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
    parser.add_argument(
        "--opend-port", type=int, default=int(os.environ.get("OPEND_PORT", "11111"))
    )
    args = parser.parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        print(
            "Web dependencies missing; install with: pip install -e './backend[web]'",
            file=sys.stderr,
        )
        return 1
    store = JobStore(
        PROJECT_ROOT, opend_host=args.opend_host, opend_port=args.opend_port
    )
    uvicorn.run(
        create_app(job_store=store),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
