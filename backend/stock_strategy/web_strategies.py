from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .api_errors import ApiProblem
from .api_models import (
    StrategiesResponse,
    StrategyDocument,
    StrategyVersionsResponse,
    error_responses,
)
from .experiments import ExperimentStore
from .job_store import JobStore
from .strategy_repository import (
    StrategyConflictError,
    StrategyNotFoundError,
    StrategyPermissionError,
    StrategyRepository,
    StrategyRepositoryError,
    StrategyValidationError,
)
from .web_models import (
    StrategyCreateRequest,
    StrategyRestoreRequest,
    StrategySaveRequest,
)


def create_strategies_router(
    strategies: StrategyRepository,
    jobs: JobStore,
    experiments: ExperimentStore,
) -> APIRouter:
    router = APIRouter(prefix="/api/strategies", tags=["strategies"])

    @router.get("", response_model=StrategiesResponse)
    async def list_strategy_documents() -> dict[str, Any]:
        return {"strategies": strategies.list()}

    @router.post(
        "",
        status_code=201,
        response_model=StrategyDocument,
        responses=error_responses(400, 403, 409, 422),
    )
    async def create_strategy(request: StrategyCreateRequest) -> dict[str, Any]:
        try:
            return strategies.create(
                request.name,
                content=request.content,
                template_path=request.template_path,
            )
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.get(
        "/versions",
        response_model=StrategyVersionsResponse,
        responses=error_responses(403, 404),
    )
    async def list_strategy_versions(strategy_path: str) -> dict[str, Any]:
        try:
            versions = strategies.versions(strategy_path)
            job_counts: dict[str, int] = {}
            experiment_counts: dict[str, int] = {}
            for job in jobs.list_jobs():
                revision = job.get("strategy_revision")
                if revision and job.get("strategy_path") == strategy_path:
                    job_counts[revision] = job_counts.get(revision, 0) + 1
            for experiment in experiments.list():
                revision = experiment.get("strategy_revision")
                if revision and experiment.get("strategy_path") == strategy_path:
                    experiment_counts[revision] = experiment_counts.get(revision, 0) + 1
            return {
                "strategy_path": strategy_path,
                "versions": [
                    {
                        **version,
                        "backtest_count": job_counts.get(version["revision"], 0),
                        "experiment_count": experiment_counts.get(
                            version["revision"], 0
                        ),
                    }
                    for version in versions
                ],
            }
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.post(
        "/versions/restore",
        response_model=StrategyDocument,
        responses=error_responses(403, 404, 409, 422),
    )
    async def restore_strategy_version(
        request: StrategyRestoreRequest,
    ) -> dict[str, Any]:
        try:
            return strategies.restore(
                request.strategy_path,
                request.revision,
                expected_revision=request.expected_revision,
            )
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.get(
        "/{strategy_path:path}",
        response_model=StrategyDocument,
        responses=error_responses(403, 404),
    )
    async def read_strategy(strategy_path: str) -> dict[str, Any]:
        try:
            return strategies.read(strategy_path)
        except StrategyRepositoryError as error:
            raise strategy_http_error(error) from error

    @router.put(
        "/{strategy_path:path}",
        response_model=StrategyDocument,
        responses=error_responses(400, 403, 404, 409, 422),
    )
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
