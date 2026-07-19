import csv
import tempfile
import unittest
from pathlib import Path

from stock_strategy.opend import (
    OpenDHistory,
    OpenDRequestError,
    OpenDSymbol,
    OpenDSymbolDirectory,
    fetch_stock_directory,
    fetch_history_kline,
    fetch_stock_metadata,
    match_stock_symbols,
    write_history_csv,
)


class FakeFrame:
    def __init__(self, records):
        self.records = records
        self.columns = list(records[0]) if records else []

    def to_dict(self, orientation):
        if orientation != "records":
            raise AssertionError("unexpected orientation")
        return self.records


class FakeContext:
    def __init__(self, responses):
        self.responses = list(responses)
        self.page_keys = []
        self.requests = []
        self.closed = False

    def request_history_kline(self, symbol, **kwargs):
        self.page_keys.append(kwargs["page_req_key"])
        self.requests.append({"symbol": symbol, **kwargs})
        return self.responses.pop(0)

    def close(self):
        self.closed = True


class OpenDTest(unittest.TestCase):
    def test_stock_directory_reads_us_hk_stocks_and_closes(self):
        class DirectoryContext:
            closed = False

            def __init__(self):
                self.requests = []

            def get_stock_basicinfo(self, market, stock_type):
                self.requests.append((market, stock_type))
                rows = {
                    "US": [
                        {"code": "US.AAPL", "name": "Apple", "delisting": False},
                        {"code": "US.OLD", "name": "Old Inc", "delisting": True},
                    ],
                    "HK": [
                        {"code": "HK.00700", "name": "腾讯控股", "delisting": False}
                    ],
                }
                return 0, FakeFrame(rows[market])

            def close(self):
                self.closed = True

        context = DirectoryContext()
        symbols = fetch_stock_directory(context_factory=lambda **kwargs: context)

        self.assertEqual(context.requests, [("US", "STOCK"), ("HK", "STOCK")])
        self.assertEqual([item.code for item in symbols], ["HK.00700", "US.AAPL"])
        self.assertTrue(context.closed)

    def test_symbol_matching_handles_code_name_and_typo_queries(self):
        symbols = [
            OpenDSymbol("US.AAPL", "Apple", "US"),
            OpenDSymbol("US.AAP", "Advance Auto Parts", "US"),
            OpenDSymbol("US.TSLA", "特斯拉", "US"),
            OpenDSymbol("US.TEL", "泰科电子", "US"),
            OpenDSymbol("HK.00700", "腾讯控股", "HK"),
        ]

        self.assertEqual(match_stock_symbols(symbols, "AAPL")[0].code, "US.AAPL")
        self.assertEqual(match_stock_symbols(symbols, "apple")[0].code, "US.AAPL")
        self.assertEqual(match_stock_symbols(symbols, "腾讯")[0].code, "HK.00700")
        self.assertEqual(match_stock_symbols(symbols, "appl")[0].code, "US.AAPL")
        self.assertEqual(match_stock_symbols(symbols, "tesl")[0].code, "US.TSLA")

    def test_symbol_directory_reuses_the_cached_opend_inventory(self):
        calls = []
        directory = OpenDSymbolDirectory(
            loader=lambda: calls.append(True)
            or [OpenDSymbol("US.AAPL", "Apple", "US")],
            ttl_seconds=60,
        )

        self.assertEqual(directory.search("aapl")[0]["name"], "Apple")
        self.assertEqual(directory.search("apple")[0]["code"], "US.AAPL")
        self.assertEqual(directory.resolve(["us.aapl", "US.MISSING"])[0]["name"], "Apple")
        self.assertEqual(len(calls), 1)

    def test_fetch_stock_metadata_reads_snapshot_and_closes(self):
        class SnapshotContext:
            closed = False

            def get_market_snapshot(self, symbols):
                self.symbols = symbols
                return 0, FakeFrame(
                    [
                        {
                            "code": "US.AAPL",
                            "name": "Apple",
                            "lot_size": 1,
                            "price_spread": 0.01,
                            "suspension": False,
                        }
                    ]
                )

            def close(self):
                self.closed = True

        context = SnapshotContext()
        metadata = fetch_stock_metadata(
            "US.AAPL", context_factory=lambda **kwargs: context
        )
        self.assertEqual(context.symbols, ["US.AAPL"])
        self.assertEqual(metadata["lot_size"], 1)
        self.assertTrue(context.closed)

    def test_fetch_history_paginates_and_closes(self):
        first = [{"code": "US.AAPL", "time_key": "2025-01-02 00:00:00"}]
        second = [{"code": "US.AAPL", "time_key": "2025-01-03 00:00:00"}]
        context = FakeContext(
            [
                (0, FakeFrame(first), b"next-page"),
                (0, FakeFrame(second), None),
            ]
        )
        history = fetch_history_kline(
            "US.AAPL",
            start="2025-01-01",
            end="2025-01-31",
            context_factory=lambda **kwargs: context,
        )
        self.assertEqual(history.records, first + second)
        self.assertEqual(history.pages, 2)
        self.assertEqual(context.page_keys, [None, b"next-page"])
        self.assertEqual(context.requests[0]["session"], "ALL")
        self.assertTrue(context.requests[0]["extended_time"])
        self.assertTrue(context.closed)

    def test_fetch_history_uses_regular_session_without_extended_time(self):
        records = [{"code": "US.AAPL", "time_key": "2025-01-02 09:30:00"}]
        context = FakeContext([(0, FakeFrame(records), None)])

        fetch_history_kline(
            "US.AAPL",
            start="2025-01-01",
            end="2025-01-31",
            session="rth",
            context_factory=lambda **kwargs: context,
        )

        self.assertEqual(context.requests[0]["session"], "RTH")
        self.assertFalse(context.requests[0]["extended_time"])

    def test_fetch_history_uses_extended_time_for_eth_session(self):
        records = [{"code": "US.AAPL", "time_key": "2025-01-02 08:00:00"}]
        context = FakeContext([(0, FakeFrame(records), None)])

        fetch_history_kline(
            "US.AAPL",
            start="2025-01-01",
            end="2025-01-31",
            session="ETH",
            context_factory=lambda **kwargs: context,
        )

        self.assertEqual(context.requests[0]["session"], "ETH")
        self.assertTrue(context.requests[0]["extended_time"])

    def test_fetch_history_rejects_unknown_session_before_opening_context(self):
        with self.assertRaisesRegex(ValueError, "unsupported OpenD history session"):
            fetch_history_kline(
                "US.AAPL",
                start="2025-01-01",
                end="2025-01-31",
                session="OVERNIGHT",
                context_factory=lambda **kwargs: self.fail("context should not be opened"),
            )

    def test_fetch_history_closes_after_request_error(self):
        context = FakeContext([(1, "permission denied", None)])
        with self.assertRaisesRegex(OpenDRequestError, "permission denied"):
            fetch_history_kline(
                "US.AAPL",
                start="2025-01-01",
                end="2025-01-31",
                context_factory=lambda **kwargs: context,
            )
        self.assertTrue(context.closed)

    def test_write_history_csv_preserves_fields(self):
        history = OpenDHistory(
            records=[{"code": "US.AAPL", "time_key": "2025-01-02", "close": 100}],
            fieldnames=("code", "time_key", "close"),
            pages=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_history_csv(history, Path(directory) / "nested" / "history.csv")
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["code"], "US.AAPL")
        self.assertEqual(rows[0]["close"], "100")


if __name__ == "__main__":
    unittest.main()
