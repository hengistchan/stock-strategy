from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Mapping, TypeAlias


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

ParameterValue: TypeAlias = bool | int | float | str


@dataclass(frozen=True, slots=True)
class BacktestSpec:
    strategy: str
    symbol: str
    start: date
    end: date
    ktype: str = "K_DAY"
    autype: str = "QFQ"
    session: str = "ALL"
    initial_cash: float = 100_000
    commission_bps: float = 3
    min_commission: float = 1
    slippage_bps: float = 5
    fee_model: str = "simple"
    slippage_model: str = "bps"
    execution_model: str = "deterministic"
    max_volume_participation: float = 0.1
    spread_bps: float = 0
    impact_bps: float = 0
    fixed_tick: float = 0
    warmup_bars: int = 0
    allow_short: bool = False
    liquidate_on_end: bool = False
    parameters: Mapping[str, ParameterValue] = field(default_factory=dict)
    refresh_cache: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "ktype": self.ktype,
            "autype": self.autype,
            "session": self.session,
            "initial_cash": self.initial_cash,
            "commission_bps": self.commission_bps,
            "min_commission": self.min_commission,
            "slippage_bps": self.slippage_bps,
            "fee_model": self.fee_model,
            "slippage_model": self.slippage_model,
            "execution_model": self.execution_model,
            "max_volume_participation": self.max_volume_participation,
            "spread_bps": self.spread_bps,
            "impact_bps": self.impact_bps,
            "fixed_tick": self.fixed_tick,
            "warmup_bars": self.warmup_bars,
            "allow_short": self.allow_short,
            "liquidate_on_end": self.liquidate_on_end,
            "parameters": dict(self.parameters),
            "refresh_cache": self.refresh_cache,
        }


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    name: str
    base: BacktestSpec
    parameter_grid: Mapping[str, list[ParameterValue]]
    objective: str = "sharpe_ratio"
    validation: "EvaluationWindow | None" = None
    test: "EvaluationWindow | None" = None
    walk_forward_folds: int = 0
    constraints: tuple["MetricConstraint", ...] = ()
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricConstraint:
    metric: str
    op: Literal[">=", "<="]
    value: float

    def to_dict(self) -> dict[str, str | float]:
        return {"metric": self.metric, "op": self.op, "value": self.value}


@dataclass(frozen=True, slots=True)
class EvaluationWindow:
    start: date
    end: date

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}
