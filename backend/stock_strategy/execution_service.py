from __future__ import annotations

from dataclasses import dataclass
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
        prepared = self.prepare_backtest(request)
        job = self.jobs.create_job(
            prepared.request.model_dump(mode="json"),
            prepared.strategy_path,
            strategy_source=prepared.strategy_source,
            strategy_revision=prepared.strategy_revision,
        )
        self.jobs.launch(job["id"])
        return job

    def create_experiment(self, request: ExperimentRequest) -> dict[str, Any]:
        prepared = self.prepare_backtest(request.base)
        if not prepared.definitions:
            raise ValueError(
                "该策略没有声明 STRATEGY_PARAMETERS，无法创建参数实验"
            )

        known = {definition["name"] for definition in prepared.definitions}
        unknown = sorted(set(request.parameter_grid) - known)
        if unknown:
            raise ValueError("unknown strategy parameters: " + ", ".join(unknown))

        normalized_grid: dict[str, list[Any]] = {}
        for name, candidates in request.parameter_grid.items():
            normalized_grid[name] = [
                resolve_parameter_values(
                    prepared.definitions,
                    {**prepared.request.parameters, name: candidate},
                )[name]
                for candidate in candidates
            ]
        expand_parameter_grid(normalized_grid)

        experiment = self.experiments.create(
            name=request.name,
            base_request=prepared.request.model_dump(mode="json"),
            parameter_grid=normalized_grid,
            strategy_path=prepared.strategy_path,
            strategy_source=prepared.strategy_source,
            strategy_revision=prepared.strategy_revision,
            objective=request.objective,
        )
        self.experiments.launch(experiment["id"])
        return experiment

    def prepare_backtest(
        self, request: BacktestRequest
    ) -> PreparedBacktest:
        strategy_path = self.strategies.resolve_for_backtest(request.strategy)
        strategy_document = self.strategies.read(request.strategy)
        incompatibility = compatibility_error(
            strategy_document["compatibility"], request.ktype, request.session
        )
        if incompatibility:
            raise StrategyValidationError(incompatibility)
        definitions = strategy_document["parameters"]
        parameters = resolve_parameter_values(definitions, request.parameters)
        return PreparedBacktest(
            request=request.model_copy(update={"parameters": parameters}),
            strategy_path=strategy_path,
            strategy_source=strategy_document["content"],
            strategy_revision=strategy_document["revision"],
            definitions=definitions,
        )


@dataclass(frozen=True, slots=True)
class PreparedBacktest:
    request: BacktestRequest
    strategy_path: Path
    strategy_source: str
    strategy_revision: str
    definitions: list[dict[str, Any]]
