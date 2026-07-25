from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .application_models import (
    KLINE_TYPES,
    SESSION_TYPES,
    SYMBOL_PATTERN,
    BacktestSpec,
    EvaluationWindow,
    ExperimentSpec,
    ParameterValue,
)
from .strategy_repository import MAX_STRATEGY_BYTES


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

    @model_validator(mode="after")
    def validate_research_windows(self) -> "ExperimentRequest":
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


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=67)
    content: str | None = Field(default=None, max_length=MAX_STRATEGY_BYTES)
    template_path: str | None = Field(default=None, max_length=200)


class StrategySaveRequest(BaseModel):
    content: str = Field(max_length=MAX_STRATEGY_BYTES)
    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)
