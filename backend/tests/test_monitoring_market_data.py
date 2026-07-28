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
        self.history_calls: list[dict[str, Any]] = []
        self.subscribed: list[str] = []

    def get_global_state(self):
        return 0, {
            "market_sz": "MORNING",
            "market_us": "AFTER_HOURS",
            "market_sh": "REST",
            "market_hk": "OPEN",
            "market_hkfuture": "NIGHT_OPEN",
            "market_usfuture": "N/A",
            "server_ver": "10.6.6608",
            "trd_logined": "0",
            "qot_logined": "1",
            "timestamp": 1785129000,
            "local_timestamp": 1785129000.25,
        }

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
                    "option_net_open_interest": 80 if option else math.nan,
                    "option_contract_size": 100 if option else math.nan,
                    "option_contract_nominal_value": 10000 if option else math.nan,
                    "option_contract_multiplier": 100 if option else math.nan,
                    "option_owner_lot_multiplier": 1 if option else math.nan,
                    "option_area_type": "AMERICAN" if option else "N/A",
                    "in_the_money": True if option else "N/A",
                    "intrinsic_value_per": 5 if option else math.nan,
                    "time_value_per": 1 if option else math.nan,
                    "option_delta": 0.52 if option else math.nan,
                    "option_gamma": 0.08 if option else math.nan,
                    "option_vega": 0.12 if option else math.nan,
                    "option_theta": -0.16 if option else math.nan,
                    "option_rho": 0.03 if option else math.nan,
                    "option_expiry_date_distance": 4 if option else math.nan,
                    "index_option_type": "N/A",
                }
            )
        return 0, FakeFrame(records)

    def request_history_kline(
        self,
        code: str,
        *,
        ktype: str,
        autype: str,
        max_count: int,
        page_req_key: Any,
    ):
        self.history_calls.append(
            {
                "code": code,
                "ktype": ktype,
                "autype": autype,
                "max_count": max_count,
                "page_req_key": page_req_key,
            }
        )
        return (
            0,
            FakeFrame(
                [
                    {
                        "code": code,
                        "time_key": "2026-07-27 10:28:00",
                        "open": 101,
                        "high": 103,
                        "low": 100,
                        "close": 102,
                        "volume": 10,
                        "turnover": 1020,
                        "turnover_rate": 0.1,
                        "change_rate": 1,
                        "last_close": 101,
                        "is_closed": True,
                    },
                    {
                        "code": code,
                        "time_key": "2026-07-27 10:29:00",
                        "open": 102,
                        "high": 104,
                        "low": 101,
                        "close": 103,
                        "volume": 20,
                        "turnover": 2060,
                        "turnover_rate": 0.2,
                        "change_rate": 0.98,
                        "last_close": 102,
                        "is_closed": True,
                    },
                    {
                        "code": code,
                        "time_key": "2026-07-27 10:30:00",
                        "open": 103,
                        "high": 106,
                        "low": 102,
                        "close": 105,
                        "volume": 30,
                        "turnover": 3150,
                        "turnover_rate": 0.3,
                        "change_rate": 1.94,
                        "last_close": 103,
                        "is_closed": True,
                    },
                ]
            ),
            b"next-page-key",
        )

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

    def test_normalizes_global_market_state(self):
        state = self.source.global_state()

        self.assertEqual(state["source"], "opend")
        self.assertEqual(
            state["market_states"],
            {
                "sz": "MORNING",
                "us": "AFTER_HOURS",
                "sh": "REST",
                "hk": "OPEN",
                "hk_future": "NIGHT_OPEN",
            },
        )
        self.assertEqual(state["server_version"], "10.6.6608")
        self.assertTrue(state["quote_logged_in"])
        self.assertFalse(state["trade_logged_in"])
        self.assertEqual(state["server_timestamp"], 1785129000)
        self.assertEqual(state["local_timestamp"], 1785129000.25)

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
        self.assertEqual(option["option_contract_size"], 100)
        self.assertEqual(option["option_contract_nominal_value"], 10000)
        self.assertEqual(option["option_contract_multiplier"], 100)
        self.assertEqual(option["option_owner_lot_multiplier"], 1)
        self.assertEqual(option["option_area_type"], "AMERICAN")
        self.assertTrue(option["option_in_the_money"])
        self.assertEqual(option["option_intrinsic_value"], 5)
        self.assertEqual(option["option_time_value"], 1)
        self.assertEqual(option["option_intrinsic_value_per"], 5)
        self.assertEqual(option["option_time_value_per"], 1)
        self.assertEqual(
            {
                greek: option[f"option_{greek}"]
                for greek in ("delta", "gamma", "vega", "theta", "rho")
            },
            {
                "delta": 0.52,
                "gamma": 0.08,
                "vega": 0.12,
                "theta": -0.16,
                "rho": 0.03,
            },
        )
        self.assertNotIn("mid_price", option)
        self.assertNotIn("bid_ask_spread", option)

    def test_normalizes_recent_bars_and_marks_latest_bar_open(self):
        bars = self.source.recent_bars("us.aapl", 2, "k_1m")

        self.assertEqual(
            self.context.history_calls,
            [
                {
                    "code": "US.AAPL",
                    "ktype": "K_1M",
                    "autype": "qfq",
                    "max_count": 2,
                    "page_req_key": None,
                }
            ],
        )
        self.assertEqual([bar["close"] for bar in bars], [103, 105])
        self.assertEqual(
            [bar["source_time"] for bar in bars],
            ["2026-07-27 10:29:00", "2026-07-27 10:30:00"],
        )
        self.assertEqual(
            [bar["is_closed"] for bar in bars],
            [True, False],
        )
        self.assertEqual(bars[0]["fetched_at"], "2026-07-27T10:30:00+00:00")
        self.assertEqual(bars[0]["ktype"], "K_1M")
        self.assertEqual(bars[0]["source"], "opend")

    def test_rejects_invalid_recent_bar_requests_before_opening_context(self):
        invalid_counts: list[Any] = [0, 1001, True]
        for count in invalid_counts:
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "recent bar count"):
                    self.source.recent_bars("US.AAPL", count, "K_1M")
        with self.assertRaisesRegex(ValueError, "kline type"):
            self.source.recent_bars("US.AAPL", 10, "")
        self.assertEqual(self.context.history_calls, [])

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

    def test_manages_quotes_and_exposes_generic_subscription_usage(self):
        subscribed = self.source.subscribe_quotes(["US.AAPL", "US.AAPL"])
        unsubscribed = self.source.unsubscribe_quotes(["US.AAPL"])

        self.assertEqual(
            subscribed["scope"],
            "all_connections_all_security_types",
        )
        self.assertEqual(subscribed["generic_total_used"], 1)
        self.assertEqual(subscribed["generic_own_used"], 1)
        self.assertEqual(subscribed["generic_remaining"], 199)
        self.assertEqual(unsubscribed["generic_own_used"], 0)
        for legacy_key in ("total_used", "own_used", "remaining"):
            self.assertNotIn(legacy_key, subscribed)

    def test_maps_history_errors_and_rejects_non_futu_response_shape(self):
        class FailingHistoryContext(FakeQuoteContext):
            def request_history_kline(self, code: str, **kwargs: Any):
                return -1, "history permission denied", None

        failing = OpenDMonitoringDataSource(
            context_factory=lambda **_kwargs: FailingHistoryContext()
        )
        with self.assertRaisesRegex(OpenDRequestError, "history permission denied"):
            failing.recent_bars("US.AAPL", 10, "K_DAY")
        failing.close()

        class MalformedHistoryContext(FakeQuoteContext):
            def request_history_kline(self, code: str, **kwargs: Any):
                return 0, FakeFrame([])

        malformed = OpenDMonitoringDataSource(
            context_factory=lambda **_kwargs: MalformedHistoryContext()
        )
        with self.assertRaisesRegex(OpenDRequestError, "unexpected response"):
            malformed.recent_bars("US.AAPL", 10, "K_DAY")
        malformed.close()

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
