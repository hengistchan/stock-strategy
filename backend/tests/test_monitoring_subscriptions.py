from __future__ import annotations

import dataclasses
import math
import unittest

from stock_strategy.monitoring_subscriptions import (
    GenericSubscriptionBudget,
    SubscriptionIntent,
    SubscriptionIntentSource,
    SubscriptionPlanner,
    SubscriptionTarget,
)


def budget(*, remaining: int) -> GenericSubscriptionBudget:
    return GenericSubscriptionBudget(
        generic_total_used=12,
        generic_own_used=4,
        generic_remaining=remaining,
    )


class SubscriptionPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = SubscriptionPlanner()

    def test_targets_are_exact_normalized_security_and_subtype_pairs(self):
        target = SubscriptionTarget(" us.aapl260731c95000 ", " quote ")

        self.assertEqual(target.code, "US.AAPL260731C95000")
        self.assertEqual(target.subtype, "QUOTE")
        for invalid in (
            "US.AAPL*",
            "US.AAPL.*",
            "US.AAPL,US.MSFT",
            "US.OPTION_CHAIN",
            "AAPL",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "exact security code"):
                    SubscriptionTarget(invalid)
        with self.assertRaisesRegex(ValueError, "exact subtype"):
            SubscriptionTarget("US.AAPL", "*")

    def test_prioritizes_rules_then_watchlist_then_temporary_page_interest(self):
        now = 1_000.0
        persistent_option = SubscriptionIntent.persistent_rule("US.AAPL260731C95000")
        watched_stock = SubscriptionIntent.watchlist("US.AAPL")
        visible_option = SubscriptionIntent.temporary_page_interest(
            "US.AAPL260731P95000",
            now=now,
            ttl_seconds=30,
        )

        plan = self.planner.plan(
            intents=(visible_option, watched_stock, persistent_option),
            actual_owned=(),
            budget=budget(remaining=2),
            now=now,
        )

        self.assertEqual(
            plan.to_subscribe,
            (
                SubscriptionTarget("US.AAPL260731C95000"),
                SubscriptionTarget("US.AAPL"),
            ),
        )
        self.assertEqual(
            plan.deferred,
            (SubscriptionTarget("US.AAPL260731P95000"),),
        )
        self.assertEqual(
            plan.desired,
            frozenset(
                {
                    persistent_option.target,
                    watched_stock.target,
                    visible_option.target,
                }
            ),
        )

    def test_insufficient_generic_capacity_never_evicts_existing_interest(self):
        existing_page = SubscriptionIntent.temporary_page_interest(
            "US.MSFT",
            now=100,
            ttl_seconds=30,
        )
        new_rule = SubscriptionIntent.persistent_rule("US.AAPL260731C95000")

        plan = self.planner.plan(
            intents=(existing_page, new_rule),
            actual_owned=(existing_page.target,),
            budget=budget(remaining=0),
            now=110,
        )

        self.assertEqual(plan.retained, frozenset({existing_page.target}))
        self.assertEqual(plan.to_unsubscribe, ())
        self.assertEqual(plan.to_subscribe, ())
        self.assertEqual(plan.deferred, (new_rule.target,))

    def test_diff_removes_only_undesired_owned_targets_before_a_later_replan(self):
        stale = SubscriptionTarget("US.OLD")
        requested = SubscriptionIntent.persistent_rule("US.AAPL")

        plan = self.planner.plan(
            intents=(requested,),
            actual_owned=(stale,),
            budget=budget(remaining=0),
            now=100,
        )

        self.assertEqual(plan.to_unsubscribe, (stale,))
        self.assertEqual(plan.deferred, (requested.target,))
        self.assertEqual(plan.to_subscribe, ())

    def test_temporary_interest_expires_at_the_ttl_boundary(self):
        temporary = SubscriptionIntent.temporary_page_interest(
            "HK.00700",
            now=50,
            ttl_seconds=10,
        )

        active = self.planner.plan(
            intents=(temporary,),
            actual_owned=(temporary.target,),
            budget=budget(remaining=0),
            now=59.999,
        )
        expired = self.planner.plan(
            intents=(temporary,),
            actual_owned=(temporary.target,),
            budget=budget(remaining=0),
            now=60,
        )

        self.assertEqual(active.retained, frozenset({temporary.target}))
        self.assertEqual(active.expired_intents, ())
        self.assertEqual(expired.desired, frozenset())
        self.assertEqual(expired.to_unsubscribe, (temporary.target,))
        self.assertEqual(expired.expired_intents, (temporary,))

    def test_persistent_interest_keeps_target_after_overlapping_page_ttl_expires(self):
        temporary = SubscriptionIntent.temporary_page_interest(
            "US.AAPL",
            now=10,
            ttl_seconds=5,
        )
        watchlist = SubscriptionIntent.watchlist("US.AAPL")
        rule = SubscriptionIntent.persistent_rule("US.AAPL")

        plan = self.planner.plan(
            intents=(temporary, watchlist, rule),
            actual_owned=(),
            budget=budget(remaining=1),
            now=20,
        )

        self.assertEqual(plan.to_subscribe, (rule.target,))
        self.assertEqual(plan.desired, frozenset({rule.target}))
        self.assertEqual(plan.expired_intents, (temporary,))

    def test_same_code_with_distinct_subtypes_remains_an_exact_diff(self):
        quote = SubscriptionIntent.watchlist("US.AAPL", subtype="QUOTE")
        order_book = SubscriptionIntent.persistent_rule(
            "US.AAPL",
            subtype="ORDER_BOOK",
        )

        plan = self.planner.plan(
            intents=(quote, order_book),
            actual_owned=(quote.target,),
            budget=budget(remaining=1),
            now=100,
        )

        self.assertEqual(plan.retained, frozenset({quote.target}))
        self.assertEqual(plan.to_subscribe, (order_book.target,))
        self.assertEqual(plan.to_unsubscribe, ())

    def test_generic_usage_names_do_not_claim_an_option_specific_quota(self):
        names = {field.name for field in dataclasses.fields(GenericSubscriptionBudget)}

        self.assertEqual(
            names,
            {
                "generic_total_used",
                "generic_own_used",
                "generic_remaining",
            },
        )
        self.assertFalse(any("option" in name for name in names))

    def test_rejects_invalid_ttl_clock_and_generic_usage(self):
        with self.assertRaisesRegex(ValueError, "TTL"):
            SubscriptionIntent.temporary_page_interest(
                "US.AAPL",
                now=0,
                ttl_seconds=0,
            )
        with self.assertRaisesRegex(ValueError, "finite clock"):
            SubscriptionIntent.temporary_page_interest(
                "US.AAPL",
                now=math.inf,
                ttl_seconds=10,
            )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            GenericSubscriptionBudget(
                generic_total_used=1,
                generic_own_used=1,
                generic_remaining=-1,
            )
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            GenericSubscriptionBudget(
                generic_total_used=1,
                generic_own_used=2,
                generic_remaining=0,
            )

    def test_source_values_encode_the_documented_business_priority(self):
        self.assertGreater(
            SubscriptionIntentSource.PERSISTENT_RULE,
            SubscriptionIntentSource.WATCHLIST,
        )
        self.assertGreater(
            SubscriptionIntentSource.WATCHLIST,
            SubscriptionIntentSource.TEMPORARY_PAGE_INTEREST,
        )


if __name__ == "__main__":
    unittest.main()
