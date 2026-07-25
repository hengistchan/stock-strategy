from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import (
    AccountState,
    ExecutionReceipt,
    OrderProposal,
    OrderSide,
    PositionState,
    RiskDecision,
    SignalContext,
)
from .protocols import (
    ExitPolicy,
    OrderExecutor,
    PositionSizer,
    RiskPolicy,
    SignalModel,
)


@dataclass(slots=True)
class PipelineDecision:
    status: Literal["ready", "no_action", "rejected"]
    proposal: OrderProposal | None = None
    risk: RiskDecision | None = None
    executor: OrderExecutor | None = None
    reason: str = ""
    _receipt: ExecutionReceipt | None = None

    def execute(self) -> ExecutionReceipt | None:
        if self.status == "no_action":
            return None
        if self.status != "ready" or self.proposal is None or self.executor is None:
            raise RuntimeError(f"pipeline decision is not executable: {self.reason}")
        if self._receipt is None:
            self._receipt = self.executor.submit(self.proposal)
        return self._receipt


class StrategyPipeline:
    def __init__(
        self,
        *,
        signal: SignalModel,
        sizer: PositionSizer,
        risk: RiskPolicy,
        executor: OrderExecutor,
        exit: ExitPolicy | None = None,
    ) -> None:
        self.signal = signal
        self.sizer = sizer
        self.risk = risk
        self.executor = executor
        self.exit = exit

    def evaluate(
        self,
        context: SignalContext,
        account: AccountState,
        position: PositionState | None = None,
    ) -> PipelineDecision:
        if position is not None and position.quantity != 0:
            if self.exit is None:
                return PipelineDecision("no_action", reason="position_open")
            exit_decision = self.exit.evaluate(context, position)
            if exit_decision is None:
                return PipelineDecision("no_action", reason="hold")
            side: OrderSide = "sell" if position.quantity > 0 else "buy_back"
            proposal = OrderProposal(
                symbol=position.symbol,
                side=side,
                quantity=exit_decision.quantity or abs(position.quantity),
                reason=exit_decision.reason,
            )
            return PipelineDecision(
                "ready",
                proposal=proposal,
                risk=RiskDecision(True, "position_reduction"),
                executor=self.executor,
                reason=exit_decision.reason,
            )

        signal = self.signal.evaluate(context)
        if signal is None:
            return PipelineDecision("no_action", reason="no_signal")
        quantity = self.sizer.calculate(signal, account)
        if quantity <= 0:
            return PipelineDecision("rejected", reason="zero_quantity")
        proposal = OrderProposal(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            stop_price=signal.stop_price,
            reason=signal.reason,
            metadata=signal.metadata,
        )
        risk = self.risk.validate(proposal, account, position)
        if not risk.approved:
            return PipelineDecision(
                "rejected",
                proposal=proposal,
                risk=risk,
                reason=risk.reason,
            )
        return PipelineDecision(
            "ready",
            proposal=proposal,
            risk=risk,
            executor=self.executor,
            reason=signal.reason,
        )
