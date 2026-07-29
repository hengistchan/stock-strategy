#!/usr/bin/env python3
"""Run a deterministic stock and option monitoring HTTP acceptance journey."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from stock_strategy.event_stream import EventBroker
from stock_strategy.job_store import JobStore
from stock_strategy.monitoring_repository import MonitoringRepository
from stock_strategy.monitoring_service import MonitoringService
from stock_strategy.web import create_app

US_STOCK = "US.AAPL"
HK_STOCK = "HK.00700"
CALL_OPTION = "US.AAPL260807C100000"
PUT_OPTION = "US.AAPL260807P100000"
EXPIRATION = "2026-08-07"
EXPECTED_OWNED_CODES = [HK_STOCK, US_STOCK, CALL_OPTION]
EVIDENCE_NAME = "monitoring-acceptance.json"
NEW_YORK = ZoneInfo("America/New_York")
HONG_KONG = ZoneInfo("Asia/Hong_Kong")


class AcceptanceFailure(AssertionError):
    """Raised when a deterministic acceptance invariant is not satisfied."""


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
    """Deterministic OpenD-shaped boundary fixture; all orchestration remains real."""

    def __init__(
        self,
        clock: MutableClock,
        *,
        stock_price: float = 99,
        option_iv: float = 25,
    ) -> None:
        self.clock = clock
        self.snapshots_by_code: dict[str, dict[str, Any]] = {}
        self.owned_codes: set[str] = set()
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []
        self.snapshot_calls: list[list[str]] = []
        self.close_calls = 0
        self.chain_calls = 0
        self.set_values(
            stock_price=stock_price,
            option_iv=option_iv,
            source_at=clock.now() - timedelta(seconds=1),
        )

    def set_values(
        self,
        *,
        stock_price: float,
        option_iv: float,
        source_at: datetime,
    ) -> None:
        self.snapshots_by_code = {
            US_STOCK: _stock_snapshot(
                US_STOCK,
                "Apple",
                stock_price,
                source_at,
                self.clock.now(),
            ),
            HK_STOCK: _stock_snapshot(
                HK_STOCK,
                "Tencent",
                500,
                source_at.astimezone(HONG_KONG),
                self.clock.now(),
            ),
            CALL_OPTION: _option_snapshot(
                CALL_OPTION,
                "CALL",
                5,
                option_iv,
                source_at,
                self.clock.now(),
            ),
            PUT_OPTION: _option_snapshot(
                PUT_OPTION,
                "PUT",
                4,
                22,
                source_at,
                self.clock.now(),
            ),
        }

    def global_state(self) -> dict[str, Any]:
        return {
            "source": "opend",
            "market_states": {"us": "MORNING", "hk": "MORNING"},
            "server_version": "acceptance-fixture",
        }

    def snapshots(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        requested = list(codes)
        self.snapshot_calls.append(requested)
        return [
            dict(self.snapshots_by_code[code])
            for code in requested
            if code in self.snapshots_by_code
        ]

    def recent_bars(
        self,
        code: str,
        count: int,
        ktype: str,
    ) -> list[dict[str, Any]]:
        interval = timedelta(minutes=5) if ktype == "K_5M" else timedelta(days=1)
        start = self.clock.now() - interval * count
        bars = [
            {
                "code": code,
                "source": "opend",
                "source_time": (start + interval * index).isoformat(timespec="seconds"),
                "fetched_at": self.clock.now().isoformat(timespec="seconds"),
                "ktype": ktype,
                "open": float(index + 1),
                "high": float(index + 2),
                "low": float(index),
                "close": float(index + 1),
                "volume": float(1_000 + index),
                "is_closed": True,
            }
            for index in range(count)
        ]
        bars[-1]["close"] = 10_000.0
        bars[-1]["is_closed"] = False
        return bars

    def option_expirations(self, underlying: str) -> list[dict[str, Any]]:
        _require(underlying == US_STOCK, f"unexpected expiration target: {underlying}")
        return [
            {
                "expiration": EXPIRATION,
                "days_to_expiry": 11,
                "cycle": "WEEK",
            }
        ]

    def option_chain(
        self,
        underlying: str,
        expiration: str,
    ) -> list[dict[str, Any]]:
        _require(underlying == US_STOCK, f"unexpected chain target: {underlying}")
        _require(expiration == EXPIRATION, f"unexpected expiration: {expiration}")
        self.chain_calls += 1
        return [
            _option_contract(CALL_OPTION, "CALL", underlying, expiration),
            _option_contract(PUT_OPTION, "PUT", underlying, expiration),
        ]

    def option_analytics(self, code: str) -> dict[str, Any]:
        return {
            "code": code,
            "volatility_history": [
                {
                    "implied_volatility": self.snapshots_by_code[code][
                        "option_implied_volatility"
                    ],
                    "history_volatility": 20,
                }
            ],
            "exercise_probability_history": [],
        }

    def subscription_status(self) -> dict[str, Any]:
        used = len(self.owned_codes)
        return {
            "scope": "all_connections_all_security_types",
            "generic_total_used": used,
            "generic_own_used": used,
            "generic_remaining": 20 - used,
            "subscriptions": {"QUOTE": sorted(self.owned_codes)},
        }

    def subscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        requested = list(dict.fromkeys(codes))
        self.subscribe_calls.append(requested)
        self.owned_codes.update(requested)
        return self.subscription_status()

    def unsubscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        requested = list(dict.fromkeys(codes))
        self.unsubscribe_calls.append(requested)
        self.owned_codes.difference_update(requested)
        return self.subscription_status()

    def close(self) -> None:
        self.close_calls += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the deterministic monitoring HTTP journey and write JSON evidence."
        )
    )
    parser.add_argument("--output", type=Path, default=Path("runs/acceptance"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    output = args.output
    output_dir = (
        output.resolve() if output.is_absolute() else (project_root / output).resolve()
    )
    try:
        evidence = run_acceptance()
        evidence_path = _write_evidence(output_dir, evidence)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "message": str(error),
                    "error_type": type(error).__name__,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    payload = {
        "status": "passed",
        "evidence_path": str(evidence_path),
        "evidence": evidence,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="stock-strategy-monitoring-acceptance-"
    ) as directory:
        root = Path(directory)
        _prepare_project_root(root)
        database_path = root / "runs" / "state.sqlite3"
        clock = MutableClock()

        first_market = FakeMonitoringMarketData(clock)
        first_service, first_app = _build_runtime(
            root,
            database_path,
            first_market,
            clock,
        )
        first_paths = _openapi_paths(first_app)
        with TestClient(first_app) as client:
            empty_watchlist = _request_json(
                client.get("/api/monitoring/watchlist"),
                200,
                "read empty watchlist",
            )
            _require(
                empty_watchlist["instruments"] == [],
                "watchlist did not start empty",
            )
            _poll(client, first_service)

            for payload in (
                {
                    "code": US_STOCK,
                    "name": "Apple",
                    "instrument_type": "stock",
                },
                {
                    "code": HK_STOCK,
                    "name": "Tencent",
                    "instrument_type": "stock",
                },
            ):
                _request_json(
                    client.post("/api/monitoring/watchlist", json=payload),
                    201,
                    f"add {payload['code']} to watchlist",
                )

            watchlist = _request_json(
                client.get("/api/monitoring/watchlist"),
                200,
                "read populated watchlist",
            )
            watchlist_codes = sorted(item["code"] for item in watchlist["instruments"])
            _require(
                watchlist_codes == [HK_STOCK, US_STOCK],
                f"unexpected watchlist codes: {watchlist_codes}",
            )

            snapshots = [
                _request_json(
                    client.get(f"/api/monitoring/underlyings/{code}/snapshot"),
                    200,
                    f"read {code} snapshot",
                )
                for code in (US_STOCK, HK_STOCK)
            ]
            _require(
                [item["snapshot"]["code"] for item in snapshots]
                == [US_STOCK, HK_STOCK],
                "cross-market snapshots did not preserve requested codes",
            )

            expirations = _request_json(
                client.get(
                    f"/api/monitoring/underlyings/{US_STOCK}/option-expirations"
                ),
                200,
                "read option expirations",
            )
            _require(
                expirations["expirations"][0]["expiration"] == EXPIRATION,
                "option expiration mismatch",
            )
            chain = _request_json(
                client.get(
                    f"/api/monitoring/underlyings/{US_STOCK}/option-chain",
                    params={"expiration": EXPIRATION},
                ),
                200,
                "read option chain",
            )
            chain_codes = sorted(item["code"] for item in chain["contracts"])
            _require(
                chain_codes == [CALL_OPTION, PUT_OPTION],
                f"option chain mismatch: {chain_codes}",
            )

            rules = [
                _request_json(
                    client.post("/api/monitoring/rules", json=payload),
                    201,
                    f"create {payload['instrument_type']} rule",
                )
                for payload in (_stock_rule(), _option_rule())
            ]
            _require(
                sorted(rule["metric"] for rule in rules)
                == ["last_price", "option_implied_volatility"],
                "stock and option rules were not both created",
            )
            scoped_rules = _request_json(
                client.get(
                    "/api/monitoring/rules",
                    params={"underlying_code": US_STOCK},
                ),
                200,
                "read rules by underlying",
            )
            _require(
                {rule["code"] for rule in scoped_rules["rules"]}
                == {US_STOCK, CALL_OPTION},
                "underlying scope did not group stock and option rules",
            )
            _require(
                all(
                    rule["underlying_code"] == US_STOCK
                    for rule in scoped_rules["rules"]
                ),
                "rule evidence did not preserve the underlying code",
            )

            _poll(client, first_service)
            baseline_alerts = _alerts(client)
            _require(baseline_alerts == [], "baseline unexpectedly emitted an alert")
            baseline_rules = _rules_by_metric(client)
            _require(
                baseline_rules["last_price"]["last_value"] == 99,
                "stock baseline was not persisted",
            )
            _require(
                baseline_rules["option_implied_volatility"]["last_value"] == 25,
                "option baseline was not persisted",
            )

            clock.advance(10)
            first_edge_at = clock.now() - timedelta(seconds=1)
            first_market.set_values(
                stock_price=101,
                option_iv=35,
                source_at=first_edge_at,
            )
            _poll(client, first_service)
            first_edge_alerts = _alerts(client)
            _require(
                len(first_edge_alerts) == 2,
                f"first edge expected 2 alerts, got {len(first_edge_alerts)}",
            )
            scoped_alerts = _request_json(
                client.get(
                    "/api/monitoring/alerts",
                    params={"underlying_code": US_STOCK, "limit": 100},
                ),
                200,
                "read alerts by underlying",
            )
            _require(
                {alert["code"] for alert in scoped_alerts["alerts"]}
                == {US_STOCK, CALL_OPTION},
                "underlying scope did not group stock and option alerts",
            )
            _require(
                all(
                    alert["underlying_code"] == US_STOCK
                    for alert in scoped_alerts["alerts"]
                ),
                "alert evidence did not preserve the underlying code",
            )

            _poll(client, first_service)
            duplicate_alerts = _alerts(client)
            _require(
                len(duplicate_alerts) == 2,
                "duplicate provider observations emitted repeated alerts",
            )

            first_market.set_values(
                stock_price=98,
                option_iv=20,
                source_at=first_edge_at - timedelta(seconds=5),
            )
            _poll(client, first_service)
            out_of_order_alerts = _alerts(client)
            _require(
                len(out_of_order_alerts) == 2,
                "out-of-order provider observations emitted repeated alerts",
            )
            out_of_order_rules = _rules_by_metric(client)
            _require(
                out_of_order_rules["last_price"]["last_value"] == 101,
                "out-of-order stock observation rewound durable state",
            )
            _require(
                out_of_order_rules["option_implied_volatility"]["last_value"] == 35,
                "out-of-order option observation rewound durable state",
            )

            first_page = _request_json(
                client.get("/api/monitoring/alerts", params={"limit": 1}),
                200,
                "read first alert page",
            )
            _require(
                len(first_page["alerts"]) == 1
                and first_page["next_cursor"] is not None,
                "first alert page did not expose a continuation cursor",
            )
            second_page = _request_json(
                client.get(
                    "/api/monitoring/alerts",
                    params={"limit": 1, "cursor": first_page["next_cursor"]},
                ),
                200,
                "read second alert page",
            )
            _require(
                len(second_page["alerts"]) == 1 and second_page["next_cursor"] is None,
                "second alert page did not terminate the cursor journey",
            )
            acknowledged = _request_json(
                client.post(
                    f"/api/monitoring/alerts/{first_page['alerts'][0]['id']}/ack"
                ),
                200,
                "acknowledge alert",
            )
            _require(
                acknowledged["acknowledged_at"] is not None,
                "alert acknowledgement was not persisted",
            )
            _require(
                _openapi_paths(first_app) == first_paths,
                "acceptance journey mutated the production OpenAPI contract",
            )

        _assert_shutdown(first_market, "first service")

        clock.advance(10)
        restarted_market = FakeMonitoringMarketData(
            clock,
            stock_price=110,
            option_iv=40,
        )
        restarted_service, restarted_app = _build_runtime(
            root,
            database_path,
            restarted_market,
            clock,
        )
        restarted_paths = _openapi_paths(restarted_app)
        _require(
            restarted_paths == first_paths,
            "restart changed the production OpenAPI contract",
        )
        with TestClient(restarted_app) as client:
            _poll(client, restarted_service)
            persisted_watchlist = _request_json(
                client.get("/api/monitoring/watchlist"),
                200,
                "read watchlist after restart",
            )
            persisted_rules = _request_json(
                client.get("/api/monitoring/rules"),
                200,
                "read rules after restart",
            )
            restart_alerts = _alerts(client)
            _require(
                len(persisted_watchlist["instruments"]) == 2,
                "watchlist did not survive restart",
            )
            _require(
                len(persisted_rules["rules"]) == 2,
                "rules did not survive restart",
            )
            _require(
                len(restart_alerts) == 2,
                "restart first batch emitted a false positive",
            )
            _require(
                sum(alert["acknowledged_at"] is not None for alert in restart_alerts)
                == 1,
                "alert acknowledgement did not survive restart",
            )

            clock.advance(10)
            restarted_market.set_values(
                stock_price=95,
                option_iv=20,
                source_at=clock.now() - timedelta(seconds=1),
            )
            _poll(client, restarted_service)
            _require(
                len(_alerts(client)) == 2,
                "inactive side of a new edge emitted an alert",
            )

            clock.advance(10)
            restarted_market.set_values(
                stock_price=103,
                option_iv=36,
                source_at=clock.now() - timedelta(seconds=1),
            )
            _poll(client, restarted_service)
            final_alerts = _alerts(client)
            _require(
                len(final_alerts) == 4,
                f"second real edge expected 4 total alerts, got {len(final_alerts)}",
            )

        _assert_shutdown(restarted_market, "restarted service")
        private_paths = _private_test_paths(first_paths)
        _require(
            private_paths == [],
            f"test-only routes leaked into production OpenAPI: {private_paths}",
        )

        return {
            "status": "passed",
            "journey": {
                "initial_watchlist_count": 0,
                "watchlist_codes": [HK_STOCK, US_STOCK],
                "snapshot_codes": [US_STOCK, HK_STOCK],
                "expiration": EXPIRATION,
                "chain_contract_codes": [CALL_OPTION, PUT_OPTION],
                "rule_metrics": ["last_price", "option_implied_volatility"],
                "underlying_scoped_rule_count": len(scoped_rules["rules"]),
                "underlying_scoped_alert_count": len(scoped_alerts["alerts"]),
                "baseline_alert_count": 0,
                "first_edge_alert_count": len(first_edge_alerts),
                "duplicate_alert_count": len(duplicate_alerts),
                "out_of_order_alert_count": len(out_of_order_alerts),
                "alert_page_sizes": [
                    len(first_page["alerts"]),
                    len(second_page["alerts"]),
                ],
                "acknowledged": True,
                "restart_persisted": {
                    "watchlist": len(persisted_watchlist["instruments"]),
                    "rules": len(persisted_rules["rules"]),
                    "alerts": len(restart_alerts),
                },
                "restart_first_batch_alert_count": len(restart_alerts),
                "final_alert_count": len(final_alerts),
            },
            "runtime": {
                "database": "temporary_sqlite_wal",
                "service": "MonitoringService",
                "events": "EventBroker",
                "http_client": "TestClient",
            },
            "shutdown": {
                "expected_owned_codes": EXPECTED_OWNED_CODES,
                "first": _shutdown_evidence(first_market),
                "restarted": _shutdown_evidence(restarted_market),
            },
            "openapi": {
                "unchanged": first_paths == restarted_paths,
                "private_test_routes": private_paths,
                "monitoring_path_count": sum(
                    path.startswith("/api/monitoring") for path in first_paths
                ),
            },
        }


def _build_runtime(
    root: Path,
    database_path: Path,
    market_data: FakeMonitoringMarketData,
    clock: MutableClock,
) -> tuple[MonitoringService, Any]:
    events = EventBroker()
    store = JobStore(root, event_broker=events)
    service = MonitoringService(
        MonitoringRepository(database_path),
        market_data,
        events,
        poll_interval_seconds=3_600,
        now=clock.now,
        monotonic_clock=clock.monotonic,
    )
    app = create_app(
        project_root=root,
        job_store=store,
        frontend_root=root / "frontend",
        opend_probe=lambda _host, _port: False,
        monitoring_service=service,
    )
    return service, app


def _prepare_project_root(root: Path) -> None:
    for name in ("examples", "strategies", "data", "runs", "frontend"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "frontend" / "index.html").write_text(
        '<div id="root">Monitoring acceptance</div>',
        encoding="utf-8",
    )


def _poll(client: TestClient, service: MonitoringService) -> None:
    portal = client.portal
    if portal is None:
        raise AcceptanceFailure("TestClient lifespan portal is unavailable")
    portal.call(service.poll_once)


def _alerts(client: TestClient) -> list[dict[str, Any]]:
    payload = _request_json(
        client.get("/api/monitoring/alerts", params={"limit": 100}),
        200,
        "read alerts",
    )
    return list(payload["alerts"])


def _rules_by_metric(client: TestClient) -> dict[str, dict[str, Any]]:
    payload = _request_json(
        client.get("/api/monitoring/rules"),
        200,
        "read rules",
    )
    return {str(rule["metric"]): dict(rule) for rule in payload["rules"]}


def _request_json(response: Any, expected_status: int, label: str) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise AcceptanceFailure(
            f"{label} returned HTTP {response.status_code}: {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise AcceptanceFailure(f"{label} returned a non-object JSON payload")
    return payload


def _assert_shutdown(market_data: FakeMonitoringMarketData, label: str) -> None:
    _require(
        market_data.close_calls == 1,
        f"{label} close count was {market_data.close_calls}, expected 1",
    )
    _require(
        market_data.unsubscribe_calls == [EXPECTED_OWNED_CODES],
        (
            f"{label} unsubscribe diff was {market_data.unsubscribe_calls}, "
            f"expected {[EXPECTED_OWNED_CODES]}"
        ),
    )
    _require(
        market_data.owned_codes == set(),
        f"{label} retained owned subscriptions after close",
    )


def _shutdown_evidence(
    market_data: FakeMonitoringMarketData,
) -> dict[str, Any]:
    return {
        "close_calls": market_data.close_calls,
        "unsubscribe_calls": market_data.unsubscribe_calls,
        "remaining_owned_codes": sorted(market_data.owned_codes),
    }


def _openapi_paths(app: Any) -> list[str]:
    return sorted(str(path) for path in app.openapi()["paths"])


def _private_test_paths(paths: Iterable[str]) -> list[str]:
    markers = ("/_test", "/test-only", "/acceptance", "/poll-once")
    return [
        path
        for path in paths
        if path.startswith("/api/monitoring")
        and any(marker in path.lower() for marker in markers)
    ]


def _write_evidence(output_dir: Path, evidence: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / EVIDENCE_NAME
    pending = target.with_suffix(".json.tmp")
    pending.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pending.replace(target)
    return target


def _stock_rule() -> dict[str, Any]:
    return {
        "name": "Apple crosses 100",
        "code": US_STOCK,
        "instrument_type": "stock",
        "metric": "last_price",
        "operator": "crosses_above",
        "threshold": 100,
        "severity": "warning",
        "cooldown_seconds": 0,
        "daily_trigger_limit": 10,
        "session": "regular",
        "enabled": True,
    }


def _option_rule() -> dict[str, Any]:
    return {
        "name": "Apple call IV crosses 30",
        "code": CALL_OPTION,
        "underlying_code": US_STOCK,
        "instrument_type": "option",
        "metric": "option_implied_volatility",
        "operator": "crosses_above",
        "threshold": 30,
        "severity": "critical",
        "cooldown_seconds": 0,
        "daily_trigger_limit": 10,
        "session": "regular",
        "enabled": True,
    }


def _stock_snapshot(
    code: str,
    name: str,
    price: float,
    source_at: datetime,
    fetched_at: datetime,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "instrument_type": "stock",
        "source": "opend",
        "source_time": source_at.isoformat(timespec="seconds"),
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "last_price": price,
        "previous_close": price - 1,
        "change_rate": 1,
        "volume": 1_000,
        "bid_price": price - 0.1,
        "ask_price": price + 0.1,
    }


def _option_snapshot(
    code: str,
    option_type: str,
    price: float,
    implied_volatility: float,
    source_at: datetime,
    fetched_at: datetime,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "instrument_type": "option",
        "source": "opend",
        "source_time": source_at.isoformat(timespec="seconds"),
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "last_price": price,
        "bid_price": price - 0.1,
        "ask_price": price + 0.1,
        "volume": 100 if option_type == "CALL" else 50,
        "option_open_interest": 80 if option_type == "CALL" else 40,
        "option_implied_volatility": implied_volatility,
        "option_delta": 0.5 if option_type == "CALL" else -0.5,
        "option_gamma": 0.08,
        "option_vega": 0.12,
        "option_theta": -0.16,
        "option_rho": 0.03,
        "option_type": option_type,
        "underlying_code": US_STOCK,
        "strike_price": 100,
        "expiration": EXPIRATION,
        "days_to_expiry": 11,
        "option_contract_size": 100,
    }


def _option_contract(
    code: str,
    option_type: str,
    underlying: str,
    expiration: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": f"AAPL {option_type} 100",
        "underlying_code": underlying,
        "option_type": option_type,
        "expiration": expiration,
        "strike_price": 100,
        "lot_size": 100,
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


if __name__ == "__main__":
    raise SystemExit(main())
