from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from stock_strategy.event_stream import EventBroker
from stock_strategy.monitoring_repository import MonitoringRepository
from stock_strategy.monitoring_service import MonitoringService
from stock_strategy.opend import OpenDRequestError
from stock_strategy.web import create_app


class ApiMarketData:
    def __init__(self) -> None:
        self.closed = False
        self.snapshots_by_code = {
            "US.AAPL": _stock_snapshot(),
            "US.AAPL260731C100000": _option_snapshot(
                "US.AAPL260731C100000",
                "CALL",
            ),
            "US.AAPL260731P100000": _option_snapshot(
                "US.AAPL260731P100000",
                "PUT",
            ),
        }

    def global_state(self) -> dict[str, Any]:
        return {"source": "opend", "market_states": {"us": "MORNING"}}

    def snapshots(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        return [
            dict(self.snapshots_by_code[code])
            for code in codes
            if code in self.snapshots_by_code
        ]

    def recent_bars(
        self,
        code: str,
        count: int,
        ktype: str,
    ) -> list[dict[str, Any]]:
        bars = [
            {
                "code": code,
                "source_time": f"2026-07-{index + 1:02d} 16:00:00",
                "fetched_at": "2026-07-27T10:00:05-04:00",
                "ktype": ktype,
                "close": float(index + 1),
                "is_closed": True,
            }
            for index in range(min(count, 62))
        ]
        bars[-1]["is_closed"] = False
        return bars

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
        return [
            {
                "code": f"US.AAPL260731{kind}100000",
                "name": f"AAPL {kind}100",
                "underlying_code": underlying,
                "option_type": option_type,
                "expiration": expiration,
                "strike_price": 100,
                "lot_size": 100,
            }
            for kind, option_type in (("C", "CALL"), ("P", "PUT"))
        ]

    def option_analytics(self, code: str) -> dict[str, Any]:
        return {
            "code": code,
            "volatility_history": [
                {
                    "implied_volatility": 30,
                    "history_volatility": 25,
                }
            ],
            "exercise_probability_history": [],
        }

    def subscription_status(self) -> dict[str, Any]:
        return {
            "scope": "all_connections_all_security_types",
            "generic_total_used": 0,
            "generic_own_used": 0,
            "generic_remaining": 10,
            "subscriptions": {},
        }

    def subscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        return self.subscription_status()

    def unsubscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        return self.subscription_status()

    def close(self) -> None:
        self.closed = True


class MonitoringWebTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        for name in ("examples", "strategies", "data", "runs"):
            (self.root / name).mkdir()
        self.frontend = self.root / "frontend"
        self.frontend.mkdir()
        (self.frontend / "index.html").write_text(
            '<div id="root">Strategy Lab</div>',
            encoding="utf-8",
        )
        self.market_data = ApiMarketData()
        self.repository = MonitoringRepository(self.root / "runs" / "state.sqlite3")
        self.service = MonitoringService(
            self.repository,
            self.market_data,
            EventBroker(),
            poll_interval_seconds=3_600,
            now=lambda: datetime(
                2026,
                7,
                27,
                10,
                0,
                5,
                tzinfo=ZoneInfo("America/New_York"),
            ),
        )
        self.app = create_app(
            project_root=self.root,
            frontend_root=self.frontend,
            opend_probe=lambda _host, _port: False,
            monitoring_service=self.service,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_full_monitoring_http_contract_and_lifespan(self):
        with TestClient(self.app) as client:
            created = client.post(
                "/api/monitoring/watchlist",
                json={
                    "code": "US.AAPL",
                    "name": "Apple",
                    "instrument_type": "stock",
                },
            )
            duplicate = client.post(
                "/api/monitoring/watchlist",
                json={
                    "code": "US.AAPL",
                    "name": "Apple Inc.",
                    "instrument_type": "stock",
                },
            )
            watchlist = client.get("/api/monitoring/watchlist")
            snapshot = client.get("/api/monitoring/underlyings/US.AAPL/snapshot")
            expirations = client.get(
                "/api/monitoring/underlyings/US.AAPL/option-expirations"
            )
            chain = client.get(
                "/api/monitoring/underlyings/US.AAPL/option-chain",
                params={"expiration": "2026-07-31"},
            )
            contract = client.get("/api/monitoring/contracts/US.AAPL260731C100000")
            diagnostics = client.get("/api/monitoring/diagnostics")
            rule = client.post(
                "/api/monitoring/rules",
                json=_rule_request(),
            )
            option_rule = client.post(
                "/api/monitoring/rules",
                json={
                    **_rule_request(),
                    "name": "Apple call IV",
                    "code": "US.AAPL260731C100000",
                    "underlying_code": "US.AAPL",
                    "instrument_type": "option",
                    "metric": "option_implied_volatility",
                },
            )
            rules = client.get(
                "/api/monitoring/rules",
                params={"underlying_code": "us.aapl"},
            )
            missing_option_underlying = client.post(
                "/api/monitoring/rules",
                json={
                    **_rule_request(),
                    "code": "US.AAPL260731C100000",
                    "instrument_type": "option",
                    "metric": "option_implied_volatility",
                },
            )
            invalid_rule = client.post(
                "/api/monitoring/rules",
                json={
                    **_rule_request(),
                    "metric": "option_implied_volatility",
                },
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(duplicate.status_code, 201)
        self.assertEqual(duplicate.json()["name"], "Apple Inc.")
        self.assertEqual(len(watchlist.json()["instruments"]), 1)
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["snapshot"]["ma20"], 51.5)
        self.assertEqual(expirations.json()["expirations"][0]["days_to_expiry"], 4)
        self.assertEqual(chain.status_code, 200)
        self.assertEqual(len(chain.json()["contracts"]), 2)
        self.assertEqual(
            chain.json()["summary"]["call_put_open_interest_ratio"],
            1,
        )
        self.assertEqual(contract.status_code, 200)
        self.assertEqual(
            contract.json()["contract"]["option_delta"],
            0.5,
        )
        self.assertEqual(
            [check["id"] for check in diagnostics.json()["checks"]],
            [
                "opend_rpc",
                "stock_quote",
                "us_options",
                "hk_options",
                "generic_subscription",
                "quote_freshness",
            ],
        )
        self.assertEqual(rule.status_code, 201)
        self.assertEqual(option_rule.status_code, 201)
        self.assertEqual(
            {item["code"] for item in rules.json()["rules"]},
            {"US.AAPL", "US.AAPL260731C100000"},
        )
        self.assertTrue(
            all(item["underlying_code"] == "US.AAPL" for item in rules.json()["rules"])
        )
        self.assertEqual(missing_option_underlying.status_code, 422)
        self.assertEqual(invalid_rule.status_code, 422)
        self.assertEqual(
            invalid_rule.json()["error"]["code"],
            "invalid_monitoring_request",
        )
        self.assertTrue(self.market_data.closed)

    def test_alert_cursor_ack_and_structured_not_found_errors(self):
        for index in range(3):
            self.repository.create_alert(
                {
                    "id": f"alert-{index}",
                    "dedupe_key": f"rule-1:alert-{index}",
                    "rule_id": "rule-1",
                    "rule_name": "Apple move",
                    "code": "US.AAPL",
                    "triggered_at": f"2026-07-27T10:0{index}:05-04:00",
                    "severity": "warning",
                    "metric": "last_price",
                    "operator": "above",
                    "threshold": 100,
                    "value": 101 + index,
                    "source": "opend",
                    "snapshot": _stock_snapshot(),
                }
            )

        with TestClient(self.app) as client:
            first = client.get("/api/monitoring/alerts", params={"limit": 2})
            second = client.get(
                "/api/monitoring/alerts",
                params={
                    "limit": 2,
                    "cursor": first.json()["next_cursor"],
                },
            )
            scoped = client.get(
                "/api/monitoring/alerts",
                params={"underlying_code": "us.aapl", "limit": 100},
            )
            acknowledged = client.post(
                f"/api/monitoring/alerts/{first.json()['alerts'][0]['id']}/ack"
            )
            missing = client.get("/api/monitoring/underlyings/US.UNKNOWN/snapshot")
            bad_cursor = client.get(
                "/api/monitoring/alerts",
                params={"cursor": "not-a-cursor"},
            )

        self.assertEqual(len(first.json()["alerts"]), 2)
        self.assertIsNotNone(first.json()["next_cursor"])
        self.assertEqual(len(second.json()["alerts"]), 1)
        self.assertIsNone(second.json()["next_cursor"])
        self.assertEqual(len(scoped.json()["alerts"]), 3)
        self.assertTrue(
            all(
                alert["underlying_code"] == "US.AAPL"
                for alert in scoped.json()["alerts"]
            )
        )
        self.assertIsNotNone(acknowledged.json()["acknowledged_at"])
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            missing.json()["error"]["code"],
            "monitor_snapshot_not_found",
        )
        self.assertEqual(bad_cursor.status_code, 422)

    def test_openapi_contains_no_trading_or_account_unlock_surface(self):
        schema = self.app.openapi()
        monitoring_paths = [
            path for path in schema["paths"] if path.startswith("/api/monitoring")
        ]

        self.assertIn("/api/monitoring/watchlist", monitoring_paths)
        self.assertIn("/api/monitoring/rules", monitoring_paths)
        self.assertFalse(
            any(
                forbidden in path.lower()
                for path in monitoring_paths
                for forbidden in ("order", "trade", "unlock")
            )
        )

    def test_market_permission_and_quota_failures_remain_distinct(self):
        with TestClient(self.app) as client:
            with patch.object(
                self.market_data,
                "snapshots",
                side_effect=OpenDRequestError("option authority permission denied"),
            ):
                permission = client.get("/api/monitoring/underlyings/US.AAPL/snapshot")
            with patch.object(
                self.market_data,
                "snapshots",
                side_effect=OpenDRequestError("subscription quota exhausted"),
            ):
                quota = client.get("/api/monitoring/underlyings/US.AAPL/snapshot")

        self.assertEqual(permission.status_code, 503)
        self.assertEqual(
            permission.json()["error"]["code"],
            "market_data_permission_denied",
        )
        self.assertEqual(quota.status_code, 503)
        self.assertEqual(
            quota.json()["error"]["code"],
            "market_data_quota_exhausted",
        )


def _rule_request() -> dict[str, Any]:
    return {
        "name": "Apple breakout",
        "code": "US.AAPL",
        "instrument_type": "stock",
        "metric": "last_price",
        "operator": "above",
        "threshold": 100,
        "severity": "warning",
        "cooldown_seconds": 60,
        "daily_trigger_limit": 5,
        "session": "regular",
    }


def _stock_snapshot() -> dict[str, Any]:
    return {
        "code": "US.AAPL",
        "name": "Apple",
        "instrument_type": "stock",
        "source": "opend",
        "source_time": "2026-07-27 10:00:04",
        "fetched_at": "2026-07-27T10:00:05-04:00",
        "last_price": 100,
        "previous_close": 99,
        "change_rate": 1.01,
        "volume": 1_000,
        "bid_price": 99.9,
        "ask_price": 100.1,
    }


def _option_snapshot(code: str, option_type: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "instrument_type": "option",
        "source": "opend",
        "source_time": "2026-07-27 10:00:04",
        "fetched_at": "2026-07-27T10:00:05-04:00",
        "last_price": 5,
        "bid_price": 4.9,
        "ask_price": 5.1,
        "volume": 50,
        "option_open_interest": 100,
        "option_implied_volatility": 30,
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
