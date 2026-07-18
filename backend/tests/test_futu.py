import math
import unittest

from stock_strategy.broker import Broker
from stock_strategy.context import ExecutionContext, activate_context
from stock_strategy.data import generate_sample_bars
from stock_strategy.futu import (
    BarDataType,
    BarType,
    Contract,
    CustomType,
    THType,
    UnsupportedAPIError,
    bar_close,
    bar_custom,
    ma,
    rsi,
)


class FutuApiTest(unittest.TestCase):
    def setUp(self):
        self.bars = generate_sample_bars(80)
        self.symbol = Contract("US.TEST")
        self.broker = Broker(10_000, 0, 0, 0, False)
        self.context = ExecutionContext(self.bars, self.symbol, self.broker, current_index=70)

    def test_select_uses_current_and_previous_bar(self):
        with activate_context(self.context):
            self.assertEqual(bar_close(self.symbol, BarType.K_DAY, select=1), self.bars[70].close)
            self.assertEqual(bar_close(self.symbol, BarType.K_DAY, select=2), self.bars[69].close)

    def test_indicators_return_finite_values_after_warmup(self):
        with activate_context(self.context):
            self.assertTrue(
                math.isfinite(
                    ma(self.symbol, period=20, bar_type=BarType.K_DAY, select=1)
                )
            )
            value = rsi(self.symbol, period=14, bar_type=BarType.K_DAY, select=1)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_period_and_us_session_mismatch_fail_instead_of_resampling(self):
        with activate_context(self.context):
            with self.assertRaisesRegex(UnsupportedAPIError, "resampling is not implemented"):
                bar_close(self.symbol, BarType.K_5M, select=1)
            with self.assertRaisesRegex(UnsupportedAPIError, "session filtering is not implemented"):
                bar_close(
                    self.symbol,
                    BarType.K_DAY,
                    select=1,
                    session_type=THType.RTH,
                )

    def test_non_qfq_series_call_is_rejected(self):
        self.context.autype = "HFQ"
        with activate_context(self.context):
            with self.assertRaisesRegex(UnsupportedAPIError, "require QFQ"):
                bar_close(self.symbol, BarType.K_DAY, select=1)

    def test_bar_custom_never_falls_back_to_close_for_unsupported_data(self):
        with activate_context(self.context):
            with self.assertRaisesRegex(UnsupportedAPIError, "TURNOVER"):
                bar_custom(
                    self.symbol,
                    data_type=BarDataType.TURNOVER,
                    custom_num=2,
                    custom_type=CustomType.K_DAY,
                    select=1,
                )
            with self.assertRaisesRegex(UnsupportedAPIError, "data type"):
                bar_custom(
                    self.symbol,
                    data_type="NOT_A_FIELD",
                    custom_num=2,
                    custom_type="K_DAY",
                    select=1,
                )


if __name__ == "__main__":
    unittest.main()
