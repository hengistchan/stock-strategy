from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping

EntrySide = Literal["buy", "sell_short"]
OrderSide = Literal["buy", "sell", "sell_short", "buy_back"]


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    side: EntrySide
    reference_price: float
    stop_price: float | None = None
    strength: float = 1.0
    reason: str = "signal"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reference_price <= 0:
            raise ValueError("signal reference_price must be positive")
        if not 0 <= self.strength <= 1:
            raise ValueError("signal strength must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SignalContext:
    symbol: str
    timestamp: datetime
    price: float
    values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccountState:
    cash: float
    equity: float
    buying_power: float
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    open_positions: int = 0


@dataclass(frozen=True, slots=True)
class PositionState:
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    stop_price: float | None = None
    target_price: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrderProposal:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    limit_price: float | None = None
    stop_price: float | None = None
    reason: str = "signal"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExitDecision:
    reason: str
    quantity: float | None = None


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    order_id: str | None
    proposal: OrderProposal
