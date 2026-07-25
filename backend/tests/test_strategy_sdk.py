import unittest
from datetime import datetime

from stock_strategy.sdk import (
    AccountState,
    AllowAllRiskPolicy,
    DailyRiskPolicy,
    ExecutionReceipt,
    ExitDecision,
    FixedRiskSizer,
    FractionalBuyingPowerSizer,
    OrderProposal,
    PositionState,
    Signal,
    SignalContext,
    StrategyPipeline,
)


class StaticSignal:
    def __init__(self, signal):
        self.signal = signal

    def evaluate(self, context):
        del context
        return self.signal


class StaticExit:
    def __init__(self, decision):
        self.decision = decision

    def evaluate(self, context, position):
        del context, position
        return self.decision


class RecordingExecutor:
    def __init__(self):
        self.proposals = []

    def submit(self, proposal):
        self.proposals.append(proposal)
        return ExecutionReceipt("ORDER-1", proposal)


class StrategySdkTest(unittest.TestCase):
    def setUp(self):
        self.context = SignalContext(
            symbol="US.AAPL",
            timestamp=datetime(2026, 1, 2, 9, 30),
            price=100,
        )
        self.account = AccountState(cash=10_000, equity=10_000, buying_power=10_000)

    def test_pipeline_sizes_validates_and_executes_once(self):
        executor = RecordingExecutor()
        pipeline = StrategyPipeline(
            signal=StaticSignal(Signal("US.AAPL", "buy", 100)),
            sizer=FractionalBuyingPowerSizer(0.5),
            risk=AllowAllRiskPolicy(),
            executor=executor,
        )

        decision = pipeline.evaluate(self.context, self.account)
        first = decision.execute()
        second = decision.execute()

        self.assertEqual(decision.status, "ready")
        self.assertEqual(first.order_id, "ORDER-1")
        self.assertIs(first, second)
        self.assertEqual(executor.proposals[0].quantity, 50)
        self.assertEqual(len(executor.proposals), 1)

    def test_risk_rejection_cannot_execute(self):
        executor = RecordingExecutor()
        pipeline = StrategyPipeline(
            signal=StaticSignal(Signal("US.AAPL", "buy", 100)),
            sizer=FractionalBuyingPowerSizer(0.5),
            risk=DailyRiskPolicy(
                max_daily_loss=100,
                max_consecutive_losses=2,
            ),
            executor=executor,
        )
        account = AccountState(
            cash=10_000,
            equity=10_000,
            buying_power=10_000,
            daily_realized_pnl=-100,
        )

        decision = pipeline.evaluate(self.context, account)

        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.reason, "daily_loss_limit")
        with self.assertRaises(RuntimeError):
            decision.execute()
        self.assertEqual(executor.proposals, [])

    def test_exit_bypasses_entry_sizing_and_closes_position(self):
        executor = RecordingExecutor()
        pipeline = StrategyPipeline(
            signal=StaticSignal(None),
            sizer=FractionalBuyingPowerSizer(0.5),
            risk=AllowAllRiskPolicy(),
            exit=StaticExit(ExitDecision("signal_exit")),
            executor=executor,
        )
        position = PositionState("US.AAPL", 12, 90, 100)

        receipt = pipeline.evaluate(
            self.context,
            self.account,
            position,
        ).execute()

        self.assertEqual(receipt.proposal.side, "sell")
        self.assertEqual(receipt.proposal.quantity, 12)
        self.assertEqual(receipt.proposal.reason, "signal_exit")

    def test_fixed_risk_sizer_respects_risk_capital_and_lot(self):
        sizer = FixedRiskSizer(
            0.01,
            max_position_fraction=0.5,
            lot_size=10,
        )

        quantity = sizer.calculate(
            Signal("US.AAPL", "buy", 100, stop_price=98),
            AccountState(cash=20_000, equity=20_000, buying_power=20_000),
        )

        self.assertEqual(quantity, 100)

    def test_invalid_proposal_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            OrderProposal("US.AAPL", "buy", 0)


if __name__ == "__main__":
    unittest.main()
