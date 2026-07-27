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

    def test_first_level_observation_establishes_a_baseline_without_alerting(self):
        baseline = evaluate_rule(
            operator=RuleOperator.ABOVE,
            threshold=100,
            value=101,
            previous_value=None,
            was_active=False,
        )

        self.assertTrue(baseline.active)
        self.assertFalse(baseline.triggered)

    def test_derived_option_metrics_handle_invalid_market_values(self):
        snapshot = {
            "bid_price": 9.5,
            "ask_price": 10.5,
            "volume": 150,
            "option_open_interest": 100,
            "option_implied_volatility": 35.5,
            "historical_volatility": 28.2,
            "underlying_price": 102,
            "strike_price": 100,
            "option_gamma": 0.08,
            "option_theta": -0.3,
            "days_to_expiry": 4,
        }

        self.assertEqual(metric_value(snapshot, RuleMetric.MID_PRICE), 10)
        self.assertEqual(metric_value(snapshot, RuleMetric.BID_ASK_SPREAD), 1)
        self.assertAlmostEqual(
            metric_value(snapshot, RuleMetric.BID_ASK_SPREAD_PCT) or 0,
            10,
        )
        self.assertEqual(
            metric_value(snapshot, RuleMetric.VOLUME_OPEN_INTEREST_RATIO),
            1.5,
        )
        self.assertAlmostEqual(
            metric_value(snapshot, RuleMetric.IV_HV_PREMIUM) or 0,
            7.3,
        )
        self.assertEqual(
            metric_value(snapshot, RuleMetric.STRIKE_DISTANCE_PCT),
            2,
        )
        self.assertEqual(
            metric_value(snapshot, RuleMetric.EXPIRY_GAMMA_RISK),
            2,
        )
        self.assertEqual(
            metric_value(snapshot, RuleMetric.EXPIRY_THETA_RISK),
            0.075,
        )
        self.assertIsNone(
            metric_value(
                {"volume": 10, "option_open_interest": 0},
                RuleMetric.VOLUME_OPEN_INTEREST_RATIO,
            )
        )
        self.assertIsNone(
            metric_value(
                {"bid_price": 10.5, "ask_price": 9.5},
                RuleMetric.BID_ASK_SPREAD_PCT,
            )
        )

    def test_moving_average_spread_supports_cross_rules(self):
        snapshot = {"ma20": 102, "ma60": 100}

        value = metric_value(snapshot, RuleMetric.MA20_MA60_SPREAD_PCT)

        self.assertEqual(value, 2)
        self.assertIsNone(
            metric_value(
                {"ma20": 102, "ma60": 0},
                RuleMetric.MA20_MA60_SPREAD_PCT,
            )
        )

    def test_rejects_option_only_metric_for_stock_rules(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            validate_rule_metric(
                InstrumentType.STOCK,
                RuleMetric.OPTION_IMPLIED_VOLATILITY,
            )

    def test_option_rule_support_matrix_includes_anomaly_and_chain_metrics(self):
        for metric in (
            RuleMetric.CHANGE_RATE_5M,
            RuleMetric.IV_HV_PREMIUM,
            RuleMetric.STRIKE_DISTANCE_PCT,
            RuleMetric.EXPIRY_GAMMA_RISK,
            RuleMetric.EXPIRY_THETA_RISK,
            RuleMetric.CALL_PUT_VOLUME_RATIO,
            RuleMetric.CALL_PUT_OPEN_INTEREST_RATIO,
        ):
            validate_rule_metric(InstrumentType.OPTION, metric)


if __name__ == "__main__":
    unittest.main()
