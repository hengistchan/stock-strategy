from __future__ import annotations

from datetime import date
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .application_models import (
    KLINE_TYPES,
    SESSION_TYPES,
    SYMBOL_PATTERN,
    BacktestSpec,
    EvaluationWindow,
    ExperimentSpec,
    MetricConstraint,
    ParameterValue,
)
from .strategy_repository import MAX_STRATEGY_BYTES
from .portfolio import PortfolioConfig


class BacktestRequest(BaseModel):
    strategy: str = "examples/ma_cross.py"
    symbol: str = Field(default="US.AAPL", pattern=SYMBOL_PATTERN)
    start: date
    end: date
    ktype: Literal[
        "K_DAY",
        "K_WEEK",
        "K_1M",
        "K_3M",
        "K_5M",
        "K_10M",
        "K_15M",
        "K_30M",
        "K_60M",
        "K_120M",
        "K_180M",
        "K_240M",
    ] = "K_DAY"
    autype: Literal["QFQ", "HFQ", "NONE"] = "QFQ"
    session: Literal["ALL", "RTH", "ETH"] = "ALL"
    initial_cash: float = Field(default=100_000, gt=0)
    commission_bps: float = Field(default=3, ge=0, le=1_000)
    min_commission: float = Field(default=1, ge=0)
    slippage_bps: float = Field(default=5, ge=0, le=1_000)
    fee_model: Literal["simple", "futu_auto", "futu_us", "futu_hk"] = "simple"
    slippage_model: Literal["bps", "spread"] = "bps"
    execution_model: Literal["deterministic", "volume", "conservative"] = (
        "deterministic"
    )
    max_volume_participation: float = Field(default=0.1, gt=0, le=1)
    spread_bps: float = Field(default=0, ge=0, le=1_000)
    impact_bps: float = Field(default=0, ge=0, le=1_000)
    fixed_tick: float = Field(default=0, ge=0)
    warmup_bars: int = Field(default=0, ge=0, le=100_000)
    allow_short: bool = False
    liquidate_on_end: bool = False
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)
    refresh_cache: bool = False

    @model_validator(mode="after")
    def validate_period(self) -> "BacktestRequest":
        if self.end < self.start:
            raise ValueError("结束日期不能早于开始日期。")
        return self

    def to_spec(self) -> BacktestSpec:
        return BacktestSpec(**self.model_dump())


class ExperimentRequest(BaseModel):
    name: str = Field(default="参数实验", min_length=1, max_length=80)
    base: BacktestRequest
    parameter_grid: dict[str, list[ParameterValue]]
    objective: Literal[
        "total_return_pct", "sharpe_ratio", "max_drawdown_pct"
    ] = "sharpe_ratio"
    validation: "EvaluationWindowRequest | None" = None
    test: "EvaluationWindowRequest | None" = None
    walk_forward_folds: int = Field(default=0, ge=0, le=5)
    constraints: list["MetricConstraintRequest"] = Field(default_factory=list, max_length=8)
    symbols: list[str] = Field(default_factory=list, max_length=36)

    @model_validator(mode="after")
    def validate_research_windows(self) -> "ExperimentRequest":
        normalized_symbols = [symbol.strip().upper() for symbol in self.symbols]
        if len(set(normalized_symbols)) != len(normalized_symbols):
            raise ValueError("批量验证的标的代码不能重复。")
        if any(not re.fullmatch(SYMBOL_PATTERN, symbol) for symbol in normalized_symbols):
            raise ValueError("批量验证包含无效的标的代码。")
        if normalized_symbols and len(normalized_symbols) < 2:
            raise ValueError("批量验证至少需要 2 个标的。")
        if normalized_symbols and self.parameter_grid:
            raise ValueError("批量标的验证不能同时运行参数网格。")
        if normalized_symbols and (
            self.walk_forward_folds or self.validation is not None or self.test is not None
        ):
            raise ValueError("批量标的验证不能同时配置样本外区间。")
        self.symbols = normalized_symbols
        if self.walk_forward_folds == 1:
            raise ValueError("Walk-forward 至少需要 2 折。")
        if self.walk_forward_folds and (
            self.validation is not None or self.test is not None
        ):
            raise ValueError("Walk-forward 不能同时配置固定验证或测试区间。")
        if self.test is not None and self.validation is None:
            raise ValueError("测试区间需要先配置验证区间。")
        if self.validation is not None and self.validation.start <= self.base.end:
            raise ValueError("验证区间必须晚于训练区间。")
        if self.test is not None and self.test.start <= self.validation.end:
            raise ValueError("测试区间必须晚于验证区间。")
        return self

    def to_spec(self) -> ExperimentSpec:
        return ExperimentSpec(
            name=self.name,
            base=self.base.to_spec(),
            parameter_grid={
                name: list(values) for name, values in self.parameter_grid.items()
            },
            objective=self.objective,
            validation=self.validation.to_window() if self.validation else None,
            test=self.test.to_window() if self.test else None,
            walk_forward_folds=self.walk_forward_folds,
            constraints=tuple(constraint.to_constraint() for constraint in self.constraints),
            symbols=tuple(self.symbols),
        )


class EvaluationWindowRequest(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def validate_period(self) -> "EvaluationWindowRequest":
        if self.end < self.start:
            raise ValueError("区间结束日期不能早于开始日期。")
        return self

    def to_window(self) -> EvaluationWindow:
        return EvaluationWindow(start=self.start, end=self.end)


class MetricConstraintRequest(BaseModel):
    metric: Literal[
        "total_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "total_trades",
        "total_fees",
        "exposure_pct",
    ]
    op: Literal[">=", "<="]
    value: float

    def to_constraint(self) -> MetricConstraint:
        return MetricConstraint(metric=self.metric, op=self.op, value=self.value)


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=67)
    content: str | None = Field(default=None, max_length=MAX_STRATEGY_BYTES)
    template_path: str | None = Field(default=None, max_length=200)


class StrategySaveRequest(BaseModel):
    content: str = Field(max_length=MAX_STRATEGY_BYTES)
    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)


class StrategyRestoreRequest(BaseModel):
    strategy_path: str = Field(min_length=1, max_length=200)
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class StrategyMigrationSourceRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_STRATEGY_BYTES)


class StrategyMigrationImportRequest(StrategyMigrationSourceRequest):
    name: str = Field(min_length=1, max_length=67)


class PortfolioRequest(BaseModel):
    weights: dict[str, float] = Field(min_length=2, max_length=12)
    start: date
    end: date
    initial_cash: float = Field(default=100_000, gt=0)
    commission_bps: float = Field(default=3, ge=0, le=1_000)
    min_commission: float = Field(default=1, ge=0)
    slippage_bps: float = Field(default=5, ge=0, le=1_000)
    rebalance: Literal["buy_and_hold", "monthly", "quarterly"] = "monthly"
    ktype: Literal["K_DAY"] = "K_DAY"
    autype: Literal["QFQ", "HFQ", "NONE"] = "QFQ"
    session: Literal["ALL", "RTH", "ETH"] = "ALL"

    @model_validator(mode="after")
    def validate_portfolio(self) -> "PortfolioRequest":
        if self.end < self.start:
            raise ValueError("组合结束日期不能早于开始日期。")
        normalized = {symbol.strip().upper(): weight for symbol, weight in self.weights.items()}
        if any(not re.fullmatch(SYMBOL_PATTERN, symbol) for symbol in normalized):
            raise ValueError("组合包含无效的标的代码。")
        self.weights = normalized
        PortfolioConfig(
            weights=self.weights,
            start=self.start.isoformat(),
            end=self.end.isoformat(),
            initial_cash=self.initial_cash,
            commission_bps=self.commission_bps,
            min_commission=self.min_commission,
            slippage_bps=self.slippage_bps,
            rebalance=self.rebalance,
            ktype=self.ktype,
            autype=self.autype,
            session=self.session,
        )
        return self

    def to_config(self) -> PortfolioConfig:
        return PortfolioConfig(
            weights=self.weights,
            start=self.start.isoformat(),
            end=self.end.isoformat(),
            initial_cash=self.initial_cash,
            commission_bps=self.commission_bps,
            min_commission=self.min_commission,
            slippage_bps=self.slippage_bps,
            rebalance=self.rebalance,
            ktype=self.ktype,
            autype=self.autype,
            session=self.session,
        )
