from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from stock_strategy.event_stream import EventBroker
from stock_strategy.monitoring_repository import MonitoringRepository
from stock_strategy.monitoring_service import MonitoringService

NEW_YORK = ZoneInfo("America/New_York")


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 27, 10, 0, 5, tzinfo=NEW_YORK)
        self.monotonic_value = 1_000.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.monotonic_value

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.monotonic_value += seconds


class FakeMonitoringMarketData:
    def __init__(self) -> None:
        self.market_states = {"us": "MORNING", "hk": "CLOSED"}
        self.snapshot_values: dict[str, dict[str, Any]] = {
            "US.AAPL": _stock_snapshot(99, "2026-07-27 10:00:04"),
            "US.AAPL260731C100000": _option_snapshot(
                "US.AAPL260731C100000",
                "CALL",
                4.5,
                120,
                60,
            ),
            "US.AAPL260731P100000": _option_snapshot(
                "US.AAPL260731P100000",
                "PUT",
                3.5,
                40,
                20,
            ),
        }
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []
        self.snapshot_calls: list[list[str]] = []
        self.global_state_calls = 0
        self.global_state_delay = 0.0
        self.chain_calls = 0
        self.closed = False
        self.generic_remaining = 10

    def global_state(self) -> dict[str, Any]:
        self.global_state_calls += 1
        if self.global_state_delay:
            time.sleep(self.global_state_delay)
        return {
            "source": "opend",
            "market_states": dict(self.market_states),
        }

    def snapshots(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        requested = list(codes)
        self.snapshot_calls.append(requested)
        return [
            dict(self.snapshot_values[code])
            for code in requested
            if code in self.snapshot_values
        ]

    def recent_bars(
        self,
        code: str,
        count: int,
        ktype: str,
    ) -> list[dict[str, Any]]:
        size = 62 if ktype == "K_DAY" else 4
        bars = [
            {
                "code": code,
                "source_time": f"2026-07-{index + 1:02d} 16:00:00",
                "fetched_at": "2026-07-27T10:00:05-04:00",
                "ktype": ktype,
                "close": float(index + 1),
                "volume": 100 + index,
                "is_closed": True,
            }
            for index in range(size)
        ]
        bars[-1]["close"] = 10_000.0
        bars[-1]["is_closed"] = False
        return bars[-count:]

    def option_expirations(self, underlying: str) -> list[dict[str, Any]]:
        return [
            {
                "expiration": "2026-07-31",
                "days_to_expiry": 4,
                "cycle": "WEEK",
            }
        ]

    def option_chain(
        self,
        underlying: str,
        expiration: str,
    ) -> list[dict[str, Any]]:
        self.chain_calls += 1
        return [
            {
                "code": "US.AAPL260731C100000",
                "name": "AAPL C100",
                "underlying_code": underlying,
                "option_type": "CALL",
                "expiration": expiration,
                "strike_price": 100.0,
                "lot_size": 100,
            },
            {
                "code": "US.AAPL260731P100000",
                "name": "AAPL P100",
                "underlying_code": underlying,
                "option_type": "PUT",
                "expiration": expiration,
                "strike_price": 100.0,
                "lot_size": 100,
            },
        ]

    def option_analytics(self, code: str) -> dict[str, Any]:
        return {
            "code": code,
            "volatility_history": [
                {
                    "implied_volatility": 35.0,
                    "history_volatility": 25.0,
                }
            ],
            "exercise_probability_history": [],
        }

    def subscription_status(self) -> dict[str, Any]:
        return {
            "scope": "all_connections_all_security_types",
            "generic_total_used": len(self.subscribe_calls),
            "generic_own_used": len(self.subscribe_calls),
            "generic_remaining": self.generic_remaining,
            "subscriptions": {},
        }

    def subscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        self.subscribe_calls.append(list(codes))
        return self.subscription_status()

    def unsubscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        self.unsubscribe_calls.append(list(codes))
        return self.subscription_status()

    def close(self) -> None:
        self.closed = True


class MonitoringServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = MonitoringRepository(self.root / "state.sqlite3")
        self.market_data = FakeMonitoringMarketData()
        self.clock = MutableClock()
        self.events = EventBroker()
        self.service = MonitoringService(
            self.repository,
            self.market_data,
            self.events,
            poll_interval_seconds=3_600,
            now=self.clock.now,
            monotonic_clock=self.clock.monotonic,
        )

    async def asyncTearDown(self) -> None:
        await self.service.stop()
        self.temporary_directory.cleanup()

    async def test_baseline_crossing_duplicate_and_restart_are_idempotent(self):
        self.service.add_instrument(_instrument_request())
        rule = self.service.create_rule(_rule_request())

        await self.service.poll_once()
        baseline = self.repository.get_rule(rule["id"])
        self.assertEqual(baseline["last_value"], 99)
        self.assertFalse(baseline["condition_active"])
        self.assertEqual(self.repository.list_alerts(), [])

        self.clock.advance(10)
        self.market_data.snapshot_values["US.AAPL"] = _stock_snapshot(
            101,
            "2026-07-27 10:00:14",
        )
        await self.service.poll_once()
        self.assertEqual(len(self.repository.list_alerts()), 1)

        await self.service.poll_once()
        self.assertEqual(len(self.repository.list_alerts()), 1)

        restarted = MonitoringService(
            self.repository,
            self.market_data,
            self.events,
            now=self.clock.now,
            monotonic_clock=self.clock.monotonic,
        )
        try:
            self.clock.advance(10)
            self.market_data.snapshot_values["US.AAPL"] = _stock_snapshot(
                98,
                "2026-07-27 10:00:24",
            )
            await restarted.poll_once()
            self.assertEqual(len(self.repository.list_alerts()), 1)

            self.clock.advance(10)
            self.market_data.snapshot_values["US.AAPL"] = _stock_snapshot(
                102,
                "2026-07-27 10:00:34",
            )
            await restarted.poll_once()
            self.assertEqual(len(self.repository.list_alerts()), 2)
        finally:
            await restarted.stop()

    async def test_empty_workspace_starts_without_opening_opend(self):
        await self.service.poll_once()

        self.assertEqual(self.service.status()["phase"], "ready")
        self.assertEqual(self.market_data.global_state_calls, 0)

    async def test_slow_opend_request_is_bounded_and_marks_runtime_degraded(self):
        self.service.add_instrument(_instrument_request())
        self.market_data.global_state_delay = 0.05
        bounded = MonitoringService(
            self.repository,
            self.market_data,
            self.events,
            request_timeout_seconds=0.005,
            now=self.clock.now,
            monotonic_clock=self.clock.monotonic,
        )
        try:
            with self.assertRaises(TimeoutError):
                await bounded.poll_once()
            self.assertEqual(bounded.status()["phase"], "degraded")
        finally:
            await bounded.stop()

    async def test_stale_and_closed_quotes_pause_rule_state(self):
        us_rule = self.service.create_rule(_rule_request())
        hk_rule = self.service.create_rule(
            {
                **_rule_request(),
                "name": "Tencent move",
                "code": "HK.00700",
            }
        )
        self.market_data.snapshot_values["HK.00700"] = {
            **_stock_snapshot(500, "2026-07-27 10:00:04"),
            "code": "HK.00700",
            "name": "Tencent",
        }
        self.market_data.snapshot_values["US.AAPL"] = _stock_snapshot(
            101,
            "2026-07-27 09:00:00",
        )

        await self.service.poll_once()

        self.assertIsNone(self.repository.get_rule(us_rule["id"])["last_value"])
        self.assertIsNone(self.repository.get_rule(hk_rule["id"])["last_value"])
        self.assertEqual(self.repository.list_alerts(), [])
        self.assertEqual(self.service.status()["freshness"]["US.AAPL"], "stale")
        self.assertEqual(
            self.service.status()["freshness"]["HK.00700"],
            "market_closed",
        )

    async def test_option_chain_enriches_full_snapshot_without_subscribing_chain(self):
        self.service._snapshots["US.AAPL"] = self.market_data.snapshot_values["US.AAPL"]

        first = await self.service.option_chain("US.AAPL", "2026-07-31")
        second = await self.service.option_chain("US.AAPL", "2026-07-31")

        self.assertEqual(self.market_data.chain_calls, 1)
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["call_put_volume_ratio"], 3)
        self.assertEqual(first["summary"]["call_put_open_interest_ratio"], 3)
        self.assertEqual(first["summary"]["atm_strike"], 100)
        self.assertEqual(first["contracts"][0]["mid_price"], 4.5)
        self.assertEqual(
            first["contracts"][0]["open_interest_update_cadence"],
            "daily_as_of",
        )
        self.assertEqual(self.market_data.subscribe_calls, [])

    async def test_subscription_budget_prioritizes_exact_rule_target(self):
        self.market_data.generic_remaining = 1
        self.service.add_instrument(_instrument_request())
        self.service.create_rule(
            {
                **_rule_request(),
                "name": "Option IV",
                "code": "US.AAPL260731C100000",
                "instrument_type": "option",
                "metric": "option_implied_volatility",
                "threshold": 30,
            }
        )

        await self.service.poll_once()

        self.assertEqual(
            self.market_data.subscribe_calls,
            [["US.AAPL260731C100000"]],
        )
        owned = self.service.status()["owned_subscription_targets"]
        self.assertEqual(
            owned,
            [{"code": "US.AAPL260731C100000", "subtype": "QUOTE"}],
        )

    async def test_snapshot_indicators_ignore_the_unclosed_bar(self):
        result = await self.service.snapshot("US.AAPL")
        snapshot = result["snapshot"]

        self.assertEqual(snapshot["ma20"], 51.5)
        self.assertEqual(snapshot["ma60"], 31.5)
        self.assertEqual(snapshot["rsi14"], 100)
        self.assertLess(snapshot["change_rate_5m"], 100)

    async def test_stop_releases_only_subscriptions_owned_by_this_service(self):
        self.service.add_instrument(_instrument_request())
        await self.service.poll_once()

        await self.service.stop()

        self.assertEqual(self.market_data.unsubscribe_calls, [["US.AAPL"]])
        self.assertTrue(self.market_data.closed)


def _instrument_request() -> dict[str, Any]:
    return {
        "code": "US.AAPL",
        "name": "Apple",
        "instrument_type": "stock",
        "enabled": True,
    }


def _rule_request() -> dict[str, Any]:
    return {
        "name": "Apple breakout",
        "code": "US.AAPL",
        "instrument_type": "stock",
        "metric": "last_price",
        "operator": "above",
        "threshold": 100,
        "severity": "warning",
        "cooldown_seconds": 0,
        "daily_trigger_limit": 10,
        "session": "regular",
        "enabled": True,
    }


def _stock_snapshot(price: float, source_time: str) -> dict[str, Any]:
    return {
        "code": "US.AAPL",
        "name": "Apple",
        "instrument_type": "stock",
        "source": "opend",
        "source_time": source_time,
        "fetched_at": "2026-07-27T10:00:05-04:00",
        "last_price": price,
        "previous_close": 98,
        "change_rate": (price - 98) / 98 * 100,
        "volume": 1_000,
        "bid_price": price - 0.1,
        "ask_price": price + 0.1,
    }


def _option_snapshot(
    code: str,
    option_type: str,
    price: float,
    volume: float,
    open_interest: float,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "instrument_type": "option",
        "source": "opend",
        "source_time": "2026-07-27 10:00:04",
        "fetched_at": "2026-07-27T10:00:05-04:00",
        "last_price": price,
        "bid_price": price - 0.5,
        "ask_price": price + 0.5,
        "volume": volume,
        "option_open_interest": open_interest,
        "option_implied_volatility": 35,
        "option_delta": 0.5 if option_type == "CALL" else -0.5,
        "option_gamma": 0.08,
        "option_vega": 0.12,
        "option_theta": -0.16,
        "option_rho": 0.03,
        "option_type": option_type,
        "underlying_code": "US.AAPL",
        "strike_price": 100,
        "expiration": "2026-07-31",
        "days_to_expiry": 4,
        "option_contract_size": 100,
    }


if __name__ == "__main__":
    unittest.main()
