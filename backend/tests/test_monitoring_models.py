from __future__ import annotations

import unittest

from stock_strategy.monitoring_models import (
    InstrumentType,
    RuleMetric,
    RuleOperator,
    evaluate_rule,
    metric_value,
    validate_rule_metric,
)


class MonitoringModelsTest(unittest.TestCase):
    def test_level_rule_only_triggers_when_condition_becomes_active(self):
        first = evaluate_rule(
            operator=RuleOperator.ABOVE,
            threshold=100,
            value=101,
            previous_value=99,
            was_active=False,
        )
        repeated = evaluate_rule(
            operator=RuleOperator.ABOVE,
            threshold=100,
            value=102,
            previous_value=101,
            was_active=True,
        )
        reset = evaluate_rule(
            operator=RuleOperator.ABOVE,
            threshold=100,
            value=98,
            previous_value=102,
            was_active=True,
        )

        self.assertTrue(first.triggered)
        self.assertTrue(first.active)
        self.assertFalse(repeated.triggered)
        self.assertTrue(repeated.active)
        self.assertFalse(reset.triggered)
        self.assertFalse(reset.active)

    def test_cross_rule_requires_a_previous_value_on_the_other_side(self):
        missing_history = evaluate_rule(
            operator=RuleOperator.CROSSES_BELOW,
            threshold=25,
            value=24,
            previous_value=None,
            was_active=False,
        )
        crossing = evaluate_rule(
            operator=RuleOperator.CROSSES_BELOW,
            threshold=25,
            value=24,
            previous_value=26,
            was_active=False,
        )

        self.assertFalse(missing_history.triggered)
        self.assertTrue(crossing.triggered)

    def test_derived_option_metrics_handle_invalid_market_values(self):
        snapshot = {
            "bid_price": 9.5,
            "ask_price": 10.5,
            "volume": 150,
            "option_open_interest": 100,
        }

        self.assertAlmostEqual(
            metric_value(snapshot, RuleMetric.BID_ASK_SPREAD_PCT) or 0,
            10,
        )
        self.assertEqual(
            metric_value(snapshot, RuleMetric.VOLUME_OPEN_INTEREST_RATIO),
            1.5,
        )
        self.assertIsNone(
            metric_value(
                {"volume": 10, "option_open_interest": 0},
                RuleMetric.VOLUME_OPEN_INTEREST_RATIO,
            )
        )

    def test_rejects_option_only_metric_for_stock_rules(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            validate_rule_metric(
                InstrumentType.STOCK,
                RuleMetric.OPTION_IMPLIED_VOLATILITY,
            )


if __name__ == "__main__":
    unittest.main()
