import csv
import tempfile
import unittest
from pathlib import Path

from stock_strategy.data import (
    bars_from_opend_records,
    generate_sample_bars,
    load_bars,
    load_market_data,
)


class DataTest(unittest.TestCase):
    def test_sample_data_is_deterministic_and_valid(self):
        first = generate_sample_bars(40)
        second = generate_sample_bars(40)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 40)
        self.assertTrue(all(bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high for bar in first))

    def test_load_bars_accepts_chinese_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["日期", "开盘", "最高", "最低", "收盘", "成交量"])
                for index, bar in enumerate(generate_sample_bars(30)):
                    writer.writerow([bar.date, bar.open, bar.high, bar.low, bar.close, index + 1])
            bars = load_bars(path)
        self.assertEqual(len(bars), 30)
        self.assertEqual(bars[0].volume, 1)

    def test_load_bars_rejects_invalid_ohlc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("date,open,high,low,close\n2025-01-01,10,9,8,11\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid OHLC"):
                load_bars(path)

    def test_opend_csv_preserves_intraday_time_and_infers_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "opend.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["", "code", "name", "time_key", "open", "close", "high", "low", "volume", "turnover"])
                for index in range(30):
                    minute = 30 + index
                    writer.writerow([index, "US.AAPL", "Apple", f"2025-01-02 09:{minute:02d}:00", 100, 101, 102, 99, 1_000, 100_000])
            market_data = load_market_data(path)
        self.assertEqual(market_data.source_format, "opend")
        self.assertEqual(market_data.symbol, "US.AAPL")
        self.assertEqual(len(market_data.bars), 30)
        self.assertEqual(market_data.bars[0].date, "2025-01-02 09:30:00")
        self.assertEqual(market_data.bars[-1].date, "2025-01-02 09:59:00")

    def test_opend_records_require_symbol_for_multi_symbol_data(self):
        records = []
        for index in range(30):
            for symbol in ("US.AAPL", "US.MSFT"):
                records.append(
                    {
                        "code": symbol,
                        "time_key": f"2025-01-{index + 1:02d} 00:00:00",
                        "open": 100,
                        "close": 101,
                        "high": 102,
                        "low": 99,
                        "volume": 1_000,
                    }
                )
        with self.assertRaisesRegex(ValueError, "multiple symbols"):
            bars_from_opend_records(records)
        selected = bars_from_opend_records(records, symbol="US.MSFT")
        self.assertEqual(selected.symbol, "US.MSFT")
        self.assertEqual(len(selected.bars), 30)


if __name__ == "__main__":
    unittest.main()
