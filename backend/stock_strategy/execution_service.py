from __future__ import annotations

from pathlib import Path
from typing import Any

from .experiments import ExperimentStore, expand_parameter_grid
from .job_store import JobStore
from .strategy_parameters import resolve_parameter_values
from .strategy_repository import (
    StrategyRepository,
    StrategyValidationError,
    compatibility_error,
)
from .web_models import BacktestRequest, ExperimentRequest


class ExecutionService:
    """Application layer for validating and launching backtests and experiments."""

    def __init__(
        self,
        strategies: StrategyRepository,
        jobs: JobStore,
        experiments: ExperimentStore,
    ) -> None:
        self.strategies = strategies
        self.jobs = jobs
        self.experiments = experiments

    def create_backtest(self, request: BacktestRequest) -> dict[str, Any]:
        normalized, strategy_path, _definitions = self.prepare_backtest(request)
        job = self.jobs.create_job(normalized, strategy_path)
        self.jobs.launch(job["id"])
        return job

    def create_experiment(self, request: ExperimentRequest) -> dict[str, Any]:
        normalized_base, strategy_path, definitions = self.prepare_backtest(request.base)
        if not definitions:
            raise ValueError(
                "该策略没有声明 STRATEGY_PARAMETERS，无法创建参数实验"
            )

        known = {definition["name"] for definition in definitions}
        unknown = sorted(set(request.parameter_grid) - known)
        if unknown:
            raise ValueError("unknown strategy parameters: " + ", ".join(unknown))

        normalized_grid: dict[str, list[Any]] = {}
        for name, candidates in request.parameter_grid.items():
            normalized_grid[name] = [
                resolve_parameter_values(
                    definitions,
                    {**normalized_base.parameters, name: candidate},
                )[name]
                for candidate in candidates
            ]
        expand_parameter_grid(normalized_grid)

        experiment = self.experiments.create(
            name=request.name,
            base_request=normalized_base.model_dump(mode="json"),
            parameter_grid=normalized_grid,
            strategy_path=strategy_path,
            objective=request.objective,
        )
        self.experiments.launch(experiment["id"])
        return experiment

    def prepare_backtest(
        self, request: BacktestRequest
    ) -> tuple[BacktestRequest, Path, list[dict[str, Any]]]:
        strategy_path = self.strategies.resolve_for_backtest(request.strategy)
        strategy_document = self.strategies.read(request.strategy)
        incompatibility = compatibility_error(
            strategy_document["compatibility"], request.ktype, request.session
        )
        if incompatibility:
            raise StrategyValidationError(incompatibility)
        definitions = strategy_document["parameters"]
        parameters = resolve_parameter_values(definitions, request.parameters)
        return request.model_copy(update={"parameters": parameters}), strategy_path, definitions
