from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .strategy_repository import MAX_STRATEGY_BYTES


SYMBOL_PATTERN = r"^[A-Z]{2,8}\.[A-Z0-9.-]{1,24}$"
KLINE_TYPES = (
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
)
SESSION_TYPES = ("ALL", "RTH", "ETH")


ParameterValue = bool | int | float | str


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


class ExperimentRequest(BaseModel):
    name: str = Field(default="参数实验", min_length=1, max_length=80)
    base: BacktestRequest
    parameter_grid: dict[str, list[ParameterValue]]
    objective: Literal[
        "total_return_pct", "sharpe_ratio", "max_drawdown_pct"
    ] = "sharpe_ratio"


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=67)
    content: str | None = Field(default=None, max_length=MAX_STRATEGY_BYTES)
    template_path: str | None = Field(default=None, max_length=200)


class StrategySaveRequest(BaseModel):
    content: str = Field(max_length=MAX_STRATEGY_BYTES)
    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)
