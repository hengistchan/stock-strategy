from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter

from .api_models import (
    ConfigResponse,
    DiagnosticsResponse,
    HealthResponse,
)
from .application_models import KLINE_TYPES, SESSION_TYPES
from .diagnostics import DiagnosticsService
from .job_store import JobStore
from .strategy_repository import StrategyRepository


def create_system_router(
    store: JobStore,
    strategies: StrategyRepository,
    diagnostics: DiagnosticsService,
    opend_probe: Callable[[str, int], bool],
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "opend": {
                "connected": opend_probe(store.opend_host, store.opend_port),
                "host": store.opend_host,
                "port": store.opend_port,
            },
        }

    @router.get("/diagnostics", response_model=DiagnosticsResponse)
    def diagnostics_report() -> dict[str, object]:
        return diagnostics.run().to_dict()

    @router.get("/config", response_model=ConfigResponse)
    async def config() -> dict[str, Any]:
        return {
            "strategies": strategies.list(),
            "kline_types": list(KLINE_TYPES),
            "adjustment_types": ["QFQ", "HFQ", "NONE"],
            "session_types": list(SESSION_TYPES),
        }

    return router
