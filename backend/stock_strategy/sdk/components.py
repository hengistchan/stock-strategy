from __future__ import annotations

import math

from .models import (
    AccountState,
    ExitDecision,
    OrderProposal,
    PositionState,
    RiskDecision,
    Signal,
    SignalContext,
)


class FractionalBuyingPowerSizer:
    def __init__(self, fraction: float, *, lot_size: float = 1.0) -> None:
        if not 0 < fraction <= 1:
            raise ValueError("fraction must be in (0, 1]")
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")
        self.fraction = fraction
        self.lot_size = lot_size

    def calculate(self, signal: Signal, account: AccountState) -> float:
        raw = account.buying_power * self.fraction / signal.reference_price
        return math.floor(raw / self.lot_size) * self.lot_size


class FixedRiskSizer:
    def __init__(
        self,
        risk_fraction: float,
        *,
        max_position_fraction: float = 1.0,
        lot_size: float = 1.0,
    ) -> None:
        if not 0 < risk_fraction <= 1:
            raise ValueError("risk_fraction must be in (0, 1]")
        if not 0 < max_position_fraction <= 1:
            raise ValueError("max_position_fraction must be in (0, 1]")
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")
        self.risk_fraction = risk_fraction
        self.max_position_fraction = max_position_fraction
        self.lot_size = lot_size

    def calculate(self, signal: Signal, account: AccountState) -> float:
        if signal.stop_price is None:
            return 0.0
        per_share_risk = abs(signal.reference_price - signal.stop_price)
        if per_share_risk <= 0:
            return 0.0
        risk_quantity = account.equity * self.risk_fraction / per_share_risk
        capital_quantity = (
            account.buying_power * self.max_position_fraction / signal.reference_price
        )
        raw = min(risk_quantity, capital_quantity)
        return math.floor(raw / self.lot_size) * self.lot_size


class AllowAllRiskPolicy:
    def validate(
        self,
        proposal: OrderProposal,
        account: AccountState,
        position: PositionState | None,
    ) -> RiskDecision:
        del proposal, account, position
        return RiskDecision(True)


class DailyRiskPolicy:
    def __init__(
        self,
        *,
        max_daily_loss: float,
        max_consecutive_losses: int,
        max_open_positions: int = 1,
    ) -> None:
        if max_daily_loss <= 0:
            raise ValueError("max_daily_loss must be positive")
        if max_consecutive_losses < 1 or max_open_positions < 1:
            raise ValueError("risk limits must be positive")
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.max_open_positions = max_open_positions

    def validate(
        self,
        proposal: OrderProposal,
        account: AccountState,
        position: PositionState | None,
    ) -> RiskDecision:
        del proposal, position
        if account.daily_realized_pnl <= -self.max_daily_loss:
            return RiskDecision(False, "daily_loss_limit")
        if account.consecutive_losses >= self.max_consecutive_losses:
            return RiskDecision(False, "consecutive_loss_limit")
        if account.open_positions >= self.max_open_positions:
            return RiskDecision(False, "position_limit")
        return RiskDecision(True)


class StructuralExitPolicy:
    def evaluate(
        self,
        context: SignalContext,
        position: PositionState,
    ) -> ExitDecision | None:
        if position.quantity > 0:
            if position.stop_price is not None and context.price <= position.stop_price:
                return ExitDecision("structural_stop")
            if (
                position.target_price is not None
                and context.price >= position.target_price
            ):
                return ExitDecision("structural_target")
        elif position.quantity < 0:
            if position.stop_price is not None and context.price >= position.stop_price:
                return ExitDecision("structural_stop")
            if (
                position.target_price is not None
                and context.price <= position.target_price
            ):
                return ExitDecision("structural_target")
        return None
