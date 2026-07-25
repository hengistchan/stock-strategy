import unittest
from pathlib import Path

from stock_strategy.backtest_command import build_backtest_command


class BacktestCommandTest(unittest.TestCase):
    def test_serializes_legacy_defaults_flags_and_sorted_parameters(self):
        job = {
            "request": {
                "symbol": "US.AAPL",
                "start": "2025-01-01",
                "end": "2025-12-31",
                "ktype": "K_5M",
                "autype": "QFQ",
                "initial_cash": 100_000,
                "commission_bps": 3,
                "min_commission": 1,
                "slippage_bps": 5,
                "warmup_bars": 30,
                "allow_short": True,
                "liquidate_on_end": True,
                "refresh_cache": True,
                "parameters": {"z": True, "a": 2},
            }
        }

        command = build_backtest_command(
            job,
            strategy_path=Path("/run/strategy.py"),
            cache_path=Path("/data/cache.csv"),
            output_path=Path("/run/output"),
            opend_host="127.0.0.1",
            opend_port=11111,
        )

        self.assertEqual(command[1:4], ["-P", "-m", "stock_strategy"])
        self.assertEqual(command[command.index("--session") + 1], "ALL")
        self.assertLess(command.index("a=2"), command.index("z=true"))
        self.assertIn("--allow-short", command)
        self.assertIn("--liquidate-on-end", command)
        self.assertIn("--refresh-opend-cache", command)


if __name__ == "__main__":
    unittest.main()
