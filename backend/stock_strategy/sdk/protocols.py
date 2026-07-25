from __future__ import annotations

from typing import Protocol

from .models import (
    AccountState,
    ExecutionReceipt,
    ExitDecision,
    OrderProposal,
    PositionState,
    RiskDecision,
    Signal,
    SignalContext,
)


class SignalModel(Protocol):
    def evaluate(self, context: SignalContext) -> Signal | None: ...


class PositionSizer(Protocol):
    def calculate(self, signal: Signal, account: AccountState) -> float: ...


class RiskPolicy(Protocol):
    def validate(
        self,
        proposal: OrderProposal,
        account: AccountState,
        position: PositionState | None,
    ) -> RiskDecision: ...


class ExitPolicy(Protocol):
    def evaluate(
        self,
        context: SignalContext,
        position: PositionState,
    ) -> ExitDecision | None: ...


class OrderExecutor(Protocol):
    def submit(self, proposal: OrderProposal) -> ExecutionReceipt: ...
