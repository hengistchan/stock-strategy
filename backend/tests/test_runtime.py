import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from stock_strategy.data import generate_sample_bars
from stock_strategy.models import Bar, BarType, THType
from stock_strategy.reporting import write_artifacts
from stock_strategy.runtime import ENGINE_CONTRACT_VERSION, BacktestConfig, run_backtest


class RuntimeTest(unittest.TestCase):
    def test_example_strategy_runs_end_to_end(self):
        strategy = Path(__file__).parents[2] / "examples" / "ma_cross.py"
        result = run_backtest(
            BacktestConfig(strategy_path=strategy, warmup_bars=60),
            generate_sample_bars(400),
        )
        self.assertEqual(result.bar_count, 400)
        self.assertGreater(result.metrics.final_equity, 0)
        self.assertGreaterEqual(result.metrics.total_trades, 1)
        self.assertEqual(len(result.equity_curve), 400)
        self.assertEqual(
            result.settings["engine_contract"]["version"],
            ENGINE_CONTRACT_VERSION,
        )

    def test_example_strategy_uses_the_selected_opend_interval_and_session(self):
        strategy = Path(__file__).parents[2] / "examples" / "ma_cross.py"
        result = run_backtest(
            BacktestConfig(
                strategy_path=strategy,
                bar_type=BarType.K_5M,
                session_type=THType.RTH,
                warmup_bars=60,
            ),
            generate_sample_bars(400),
        )

        self.assertEqual(result.settings["bar_type"], BarType.K_5M)
        self.assertEqual(result.settings["session_type"], THType.RTH)

    def test_default_lifecycle_has_no_project_specific_warmup(self):
        self.assertEqual(BacktestConfig(strategy_path="strategy.py").warmup_bars, 0)

    def test_explicit_warmup_delays_first_strategy_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            strategy = Path(directory) / "strategy.py"
            strategy.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.sent = False

    def handle_data(self):
        if not self.sent:
            place_market(self.symbol, qty=1, side=OrderSide.BUY)
            self.sent = True
""",
                encoding="utf-8",
            )
            bars = generate_sample_bars(20)
            result = run_backtest(
                BacktestConfig(
                    strategy_path=strategy,
                    warmup_bars=5,
                    liquidate_on_end=True,
                ),
                bars,
            )

        self.assertEqual(result.trades[0].entry_date, bars[6].date)

    def test_injected_futu_names_work_without_import(self):
        with tempfile.TemporaryDirectory() as directory:
            strategy = Path(directory) / "strategy.py"
            strategy.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.sent = False

    def handle_data(self):
        if not self.sent:
            place_market(self.symbol, qty=1, side=OrderSide.BUY)
            self.sent = True
""",
                encoding="utf-8",
            )
            bars = generate_sample_bars(35)
            result = run_backtest(
                BacktestConfig(
                    strategy_path=strategy,
                    warmup_bars=0,
                    liquidate_on_end=True,
                ),
                bars,
            )
        self.assertEqual(result.trades[0].entry_date, bars[1].date)
        self.assertEqual(result.trades[0].exit_reason, "end-of-test")

    def test_device_time_uses_historical_bar_and_converts_us_dst(self):
        with tempfile.TemporaryDirectory() as directory:
            strategy = Path(directory) / "strategy.py"
            strategy.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.sent = False

    def handle_data(self):
        now = device_time(TimeZone.UTC_PLUS_8)
        expected_hour = 13 if now.month == 1 else 12
        if now.hour != expected_hour:
            raise RuntimeError("unexpected converted hour")
        if now.hour == expected_hour and not self.sent:
            place_market(self.symbol, qty=1, side=OrderSide.BUY)
            self.sent = True
""",
                encoding="utf-8",
            )
            bars = [
                Bar("2024-01-02 00:00:00", 100, 101, 99, 100, 1),
                Bar("2024-01-03 00:00:00", 100, 101, 99, 100, 1),
                Bar("2024-07-02 00:00:00", 100, 101, 99, 100, 1),
                Bar("2024-07-03 00:00:00", 100, 101, 99, 100, 1),
            ]
            result = run_backtest(
                BacktestConfig(strategy_path=strategy, liquidate_on_end=True), bars
            )

        self.assertEqual(result.trades[0].entry_date, "2024-01-03 00:00:00")

    def test_open_position_is_preserved_and_marked_to_market_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            strategy = Path(directory) / "strategy.py"
            strategy.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.sent = False

    def handle_data(self):
        if not self.sent:
            place_market(self.symbol, qty=1, side=OrderSide.BUY)
            self.sent = True
""",
                encoding="utf-8",
            )
            bars = generate_sample_bars(10)
            result = run_backtest(
                BacktestConfig(strategy_path=strategy, warmup_bars=0), bars
            )

        self.assertEqual(result.metrics.total_trades, 0)
        self.assertEqual(result.settings["ending_position"]["quantity"], 1)
        self.assertEqual(result.settings["ending_position"]["mark_price"], bars[-1].close)
        self.assertNotEqual(result.settings["ending_position"]["side"], "NONE")

    def test_declared_strategy_parameters_are_injected_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            strategy = Path(directory) / "strategy.py"
            strategy.write_text(
                '''
STRATEGY_PARAMETERS = {
    "quantity": {"type": "int", "default": 1, "min": 1, "max": 10}
}

class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.quantity = strategy_parameter("quantity")
        self.sent = False

    def handle_data(self):
        if not self.sent:
            place_market(self.symbol, qty=self.quantity, side=OrderSide.BUY)
            self.sent = True
''',
                encoding="utf-8",
            )
            result = run_backtest(
                BacktestConfig(
                    strategy_path=strategy,
                    strategy_parameters={"quantity": 4},
                ),
                generate_sample_bars(30),
            )

        self.assertEqual(result.settings["strategy_parameters"], {"quantity": 4})
        self.assertEqual(result.settings["ending_position"]["quantity"], 4)

    def test_artifacts_include_valid_svg_and_csv(self):
        strategy = Path(__file__).parents[2] / "examples" / "ma_cross.py"
        result = run_backtest(
            BacktestConfig(strategy_path=strategy, warmup_bars=60),
            generate_sample_bars(240),
        )
        with tempfile.TemporaryDirectory() as directory:
            artifacts = write_artifacts(result, directory)
            self.assertTrue(Path(artifacts.summary_path).exists())
            self.assertTrue(Path(artifacts.trades_path).exists())
            self.assertTrue(Path(artifacts.equity_path).exists())
            ElementTree.parse(artifacts.chart_path)


if __name__ == "__main__":
    unittest.main()
