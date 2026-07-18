import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from stock_strategy.cli import main
from stock_strategy.opend import OpenDHistory


class CliTest(unittest.TestCase):
    def test_cli_infers_symbol_from_opend_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "opend.csv"
            strategy_path = root / "strategy.py"
            output_path = root / "runs"
            start = datetime(2025, 1, 2, 9, 30)
            with data_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["code", "name", "time_key", "open", "close", "high", "low", "volume", "turnover"],
                )
                writer.writeheader()
                for index in range(80):
                    timestamp = start + timedelta(minutes=index)
                    writer.writerow(
                        {
                            "code": "US.MSFT",
                            "name": "Microsoft",
                            "time_key": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": 100 + index * 0.1,
                            "close": 100.05 + index * 0.1,
                            "high": 100.2 + index * 0.1,
                            "low": 99.9 + index * 0.1,
                            "volume": 1_000 + index,
                            "turnover": 100_000 + index,
                        }
                    )
            strategy_path.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.sent = False

    def handle_data(self):
        if not self.sent:
            place_market(self.symbol, qty=10, side=OrderSide.BUY)
            self.sent = True
""",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                return_code = main(
                    [
                        "--strategy",
                        str(strategy_path),
                        "--data",
                        str(data_path),
                        "--warmup-bars",
                        "0",
                        "--output",
                        str(output_path),
                        "--no-chart",
                    ]
                )
            summary_path = next(output_path.glob("*/summary.json"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(return_code, 0)
        self.assertEqual(summary["symbol"], "US.MSFT")
        self.assertEqual(summary["period"]["bars"], 80)
        self.assertEqual(summary["period"]["start"], "2025-01-02 09:30:00")
        self.assertEqual(summary["settings"]["bar_type"], "K_DAY")
        self.assertEqual(summary["settings"]["session_type"], "ALL")
        self.assertEqual(summary["settings"]["autype"], "QFQ")
        self.assertFalse(summary["settings"]["liquidate_on_end"])

    def test_cli_fetches_opend_history_and_writes_cache(self):
        records = []
        start = datetime(2025, 1, 2, 9, 30)
        for index in range(80):
            records.append(
                {
                    "code": "US.AAPL",
                    "time_key": (start + timedelta(minutes=index)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "open": 100 + index * 0.1,
                    "close": 100.05 + index * 0.1,
                    "high": 100.2 + index * 0.1,
                    "low": 99.9 + index * 0.1,
                    "volume": 1_000 + index,
                }
            )
        history = OpenDHistory(
            records=records,
            fieldnames=tuple(records[0]),
            pages=2,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy_path = root / "strategy.py"
            strategy_path.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.sent = False

    def handle_data(self):
        if not self.sent:
            place_market(self.symbol, qty=10, side=OrderSide.BUY)
            self.sent = True
""",
                encoding="utf-8",
            )
            cache_path = root / "data" / "history.csv"
            output_path = root / "runs"
            with patch(
                "stock_strategy.cli.fetch_history_kline", return_value=history
            ) as fetch_history:
                with redirect_stdout(io.StringIO()):
                    return_code = main(
                        [
                            "--strategy",
                            str(strategy_path),
                            "--opend",
                            "--symbol",
                            "US.AAPL",
                            "--start",
                            "2025-01-01",
                            "--end",
                            "2025-01-31",
                            "--warmup-bars",
                            "0",
                            "--ktype",
                            "K_5M",
                            "--autype",
                            "HFQ",
                            "--session",
                            "RTH",
                            "--liquidate-on-end",
                            "--opend-cache",
                            str(cache_path),
                            "--output",
                            str(output_path),
                            "--no-chart",
                        ]
                    )
            fetch_history.assert_called_once_with(
                "US.AAPL",
                start="2025-01-01",
                end="2025-01-31",
                ktype="K_5M",
                autype="hfq",
                session="RTH",
                host="127.0.0.1",
                port=11111,
            )
            summary_path = next(output_path.glob("*/summary.json"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            cache_exists = cache_path.exists()
        self.assertEqual(return_code, 0)
        self.assertTrue(cache_exists)
        self.assertEqual(summary["settings"]["data_source_format"], "opend")
        self.assertEqual(summary["settings"]["opend"]["pages"], 2)
        self.assertEqual(summary["settings"]["bar_type"], "K_5M")
        self.assertEqual(summary["settings"]["session_type"], "RTH")
        self.assertEqual(summary["settings"]["autype"], "HFQ")
        self.assertTrue(summary["settings"]["liquidate_on_end"])
        self.assertEqual(summary["settings"]["opend"]["session"], "RTH")
        self.assertFalse(summary["settings"]["opend"]["extended_time"])


if __name__ == "__main__":
    unittest.main()
