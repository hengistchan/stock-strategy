from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, Protocol

from .models import Bar, Order, OrderSide


FUTU_US_FEE_SOURCE = (
    "https://www.futuhk.com/en/support/"
    "topic2_283from_platform%3D4%26platform_langArea%3Dmm%26lang%3Den-us"
)
FUTU_HK_FEE_SOURCE = "https://www.futuhk.com/hans/support/topic2_335"


@dataclass(frozen=True, slots=True)
class FeeBreakdown:
    components: Mapping[str, float]

    def __post_init__(self) -> None:
        normalized = {str(name): float(value) for name, value in self.components.items()}
        if not normalized:
            raise ValueError("fee breakdown must contain at least one component")
        if any(not math.isfinite(value) or value < 0 for value in normalized.values()):
            raise ValueError("fee components must be finite and non-negative")
        object.__setattr__(self, "components", normalized)

    @property
    def total(self) -> float:
        return sum(self.components.values())


class FeeModel(Protocol):
    def calculate(self, *, price: float, quantity: float, side: OrderSide) -> float: ...

    def manifest(self) -> dict[str, Any]: ...


class AttributedFeeModel(FeeModel, Protocol):
    def calculate_breakdown(
        self, *, price: float, quantity: float, side: OrderSide
    ) -> FeeBreakdown: ...


class SlippageModel(Protocol):
    def apply(self, *, price: float, side: OrderSide) -> float: ...

    def manifest(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    price: float
    quantity: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.price) or self.price <= 0:
            raise ValueError("execution price must be positive and finite")
        if not math.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("execution quantity must be positive and finite")


class BarExecutionModel(Protocol):
    def decide(
        self,
        *,
        order: Order,
        bar: Bar,
        candidate_price: float,
        remaining_quantity: float,
    ) -> ExecutionDecision | None: ...

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

    def calculate_breakdown(
        self, *, price: float, quantity: float, side: OrderSide
    ) -> FeeBreakdown:
        del side
        return FeeBreakdown(
            {
                "commission": max(
                    self.min_commission,
                    price * quantity * self.commission_bps / 10_000,
                )
            }
        )

    def calculate(self, *, price: float, quantity: float, side: OrderSide) -> float:
        return self.calculate_breakdown(
            price=price, quantity=quantity, side=side
        ).total

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "bps-commission-v1",
            "fee_granularity": "fill",
            **asdict(self),
        }


@dataclass(frozen=True, slots=True)
class FutuUSStockFeeModel:
    """FUTU HK fixed-plan US stock fees, excluding promotions and ADR charges."""

    commission_per_share: float = 0.0049
    min_commission: float = 0.99
    platform_per_share: float = 0.005
    min_platform: float = 1.0
    settlement_per_share: float = 0.003
    sec_rate: float = 0.0000206
    sec_minimum: float = 0.01
    finra_per_share: float = 0.000195
    finra_minimum: float = 0.01
    finra_maximum: float = 9.79
    cat_per_share: float = 0.000003

    def calculate_breakdown(
        self, *, price: float, quantity: float, side: OrderSide
    ) -> FeeBreakdown:
        turnover = _validated_turnover(price, quantity)
        is_sell = side in (OrderSide.SELL, OrderSide.SELL_SHORT)
        components = {
            "commission": max(self.min_commission, quantity * self.commission_per_share),
            "platform": max(self.min_platform, quantity * self.platform_per_share),
            "settlement": quantity * self.settlement_per_share,
            "sec_regulatory": max(self.sec_minimum, turnover * self.sec_rate)
            if is_sell
            else 0.0,
            "finra_activity": min(
                self.finra_maximum,
                max(self.finra_minimum, quantity * self.finra_per_share),
            )
            if is_sell
            else 0.0,
            "cat": quantity * self.cat_per_share,
        }
        return FeeBreakdown(components)

    def calculate(self, *, price: float, quantity: float, side: OrderSide) -> float:
        return self.calculate_breakdown(
            price=price, quantity=quantity, side=side
        ).total

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "futu-hk-us-stock-fixed-v1",
            "currency": "USD",
            "instrument_scope": "US stocks and ETFs; NMS CAT rate assumed",
            "fee_granularity": "fill",
            "partial_fill_minimum_policy": "per-fill-conservative",
            "excludes": ["promotions", "tiered package", "ADR fees", "borrow fees"],
            "source": FUTU_US_FEE_SOURCE,
            "verified_on": "2026-07-25",
            **asdict(self),
        }


@dataclass(frozen=True, slots=True)
class FutuHKStockFeeModel:
    """FUTU HK fixed-plan Hong Kong ordinary-stock fees."""

    commission_rate: float = 0.0003
    min_commission: float = 3.0
    platform_per_order: float = 15.0
    settlement_rate: float = 0.000042
    stamp_duty_rate: float = 0.001
    trading_fee_rate: float = 0.0000565
    sfc_levy_rate: float = 0.000027
    frc_levy_rate: float = 0.0000015
    commission_waived: bool = False
    stamp_duty_applicable: bool = True

    def calculate_breakdown(
        self, *, price: float, quantity: float, side: OrderSide
    ) -> FeeBreakdown:
        del side
        turnover = _validated_turnover(price, quantity)
        components = {
            "commission": 0.0
            if self.commission_waived
            else max(self.min_commission, turnover * self.commission_rate),
            "platform": self.platform_per_order,
            "settlement": turnover * self.settlement_rate,
            "stamp_duty": math.ceil(turnover * self.stamp_duty_rate)
            if self.stamp_duty_applicable
            else 0.0,
            "trading_fee": max(0.01, turnover * self.trading_fee_rate),
            "sfc_levy": max(0.01, turnover * self.sfc_levy_rate),
            "frc_levy": turnover * self.frc_levy_rate,
        }
        return FeeBreakdown(components)

    def calculate(self, *, price: float, quantity: float, side: OrderSide) -> float:
        return self.calculate_breakdown(
            price=price, quantity=quantity, side=side
        ).total

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "futu-hk-hk-stock-fixed-v1",
            "currency": "HKD",
            "instrument_scope": "HK ordinary stocks",
            "fee_granularity": "fill",
            "partial_fill_minimum_policy": "per-fill-conservative",
            "excludes": ["promotions", "tiered package", "short borrow fees"],
            "source": FUTU_HK_FEE_SOURCE,
            "verified_on": "2026-07-25",
            **asdict(self),
        }


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


@dataclass(frozen=True, slots=True)
class SpreadAwareSlippageModel:
    half_spread_bps: float = 2.0
    impact_bps: float = 3.0
    fixed_tick: float = 0.0

    def __post_init__(self) -> None:
        values = (self.half_spread_bps, self.impact_bps, self.fixed_tick)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("spread and impact values must be finite and non-negative")

    def apply(self, *, price: float, side: OrderSide) -> float:
        adverse_move = price * (self.half_spread_bps + self.impact_bps) / 10_000
        adverse_move += self.fixed_tick
        if side in (OrderSide.BUY, OrderSide.BUY_BACK):
            return price + adverse_move
        return price - adverse_move

    def manifest(self) -> dict[str, Any]:
        return {"name": "spread-aware-slippage-v1", **asdict(self)}


@dataclass(frozen=True, slots=True)
class DeterministicOHLCExecutionModel:
    def decide(
        self,
        *,
        order: Order,
        bar: Bar,
        candidate_price: float,
        remaining_quantity: float,
    ) -> ExecutionDecision:
        del order, bar
        return ExecutionDecision(candidate_price, remaining_quantity)

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "deterministic-ohlc-v1",
            "fill_clock": "next-bar",
            "liquidity": "unlimited",
        }


@dataclass(frozen=True, slots=True)
class VolumeParticipationExecutionModel:
    max_participation: float = 0.1

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.max_participation)
            or self.max_participation <= 0
            or self.max_participation > 1
        ):
            raise ValueError("max_participation must be in (0, 1]")

    def decide(
        self,
        *,
        order: Order,
        bar: Bar,
        candidate_price: float,
        remaining_quantity: float,
    ) -> ExecutionDecision | None:
        del order
        capacity = math.floor(max(0.0, bar.volume) * self.max_participation)
        if capacity <= 0:
            return None
        return ExecutionDecision(candidate_price, min(remaining_quantity, capacity))

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "volume-participation-v1",
            "fill_clock": "next-bar",
            "max_participation": self.max_participation,
            "partial_fills": True,
        }


@dataclass(frozen=True, slots=True)
class ConservativeBarExecutionModel:
    max_participation: float = 0.1

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.max_participation)
            or self.max_participation <= 0
            or self.max_participation > 1
        ):
            raise ValueError("max_participation must be in (0, 1]")

    def decide(
        self,
        *,
        order: Order,
        bar: Bar,
        candidate_price: float,
        remaining_quantity: float,
    ) -> ExecutionDecision | None:
        capacity = math.floor(max(0.0, bar.volume) * self.max_participation)
        if capacity <= 0:
            return None
        if order.side in (OrderSide.BUY, OrderSide.BUY_BACK):
            price = min(bar.high, max(candidate_price, bar.close))
            if order.limit_price is not None and order.order_type in {
                "LIMIT",
                "STOP_LIMIT",
                "LIMIT_IF_TOUCHED",
                "TRAILING_STOP_LIMIT",
            }:
                price = min(price, order.limit_price)
        else:
            price = max(bar.low, min(candidate_price, bar.close))
            if order.limit_price is not None and order.order_type in {
                "LIMIT",
                "STOP_LIMIT",
                "LIMIT_IF_TOUCHED",
                "TRAILING_STOP_LIMIT",
            }:
                price = max(price, order.limit_price)
        return ExecutionDecision(price, min(remaining_quantity, capacity))

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "conservative-bar-v1",
            "fill_clock": "next-bar",
            "price_policy": "adverse-of-candidate-and-close-bounded-by-ohlc",
            "max_participation": self.max_participation,
            "partial_fills": True,
        }


def build_fee_model(
    name: str,
    *,
    symbol: str,
    commission_bps: float,
    min_commission: float,
) -> FeeModel:
    normalized = name.strip().lower()
    if normalized == "simple":
        return BpsCommissionModel(commission_bps, min_commission)
    if normalized == "futu_auto":
        normalized = "futu_us" if symbol.upper().startswith("US.") else "futu_hk"
    if normalized == "futu_us":
        if not symbol.upper().startswith("US."):
            raise ValueError("futu_us fee model only supports US symbols")
        return FutuUSStockFeeModel()
    if normalized == "futu_hk":
        if not symbol.upper().startswith("HK."):
            raise ValueError("futu_hk fee model only supports HK symbols")
        return FutuHKStockFeeModel()
    raise ValueError(f"unsupported fee model: {name}")


def build_slippage_model(
    name: str,
    *,
    slippage_bps: float,
    spread_bps: float,
    impact_bps: float,
    fixed_tick: float,
) -> SlippageModel:
    normalized = name.strip().lower()
    if normalized == "bps":
        return BpsSlippageModel(slippage_bps)
    if normalized == "spread":
        return SpreadAwareSlippageModel(
            half_spread_bps=spread_bps / 2,
            impact_bps=impact_bps,
            fixed_tick=fixed_tick,
        )
    raise ValueError(f"unsupported slippage model: {name}")


def build_bar_execution_model(
    name: str, *, max_volume_participation: float
) -> BarExecutionModel:
    normalized = name.strip().lower()
    if normalized == "deterministic":
        return DeterministicOHLCExecutionModel()
    if normalized == "volume":
        return VolumeParticipationExecutionModel(max_volume_participation)
    if normalized == "conservative":
        return ConservativeBarExecutionModel(max_volume_participation)
    raise ValueError(f"unsupported bar execution model: {name}")


def _validated_turnover(price: float, quantity: float) -> float:
    if (
        not math.isfinite(price)
        or not math.isfinite(quantity)
        or price <= 0
        or quantity <= 0
    ):
        raise ValueError("price and quantity must be positive and finite")
    return price * quantity
