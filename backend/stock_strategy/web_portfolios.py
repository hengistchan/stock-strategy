from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from .api_errors import ApiProblem
from .api_models import PortfolioResponse, error_responses
from .portfolio import PortfolioService
from .web_models import PortfolioRequest


def create_portfolios_router(service: PortfolioService) -> APIRouter:
    router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])

    @router.post(
        "",
        response_model=PortfolioResponse,
        responses=error_responses(422, 503),
    )
    async def run_portfolio(request: PortfolioRequest) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(service.run, request.to_config())
        except ValueError as error:
            raise ApiProblem(
                status_code=422,
                code="invalid_portfolio_request",
                message=str(error),
            ) from error
        except Exception as error:
            raise ApiProblem(
                status_code=503,
                code="portfolio_data_unavailable",
                message=f"OpenD 组合行情读取失败：{error}",
            ) from error

    return router
