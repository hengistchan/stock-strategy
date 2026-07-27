from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone
from typing import Any

from stock_strategy.monitoring_market_data import (
    OpenDMonitoringDataSource,
)
from stock_strategy.opend import OpenDRequestError


class FakeFrame:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    def to_dict(self, orientation: str) -> list[dict[str, Any]]:
        if orientation != "records":
            raise AssertionError(orientation)
        return self.records


class FakeQuoteContext:
    def __init__(self, **_kwargs: Any) -> None:
        self.closed = False
        self.snapshot_calls: list[list[str]] = []
        self.subscribed: list[str] = []

    def get_market_snapshot(self, codes: list[str]):
        self.snapshot_calls.append(codes)
        records = []
        for code in codes:
            option = "C" in code.split(".", 1)[-1]
            records.append(
                {
                    "code": code,
                    "name": f"Name {code}",
                    "update_time": "2026-07-27 10:30:00",
                    "last_price": 105,
                    "prev_close_price": 100,
                    "open_price": 101,
                    "high_price": 106,
                    "low_price": 99,
                    "volume": 150,
                    "turnover": 15000,
                    "bid_price": 104,
                    "ask_price": 106,
                    "option_valid": option,
                    "option_type": "CALL" if option else "N/A",
                    "stock_owner": "US.AAPL" if option else "N/A",
                    "option_strike_price": 100 if option else math.nan,
                    "option_implied_volatility": 35.5 if option else math.nan,
                    "option_open_interest": 100 if option else math.nan,
                    "option_delta": 0.52 if option else math.nan,
                    "option_expiry_date_distance": 4 if option else math.nan,
                }
            )
        return 0, FakeFrame(records)

    def get_option_expiration_date(self, code: str):
        assert code == "US.AAPL"
        return 0, FakeFrame(
            [
                {
                    "strike_time": "2026-08-07",
                    "option_expiry_date_distance": 11,
                    "expiration_cycle": "WEEK",
                },
                {
                    "strike_time": "2026-07-31",
                    "option_expiry_date_distance": 4,
                    "expiration_cycle": "WEEK",
                },
            ]
        )

    def get_option_chain(self, code: str, **kwargs: Any):
        assert code == "US.AAPL"
        assert kwargs["start"] == "2026-07-31"
        assert kwargs["end"] == "2026-07-31"
        return 0, FakeFrame(
            [
                {
                    "code": "US.AAPL260731P100000",
                    "name": "AAPL P100",
                    "stock_owner": code,
                    "option_type": "PUT",
                    "strike_time": "2026-07-31",
                    "strike_price": 100,
                    "lot_size": 100,
                    "suspension": False,
                    "expiration_cycle": "WEEK",
                    "option_standard_type": "STANDARD",
                    "option_settlement_mode": "N/A",
                },
                {
                    "code": "US.AAPL260731C95000",
                    "name": "AAPL C95",
                    "stock_owner": code,
                    "option_type": "CALL",
                    "strike_time": "2026-07-31",
                    "strike_price": 95,
                    "lot_size": 100,
                    "suspension": False,
                    "expiration_cycle": "WEEK",
                    "option_standard_type": "STANDARD",
                    "option_settlement_mode": "N/A",
                },
            ]
        )

    def get_option_volatility(self, code: str):
        assert code == "US.AAPL260731C95000"
        return 0, FakeFrame(
            [
                {
                    "timestamp_str": "2026-07-27",
                    "implied_volatility": 35.5,
                    "history_volatility": 28.2,
                    "volatility_premium": 7.3,
                    "analysis": "elevated",
                }
            ]
        )

    def get_option_exercise_probability(self, code: str):
        assert code == "US.AAPL260731C95000"
        return 0, FakeFrame(
            [
                {
                    "timestamp_str": "2026-07-27",
                    "security_price": 105,
                    "strike_probability": math.nan,
                }
            ]
        )

    def query_subscription(self, is_all_conn: bool = True):
        assert is_all_conn
        return 0, {
            "total_used": len(self.subscribed),
            "own_used": len(self.subscribed),
            "remain": 200 - len(self.subscribed),
            "sub_list": {"QUOTE": list(self.subscribed)},
        }

    def subscribe(self, codes: list[str], subtype: list[str], **kwargs: Any):
        assert subtype == ["QUOTE"]
        assert kwargs["subscribe_push"] is False
        self.subscribed.extend(code for code in codes if code not in self.subscribed)
        return 0, None

    def unsubscribe(
        self,
        codes: list[str],
        subtype: list[str],
        unsubscribe_all: bool = False,
    ):
        assert subtype == ["QUOTE"]
        assert not unsubscribe_all
        self.subscribed = [code for code in self.subscribed if code not in codes]
        return 0, None

    def close(self):
        self.closed = True


class MonitoringMarketDataTest(unittest.TestCase):
    def setUp(self):
        self.context = FakeQuoteContext()
        self.source = OpenDMonitoringDataSource(
            context_factory=lambda **_kwargs: self.context,
            now=lambda: datetime(2026, 7, 27, 10, 30, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.source.close()

    def test_normalizes_stock_and_option_snapshots(self):
        snapshots = self.source.snapshots(["US.AAPL", "US.AAPL260731C95000", "US.AAPL"])

        self.assertEqual(len(snapshots), 2)
        stock, option = snapshots
        self.assertEqual(stock["instrument_type"], "stock")
        self.assertAlmostEqual(stock["change_rate"], 5)
        self.assertIsNone(stock["option_implied_volatility"])
        self.assertEqual(option["instrument_type"], "option")
        self.assertEqual(option["underlying_code"], "US.AAPL")
        self.assertEqual(option["option_implied_volatility"], 35.5)
        self.assertEqual(option["days_to_expiry"], 4)

    def test_discovers_sorted_expirations_and_contracts(self):
        expirations = self.source.option_expirations("us.aapl")
        contracts = self.source.option_chain("US.AAPL", "2026-07-31")

        self.assertEqual(
            [item["expiration"] for item in expirations],
            ["2026-07-31", "2026-08-07"],
        )
        self.assertEqual(
            [item["strike_price"] for item in contracts],
            [95, 100],
        )
        self.assertIsNone(contracts[0]["settlement_mode"])

    def test_hk_snapshots_use_permission_safe_batches(self):
        codes = [f"HK.{index:05d}" for index in range(21)]

        self.source.snapshots(codes)

        self.assertEqual(
            [len(batch) for batch in self.context.snapshot_calls],
            [20, 1],
        )

    def test_returns_serializable_option_analytics(self):
        analytics = self.source.option_analytics("US.AAPL260731C95000")

        self.assertEqual(
            analytics["volatility_history"][0]["volatility_premium"],
            7.3,
        )
        self.assertIsNone(
            analytics["exercise_probability_history"][0]["strike_probability"]
        )

    def test_manages_quote_subscriptions_and_exposes_budget(self):
        subscribed = self.source.subscribe_quotes(["US.AAPL", "US.AAPL"])
        unsubscribed = self.source.unsubscribe_quotes(["US.AAPL"])

        self.assertEqual(subscribed["own_used"], 1)
        self.assertEqual(subscribed["remaining"], 199)
        self.assertEqual(unsubscribed["own_used"], 0)

    def test_closes_context_and_maps_opend_errors(self):
        self.source.snapshots(["US.AAPL"])
        self.source.close()
        self.assertTrue(self.context.closed)

        class FailingContext(FakeQuoteContext):
            def get_market_snapshot(self, codes: list[str]):
                return -1, "permission denied"

        failing = OpenDMonitoringDataSource(
            context_factory=lambda **_kwargs: FailingContext()
        )
        with self.assertRaisesRegex(OpenDRequestError, "permission denied"):
            failing.snapshots(["US.AAPL"])
        failing.close()


if __name__ == "__main__":
    unittest.main()
