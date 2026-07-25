from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Protocol

from .models import OrderSide


class FeeModel(Protocol):
    def calculate(self, *, price: float, quantity: float, side: OrderSide) -> float: ...

    def manifest(self) -> dict[str, Any]: ...


class SlippageModel(Protocol):
    def apply(self, *, price: float, side: OrderSide) -> float: ...

    def manifest(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class BpsCommissionModel:
    commission_bps: float = 3.0
    min_commission: float = 1.0

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.commission_bps)
            or not math.isfinite(self.min_commission)
            or self.commission_bps < 0
            or self.min_commission < 0
        ):
            raise ValueError("commission values must be finite and non-negative")

    def calculate(self, *, price: float, quantity: float, side: OrderSide) -> float:
        del side
        return max(
            self.min_commission,
            price * quantity * self.commission_bps / 10_000,
        )

    def manifest(self) -> dict[str, Any]:
        return {"name": "bps-commission-v1", **asdict(self)}


@dataclass(frozen=True, slots=True)
class BpsSlippageModel:
    slippage_bps: float = 5.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.slippage_bps) or self.slippage_bps < 0:
            raise ValueError("slippage_bps must be finite and non-negative")

    def apply(self, *, price: float, side: OrderSide) -> float:
        rate = self.slippage_bps / 10_000
        if side in (OrderSide.BUY, OrderSide.BUY_BACK):
            return price * (1 + rate)
        return price * (1 - rate)

    def manifest(self) -> dict[str, Any]:
        return {"name": "bps-slippage-v1", **asdict(self)}
