from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .execution_service import ExecutionService
from .job_lifecycle import InvalidJobTransition
from .job_store import JobStore
from .result_reader import INITIAL_PRICE_WINDOW, MAX_PRICE_WINDOW
from .strategy_parameters import StrategyParameterError
from .strategy_repository import StrategyRepositoryError
from .web_models import BacktestRequest


def create_jobs_router(
    store: JobStore,
    execution: ExecutionService,
) -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["backtests"])

    @router.get("")
    async def jobs() -> dict[str, Any]:
        return {"jobs": store.list_jobs()[:50]}

    @router.post("", status_code=202)
    async def create_job(request: BacktestRequest) -> dict[str, Any]:
        try:
            return execution.create_backtest(request)
        except (StrategyRepositoryError, StrategyParameterError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/{job_id}")
    async def job(job_id: str) -> dict[str, Any]:
        try:
            return store.get_job(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error

    @router.delete("/{job_id}", status_code=202)
    async def cancel_job(job_id: str) -> dict[str, Any]:
        try:
            return await store.cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error

    @router.post("/{job_id}/retry", status_code=202)
    async def retry_job(job_id: str) -> dict[str, Any]:
        try:
            return store.retry(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error
        except (InvalidJobTransition, OSError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{job_id}/result")
    async def result(job_id: str) -> dict[str, Any]:
        try:
            return store.load_result(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{job_id}/prices")
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

    @router.get("/{job_id}/report.svg")
    async def report(job_id: str) -> FileResponse:
        try:
            return FileResponse(store.report_path(job_id), media_type="image/svg+xml")
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到这次回测。") from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router
