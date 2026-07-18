import math
import unittest

from stock_strategy.broker import Broker
from stock_strategy.context import ExecutionContext, activate_context
from stock_strategy.data import generate_sample_bars
from stock_strategy.futu import (
    BarType,
    APIException,
    Contract,
    Currency,
    DataUnavailableError,
    ErrCode,
    OrderSide,
    OrderStatus,
    THType,
    TimeZone,
    boll_upper,
    bar_turnover,
    cancel_order_by_orderid,
    get_MyLang_indicator,
    get_Python_indicator,
    get_orderid_by_groupid,
    lot_size,
    min_tick,
    net_asset,
    order_filled_avg_price,
    order_filled_qty,
    order_qty,
    order_status,
    order_create_time,
    place_market,
    place_stop,
    register_indicator,
    register_indicator_Python,
    request_executionid,
    reverse_positions,
)


class StockManualCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.bars = generate_sample_bars(100)
        self.symbol = Contract("US.TEST")
        self.broker = Broker(100_000, 3, 1, 5, False, bar_type=BarType.K_DAY)
        self.context = ExecutionContext(
            self.bars,
            self.symbol,
            self.broker,
            current_index=70,
            bar_type=BarType.K_DAY,
            session_type=THType.ALL,
            market_metadata={"lot_size": 1, "price_spread": 0.01},
        )

    def test_stock_metadata_account_and_order_queries_share_simulated_state(self):
        with activate_context(self.context):
            self.assertEqual(lot_size(self.symbol), 1)
            self.assertEqual(min_tick(self.symbol), 0.01)
            self.assertEqual(net_asset(Currency.USD), 100_000)

            order_id = place_market(self.symbol, 10, OrderSide.BUY)
            self.assertEqual(order_status(order_id), OrderStatus.SUBMITTED)
            self.assertEqual(order_qty(order_id), 10)
            self.assertEqual(order_filled_qty(order_id), 0)
            market_time = order_create_time(order_id)
            china_time = order_create_time(order_id, TimeZone.UTC_PLUS_8)
            self.assertIsNotNone(market_time.tzinfo)
            self.assertIsNotNone(china_time.tzinfo)
            self.assertNotEqual(market_time.utcoffset(), china_time.utcoffset())

            self.context.current_index = 71
            self.broker.process_bar(self.bars[71], 71)
            self.assertEqual(order_status(order_id), OrderStatus.FILLED_ALL)
            self.assertEqual(order_filled_qty(order_id), 10)
            self.assertGreater(order_filled_avg_price(order_id), 0)
            self.assertEqual(len(request_executionid(self.symbol)), 1)

            stop_id = place_stop(
                self.symbol,
                aux_price=self.bars[71].close * 0.9,
                qty=10,
                side=OrderSide.SELL,
            )
            cancel_order_by_orderid(stop_id)
            self.assertEqual(order_status(stop_id), OrderStatus.CANCELLED_ALL)

    def test_builtin_and_registered_stock_indicators_are_executable(self):
        with activate_context(self.context):
            self.assertTrue(
                math.isfinite(
                    boll_upper(self.symbol, period=20, bar_type=BarType.K_DAY, select=1)
                )
            )
            register_indicator(
                "MA",
                "MA1:MA(CLOSE,P1),COLORFF8D1E;MA2:MA(CLOSE,P2);",
                ["P1", "P2"],
            )
            mylang = get_MyLang_indicator(
                "MA",
                "MA1",
                self.symbol,
                {"P1": 5, "P2": 10},
                bar_type=BarType.K_DAY,
                select=1,
            )
            self.assertAlmostEqual(
                mylang,
                sum(bar.close for bar in self.bars[66:71]) / 5,
            )

            register_indicator_Python(
                "MA5",
                """
def moving(n=5):
    return close().sma(n)

if __name__ == "__main__":
    n = input_parameter("n", 5)
    output_parameter(MA5=moving(n))
""",
            )
            python_value = get_Python_indicator(
                "MA5",
                "MA5",
                self.symbol,
                {"n": 5},
                bar_type=BarType.K_DAY,
                select=1,
            )
            self.assertAlmostEqual(python_value, mylang)

    def test_manual_errors_expose_futu_error_codes(self):
        with activate_context(self.context):
            with self.assertRaises(APIException) as raised:
                min_tick(Contract("US.OTHER"))
            self.assertEqual(raised.exception.err_code, ErrCode.InvalidArgument)

            with self.assertRaises(DataUnavailableError) as unavailable:
                bar_turnover(self.symbol, bar_type=BarType.K_DAY, select=1)
            self.assertEqual(
                unavailable.exception.err_code, ErrCode.NoDataAvailable
            )

    def test_reverse_positions_closes_then_opens_the_opposite_stock_position(self):
        broker = Broker(
            100_000, 0, 0, 0, True, bar_type=BarType.K_DAY
        )
        context = ExecutionContext(
            self.bars,
            self.symbol,
            broker,
            current_index=70,
            bar_type=BarType.K_DAY,
            market_metadata={"lot_size": 1, "price_spread": 0.01},
        )
        with activate_context(context):
            place_market(self.symbol, 10, OrderSide.BUY)
            context.current_index = 71
            broker.process_bar(self.bars[71], 71)
            self.assertEqual(broker.position.quantity, 10)

            group_id = reverse_positions(self.symbol)
            self.assertIsNotNone(group_id)
            group = get_orderid_by_groupid(group_id)
            self.assertTrue(group["closing_orderid"].startswith("SIM-"))
            self.assertEqual(group["opening_orderid"], "")
            context.current_index = 72
            broker.process_bar(self.bars[72], 72)
            self.assertEqual(broker.position.quantity, 0)
            self.assertEqual(len(broker.pending_orders), 1)
            self.assertEqual(broker.pending_orders[0].side, OrderSide.SELL_SHORT)
            self.assertEqual(
                get_orderid_by_groupid(group_id)["opening_orderid"],
                broker.pending_orders[0].order_id,
            )

            context.current_index = 73
            broker.process_bar(self.bars[73], 73)
            self.assertEqual(broker.position.quantity, -10)


if __name__ == "__main__":
    unittest.main()
