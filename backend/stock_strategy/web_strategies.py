from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .api_errors import ApiProblem
from .strategy_repository import (
    StrategyConflictError,
    StrategyNotFoundError,
    StrategyPermissionError,
    StrategyRepository,
    StrategyRepositoryError,
    StrategyValidationError,
)
from .web_models import StrategyCreateRequest, StrategySaveRequest


def create_strategies_router(strategies: StrategyRepository) -> APIRouter:
    router = APIRouter(prefix="/api/strategies", tags=["strategies"])

    @router.get("")
    async def list_strategy_documents() -> dict[str, Any]:
        return {"strategies": strategies.list()}

    @router.post("", status_code=201)
    async def create_strategy(request: StrategyCreateRequest) -> dict[str, Any]:
        try:
            return strategies.create(
                request.name,
                content=request.content,
                template_path=request.template_path,
            )
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.get("/{strategy_path:path}")
    async def read_strategy(strategy_path: str) -> dict[str, Any]:
        try:
            return strategies.read(strategy_path)
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.put("/{strategy_path:path}")
    async def save_strategy(
        strategy_path: str,
        request: StrategySaveRequest,
    ) -> dict[str, Any]:
        try:
            return strategies.save(
                strategy_path,
                request.content,
                expected_revision=request.expected_revision,
            )
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    return router


def strategy_http_error(error: StrategyRepositoryError) -> ApiProblem:
    if isinstance(error, StrategyNotFoundError):
        return ApiProblem(404, "strategy_not_found", str(error))
    if isinstance(error, StrategyConflictError):
        return ApiProblem(409, "strategy_revision_conflict", str(error))
    if isinstance(error, StrategyPermissionError):
        return ApiProblem(403, "strategy_write_forbidden", str(error))
    if isinstance(error, StrategyValidationError):
        return ApiProblem(422, "invalid_strategy", str(error))
    return ApiProblem(400, "strategy_repository_error", str(error))
