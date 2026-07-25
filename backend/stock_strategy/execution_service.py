from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .application_models import BacktestSpec, ExperimentSpec
from .experiments import ExperimentStore, expand_parameter_grid
from .job_store import JobStore
from .strategy_parameters import resolve_parameter_values
from .strategy_repository import (
    StrategyRepository,
    StrategyValidationError,
    compatibility_error,
)

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

    def create_backtest(self, request: BacktestSpec) -> dict[str, Any]:
        prepared = self.prepare_backtest(request)
        job = self.jobs.create_job(
            prepared.request.to_dict(),
            prepared.strategy_path,
            strategy_source=prepared.strategy_source,
            strategy_revision=prepared.strategy_revision,
        )
        self.jobs.launch(job["id"])
        return job

    def create_experiment(self, request: ExperimentSpec) -> dict[str, Any]:
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
                    {**dict(prepared.request.parameters), name: candidate},
                )[name]
                for candidate in candidates
            ]
        expand_parameter_grid(normalized_grid)

        experiment = self.experiments.create(
            name=request.name,
            base_request=prepared.request.to_dict(),
            parameter_grid=normalized_grid,
            strategy_path=prepared.strategy_path,
            strategy_source=prepared.strategy_source,
            strategy_revision=prepared.strategy_revision,
            objective=request.objective,
            validation_window=(
                request.validation.to_dict() if request.validation else None
            ),
            test_window=request.test.to_dict() if request.test else None,
        )
        self.experiments.launch(experiment["id"])
        return experiment

    def prepare_backtest(
        self, request: BacktestSpec
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
            request=replace(request, parameters=parameters),
            strategy_path=strategy_path,
            strategy_source=strategy_document["content"],
            strategy_revision=strategy_document["revision"],
            definitions=definitions,
        )


@dataclass(frozen=True, slots=True)
class PreparedBacktest:
    request: BacktestSpec
    strategy_path: Path
    strategy_source: str
    strategy_revision: str
    definitions: list[dict[str, Any]]
