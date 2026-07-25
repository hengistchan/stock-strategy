from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from .api_errors import ApiProblem
from .api_models import (
    BacktestJob,
    BacktestResultResponse,
    JobsResponse,
    PriceWindowResponse,
    error_responses,
)
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

    @router.get("", response_model=JobsResponse)
    async def jobs() -> dict[str, Any]:
        return {"jobs": store.list_jobs()[:50]}

    @router.post(
        "",
        status_code=202,
        response_model=BacktestJob,
        responses=error_responses(422),
    )
    async def create_job(request: BacktestRequest) -> dict[str, Any]:
        try:
            return execution.create_backtest(request.to_spec())
        except (StrategyRepositoryError, StrategyParameterError) as error:
            raise ApiProblem(
                status_code=422,
                code="invalid_backtest_request",
                message=str(error),
            ) from error

    @router.get(
        "/{job_id}",
        response_model=BacktestJob,
        responses=error_responses(404),
    )
    async def job(job_id: str) -> dict[str, Any]:
        try:
            return store.get_job(job_id)
        except KeyError as error:
            raise _backtest_not_found() from error

    @router.delete(
        "/{job_id}",
        status_code=202,
        response_model=BacktestJob,
        responses=error_responses(404),
    )
    async def cancel_job(job_id: str) -> dict[str, Any]:
        try:
            return await store.cancel(job_id)
        except KeyError as error:
            raise _backtest_not_found() from error

    @router.post(
        "/{job_id}/retry",
        status_code=202,
        response_model=BacktestJob,
        responses=error_responses(404, 409),
    )
    async def retry_job(job_id: str) -> dict[str, Any]:
        try:
            return store.retry(job_id)
        except KeyError as error:
            raise _backtest_not_found() from error
        except (InvalidJobTransition, OSError, ValueError) as error:
            raise ApiProblem(
                status_code=409,
                code="invalid_backtest_transition",
                message=str(error),
            ) from error

    @router.get(
        "/{job_id}/result",
        response_model=BacktestResultResponse,
        responses=error_responses(404, 409),
    )
    async def result(job_id: str) -> dict[str, Any]:
        try:
            return store.load_result(job_id)
        except KeyError as error:
            raise _backtest_not_found() from error
        except RuntimeError as error:
            raise ApiProblem(
                status_code=409,
                code="backtest_result_unavailable",
                message=str(error),
            ) from error

    @router.get(
        "/{job_id}/prices",
        response_model=PriceWindowResponse,
        responses=error_responses(404, 409, 422),
    )
    async def prices(
        job_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=INITIAL_PRICE_WINDOW, ge=1, le=MAX_PRICE_WINDOW),
    ) -> dict[str, Any]:
        try:
            return store.load_price_window(job_id, offset, limit)
        except KeyError as error:
            raise _backtest_not_found() from error
        except RuntimeError as error:
            raise ApiProblem(
                status_code=409,
                code="backtest_prices_unavailable",
                message=str(error),
            ) from error

    @router.get(
        "/{job_id}/report.svg",
        responses=error_responses(404, 409),
    )
    async def report(job_id: str) -> FileResponse:
        try:
            return FileResponse(store.report_path(job_id), media_type="image/svg+xml")
        except KeyError as error:
            raise _backtest_not_found() from error
        except RuntimeError as error:
            raise ApiProblem(
                status_code=409,
                code="backtest_report_unavailable",
                message=str(error),
            ) from error

    return router


def _backtest_not_found() -> ApiProblem:
    return ApiProblem(
        status_code=404,
        code="backtest_not_found",
        message="找不到这次回测。",
    )
