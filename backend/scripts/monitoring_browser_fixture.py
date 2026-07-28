#!/usr/bin/env python3
"""Run the production web app against deterministic monitoring market data.

This process exists only for browser integration tests.  Production monitoring
routes, persistence, rule evaluation, and SSE all remain the real application
implementations; only the OpenD-shaped market-data boundary is replaced.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, FastAPI

from stock_strategy.event_stream import EventBroker
from stock_strategy.job_store import JobStore
from stock_strategy.monitoring_repository import MonitoringRepository
from stock_strategy.monitoring_service import MonitoringService
from stock_strategy.opend import OpenDRequestError, OpenDSymbolDirectory
from stock_strategy.web import create_app

US_STOCK = "US.AAPL"
HK_STOCK = "HK.00700"
US_CALL = "US.AAPL260807C100000"
US_PUT = "US.AAPL260807P100000"
HK_CALL = "HK.00700260827C500000"
HK_PUT = "HK.00700260827P500000"
US_EXPIRATION = "2026-08-07"
HK_EXPIRATION = "2026-08-27"
NEW_YORK = ZoneInfo("America/New_York")
HONG_KONG = ZoneInfo("Asia/Hong_Kong")
SCENARIOS = frozenset(
    {
        "baseline",
        "edge",
        "duplicate",
        "out-of-order",
        "stale",
        "reconnecting",
        "permission",
        "quota",
        "reset",
        "recover",
    }
)


class FixtureClock:
    """A thread-safe wall and monotonic clock controlled by test endpoints."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._current = datetime(2026, 7, 27, 10, 0, 5, tzinfo=NEW_YORK)
        self._monotonic = 1_000.0

    def now(self) -> datetime:
        with self._lock:
            return self._current

    def monotonic(self) -> float:
        with self._lock:
            return self._monotonic

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("fixture clock cannot move backwards")
        with self._lock:
            self._current += timedelta(seconds=seconds)
            self._monotonic += seconds


class FixtureMonitoringMarketData:
    """Deterministic, mutable implementation of the production OpenD boundary."""

    def __init__(
        self,
        clock: FixtureClock,
        *,
        snapshots: Mapping[str, Mapping[str, Any]] | None = None,
        failure_mode: str | None = None,
        external_codes: Iterable[str] = ("US.MSFT",),
    ) -> None:
        self.clock = clock
        self._lock = RLock()
        self.failure_mode = failure_mode
        self.external_codes = set(external_codes)
        self.owned_codes: set[str] = set()
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []
        self.snapshot_calls: list[list[str]] = []
        self.close_calls = 0
        self.closed = False
        if snapshots is None:
            self.snapshots_by_code: dict[str, dict[str, Any]] = {}
            self.set_values(
                stock_price=99,
                option_iv=25,
                source_at=clock.now() - timedelta(seconds=1),
            )
        else:
            self.snapshots_by_code = {
                code: dict(snapshot) for code, snapshot in snapshots.items()
            }

    def clone(self) -> FixtureMonitoringMarketData:
        with self._lock:
            return FixtureMonitoringMarketData(
                self.clock,
                snapshots=self.snapshots_by_code,
                failure_mode=self.failure_mode,
                external_codes=self.external_codes,
            )

    def set_failure(self, mode: str | None) -> None:
        if mode not in {None, "permission", "quota"}:
            raise ValueError(f"unsupported fixture failure mode: {mode}")
        with self._lock:
            self.failure_mode = mode

    def set_values(
        self,
        *,
        stock_price: float,
        option_iv: float,
        source_at: datetime,
    ) -> None:
        fetched_at = self.clock.now()
        with self._lock:
            self.snapshots_by_code = {
                US_STOCK: _stock_snapshot(
                    US_STOCK,
                    "Apple",
                    stock_price,
                    source_at,
                    fetched_at,
                ),
                HK_STOCK: _stock_snapshot(
                    HK_STOCK,
                    "Tencent",
                    500,
                    source_at.astimezone(HONG_KONG),
                    fetched_at,
                ),
                US_CALL: _option_snapshot(
                    US_CALL,
                    "CALL",
                    US_STOCK,
                    US_EXPIRATION,
                    strike_price=100,
                    price=5,
                    implied_volatility=option_iv,
                    source_at=source_at,
                    fetched_at=fetched_at,
                ),
                US_PUT: _option_snapshot(
                    US_PUT,
                    "PUT",
                    US_STOCK,
                    US_EXPIRATION,
                    strike_price=100,
                    price=4,
                    implied_volatility=22,
                    source_at=source_at,
                    fetched_at=fetched_at,
                ),
                HK_CALL: _option_snapshot(
                    HK_CALL,
                    "CALL",
                    HK_STOCK,
                    HK_EXPIRATION,
                    strike_price=500,
                    price=12,
                    implied_volatility=31,
                    source_at=source_at.astimezone(HONG_KONG),
                    fetched_at=fetched_at,
                ),
                HK_PUT: _option_snapshot(
                    HK_PUT,
                    "PUT",
                    HK_STOCK,
                    HK_EXPIRATION,
                    strike_price=500,
                    price=11,
                    implied_volatility=29,
                    source_at=source_at.astimezone(HONG_KONG),
                    fetched_at=fetched_at,
                ),
            }

    def values(self) -> tuple[float, float]:
        with self._lock:
            return (
                float(self.snapshots_by_code[US_STOCK]["last_price"]),
                float(self.snapshots_by_code[US_CALL]["option_implied_volatility"]),
            )

    def provider_time(self) -> datetime:
        with self._lock:
            value = str(self.snapshots_by_code[US_STOCK]["source_time"])
        return datetime.fromisoformat(value)

    def global_state(self) -> dict[str, Any]:
        self._raise_if_failed()
        return {
            "source": "opend",
            "market_states": {"us": "MORNING", "hk": "MORNING"},
            "server_version": "monitoring-browser-fixture",
            "quote_logged_in": True,
            "trade_logged_in": False,
        }

    def snapshots(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        self._raise_if_failed()
        requested = list(dict.fromkeys(code.strip().upper() for code in codes))
        with self._lock:
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
        self._raise_if_failed()
        interval = timedelta(minutes=5) if ktype == "K_5M" else timedelta(days=1)
        now = self.clock.now()
        start = now - interval * count
        bars = [
            {
                "code": code,
                "source": "opend",
                "source_time": (start + interval * index).isoformat(timespec="seconds"),
                "fetched_at": now.isoformat(timespec="seconds"),
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
        if bars:
            bars[-1]["close"] = 10_000.0
            bars[-1]["is_closed"] = False
        return bars

    def option_expirations(self, underlying: str) -> list[dict[str, Any]]:
        self._raise_if_failed()
        normalized = underlying.strip().upper()
        if normalized == US_STOCK:
            return [
                {
                    "expiration": US_EXPIRATION,
                    "days_to_expiry": 11,
                    "cycle": "WEEK",
                }
            ]
        if normalized == HK_STOCK:
            return [
                {
                    "expiration": HK_EXPIRATION,
                    "days_to_expiry": 31,
                    "cycle": "MONTH",
                }
            ]
        return []

    def option_chain(
        self,
        underlying: str,
        expiration: str,
    ) -> list[dict[str, Any]]:
        self._raise_if_failed()
        normalized = underlying.strip().upper()
        if normalized == US_STOCK and expiration == US_EXPIRATION:
            values = ((US_CALL, "CALL", 100), (US_PUT, "PUT", 100))
        elif normalized == HK_STOCK and expiration == HK_EXPIRATION:
            values = ((HK_CALL, "CALL", 500), (HK_PUT, "PUT", 500))
        else:
            return []
        return [
            _option_contract(code, option_type, normalized, expiration, strike)
            for code, option_type, strike in values
        ]

    def option_analytics(self, code: str) -> dict[str, Any]:
        self._raise_if_failed()
        normalized = code.strip().upper()
        with self._lock:
            snapshot = self.snapshots_by_code.get(normalized)
            implied_volatility = (
                snapshot.get("option_implied_volatility")
                if snapshot is not None
                else None
            )
        return {
            "code": normalized,
            "volatility_history": [
                {
                    "implied_volatility": implied_volatility,
                    "historical_volatility": 20,
                }
            ],
            "exercise_probability_history": [],
        }

    def subscription_status(self) -> dict[str, Any]:
        self._raise_if_failed()
        with self._lock:
            own = sorted(self.owned_codes)
            all_codes = sorted(self.external_codes | self.owned_codes)
        return {
            "scope": "all_connections_all_security_types",
            "generic_total_used": len(all_codes),
            "generic_own_used": len(own),
            "generic_remaining": max(20 - len(all_codes), 0),
            "subscriptions": {"QUOTE": all_codes},
        }

    def subscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        self._raise_if_failed()
        requested = sorted(
            dict.fromkeys(code.strip().upper() for code in codes if code.strip())
        )
        with self._lock:
            self.subscribe_calls.append(requested)
            self.owned_codes.update(requested)
        return self.subscription_status()

    def unsubscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        requested = sorted(
            dict.fromkeys(code.strip().upper() for code in codes if code.strip())
        )
        with self._lock:
            self.unsubscribe_calls.append(requested)
            self.owned_codes.difference_update(requested)
            own = sorted(self.owned_codes)
            all_codes = sorted(self.external_codes | self.owned_codes)
        return {
            "scope": "all_connections_all_security_types",
            "generic_total_used": len(all_codes),
            "generic_own_used": len(own),
            "generic_remaining": max(20 - len(all_codes), 0),
            "subscriptions": {"QUOTE": all_codes},
        }

    def close(self) -> None:
        with self._lock:
            self.close_calls += 1
            self.closed = True

    def evidence(self) -> dict[str, Any]:
        with self._lock:
            return {
                "failure_mode": self.failure_mode,
                "owned_codes": sorted(self.owned_codes),
                "external_codes": sorted(self.external_codes),
                "subscribe_calls": [list(call) for call in self.subscribe_calls],
                "unsubscribe_calls": [list(call) for call in self.unsubscribe_calls],
                "close_calls": self.close_calls,
                "closed": self.closed,
            }

    def _raise_if_failed(self) -> None:
        with self._lock:
            failure_mode = self.failure_mode
        if failure_mode == "permission":
            raise OpenDRequestError(
                "fixture quote permission denied; authority is unavailable"
            )
        if failure_mode == "quota":
            raise OpenDRequestError("fixture generic subscription quota exhausted")


class FixtureSymbolDirectory:
    """Keep symbol search deterministic while the production router stays real."""

    _symbols = (
        {"code": US_STOCK, "name": "Apple", "market": "US"},
        {"code": HK_STOCK, "name": "Tencent", "market": "HK"},
    )

    def search(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        normalized = query.strip().upper()
        if not normalized:
            return []
        matches = [
            dict(item)
            for item in self._symbols
            if normalized in item["code"] or normalized in item["name"].upper()
        ]
        return matches[:limit]

    def resolve(self, codes: list[str]) -> list[dict[str, str]]:
        requested = {code.strip().upper() for code in codes}
        return [dict(item) for item in self._symbols if item["code"] in requested]


class SwitchableMonitoringService:
    """Delegate production router calls to the current service generation."""

    def __init__(self, service: MonitoringService) -> None:
        self._service = service

    @property
    def current(self) -> MonitoringService:
        return self._service

    def replace(self, service: MonitoringService) -> None:
        self._service = service

    async def start(self) -> None:
        await self._service.start()

    async def stop(self) -> None:
        await self._service.stop()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)


class MonitoringBrowserRuntime:
    """Own fixture state while delegating domain behavior to production code."""

    def __init__(
        self,
        state_path: Path,
        events: EventBroker,
        *,
        poll_interval_seconds: float = 3_600,
    ) -> None:
        self.state_path = state_path.resolve()
        self.events = events
        self.clock = FixtureClock()
        self.poll_interval_seconds = poll_interval_seconds
        first_market = FixtureMonitoringMarketData(self.clock)
        first_service = self._new_service(first_market)
        self.proxy = SwitchableMonitoringService(first_service)
        self.gateways = [first_market]
        self.restart_count = 0
        self._restart_lock = asyncio.Lock()

    @property
    def service(self) -> MonitoringService:
        return self.proxy.current

    @property
    def market_data(self) -> FixtureMonitoringMarketData:
        return cast(FixtureMonitoringMarketData, self.service.market_data)

    async def apply_scenario(
        self,
        scenario: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = scenario.strip().lower()
        if normalized not in SCENARIOS:
            raise ValueError(
                f"unknown fixture scenario {scenario!r}; "
                f"expected one of {sorted(SCENARIOS)}"
            )
        values = dict(payload or {})
        market = self.market_data
        if normalized in {"permission", "quota"}:
            market.set_failure(normalized)
            self._set_service_phase(
                "degraded",
                f"fixture {normalized} state is active",
            )
            return self.describe(scenario=normalized)
        if normalized == "reconnecting":
            market.set_failure(None)
            self._set_service_phase(
                "reconnecting",
                "fixture reconnect is pending",
            )
            return self.describe(scenario=normalized)

        market.set_failure(None)
        if normalized == "baseline":
            self.clock.advance(float(values.get("advance_seconds", 1)))
            market.set_values(
                stock_price=float(values.get("stock_price", 99)),
                option_iv=float(values.get("option_iv", 25)),
                source_at=self.clock.now() - timedelta(seconds=1),
            )
        elif normalized == "edge":
            self.clock.advance(float(values.get("advance_seconds", 10)))
            market.set_values(
                stock_price=float(values.get("stock_price", 101)),
                option_iv=float(values.get("option_iv", 35)),
                source_at=self.clock.now() - timedelta(seconds=1),
            )
        elif normalized == "reset":
            self.clock.advance(float(values.get("advance_seconds", 10)))
            market.set_values(
                stock_price=float(values.get("stock_price", 95)),
                option_iv=float(values.get("option_iv", 20)),
                source_at=self.clock.now() - timedelta(seconds=1),
            )
        elif normalized == "out-of-order":
            current_price, current_iv = market.values()
            market.set_values(
                stock_price=float(values.get("stock_price", current_price - 3)),
                option_iv=float(values.get("option_iv", current_iv - 10)),
                source_at=market.provider_time()
                - timedelta(seconds=float(values.get("older_by_seconds", 5))),
            )
        elif normalized == "stale":
            current_price, current_iv = market.values()
            market.set_values(
                stock_price=float(values.get("stock_price", current_price)),
                option_iv=float(values.get("option_iv", current_iv)),
                source_at=self.clock.now()
                - timedelta(
                    seconds=float(
                        values.get(
                            "age_seconds",
                            self.service.freshness_seconds + 5,
                        )
                    )
                ),
            )
        elif normalized == "recover":
            current_price, current_iv = market.values()
            self.clock.advance(float(values.get("advance_seconds", 10)))
            self._set_service_phase("reconnecting", "fixture recovery started")
            market.set_values(
                stock_price=float(values.get("stock_price", current_price)),
                option_iv=float(values.get("option_iv", current_iv)),
                source_at=self.clock.now() - timedelta(seconds=1),
            )
        # "duplicate" intentionally reuses the exact provider timestamp and values.
        await self.service.poll_once()
        return self.describe(scenario=normalized)

    async def poll(self) -> dict[str, Any]:
        try:
            await self.service.poll_once()
        except Exception as error:
            return {
                **self.describe(scenario="poll"),
                "poll_error": str(error),
            }
        return self.describe(scenario="poll")

    async def restart(self) -> dict[str, Any]:
        async with self._restart_lock:
            previous_service = self.service
            previous_market = self.market_data
            await previous_service.stop()
            next_market = previous_market.clone()
            next_market.set_failure(None)
            next_service = self._new_service(next_market)
            self.gateways.append(next_market)
            self.proxy.replace(next_service)
            self.restart_count += 1
            await next_service.start()
            await self._wait_for_initial_poll(next_service)
            return self.describe(scenario="restart")

    def describe(self, *, scenario: str = "state") -> dict[str, Any]:
        repository = self.service.repository
        alerts = repository.list_alerts(limit=100)
        return {
            "scenario": scenario,
            "state_path": str(self.state_path),
            "restart_count": self.restart_count,
            "clock": self.clock.now().isoformat(timespec="seconds"),
            "service": self.service.status(),
            "watchlist_count": len(repository.list_instruments()),
            "rule_count": len(repository.list_rules()),
            "alert_count": len(alerts),
            "gateway": self.market_data.evidence(),
            "retired_gateways": [gateway.evidence() for gateway in self.gateways[:-1]],
        }

    def _new_service(
        self,
        market_data: FixtureMonitoringMarketData,
    ) -> MonitoringService:
        return MonitoringService(
            MonitoringRepository(self.state_path),
            market_data,
            self.events,
            poll_interval_seconds=self.poll_interval_seconds,
            freshness_seconds=45,
            chain_cache_seconds=0.01,
            now=self.clock.now,
            monotonic_clock=self.clock.monotonic,
        )

    def _set_service_phase(self, phase: str, error: str | None) -> None:
        self.service._phase = phase
        self.service._last_error = error
        self.events.publish("monitor.status.updated", self.service.status())

    async def _wait_for_initial_poll(
        self,
        service: MonitoringService,
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2
        while service.status()["phase"] in {"starting", "stopped"}:
            if loop.time() >= deadline:
                raise TimeoutError("restarted monitoring service did not initialize")
            await asyncio.sleep(0.01)


def create_fixture_app(
    *,
    project_root: Path,
    state_path: Path | None = None,
    frontend_root: Path | None = None,
) -> FastAPI:
    """Build the production app plus schema-hidden browser controls."""

    root = project_root.resolve()
    for name in ("examples", "strategies", "data", "runs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    database_path = (
        state_path.resolve()
        if state_path is not None
        else root / "runs" / "state.sqlite3"
    )
    events = EventBroker()
    store = JobStore(root, event_broker=events)
    runtime = MonitoringBrowserRuntime(database_path, events)
    app = create_app(
        project_root=root,
        job_store=store,
        frontend_root=frontend_root,
        opend_probe=lambda _host, _port: True,
        symbol_directory=cast(OpenDSymbolDirectory, FixtureSymbolDirectory()),
        monitoring_service=cast(MonitoringService, runtime.proxy),
    )
    app.state.monitoring_fixture = runtime
    _install_fixture_routes(app, runtime)
    return app


def _install_fixture_routes(
    app: FastAPI,
    runtime: MonitoringBrowserRuntime,
) -> None:
    router = APIRouter(prefix="/_test/monitoring", include_in_schema=False)

    @router.get("/state", include_in_schema=False)
    async def fixture_state() -> dict[str, Any]:
        return runtime.describe()

    @router.post("/poll", include_in_schema=False)
    async def fixture_poll() -> dict[str, Any]:
        return await runtime.poll()

    @router.post("/restart", include_in_schema=False)
    async def fixture_restart() -> dict[str, Any]:
        return await runtime.restart()

    @router.post("/scenario/{scenario}", include_in_schema=False)
    async def fixture_scenario(
        scenario: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await runtime.apply_scenario(scenario, payload)
        except ValueError as error:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=str(error)) from error

    existing_routes = list(app.router.routes)
    app.include_router(router)
    fixture_routes = app.router.routes[len(existing_routes) :]
    fallback_index = next(
        (
            index
            for index, route in enumerate(existing_routes)
            if getattr(route, "path", None) == "/{frontend_path:path}"
        ),
        len(existing_routes),
    )
    app.router.routes[:] = [
        *existing_routes[:fallback_index],
        *fixture_routes,
        *existing_routes[fallback_index:],
    ]
    app.openapi_schema = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        choices=("127.0.0.1", "localhost"),
        default="127.0.0.1",
        help="The fixture is deliberately restricted to a loopback bind.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("runs/acceptance/monitoring-browser-fixture.sqlite3"),
    )
    parser.add_argument("--frontend-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65_535:
        raise SystemExit("port must be between 1 and 65535")
    state_path = args.state_path.resolve()
    fixture_root = state_path.parent / ".monitoring-browser-fixture"
    frontend_root = (
        args.frontend_root.resolve() if args.frontend_root is not None else None
    )
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "web dependencies missing; install with: pip install -e './backend[web]'"
        ) from None
    uvicorn.run(
        create_fixture_app(
            project_root=fixture_root,
            state_path=state_path,
            frontend_root=frontend_root,
        ),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


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
    underlying: str,
    expiration: str,
    *,
    strike_price: float,
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
        "underlying_code": underlying,
        "strike_price": strike_price,
        "expiration": expiration,
        "days_to_expiry": 11,
        "option_contract_size": 100,
    }


def _option_contract(
    code: str,
    option_type: str,
    underlying: str,
    expiration: str,
    strike_price: float,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": f"{underlying} {option_type} {strike_price:g}",
        "underlying_code": underlying,
        "option_type": option_type,
        "expiration": expiration,
        "strike_price": strike_price,
        "lot_size": 100,
    }


if __name__ == "__main__":
    raise SystemExit(main())
