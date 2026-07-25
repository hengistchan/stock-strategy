from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .api_errors import ApiProblem
from .api_models import (
    StrategyMigrationImportResponse,
    StrategyMigrationReport,
    error_responses,
)
from .strategy_migration import StrategyMigrationService
from .strategy_repository import StrategyRepositoryError
from .web_models import (
    StrategyMigrationImportRequest,
    StrategyMigrationSourceRequest,
)
from .web_strategies import strategy_http_error


def create_migrations_router(service: StrategyMigrationService) -> APIRouter:
    router = APIRouter(prefix="/api/migrations", tags=["strategy-migration"])

    @router.post(
        "/scan",
        response_model=StrategyMigrationReport,
        responses=error_responses(422),
    )
    async def scan_strategy(
        request: StrategyMigrationSourceRequest,
    ) -> dict[str, Any]:
        try:
            return service.scan(request.content)
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.post(
        "/fixture",
        response_model=StrategyMigrationReport,
        responses=error_responses(422),
    )
    async def validate_strategy_fixture(
        request: StrategyMigrationSourceRequest,
    ) -> dict[str, Any]:
        try:
            return await service.validate_fixture(request.content)
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.post(
        "/import",
        status_code=201,
        response_model=StrategyMigrationImportResponse,
        responses=error_responses(403, 409, 422),
    )
    async def import_strategy(
        request: StrategyMigrationImportRequest,
    ) -> dict[str, Any]:
        try:
            report = await service.validate_fixture(request.content)
            if report["fixture"]["status"] != "passed":
                raise ApiProblem(
                    status_code=422,
                    code="strategy_fixture_failed",
                    message="策略必须先通过静态扫描和确定性 fixture。",
                    details=report,
                )
            return service.import_strategy(request.name, request.content, report)
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    return router
