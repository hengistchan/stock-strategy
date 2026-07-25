import math
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from stock_strategy.broker import Broker
from stock_strategy.models import Bar, Contract, OrderSide, OrderStatus

prices = st.floats(
    min_value=1,
    max_value=1_000,
    allow_nan=False,
    allow_infinity=False,
)
quantities = st.integers(min_value=1, max_value=100)


def broker_with_no_costs(initial_cash=1_000_000):
    return Broker(
        initial_cash,
        commission_bps=0,
        min_commission=0,
        slippage_bps=0,
        allow_short=False,
    )


class BrokerPropertyTest(unittest.TestCase):
    @settings(max_examples=100, deadline=None)
    @given(
        st.lists(
            st.tuples(
                st.sampled_from(("buy", "sell", "limit_buy", "cancel")),
                prices,
                quantities,
            ),
            min_size=1,
            max_size=40,
        )
    )
    def test_arbitrary_operation_sequences_preserve_ledger_invariants(
        self,
        operations,
    ):
        broker = broker_with_no_costs()
        symbol = Contract("US.TEST")
        index = 0
        mark_price = 100.0

        for action, price, requested_quantity in operations:
            index += 1
            mark_price = price
            bar = Bar(
                f"2026-01-{(index % 27) + 1:02d}",
                price,
                price * 1.01,
                price * 0.99,
                price,
                100_000,
            )
            broker.process_bar(bar, index)
            if action == "cancel":
                broker.cancel_all(bar.date)
            elif action in {"buy", "limit_buy"}:
                quantity = min(
                    requested_quantity,
                    broker.max_cash_buy_quantity(price),
                )
                if quantity:
                    broker.submit(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        order_type=("LIMIT" if action == "limit_buy" else "MARKET"),
                        current_index=index,
                        current_date=bar.date,
                        current_price=price,
                        limit_price=price if action == "limit_buy" else None,
                    )
            elif broker.max_sell_quantity() > 0:
                broker.submit(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=min(
                        requested_quantity,
                        broker.max_sell_quantity(),
                    ),
                    order_type="MARKET",
                    current_index=index,
                    current_date=bar.date,
                    current_price=price,
                )

            self.assertGreaterEqual(broker.position.quantity, -1e-9)
            self.assertGreaterEqual(broker.cash, -1e-7)
            self.assertGreaterEqual(broker.available_cash, -1e-9)
            self.assertLessEqual(broker.reserved_buy_cash, broker.cash + 1e-7)
            self.assertTrue(math.isfinite(broker.equity(mark_price)))
            self.assertTrue(math.isfinite(broker.cash))
            self.assertTrue(math.isfinite(broker.position.quantity))
            self.assertGreaterEqual(broker.total_fees, 0)
            self.assertAlmostEqual(
                broker.total_fees,
                sum(fill.fee for fill in broker.fills),
                places=7,
            )
            self.assertAlmostEqual(
                broker.equity(mark_price),
                broker.cash + broker.position.quantity * mark_price,
                places=7,
            )
            for fill in broker.fills:
                order = broker.get_order(fill.order_id)
                self.assertLess(order.submitted_index, index)
                if order.order_type == "LIMIT":
                    if order.side in (OrderSide.BUY, OrderSide.BUY_BACK):
                        self.assertLessEqual(
                            fill.price,
                            order.limit_price + 1e-8,
                        )
                    else:
                        self.assertGreaterEqual(
                            fill.price,
                            order.limit_price - 1e-8,
                        )

    @settings(max_examples=100, deadline=None)
    @given(entry=prices, exit=prices, quantity=quantities)
    def test_round_trip_realized_pnl_matches_cash_change(
        self,
        entry,
        exit,
        quantity,
    ):
        initial_cash = entry * quantity + 10_000
        broker = broker_with_no_costs(initial_cash)
        symbol = Contract("US.TEST")
        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type="MARKET",
            current_index=0,
            current_date="2026-01-02",
            current_price=entry,
        )
        broker.process_bar(
            Bar("2026-01-03", entry, entry, entry, entry, 10_000),
            1,
        )
        broker.submit(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type="MARKET",
            current_index=1,
            current_date="2026-01-03",
            current_price=entry,
        )
        broker.process_bar(
            Bar("2026-01-04", exit, exit, exit, exit, 10_000),
            2,
        )

        expected = (exit - entry) * quantity
        self.assertAlmostEqual(broker.position.quantity, 0, places=7)
        self.assertAlmostEqual(broker.cash - initial_cash, expected, places=6)
        self.assertAlmostEqual(broker.trades[0].net_pnl, expected, places=6)

    @settings(max_examples=100, deadline=None)
    @given(limit=prices, quantity=quantities)
    def test_cancelling_buy_releases_all_reserved_cash(self, limit, quantity):
        broker = broker_with_no_costs()
        order_id = broker.submit(
            symbol=Contract("US.TEST"),
            side=OrderSide.BUY,
            quantity=quantity,
            order_type="LIMIT",
            current_index=0,
            current_date="2026-01-02",
            current_price=limit,
            limit_price=limit,
        )
        self.assertGreater(broker.reserved_buy_cash, 0)

        broker.cancel_order(order_id, "2026-01-02")

        self.assertEqual(broker.reserved_buy_cash, 0)
        self.assertEqual(broker.available_cash, broker.cash)
        self.assertEqual(
            broker.get_order(order_id).status,
            OrderStatus.CANCELLED_ALL,
        )


if __name__ == "__main__":
    unittest.main()
