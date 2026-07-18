import unittest

from stock_strategy.broker import Broker
from stock_strategy.models import Bar, BarType, Contract, OrderSide, TimeInForce


class BrokerTest(unittest.TestCase):
    def test_market_order_fills_on_next_bar_open(self):
        broker = Broker(10_000, commission_bps=0, min_commission=0, slippage_bps=0, allow_short=False)
        symbol = Contract("US.TEST")
        first = Bar("2025-01-02", 100, 102, 99, 101, 1_000)
        second = Bar("2025-01-03", 105, 108, 104, 107, 1_000)

        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=10,
            order_type="MARKET",
            current_index=0,
            current_date=first.date,
        )
        broker.process_bar(first, 0)
        self.assertEqual(broker.position.quantity, 0)

        broker.process_bar(second, 1)
        self.assertEqual(broker.position.quantity, 10)
        self.assertEqual(broker.position.average_price, 105)
        self.assertEqual(broker.cash, 8_950)

    def test_stop_order_treats_serialization_noise_as_the_same_price(self):
        broker = Broker(
            100_000,
            commission_bps=0,
            min_commission=0,
            slippage_bps=0,
            allow_short=False,
            bar_type=BarType.K_1M,
        )
        symbol = Contract("HK.09988")
        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=100,
            order_type="STOP",
            current_index=0,
            current_date="2024-01-19 11:05:00",
            stop_price=61.500530000000005,
            current_price=61.40053,
        )

        broker.process_bar(
            Bar(
                "2024-01-19 11:06:00",
                61.40053,
                61.500529999,
                61.40053,
                61.500529999,
                1_000,
            ),
            1,
        )

        self.assertEqual(broker.position.quantity, 100)
        self.assertEqual(len(broker.pending_orders), 0)

    def test_sell_closes_position_and_records_net_trade(self):
        broker = Broker(10_000, commission_bps=0, min_commission=0, slippage_bps=0, allow_short=False)
        symbol = Contract("US.TEST")
        bars = [
            Bar("2025-01-02", 100, 102, 99, 101, 1_000),
            Bar("2025-01-03", 100, 105, 99, 104, 1_000),
            Bar("2025-01-06", 110, 112, 109, 111, 1_000),
        ]
        broker.submit(symbol=symbol, side=OrderSide.BUY, quantity=10, order_type="MARKET", current_index=0, current_date=bars[0].date)
        broker.process_bar(bars[1], 1)
        broker.submit(symbol=symbol, side=OrderSide.SELL, quantity=10, order_type="MARKET", current_index=1, current_date=bars[1].date)
        broker.process_bar(bars[2], 2)

        self.assertEqual(broker.position.quantity, 0)
        self.assertEqual(len(broker.trades), 1)
        self.assertEqual(broker.trades[0].net_pnl, 100)
        self.assertEqual(broker.cash, 10_100)

    def test_day_limit_order_remains_active_within_first_eligible_trading_day(self):
        broker = Broker(10_000, commission_bps=0, min_commission=0, slippage_bps=0, allow_short=False, bar_type=BarType.K_1M)
        symbol = Contract("US.TEST")
        signal_bar = Bar("2025-01-02 09:30:00", 100, 101, 100, 101, 1_000)
        first_eligible = Bar("2025-01-02 09:31:00", 103, 104, 101, 102, 1_000)
        later_same_day = Bar("2025-01-02 09:32:00", 101, 102, 98, 100, 1_000)
        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=10,
            order_type="LIMIT",
            current_index=0,
            current_date=signal_bar.date,
            time_in_force=TimeInForce.DAY,
            limit_price=99,
        )
        broker.process_bar(signal_bar, 0)
        self.assertEqual(broker.position.quantity, 0)
        broker.process_bar(first_eligible, 1)
        self.assertEqual(len(broker.pending_orders), 1)
        broker.process_bar(later_same_day, 2)
        self.assertEqual(broker.position.average_price, 99)

    def test_day_limit_order_expires_before_checking_next_trading_day(self):
        broker = Broker(10_000, commission_bps=0, min_commission=0, slippage_bps=0, allow_short=False, bar_type=BarType.K_1M)
        symbol = Contract("US.TEST")
        bars = [
            Bar("2025-01-02 09:30:00", 100, 101, 100, 101, 1_000),
            Bar("2025-01-02 09:31:00", 103, 104, 101, 102, 1_000),
            Bar("2025-01-03 09:30:00", 98, 100, 97, 99, 1_000),
        ]
        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=10,
            order_type="LIMIT",
            current_index=0,
            current_date=bars[0].date,
            time_in_force=TimeInForce.DAY,
            limit_price=99,
        )
        broker.process_bar(bars[1], 1)
        broker.process_bar(bars[2], 2)

        self.assertEqual(broker.position.quantity, 0)
        self.assertEqual(len(broker.pending_orders), 0)
        self.assertIn("trading-day boundary", broker.logs[-1].message)

    def test_intraday_day_order_submitted_at_close_does_not_roll_overnight(self):
        broker = Broker(
            10_000,
            commission_bps=0,
            min_commission=0,
            slippage_bps=0,
            allow_short=False,
            bar_type=BarType.K_1M,
        )
        symbol = Contract("US.TEST")
        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=10,
            order_type="MARKET",
            current_index=0,
            current_date="2025-01-02 15:59:00",
            time_in_force=TimeInForce.DAY,
            current_price=100,
        )
        broker.process_bar(
            Bar("2025-01-03 09:30:00", 100, 101, 99, 100, 1_000),
            1,
        )

        self.assertEqual(broker.position.quantity, 0)
        self.assertEqual(len(broker.pending_orders), 0)
        self.assertIn("trading-day boundary", broker.logs[-1].message)

    def test_pending_buys_reserve_cash(self):
        broker = Broker(10_000, commission_bps=0, min_commission=0, slippage_bps=0, allow_short=False)
        symbol = Contract("US.TEST")
        broker.submit(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=60,
            order_type="LIMIT",
            current_index=0,
            current_date="2025-01-02 09:30:00",
            limit_price=100,
            current_price=100,
        )
        self.assertEqual(broker.max_cash_buy_quantity(100), 40)
        with self.assertRaisesRegex(ValueError, "pending buy orders"):
            broker.submit(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=50,
                order_type="LIMIT",
                current_index=0,
                current_date="2025-01-02 09:30:00",
                limit_price=100,
                current_price=100,
            )

    def test_pending_sells_freeze_available_position(self):
        broker = Broker(10_000, commission_bps=0, min_commission=0, slippage_bps=0, allow_short=False)
        symbol = Contract("US.TEST")
        broker.position.quantity = 10
        broker.position.average_price = 100
        broker.submit(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=6,
            order_type="LIMIT",
            current_index=0,
            current_date="2025-01-02 09:30:00",
            limit_price=110,
        )
        self.assertEqual(broker.max_sell_quantity(), 4)
        with self.assertRaisesRegex(ValueError, "pending sell orders"):
            broker.submit(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=5,
                order_type="LIMIT",
                current_index=0,
                current_date="2025-01-02 09:30:00",
                limit_price=110,
            )

    def test_modify_order_revalidates_reserved_cash(self):
        broker = Broker(
            10_000,
            commission_bps=0,
            min_commission=0,
            slippage_bps=0,
            allow_short=False,
        )
        order_id = broker.submit(
            symbol=Contract("US.TEST"),
            side=OrderSide.BUY,
            quantity=60,
            order_type="LIMIT",
            current_index=0,
            current_date="2025-01-02 09:30:00",
            limit_price=100,
        )
        with self.assertRaisesRegex(ValueError, "exceeds cash available"):
            broker.modify_order(
                order_id,
                "2025-01-02 09:30:00",
                quantity=101,
            )
        broker.modify_order(
            order_id,
            "2025-01-02 09:30:00",
            quantity=80,
        )
        self.assertEqual(broker.reserved_buy_cash, 8_000)


if __name__ == "__main__":
    unittest.main()
