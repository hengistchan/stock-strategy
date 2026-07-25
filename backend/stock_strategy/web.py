from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys
from typing import Any, Callable
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api_errors import ApiProblem, error_payload, install_api_error_handlers
from .execution_service import ExecutionService
from .diagnostics import DiagnosticsService, is_opend_available
from .experiments import ExperimentStore
from .job_store import JobStore, last_error as _last_error
from .opend import OpenDSymbolDirectory
from .portfolio import PortfolioService
from .paths import FRONTEND_ROOT, PROJECT_ROOT
from .result_reader import (
    read_downsampled_equity_curve as _read_downsampled_equity_curve,
)
from .strategy_repository import StrategyRepository, StrategyRepositoryError
from .web_cache import create_cache_router
from .web_events import create_events_router
from .web_experiments import create_experiments_router
from .web_jobs import create_jobs_router
from .web_portfolios import create_portfolios_router
from .web_strategies import create_strategies_router
from .web_symbols import create_symbols_router
from .web_system import create_system_router


def create_app(
    project_root: Path = PROJECT_ROOT,
    job_store: JobStore | None = None,
    experiment_store: ExperimentStore | None = None,
    opend_probe: Callable[[str, int], bool] | None = None,
    symbol_directory: OpenDSymbolDirectory | None = None,
    diagnostics_service: DiagnosticsService | None = None,
    frontend_root: Path | None = None,
    api_token: str | None = None,
    portfolio_service: PortfolioService | None = None,
) -> FastAPI:
    root = project_root.resolve()
    store = job_store or JobStore(root)
    experiments = experiment_store or ExperimentStore(root, store)
    strategies = StrategyRepository(root)
    execution = ExecutionService(strategies, store, experiments)
    portfolios = portfolio_service or PortfolioService(
        root,
        host=store.opend_host,
        port=store.opend_port,
    )
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

    app = FastAPI(
        title="Strategy Lab",
        docs_url=None,
        redoc_url=None,
        servers=[{"url": "/"}],
    )
    app.state.job_store = store
    app.state.experiment_store = experiments
    app.state.strategy_repository = strategies
    app.state.execution_service = execution
    app.state.portfolio_service = portfolios
    app.state.symbol_directory = directory
    app.state.diagnostics_service = diagnostics
    app.state.api_auth_enabled = api_token is not None
    install_api_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    if api_token is not None:
        if len(api_token) < 32:
            raise ValueError("API token must contain at least 32 characters")

        @app.middleware("http")
        async def require_api_token(request: Request, call_next):
            if request.url.path == "/api" or request.url.path.startswith("/api/"):
                authorization = request.headers.get("Authorization", "")
                bearer = (
                    authorization[7:]
                    if authorization.startswith("Bearer ")
                    else ""
                )
                cookie = unquote(request.cookies.get("strategy_lab_token", ""))
                supplied = bearer or cookie
                if not supplied or not secrets.compare_digest(supplied, api_token):
                    return JSONResponse(
                        status_code=401,
                        content=error_payload(
                            code="authentication_required",
                            message="Strategy Lab API token is required.",
                        ),
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            return await call_next(request)

    assets_root = web_root / "assets"
    if assets_root.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_root), name="assets")
    app.include_router(create_system_router(store, strategies, diagnostics, probe))
    app.include_router(create_events_router(store.events))
    app.include_router(create_symbols_router(directory))
    app.include_router(create_strategies_router(strategies, store, experiments))
    app.include_router(create_jobs_router(store, execution))
    app.include_router(create_experiments_router(experiments, execution))
    app.include_router(create_portfolios_router(portfolios))
    app.include_router(create_cache_router(store))

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

    @app.get("/{frontend_path:path}")
    async def frontend_fallback(frontend_path: str):
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise ApiProblem(
                status_code=404,
                code="api_endpoint_not_found",
                message="API endpoint not found",
            )
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
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly allow a non-loopback bind; requires STRATEGY_LAB_API_TOKEN.",
    )
    parser.add_argument("--opend-host", default=os.environ.get("OPEND_HOST", "127.0.0.1"))
    parser.add_argument(
        "--opend-port", type=int, default=int(os.environ.get("OPEND_PORT", "11111"))
    )
    args = parser.parse_args(argv)
    api_token = os.environ.get("STRATEGY_LAB_API_TOKEN")
    try:
        validate_server_exposure(args.host, args.allow_remote, api_token)
    except ValueError as error:
        parser.error(str(error))
    if not _is_loopback_host(args.host):
        print(
            "WARNING: Strategy Lab is accepting remote connections. "
            "Keep it behind a trusted firewall and never expose it directly to the Internet.",
            file=sys.stderr,
        )
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
        create_app(job_store=store, api_token=api_token),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


def validate_server_exposure(
    host: str,
    allow_remote: bool,
    api_token: str | None,
) -> None:
    if _is_loopback_host(host):
        if api_token is not None and len(api_token) < 32:
            raise ValueError("STRATEGY_LAB_API_TOKEN must contain at least 32 characters")
        return
    if not allow_remote:
        raise ValueError(
            "non-loopback binding requires the explicit --allow-remote flag"
        )
    if api_token is None or len(api_token) < 32:
        raise ValueError(
            "non-loopback binding requires STRATEGY_LAB_API_TOKEN "
            "with at least 32 characters"
        )


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "localhost", "::1"}


if __name__ == "__main__":
    raise SystemExit(main())
