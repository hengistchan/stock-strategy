import unittest

from stock_strategy.execution_models import (
    ConservativeBarExecutionModel,
    FutuHKStockFeeModel,
    FutuUSStockFeeModel,
    SpreadAwareSlippageModel,
    build_fee_model,
)
from stock_strategy.models import Bar, Contract, Order, OrderSide


class ExecutionModelsTest(unittest.TestCase):
    def test_futu_us_stock_fee_breakdown_separates_sell_only_charges(self):
        model = FutuUSStockFeeModel()

        buy = model.calculate_breakdown(price=10, quantity=100, side=OrderSide.BUY)
        sell = model.calculate_breakdown(price=10, quantity=100, side=OrderSide.SELL)

        self.assertAlmostEqual(buy.components["commission"], 0.99)
        self.assertAlmostEqual(buy.components["platform"], 1.0)
        self.assertAlmostEqual(buy.components["settlement"], 0.3)
        self.assertEqual(buy.components["sec_regulatory"], 0)
        self.assertEqual(buy.components["finra_activity"], 0)
        self.assertAlmostEqual(sell.components["sec_regulatory"], 0.0206)
        self.assertAlmostEqual(sell.components["finra_activity"], 0.0195)
        self.assertGreater(sell.total, buy.total)

    def test_futu_hk_stock_fee_breakdown_applies_rounded_stamp_duty(self):
        breakdown = FutuHKStockFeeModel().calculate_breakdown(
            price=10, quantity=1000, side=OrderSide.BUY
        )

        self.assertEqual(breakdown.components["commission"], 3)
        self.assertEqual(breakdown.components["platform"], 15)
        self.assertEqual(breakdown.components["stamp_duty"], 10)
        self.assertAlmostEqual(breakdown.total, 29.27)

    def test_fee_factory_rejects_market_mismatch(self):
        with self.assertRaisesRegex(ValueError, "only supports US"):
            build_fee_model(
                "futu_us",
                symbol="HK.00700",
                commission_bps=3,
                min_commission=1,
            )

    def test_spread_aware_slippage_is_adverse_on_both_sides(self):
        model = SpreadAwareSlippageModel(
            half_spread_bps=2, impact_bps=3, fixed_tick=0.01
        )

        self.assertAlmostEqual(model.apply(price=100, side=OrderSide.BUY), 100.06)
        self.assertAlmostEqual(model.apply(price=100, side=OrderSide.SELL), 99.94)

    def test_conservative_bar_uses_adverse_close_and_volume_capacity(self):
        order = Order(
            order_id="SIM-1",
            symbol=Contract("US.TEST"),
            side=OrderSide.BUY,
            quantity=100,
            order_type="MARKET",
            submitted_index=0,
            submitted_date="2025-01-01",
        )
        decision = ConservativeBarExecutionModel(0.1).decide(
            order=order,
            bar=Bar("2025-01-02", 100, 110, 95, 108, 30),
            candidate_price=100,
            remaining_quantity=100,
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.price, 108)
        self.assertEqual(decision.quantity, 3)

    def test_conservative_bar_never_violates_a_limit_price(self):
        order = Order(
            order_id="SIM-2",
            symbol=Contract("US.TEST"),
            side=OrderSide.BUY,
            quantity=10,
            order_type="LIMIT",
            submitted_index=0,
            submitted_date="2025-01-01",
            limit_price=101,
        )
        decision = ConservativeBarExecutionModel(1).decide(
            order=order,
            bar=Bar("2025-01-02", 100, 110, 95, 108, 100),
            candidate_price=100,
            remaining_quantity=10,
        )

        assert decision is not None
        self.assertEqual(decision.price, 101)


if __name__ == "__main__":
    unittest.main()
