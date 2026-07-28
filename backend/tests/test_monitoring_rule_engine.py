from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from stock_strategy.monitoring_rule_engine import (
    MarketSession,
    RuleSuppressionReason,
    decide_rule,
)

MARKET_TIMEZONE = timezone(timedelta(hours=-4))
OBSERVED_AT = datetime(2026, 7, 27, 14, 0, 5, tzinfo=MARKET_TIMEZONE)
PROVIDER_TIME = datetime(2026, 7, 27, 14, 0, 4, tzinfo=MARKET_TIMEZONE)


class MonitoringRuleEngineTest(unittest.TestCase):
    def test_first_observation_only_establishes_a_baseline(self) -> None:
        for operator, value, expected_active in (
            ("above", 101.0, True),
            ("below", 99.0, True),
            ("crosses_above", 101.0, True),
            ("crosses_below", 99.0, True),
        ):
            with self.subTest(operator=operator):
                decision = _decide(
                    _rule(operator=operator, last_value=None),
                    {"last_price": value},
                )

                self.assertTrue(decision.baseline)
                self.assertTrue(decision.evaluated)
                self.assertFalse(decision.triggered)
                self.assertEqual(decision.condition_active, expected_active)
                self.assertEqual(
                    decision.suppression_reason,
                    RuleSuppressionReason.BASELINE,
                )

    def test_level_and_cross_operators_trigger_only_on_an_edge(self) -> None:
        cases = (
            ("above", 99.0, False, 101.0, True),
            ("below", 101.0, False, 99.0, True),
            ("crosses_above", 99.0, False, 101.0, True),
            ("crosses_below", 101.0, False, 99.0, True),
            ("above", 101.0, True, 102.0, False),
            ("below", 99.0, True, 98.0, False),
            ("crosses_above", 101.0, True, 102.0, False),
            ("crosses_below", 99.0, True, 98.0, False),
            ("crosses_above", 99.0, False, 100.0, False),
            ("crosses_below", 101.0, False, 100.0, False),
        )
        for operator, previous, was_active, current, triggered in cases:
            with self.subTest(
                operator=operator,
                previous=previous,
                current=current,
            ):
                decision = _decide(
                    _rule(
                        operator=operator,
                        last_value=previous,
                        condition_active=was_active,
                    ),
                    {"last_price": current},
                )

                self.assertTrue(decision.evaluated)
                self.assertFalse(decision.baseline)
                self.assertEqual(decision.triggered, triggered)

    def test_sustained_true_condition_does_not_repeat(self) -> None:
        decision = _decide(
            _rule(last_value=101.0, condition_active=True),
            {"last_price": 102.0},
        )

        self.assertTrue(decision.condition_active)
        self.assertFalse(decision.triggered)
        self.assertIsNone(decision.suppression_reason)

    def test_cooldown_suppresses_edge_until_the_exact_boundary(self) -> None:
        last_triggered_at = datetime(
            2026,
            7,
            27,
            13,
            59,
            5,
            tzinfo=MARKET_TIMEZONE,
        )
        for elapsed, expected_trigger, expected_reason in (
            (timedelta(seconds=59), False, RuleSuppressionReason.COOLDOWN),
            (timedelta(seconds=60), True, None),
            (timedelta(seconds=61), True, None),
        ):
            with self.subTest(elapsed=elapsed):
                observed_at = last_triggered_at + elapsed
                decision = _decide(
                    _rule(
                        last_value=99.0,
                        condition_active=False,
                        cooldown_seconds=60,
                        last_triggered_at=last_triggered_at.isoformat(),
                    ),
                    {"last_price": 101.0},
                    observed_at=observed_at,
                )

                self.assertEqual(decision.triggered, expected_trigger)
                self.assertEqual(decision.suppression_reason, expected_reason)
                self.assertTrue(decision.condition_active)

    def test_daily_limit_uses_provider_market_date_and_resets_next_day(self) -> None:
        capped_rule = _rule(
            last_value=99.0,
            condition_active=False,
            daily_trigger_limit=2,
            trigger_date="2026-07-27",
            trigger_count=2,
        )
        next_market_day = datetime(
            2026,
            7,
            28,
            9,
            30,
            tzinfo=MARKET_TIMEZONE,
        )

        capped = _decide(capped_rule, {"last_price": 101.0})
        reset = _decide(
            capped_rule,
            {"last_price": 101.0},
            provider_time=next_market_day,
        )

        self.assertFalse(capped.triggered)
        self.assertTrue(capped.condition_active)
        self.assertEqual(
            capped.suppression_reason,
            RuleSuppressionReason.DAILY_LIMIT,
        )
        self.assertEqual(capped.trigger_date, "2026-07-27")
        self.assertTrue(reset.triggered)
        self.assertEqual(reset.trigger_date, "2026-07-28")

    def test_trigger_date_comes_from_provider_time_not_observed_time(self) -> None:
        observed_next_day = datetime(
            2026,
            7,
            28,
            0,
            0,
            tzinfo=timezone.utc,
        )

        decision = _decide(
            _rule(
                last_value=99.0,
                daily_trigger_limit=1,
                trigger_date="2026-07-27",
                trigger_count=1,
            ),
            {"last_price": 101.0},
            observed_at=observed_next_day,
            provider_time=PROVIDER_TIME,
        )

        self.assertEqual(decision.trigger_date, "2026-07-27")
        self.assertEqual(
            decision.suppression_reason,
            RuleSuppressionReason.DAILY_LIMIT,
        )

    def test_non_evaluation_gates_report_an_explicit_reason(self) -> None:
        cases = (
            (
                "disabled",
                _rule(enabled=False),
                {"last_price": 101.0},
                {},
                RuleSuppressionReason.DISABLED,
            ),
            (
                "reconnecting",
                _rule(),
                {"last_price": 101.0},
                {"reconnecting": True},
                RuleSuppressionReason.RECONNECTING,
            ),
            (
                "stale",
                _rule(condition_active=True),
                {"last_price": 101.0},
                {"is_fresh": False},
                RuleSuppressionReason.STALE,
            ),
            (
                "closed",
                _rule(session="all"),
                {"last_price": 101.0},
                {"market_session": MarketSession.CLOSED},
                RuleSuppressionReason.MARKET_CLOSED,
            ),
            (
                "unknown_session",
                _rule(session="all"),
                {"last_price": 101.0},
                {"market_session": MarketSession.UNKNOWN},
                RuleSuppressionReason.MARKET_SESSION_UNKNOWN,
            ),
            (
                "outside_session",
                _rule(session="regular"),
                {"last_price": 101.0},
                {"market_session": MarketSession.EXTENDED},
                RuleSuppressionReason.OUTSIDE_SESSION,
            ),
            (
                "missing_metric",
                _rule(),
                {},
                {},
                RuleSuppressionReason.METRIC_UNAVAILABLE,
            ),
        )
        for name, rule, snapshot, inputs, expected_reason in cases:
            with self.subTest(name=name):
                decision = _decide(rule, snapshot, **inputs)

                self.assertFalse(decision.baseline)
                self.assertFalse(decision.evaluated)
                self.assertFalse(decision.triggered)
                self.assertIsNone(decision.value)
                self.assertEqual(
                    decision.condition_active,
                    bool(rule["condition_active"]),
                )
                self.assertEqual(decision.suppression_reason, expected_reason)

    def test_rule_session_matrix_only_evaluates_open_matching_sessions(self) -> None:
        cases = (
            ("regular", MarketSession.REGULAR, True),
            ("regular", MarketSession.EXTENDED, False),
            ("extended", MarketSession.REGULAR, False),
            ("extended", MarketSession.EXTENDED, True),
            ("all", MarketSession.REGULAR, True),
            ("all", MarketSession.EXTENDED, True),
            ("all", MarketSession.CLOSED, False),
            ("all", MarketSession.UNKNOWN, False),
        )
        for rule_session, market_session, evaluated in cases:
            with self.subTest(
                rule_session=rule_session,
                market_session=market_session,
            ):
                decision = _decide(
                    _rule(session=rule_session),
                    {"last_price": 99.0},
                    market_session=market_session,
                )

                self.assertEqual(decision.evaluated, evaluated)

    def test_derived_metric_is_obtained_through_monitoring_models(self) -> None:
        decision = _decide(
            _rule(
                metric="bid_ask_spread_pct",
                threshold=5.0,
                last_value=4.0,
                condition_active=False,
            ),
            {"bid_price": 95.0, "ask_price": 105.0},
        )

        self.assertEqual(decision.value, 10.0)
        self.assertTrue(decision.triggered)

    def test_naive_input_times_are_rejected(self) -> None:
        for field, inputs in (
            ("observed_at", {"observed_at": datetime(2026, 7, 27, 14, 0)}),
            ("provider_time", {"provider_time": datetime(2026, 7, 27, 14, 0)}),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "timezone-aware"):
                    _decide(_rule(), {"last_price": 101.0}, **inputs)


def _rule(**updates: object) -> dict[str, object]:
    rule: dict[str, object] = {
        "id": "rule-1",
        "enabled": True,
        "metric": "last_price",
        "operator": "above",
        "threshold": 100.0,
        "session": "regular",
        "cooldown_seconds": 0,
        "daily_trigger_limit": 10,
        "last_value": 99.0,
        "condition_active": False,
        "last_triggered_at": None,
        "trigger_date": None,
        "trigger_count": 0,
    }
    rule.update(updates)
    return rule


def _decide(
    rule: dict[str, object],
    snapshot: dict[str, object],
    *,
    observed_at: datetime = OBSERVED_AT,
    provider_time: datetime = PROVIDER_TIME,
    is_fresh: bool = True,
    reconnecting: bool = False,
    market_session: MarketSession = MarketSession.REGULAR,
):
    return decide_rule(
        rule,
        snapshot,
        observed_at=observed_at,
        provider_time=provider_time,
        is_fresh=is_fresh,
        reconnecting=reconnecting,
        market_session=market_session,
    )


if __name__ == "__main__":
    unittest.main()
