from __future__ import annotations

import http.client
import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.monitoring_browser_fixture import (
    HK_STOCK,
    US_CALL,
    US_STOCK,
    MonitoringBrowserRuntime,
    create_fixture_app,
)
from stock_strategy.event_stream import EventBroker
from stock_strategy.job_store import JobStore
from stock_strategy.monitoring_repository import MonitoringRepository
from stock_strategy.monitoring_service import MonitoringService


class MonitoringBrowserFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.frontend = self.root / "frontend"
        self.frontend.mkdir(parents=True)
        (self.frontend / "index.html").write_text(
            '<div id="root">Monitoring browser fixture</div>',
            encoding="utf-8",
        )
        self.app = create_fixture_app(
            project_root=self.root,
            state_path=self.root / "runs" / "state.sqlite3",
            frontend_root=self.frontend,
        )
        self.runtime: MonitoringBrowserRuntime = self.app.state.monitoring_fixture

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_real_routes_are_exposed_but_fixture_routes_are_not_in_openapi(
        self,
    ) -> None:
        paths = self.app.openapi()["paths"]
        self.assertIn("/api/events", paths)
        self.assertIn("/api/monitoring/watchlist", paths)
        self.assertIn(
            "/api/monitoring/underlyings/{code}/option-chain",
            paths,
        )
        self.assertFalse(any(path.startswith("/_test/") for path in paths))
        self.assertFalse(
            any(
                marker in path.lower()
                for path in paths
                for marker in ("/trade", "/unlock")
            )
        )
        self.assertIsInstance(self.app.state.job_store, JobStore)
        self.assertIsInstance(self.runtime.events, EventBroker)
        self.assertIs(self.app.state.job_store.events, self.runtime.events)
        self.assertIsInstance(self.runtime.service, MonitoringService)
        self.assertIsInstance(
            self.runtime.service.repository,
            MonitoringRepository,
        )
        with sqlite3.connect(self.runtime.state_path) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(journal_mode, ("wal",))

        with TestClient(self.app) as client:
            state = client.get("/_test/monitoring/state")
            health = client.get("/api/health")
            fallback = client.get("/not-a-real-frontend-path")

        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["state_path"], str(self.runtime.state_path))
        self.assertTrue(health.json()["opend"]["connected"])
        self.assertNotEqual(
            state.text,
            fallback.text,
            "the frontend catch-all intercepted the fixture route",
        )

    def test_controlled_scenarios_cover_edges_ordering_freshness_and_errors(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            self._seed_watchlist_and_rules(client)

            baseline = client.post(
                "/_test/monitoring/scenario/baseline",
            )
            edge = client.post("/_test/monitoring/scenario/edge")
            duplicate = client.post(
                "/_test/monitoring/scenario/duplicate",
            )
            out_of_order = client.post(
                "/_test/monitoring/scenario/out-of-order",
            )
            rules = client.get("/api/monitoring/rules").json()["rules"]

            self.assertEqual(baseline.json()["alert_count"], 0)
            self.assertEqual(edge.json()["alert_count"], 2)
            self.assertEqual(duplicate.json()["alert_count"], 2)
            self.assertEqual(out_of_order.json()["alert_count"], 2)
            values = {rule["metric"]: rule["last_value"] for rule in rules}
            self.assertEqual(values["last_price"], 101)
            self.assertEqual(values["option_implied_volatility"], 35)

            stale = client.post("/_test/monitoring/scenario/stale")
            watchlist = client.get("/api/monitoring/watchlist").json()
            self.assertEqual(stale.status_code, 200)
            self.assertEqual(
                {item["code"]: item["freshness"] for item in watchlist["instruments"]},
                {HK_STOCK: "stale", US_STOCK: "stale"},
            )

            reconnecting = client.post("/_test/monitoring/scenario/reconnecting")
            self.assertEqual(
                reconnecting.json()["service"]["phase"],
                "reconnecting",
            )
            self.assertTrue(reconnecting.json()["service"]["rules_paused"])

            client.post("/_test/monitoring/scenario/permission")
            permission = client.get(f"/api/monitoring/underlyings/{US_STOCK}/snapshot")
            self.assertEqual(permission.status_code, 503)
            self.assertEqual(
                permission.json()["error"]["code"],
                "market_data_permission_denied",
            )

            client.post("/_test/monitoring/scenario/quota")
            quota = client.get(f"/api/monitoring/underlyings/{US_STOCK}/snapshot")
            self.assertEqual(quota.status_code, 503)
            self.assertEqual(
                quota.json()["error"]["code"],
                "market_data_quota_exhausted",
            )

            recovered = client.post("/_test/monitoring/scenario/recover")
            self.assertEqual(recovered.status_code, 200)
            self.assertEqual(recovered.json()["service"]["phase"], "ready")

            invalid = client.post(
                "/_test/monitoring/scenario/not-real",
            )
            self.assertEqual(invalid.status_code, 422)

    def test_restart_reuses_sqlite_and_broker_without_false_alert_or_leak(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            self._seed_watchlist_and_rules(client)
            client.post("/_test/monitoring/scenario/baseline")
            client.post("/_test/monitoring/scenario/edge")
            alerts = client.get(
                "/api/monitoring/alerts",
                params={"limit": 100},
            ).json()["alerts"]
            acknowledged = client.post(f"/api/monitoring/alerts/{alerts[0]['id']}/ack")
            self.assertEqual(acknowledged.status_code, 200)
            original_broker = self.runtime.events

            restarted = client.post("/_test/monitoring/restart")
            self.assertEqual(restarted.status_code, 200)
            payload = restarted.json()
            self.assertEqual(payload["restart_count"], 1)
            self.assertEqual(payload["watchlist_count"], 2)
            self.assertEqual(payload["rule_count"], 2)
            self.assertEqual(payload["alert_count"], 2)
            self.assertIs(self.runtime.events, original_broker)

            retired = payload["retired_gateways"][0]
            expected_owned = [HK_STOCK, US_STOCK, US_CALL]
            self.assertEqual(retired["unsubscribe_calls"], [expected_owned])
            self.assertEqual(retired["owned_codes"], [])
            self.assertEqual(retired["external_codes"], ["US.MSFT"])
            self.assertEqual(retired["close_calls"], 1)

            persisted_alerts = client.get(
                "/api/monitoring/alerts",
                params={"limit": 100},
            ).json()["alerts"]
            self.assertEqual(len(persisted_alerts), 2)
            self.assertEqual(
                sum(alert["acknowledged_at"] is not None for alert in persisted_alerts),
                1,
            )

            client.post("/_test/monitoring/scenario/reset")
            second_edge = client.post("/_test/monitoring/scenario/edge")
            self.assertEqual(second_edge.json()["alert_count"], 4)
            current_gateway = self.runtime.market_data

        self.assertEqual(
            current_gateway.unsubscribe_calls,
            [[HK_STOCK, US_STOCK, US_CALL]],
        )
        self.assertEqual(current_gateway.owned_codes, set())
        self.assertEqual(current_gateway.external_codes, {"US.MSFT"})
        self.assertEqual(current_gateway.close_calls, 1)

    def test_real_http_event_stream_delivers_monitor_alert(self) -> None:
        server, thread, sock, base_url = _start_server(self.app)
        stream_connection = http.client.HTTPConnection(
            "127.0.0.1",
            int(base_url.rsplit(":", 1)[1]),
            timeout=5,
        )
        try:
            stream_connection.request(
                "GET",
                "/api/events",
                headers={"Accept": "text/event-stream"},
            )
            response = stream_connection.getresponse()
            self.assertEqual(response.status, 200)
            ready = _read_sse_event(response)
            self.assertEqual(ready["event"], "stream.ready")

            _http_json(
                base_url,
                "/api/monitoring/watchlist",
                {
                    "code": US_STOCK,
                    "name": "Apple",
                    "instrument_type": "stock",
                },
            )
            _http_json(
                base_url,
                "/api/monitoring/rules",
                _stock_rule(),
            )
            _http_json(
                base_url,
                "/_test/monitoring/scenario/baseline",
                {},
            )
            _http_json(
                base_url,
                "/_test/monitoring/scenario/edge",
                {},
            )

            alert_event: dict[str, Any] | None = None
            for _ in range(20):
                event = _read_sse_event(response)
                if event.get("event") == "monitor.alert.triggered":
                    alert_event = event
                    break
            self.assertIsNotNone(alert_event)
            assert alert_event is not None
            self.assertEqual(alert_event["data"]["alert"]["code"], US_STOCK)
            self.assertEqual(
                alert_event["data"]["alert"]["metric"],
                "last_price",
            )

            alerts = _http_get_json(
                base_url,
                "/api/monitoring/alerts?limit=100",
            )
            self.assertEqual(len(alerts["alerts"]), 1)
        finally:
            stream_connection.close()
            server.should_exit = True
            thread.join(timeout=5)
            if thread.is_alive():
                server.force_exit = True
                thread.join(timeout=5)
            sock.close()
        self.assertFalse(thread.is_alive(), "fixture uvicorn server did not stop")

    def _seed_watchlist_and_rules(self, client: TestClient) -> None:
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
            response = client.post("/api/monitoring/watchlist", json=payload)
            self.assertEqual(response.status_code, 201)
        for payload in (_stock_rule(), _option_rule()):
            response = client.post("/api/monitoring/rules", json=payload)
            self.assertEqual(response.status_code, 201)


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
        "code": US_CALL,
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


def _start_server(
    app: FastAPI,
) -> tuple[uvicorn.Server, threading.Thread, socket.socket, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = int(sock.getsockname()[1])
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        lifespan="on",
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive():
        if time.monotonic() >= deadline:
            raise TimeoutError("fixture uvicorn server did not start")
        time.sleep(0.01)
    if not thread.is_alive():
        raise RuntimeError("fixture uvicorn server exited during startup")
    return server, thread, sock, f"http://127.0.0.1:{port}"


def _read_sse_event(response: http.client.HTTPResponse) -> dict[str, Any]:
    event: dict[str, Any] = {}
    while True:
        raw = response.readline()
        if not raw:
            raise EOFError("SSE stream closed before the expected event")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if event:
                return event
            continue
        if line.startswith(":") or line.startswith("retry:"):
            continue
        field, separator, value = line.partition(":")
        if not separator:
            continue
        normalized = value.lstrip()
        if field == "data":
            event[field] = json.loads(normalized)
        else:
            event[field] = normalized


def _http_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
        return json.loads(response.read())


def _http_get_json(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:  # nosec B310
        return json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
