from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .api_errors import ApiProblem
from .execution_service import ExecutionService
from .experiments import ExperimentStore
from .strategy_parameters import StrategyParameterError
from .strategy_repository import StrategyRepositoryError
from .web_models import ExperimentRequest


def create_experiments_router(
    experiments: ExperimentStore,
    execution: ExecutionService,
) -> APIRouter:
    router = APIRouter(prefix="/api/experiments", tags=["experiments"])

    @router.get("")
    async def list_experiments() -> dict[str, Any]:
        return {"experiments": experiments.list()[:50]}

    @router.post("", status_code=202)
    async def create_experiment(request: ExperimentRequest) -> dict[str, Any]:
        try:
            return execution.create_experiment(request)
        except (
            StrategyRepositoryError,
            StrategyParameterError,
            ValueError,
        ) as error:
            raise ApiProblem(
                status_code=422,
                code="invalid_experiment_request",
                message=str(error),
            ) from error

    @router.get("/{experiment_id}")
    async def get_experiment(experiment_id: str) -> dict[str, Any]:
        try:
            return experiments.get(experiment_id)
        except KeyError as error:
            raise ApiProblem(
                status_code=404,
                code="experiment_not_found",
                message="找不到这次参数实验。",
            ) from error

    return router
