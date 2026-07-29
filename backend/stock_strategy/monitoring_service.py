from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

from .event_stream import EventBroker
from .monitoring_market_data import MonitoringMarketDataSource
from .monitoring_models import (
    InstrumentType,
    RuleMetric,
    RuleOperator,
    RuleSeverity,
    validate_rule_metric,
)
from .monitoring_repository import MonitoringRepository
from .monitoring_rule_engine import (
    MarketSession,
    RuleSuppressionReason,
    decide_rule,
)
from .monitoring_subscriptions import (
    GenericSubscriptionBudget,
    SubscriptionIntent,
    SubscriptionPlanner,
    SubscriptionTarget,
)
from .technical_indicators import (
    IndicatorBar,
    closed_bar_sma,
    closed_bar_wilder_rsi,
)

_REGULAR_MARKET_STATES = frozenset({"MORNING", "AFTERNOON", "OPEN", "TRADING"})
_EXTENDED_MARKET_STATES = frozenset(
    {"PRE_MARKET", "AFTER_HOURS", "OVERNIGHT", "NIGHT_OPEN"}
)
_CLOSED_MARKET_STATES = frozenset({"CLOSED", "REST", "NONE", "NOT_OPEN", "CLOSE"})
_INDICATOR_METRICS = frozenset(
    {
        RuleMetric.MA20,
        RuleMetric.MA60,
        RuleMetric.MA20_MA60_SPREAD_PCT,
        RuleMetric.RSI14,
    }
)
_CHAIN_METRICS = frozenset(
    {
        RuleMetric.CALL_PUT_VOLUME_RATIO,
        RuleMetric.CALL_PUT_OPEN_INTEREST_RATIO,
    }
)


class MonitoringService:
    """Coordinate durable monitoring state, OpenD reads, rules, and SSE."""

    def __init__(
        self,
        repository: MonitoringRepository,
        market_data: MonitoringMarketDataSource,
        events: EventBroker,
        *,
        poll_interval_seconds: float = 3.0,
        freshness_seconds: float = 45.0,
        chain_cache_seconds: float = 5.0,
        request_timeout_seconds: float = 10.0,
        now: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("monitor poll interval must be positive")
        if freshness_seconds <= 0:
            raise ValueError("monitor freshness threshold must be positive")
        if request_timeout_seconds <= 0:
            raise ValueError("monitor request timeout must be positive")
        self.repository = repository
        self.market_data = market_data
        self.events = events
        self.poll_interval_seconds = poll_interval_seconds
        self.freshness_seconds = freshness_seconds
        self.chain_cache_seconds = chain_cache_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self._now = now or (lambda: datetime.now().astimezone())
        self._monotonic = monotonic_clock or monotonic
        self._planner = SubscriptionPlanner()
        self._phase = "stopped"
        self._last_success_at: str | None = None
        self._last_error: str | None = None
        self._market_states: dict[str, str] = {}
        self._generic_subscription_budget: dict[str, Any] | None = None
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._owned_subscriptions: set[SubscriptionTarget] = set()
        self._temporary_intents: dict[SubscriptionTarget, SubscriptionIntent] = {}
        self._chain_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        self._expiration_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._bar_cache: dict[
            tuple[str, str, int], tuple[float, list[dict[str, Any]]]
        ] = {}
        self._contracts: dict[str, dict[str, Any]] = {}
        self._rebaseline_rules: set[str] = set()
        self._poll_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._phase = "starting"
        self._last_error = None
        self._task = asyncio.create_task(
            self._supervise(),
            name="strategy-lab-monitoring",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        owned_codes = sorted({target.code for target in self._owned_subscriptions})
        if owned_codes:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        self.market_data.unsubscribe_quotes,
                        owned_codes,
                    ),
                    timeout=5,
                )
            except (Exception, TimeoutError):
                pass
        self._owned_subscriptions.clear()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.market_data.close),
                timeout=5,
            )
        except (Exception, TimeoutError):
            pass
        self._phase = "stopped"

    def status(self) -> dict[str, Any]:
        freshness = {
            code: self._snapshot_freshness(snapshot)[0]
            for code, snapshot in self._snapshots.items()
        }
        return {
            "phase": self._phase,
            "rules_paused": self._phase != "ready",
            "last_success_at": self._last_success_at,
            "last_error": self._last_error,
            "market_states": dict(self._market_states),
            "generic_subscription_budget": (
                dict(self._generic_subscription_budget)
                if self._generic_subscription_budget is not None
                else None
            ),
            "freshness": freshness,
            "owned_subscription_targets": [
                {"code": target.code, "subtype": target.subtype}
                for target in sorted(self._owned_subscriptions)
            ],
        }

    async def diagnostics(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        try:
            global_state = await self._call_market(self.market_data.global_state)
        except Exception as error:
            checks.append(
                _diagnostic_check(
                    "opend_rpc",
                    "fail",
                    f"OpenD monitoring RPC failed: {error}",
                    "Confirm OpenD is running and quote login is available.",
                )
            )
        else:
            checks.append(
                _diagnostic_check(
                    "opend_rpc",
                    "pass",
                    (
                        "OpenD monitoring RPC readable"
                        f" · server {global_state.get('server_version') or 'unknown'}"
                    ),
                )
            )

        stock_snapshot: dict[str, Any] | None = None
        try:
            values = await self._call_market(
                self.market_data.snapshots,
                ["US.AAPL"],
            )
            stock_snapshot = dict(values[0]) if values else None
            if stock_snapshot is None:
                raise RuntimeError("empty stock snapshot")
        except Exception as error:
            checks.append(
                _diagnostic_check(
                    "stock_quote",
                    "fail",
                    f"US stock quote probe failed: {error}",
                    "Confirm US stock quote authority in OpenD.",
                )
            )
        else:
            checks.append(
                _diagnostic_check(
                    "stock_quote",
                    "pass",
                    "US stock snapshot readable · US.AAPL",
                )
            )

        option_snapshots: list[dict[str, Any]] = []
        for market, underlying in (("us", "US.AAPL"), ("hk", "HK.00700")):
            option_check, option_snapshot = await self._option_diagnostic(
                market,
                underlying,
            )
            checks.append(option_check)
            if option_snapshot is not None:
                option_snapshots.append(option_snapshot)

        try:
            budget = await self._call_market(self.market_data.subscription_status)
        except Exception as error:
            checks.append(
                _diagnostic_check(
                    "generic_subscription",
                    "fail",
                    f"Generic subscription status failed: {error}",
                    "Inspect OpenD subscription permissions and connection state.",
                )
            )
        else:
            checks.append(
                _diagnostic_check(
                    "generic_subscription",
                    "pass",
                    (
                        "Generic all-security subscription usage"
                        f" · own {budget.get('generic_own_used', 0)}"
                        f" · remaining {budget.get('generic_remaining', 0)}"
                    ),
                )
            )

        freshness_values = [
            self._snapshot_freshness(snapshot)[0]
            for snapshot in [
                *([stock_snapshot] if stock_snapshot is not None else []),
                *option_snapshots,
            ]
        ]
        if not freshness_values:
            checks.append(
                _diagnostic_check(
                    "quote_freshness",
                    "blocked",
                    "Quote freshness requires at least one readable snapshot",
                )
            )
        elif any(value == "stale" for value in freshness_values):
            checks.append(
                _diagnostic_check(
                    "quote_freshness",
                    "fail",
                    f"Stale monitoring snapshots detected: {freshness_values}",
                    "Check market state, OpenD connectivity, and quote authority.",
                )
            )
        else:
            checks.append(
                _diagnostic_check(
                    "quote_freshness",
                    "pass",
                    f"Snapshot states: {', '.join(freshness_values)}",
                )
            )
        return {
            "ready": all(check["status"] == "pass" for check in checks),
            "checks": checks,
        }

    async def poll_once(self) -> None:
        async with self._poll_lock:
            previous_phase = self._phase
            self._phase = (
                "reconnecting"
                if previous_phase in {"degraded", "reconnecting"}
                else "starting"
            )
            try:
                instruments = await asyncio.to_thread(self.repository.list_instruments)
                rules = await asyncio.to_thread(
                    self.repository.list_rules,
                    enabled=True,
                )
                if previous_phase != "ready":
                    self._rebaseline_rules.update(str(rule["id"]) for rule in rules)
                targets = {
                    str(item["code"]) for item in instruments if bool(item["enabled"])
                }
                targets.update(str(rule["code"]) for rule in rules)
                if (
                    not targets
                    and not self._owned_subscriptions
                    and not self._temporary_intents
                ):
                    self._phase = "ready"
                    self._last_success_at = _iso(self._now())
                    self._last_error = None
                    return

                global_state = await self._call_market(self.market_data.global_state)
                self._market_states = {
                    str(key).lower(): str(value).upper()
                    for key, value in dict(
                        global_state.get("market_states") or {}
                    ).items()
                }
                budget = await self._call_market(self.market_data.subscription_status)
                self._generic_subscription_budget = dict(budget)
                await self._reconcile_subscriptions(
                    budget,
                    instruments=instruments,
                    rules=rules,
                )
                snapshots = (
                    await self._call_market(
                        self.market_data.snapshots,
                        sorted(targets),
                    )
                    if targets
                    else []
                )
                for snapshot in snapshots:
                    code = str(snapshot["code"])
                    self._snapshots[code] = dict(snapshot)
                    self.events.publish(
                        "monitor.quote.updated",
                        {"code": code, "snapshot": dict(snapshot)},
                    )
                self._phase = "ready"
                await self._evaluate_rules(rules)
                self._last_success_at = _iso(self._now())
                self._last_error = None
                self.events.publish(
                    "monitor.status.updated",
                    self.status(),
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._phase = "degraded"
                self._last_error = str(error)
                self.events.publish(
                    "monitor.status.updated",
                    self.status(),
                )
                raise

    def list_instruments(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for instrument in self.repository.list_instruments():
            item = dict(instrument)
            snapshot = self._snapshots.get(str(item["code"]))
            item["snapshot"] = dict(snapshot) if snapshot is not None else None
            item["freshness"] = (
                self._snapshot_freshness(snapshot)[0]
                if snapshot is not None
                else "unavailable"
            )
            result.append(item)
        return result

    def add_instrument(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        code = _normalize_code(str(payload["code"]))
        now = _iso(self._now())
        try:
            existing = self.repository.get_instrument(code)
        except KeyError:
            existing = None
        instrument = self.repository.upsert_instrument(
            {
                "code": code,
                "name": str(payload["name"]).strip(),
                "market": code.split(".", 1)[0],
                "instrument_type": str(payload.get("instrument_type") or "stock"),
                "underlying_code": payload.get("underlying_code"),
                "enabled": bool(payload.get("enabled", True)),
                "created_at": (
                    str(existing["created_at"]) if existing is not None else now
                ),
                "updated_at": now,
            }
        )
        self.events.publish(
            "monitor.watchlist.updated",
            {"action": "upserted", "instrument": instrument},
        )
        return instrument

    def update_instrument(
        self,
        code: str,
        updates: Mapping[str, Any],
    ) -> dict[str, Any]:
        current = self.repository.get_instrument(_normalize_code(code))
        merged = {**current, **dict(updates), "updated_at": _iso(self._now())}
        instrument = self.repository.upsert_instrument(merged)
        self.events.publish(
            "monitor.watchlist.updated",
            {"action": "updated", "instrument": instrument},
        )
        return instrument

    def delete_instrument(self, code: str) -> None:
        normalized = _normalize_code(code)
        self.repository.delete_instrument(normalized)
        self._snapshots.pop(normalized, None)
        self.events.publish(
            "monitor.watchlist.updated",
            {"action": "deleted", "code": normalized},
        )

    async def snapshot(self, code: str) -> dict[str, Any]:
        normalized = _normalize_code(code)
        values = await self._call_market(
            self.market_data.snapshots,
            [normalized],
        )
        if not values:
            raise KeyError(normalized)
        enriched = await self._enrich_snapshot(
            dict(values[0]),
            {
                RuleMetric.MA20,
                RuleMetric.MA60,
                RuleMetric.RSI14,
                RuleMetric.CHANGE_RATE_5M,
            },
        )
        self._snapshots[normalized] = enriched
        freshness, age = self._snapshot_freshness(enriched)
        return {
            "snapshot": enriched,
            "freshness": freshness,
            "market_state": self._market_state(normalized),
            "age_seconds": age,
        }

    async def expirations(self, underlying: str) -> dict[str, Any]:
        code = _normalize_code(underlying)
        cached = self._expiration_cache.get(code)
        if cached is not None and self._monotonic() - cached[0] < 300:
            return _copy_payload(cached[1])
        values = await self._call_market(
            self.market_data.option_expirations,
            code,
        )
        payload = {
            "underlying": code,
            "expirations": values,
            "fetched_at": _iso(self._now()),
        }
        self._expiration_cache[code] = (self._monotonic(), payload)
        return _copy_payload(payload)

    async def option_chain(
        self,
        underlying: str,
        expiration: str,
    ) -> dict[str, Any]:
        code = _normalize_code(underlying)
        normalized_expiration = _normalize_expiration(expiration)
        key = (code, normalized_expiration)
        cached = self._chain_cache.get(key)
        if (
            cached is not None
            and self._monotonic() - cached[0] < self.chain_cache_seconds
        ):
            return _copy_payload(cached[1])

        contracts = await self._call_market(
            self.market_data.option_chain,
            code,
            normalized_expiration,
        )
        contract_codes = [str(contract["code"]) for contract in contracts]
        snapshots = await self._call_market(
            self.market_data.snapshots,
            [code, *contract_codes],
        )
        by_code = {str(snapshot["code"]): dict(snapshot) for snapshot in snapshots}
        underlying_snapshot = by_code.get(code)
        if underlying_snapshot is None:
            raise KeyError(code)
        underlying_price = _number(underlying_snapshot.get("last_price"))
        merged_contracts: list[dict[str, Any]] = []
        for contract in contracts:
            contract_code = str(contract["code"])
            merged = {
                **dict(contract),
                **by_code.get(contract_code, {}),
                "underlying_price": underlying_price,
                "open_interest_update_cadence": "daily_as_of",
            }
            _add_quote_derived_fields(merged)
            merged_contracts.append(merged)
            self._contracts[contract_code] = dict(merged)
            if contract_code in by_code:
                self._snapshots[contract_code] = dict(merged)
        self._snapshots[code] = dict(underlying_snapshot)
        summary = _option_chain_summary(merged_contracts, underlying_price)
        for contract in merged_contracts:
            contract.update(
                call_put_volume_ratio=summary["call_put_volume_ratio"],
                call_put_open_interest_ratio=summary["call_put_open_interest_ratio"],
            )
        payload = {
            "underlying": code,
            "expiration": normalized_expiration,
            "underlying_snapshot": underlying_snapshot,
            "contracts": merged_contracts,
            "summary": summary,
            "fetched_at": _iso(self._now()),
            "source": "opend",
        }
        self._chain_cache[key] = (self._monotonic(), payload)
        return _copy_payload(payload)

    async def option_contract(self, code: str) -> dict[str, Any]:
        normalized = _normalize_code(code)
        snapshots = await self._call_market(
            self.market_data.snapshots,
            [normalized],
        )
        if not snapshots:
            raise KeyError(normalized)
        snapshot = dict(snapshots[0])
        underlying_code = snapshot.get("underlying_code")
        if underlying_code:
            underlying_values = await self._call_market(
                self.market_data.snapshots,
                [str(underlying_code)],
            )
            if underlying_values:
                snapshot["underlying_price"] = underlying_values[0].get("last_price")
        analytics = await self._call_market(
            self.market_data.option_analytics,
            normalized,
        )
        _add_quote_derived_fields(snapshot)
        self._snapshots[normalized] = snapshot
        known = self._contracts.get(normalized, {})
        contract = {**known, **snapshot}
        self._contracts[normalized] = contract
        intent = SubscriptionIntent.temporary_page_interest(
            normalized,
            now=self._monotonic(),
            ttl_seconds=30,
        )
        self._temporary_intents[intent.target] = intent
        return {
            "contract": contract,
            "analytics": analytics,
            "freshness": self._snapshot_freshness(snapshot)[0],
        }

    async def bars(
        self,
        code: str,
        *,
        count: int,
        ktype: str,
    ) -> dict[str, Any]:
        normalized = _normalize_code(code)
        values = await self._load_bars(normalized, count=count, ktype=ktype)
        return {"code": normalized, "ktype": ktype, "bars": values}

    def list_rules(
        self,
        *,
        code: str | None = None,
        underlying_code: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        return self.repository.list_rules(
            code=_normalize_code(code) if code is not None else None,
            underlying_code=(
                _normalize_code(underlying_code)
                if underlying_code is not None
                else None
            ),
            enabled=enabled,
        )

    def create_rule(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        instrument_type = InstrumentType(str(payload["instrument_type"]))
        metric = RuleMetric(str(payload["metric"]))
        validate_rule_metric(instrument_type, metric)
        code = _normalize_code(str(payload["code"]))
        requested_underlying = payload.get("underlying_code")
        if instrument_type is InstrumentType.STOCK:
            underlying_code = (
                _normalize_code(str(requested_underlying))
                if requested_underlying is not None
                else code
            )
            if underlying_code != code:
                raise ValueError("stock rule underlying_code must match the rule code")
        else:
            if requested_underlying is None:
                raise ValueError("option rule underlying_code is required")
            underlying_code = _normalize_code(str(requested_underlying))
            if underlying_code.split(".", 1)[0] != code.split(".", 1)[0]:
                raise ValueError(
                    "option rule and underlying_code must use the same market"
                )
        now = _iso(self._now())
        rule = self.repository.create_rule(
            {
                "id": f"rule-{uuid.uuid4().hex}",
                "name": str(payload["name"]).strip(),
                "code": code,
                "underlying_code": underlying_code,
                "instrument_type": instrument_type.value,
                "metric": metric.value,
                "operator": RuleOperator(str(payload["operator"])).value,
                "threshold": float(payload["threshold"]),
                "severity": RuleSeverity(str(payload["severity"])).value,
                "cooldown_seconds": int(payload.get("cooldown_seconds", 300)),
                "daily_trigger_limit": int(payload.get("daily_trigger_limit", 10)),
                "session": str(payload.get("session", "regular")),
                "enabled": bool(payload.get("enabled", True)),
                "created_at": now,
                "updated_at": now,
            }
        )
        self.events.publish(
            "monitor.rule.updated",
            {"action": "created", "rule": rule},
        )
        return rule

    def update_rule(
        self,
        rule_id: str,
        updates: Mapping[str, Any],
    ) -> dict[str, Any]:
        current = self.repository.get_rule(rule_id)
        normalized = dict(updates)
        if "metric" in normalized:
            validate_rule_metric(
                InstrumentType(str(current["instrument_type"])),
                RuleMetric(str(normalized["metric"])),
            )
        normalized["updated_at"] = _iso(self._now())
        rule = self.repository.update_rule(rule_id, normalized)
        self.events.publish(
            "monitor.rule.updated",
            {"action": "updated", "rule": rule},
        )
        return rule

    def delete_rule(self, rule_id: str) -> None:
        self.repository.delete_rule(rule_id)
        self.events.publish(
            "monitor.rule.updated",
            {"action": "deleted", "rule_id": rule_id},
        )

    def alerts(
        self,
        *,
        code: str | None,
        underlying_code: str | None = None,
        unacknowledged_only: bool,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        before = _decode_cursor(cursor) if cursor is not None else None
        alerts, has_more = self.repository.list_alerts_page(
            code=_normalize_code(code) if code is not None else None,
            underlying_code=(
                _normalize_code(underlying_code)
                if underlying_code is not None
                else None
            ),
            unacknowledged_only=unacknowledged_only,
            before=before,
            limit=limit,
        )
        next_cursor = (
            _encode_cursor(
                str(alerts[-1]["triggered_at"]),
                str(alerts[-1]["id"]),
            )
            if has_more and alerts
            else None
        )
        return {"alerts": alerts, "next_cursor": next_cursor}

    def acknowledge_alert(self, alert_id: str) -> dict[str, Any]:
        alert = self.repository.acknowledge_alert(
            alert_id,
            _iso(self._now()),
        )
        self.events.publish(
            "monitor.alert.acknowledged",
            {"alert": alert},
        )
        return alert

    async def _supervise(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(self.poll_interval_seconds)

    async def _option_diagnostic(
        self,
        market: str,
        underlying: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        check_id = f"{market}_options"
        try:
            expirations = await self._call_market(
                self.market_data.option_expirations,
                underlying,
            )
            if not expirations:
                return (
                    _diagnostic_check(
                        check_id,
                        "blocked",
                        f"No active option expiration for {underlying}",
                        "The market may have no listed unexpired contracts.",
                    ),
                    None,
                )
            expiration = str(expirations[0]["expiration"])
            contracts = await self._call_market(
                self.market_data.option_chain,
                underlying,
                expiration,
            )
            if not contracts:
                return (
                    _diagnostic_check(
                        check_id,
                        "blocked",
                        f"No contracts returned for {underlying} {expiration}",
                    ),
                    None,
                )
            contract_code = str(contracts[0]["code"])
            snapshots = await self._call_market(
                self.market_data.snapshots,
                [contract_code],
            )
            if not snapshots:
                raise RuntimeError(
                    "static chain succeeded but option snapshot is empty"
                )
            snapshot = dict(snapshots[0])
        except Exception as error:
            return (
                _diagnostic_check(
                    check_id,
                    "fail",
                    f"{market.upper()} option probe failed: {error}",
                    (
                        "Confirm the corresponding option quote authority; "
                        "static chain access alone is insufficient."
                    ),
                ),
                None,
            )
        return (
            _diagnostic_check(
                check_id,
                "pass",
                (
                    f"{market.upper()} option chain and dynamic snapshot readable"
                    f" · {contract_code}"
                ),
            ),
            snapshot,
        )

    async def _reconcile_subscriptions(
        self,
        status: Mapping[str, Any],
        *,
        instruments: list[dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> None:
        intents: list[SubscriptionIntent] = [
            SubscriptionIntent.watchlist(str(item["code"]))
            for item in instruments
            if bool(item["enabled"])
        ]
        intents.extend(
            SubscriptionIntent.persistent_rule(str(rule["code"])) for rule in rules
        )
        intents.extend(self._temporary_intents.values())
        budget = GenericSubscriptionBudget(
            generic_total_used=int(status.get("generic_total_used") or 0),
            generic_own_used=int(status.get("generic_own_used") or 0),
            generic_remaining=int(status.get("generic_remaining") or 0),
        )
        plan = self._planner.plan(
            intents=intents,
            actual_owned=self._owned_subscriptions,
            budget=budget,
            now=self._monotonic(),
        )
        if plan.to_unsubscribe:
            codes = sorted({target.code for target in plan.to_unsubscribe})
            await self._call_market(
                self.market_data.unsubscribe_quotes,
                codes,
            )
            self._owned_subscriptions.difference_update(plan.to_unsubscribe)
        if plan.to_subscribe:
            codes = sorted({target.code for target in plan.to_subscribe})
            await self._call_market(
                self.market_data.subscribe_quotes,
                codes,
            )
            self._owned_subscriptions.update(plan.to_subscribe)
        for intent in plan.expired_intents:
            self._temporary_intents.pop(intent.target, None)
        self.events.publish(
            "monitor.subscription.updated",
            {
                "owned": [
                    {"code": target.code, "subtype": target.subtype}
                    for target in sorted(self._owned_subscriptions)
                ],
                "deferred": [
                    {"code": target.code, "subtype": target.subtype}
                    for target in plan.deferred
                ],
                "generic_budget": dict(status),
            },
        )

    async def _evaluate_rules(self, rules: list[dict[str, Any]]) -> None:
        for rule in rules:
            code = str(rule["code"])
            snapshot = self._snapshots.get(code)
            if snapshot is None:
                continue
            metric = RuleMetric(str(rule["metric"]))
            enriched = await self._enrich_snapshot(dict(snapshot), {metric})
            self._snapshots[code] = enriched
            provider_time = _provider_datetime(
                code,
                enriched.get("source_time"),
            )
            if provider_time is None:
                continue
            freshness, _age = self._snapshot_freshness(enriched)
            rebaseline = str(rule["id"]) in self._rebaseline_rules
            decision_rule = (
                {**rule, "last_value": None, "condition_active": False}
                if rebaseline
                else rule
            )
            decision = decide_rule(
                decision_rule,
                enriched,
                observed_at=self._now(),
                provider_time=provider_time,
                is_fresh=freshness == "live",
                reconnecting=False,
                market_session=self._market_session(code),
            )
            if not decision.evaluated or decision.value is None:
                continue
            if decision.condition_active is None:
                continue
            observation_key = f"{code}:{provider_time.isoformat()}:{metric.value}"
            alert_payload: dict[str, Any] | None = None
            triggered_at: str | None = None
            if decision.triggered:
                triggered_at = _iso(self._now())
                alert_payload = {
                    "id": f"alert-{uuid.uuid4().hex}",
                    "dedupe_key": (
                        f"{rule['id']}:{observation_key}:"
                        f"{RuleOperator(str(rule['operator'])).value}"
                    ),
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "code": code,
                    "underlying_code": rule.get("underlying_code"),
                    "triggered_at": triggered_at,
                    "severity": rule["severity"],
                    "metric": metric.value,
                    "operator": rule["operator"],
                    "threshold": rule["threshold"],
                    "value": decision.value,
                    "source": "opend",
                    "provider_time": provider_time.isoformat(),
                    "received_at": _iso(self._now()),
                    "snapshot": enriched,
                }
            updated, persisted_alert, applied = await asyncio.to_thread(
                self.repository.record_evaluation,
                str(rule["id"]),
                evaluated_at=_iso(self._now()),
                provider_time=_utc_iso(provider_time),
                observation_key=observation_key,
                value=decision.value,
                condition_active=decision.condition_active,
                alert=alert_payload,
                triggered_at=triggered_at,
                trigger_date=decision.trigger_date,
                increment_trigger=decision.triggered,
            )
            if not applied:
                continue
            self._rebaseline_rules.discard(str(rule["id"]))
            self.events.publish(
                "monitor.rule.updated",
                {"action": "evaluated", "rule": updated},
            )
            if persisted_alert is not None:
                self.events.publish(
                    "monitor.alert.triggered",
                    {"alert": persisted_alert},
                )
            elif decision.suppression_reason in {
                RuleSuppressionReason.COOLDOWN,
                RuleSuppressionReason.DAILY_LIMIT,
            }:
                self.events.publish(
                    "monitor.rule.suppressed",
                    {
                        "rule_id": rule["id"],
                        "reason": (
                            decision.suppression_reason.value
                            if decision.suppression_reason
                            else RuleSuppressionReason.DAILY_LIMIT.value
                        ),
                    },
                )

    async def _enrich_snapshot(
        self,
        snapshot: dict[str, Any],
        metrics: set[RuleMetric],
    ) -> dict[str, Any]:
        code = str(snapshot["code"])
        if metrics & _INDICATOR_METRICS:
            bars = await self._load_bars(code, count=62, ktype="K_DAY")
            indicator_bars = [
                IndicatorBar(
                    close=float(bar["close"]),
                    is_closed=bool(bar["is_closed"]),
                )
                for bar in bars
                if _number(bar.get("close")) is not None
            ]
            snapshot["ma20"] = closed_bar_sma(indicator_bars, 20)
            snapshot["ma60"] = closed_bar_sma(indicator_bars, 60)
            snapshot["rsi14"] = closed_bar_wilder_rsi(indicator_bars, 14)
        if RuleMetric.CHANGE_RATE_5M in metrics:
            bars = await self._load_bars(code, count=4, ktype="K_5M")
            closes = [
                float(bar["close"])
                for bar in bars
                if bool(bar["is_closed"]) and _number(bar.get("close")) is not None
            ]
            snapshot["change_rate_5m"] = (
                (closes[-1] - closes[-2]) / closes[-2] * 100
                if len(closes) >= 2 and closes[-2] > 0
                else None
            )
        if RuleMetric.IV_HV_PREMIUM in metrics:
            analytics = await self._call_market(
                self.market_data.option_analytics,
                code,
            )
            history = analytics.get("volatility_history") or []
            if history:
                latest = history[-1]
                snapshot["historical_volatility"] = _number(
                    (
                        latest.get("historical_volatility")
                        if latest.get("historical_volatility") is not None
                        else latest.get("history_volatility")
                    )
                    if isinstance(latest, Mapping)
                    else None
                )
        if metrics & {
            RuleMetric.STRIKE_DISTANCE_PCT,
            RuleMetric.EXPIRY_GAMMA_RISK,
            RuleMetric.EXPIRY_THETA_RISK,
        }:
            underlying_code = snapshot.get("underlying_code")
            if underlying_code:
                underlying = self._snapshots.get(str(underlying_code))
                if underlying is None:
                    values = await self._call_market(
                        self.market_data.snapshots,
                        [str(underlying_code)],
                    )
                    underlying = dict(values[0]) if values else None
                if underlying is not None:
                    snapshot["underlying_price"] = underlying.get("last_price")
        if metrics & _CHAIN_METRICS:
            underlying_code = snapshot.get("underlying_code")
            expiration = snapshot.get("expiration")
            if underlying_code and expiration:
                chain = await self.option_chain(
                    str(underlying_code),
                    str(expiration)[:10],
                )
                snapshot.update(chain["summary"])
        _add_quote_derived_fields(snapshot)
        return snapshot

    async def _load_bars(
        self,
        code: str,
        *,
        count: int,
        ktype: str,
    ) -> list[dict[str, Any]]:
        key = (code, ktype, count)
        cached = self._bar_cache.get(key)
        ttl = 20 if ktype == "K_5M" else 300
        if cached is not None and self._monotonic() - cached[0] < ttl:
            return [dict(bar) for bar in cached[1]]
        values = await self._call_market(
            self.market_data.recent_bars,
            code,
            count,
            ktype,
        )
        normalized = [dict(bar) for bar in values]
        self._bar_cache[key] = (self._monotonic(), normalized)
        return [dict(bar) for bar in normalized]

    async def _call_market(
        self,
        method: Callable[..., Any],
        *args: Any,
    ) -> Any:
        return await asyncio.wait_for(
            asyncio.to_thread(method, *args),
            timeout=self.request_timeout_seconds,
        )

    def _snapshot_freshness(
        self,
        snapshot: Mapping[str, Any] | None,
    ) -> tuple[str, float | None]:
        if snapshot is None:
            return "unavailable", None
        code = str(snapshot.get("code") or "")
        state = self._market_state(code)
        if state in _CLOSED_MARKET_STATES:
            return "market_closed", None
        provider_time = _provider_datetime(code, snapshot.get("source_time"))
        if provider_time is None:
            return "unavailable", None
        age = max(0.0, (self._now() - provider_time).total_seconds())
        return (
            ("live" if age <= self.freshness_seconds else "stale"),
            age,
        )

    def _market_state(self, code: str) -> str:
        market = code.split(".", 1)[0].lower()
        return self._market_states.get(market, "UNKNOWN").upper()

    def _market_session(self, code: str) -> MarketSession:
        state = self._market_state(code)
        if state in _REGULAR_MARKET_STATES:
            return MarketSession.REGULAR
        if state in _EXTENDED_MARKET_STATES:
            return MarketSession.EXTENDED
        if state in _CLOSED_MARKET_STATES:
            return MarketSession.CLOSED
        return MarketSession.UNKNOWN


def _option_chain_summary(
    contracts: list[dict[str, Any]],
    underlying_price: float | None,
) -> dict[str, float | int | None]:
    calls = [item for item in contracts if str(item.get("option_type")) == "CALL"]
    puts = [item for item in contracts if str(item.get("option_type")) == "PUT"]
    call_volume = _complete_sum(calls, "volume")
    put_volume = _complete_sum(puts, "volume")
    call_open_interest = _complete_sum(calls, "option_open_interest")
    put_open_interest = _complete_sum(puts, "option_open_interest")
    strikes = sorted(
        {
            value
            for item in contracts
            if (value := _number(item.get("strike_price"))) is not None
        }
    )
    atm_strike = (
        min(strikes, key=lambda strike: abs(strike - underlying_price))
        if strikes and underlying_price is not None
        else None
    )
    return {
        "contract_count": len(contracts),
        "strike_count": len(strikes),
        "atm_strike": atm_strike,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "call_open_interest": call_open_interest,
        "put_open_interest": put_open_interest,
        "call_put_volume_ratio": _safe_ratio(call_volume, put_volume),
        "call_put_open_interest_ratio": _safe_ratio(
            call_open_interest,
            put_open_interest,
        ),
    }


def _complete_sum(
    contracts: list[dict[str, Any]],
    field: str,
) -> float | None:
    values = [_number(contract.get(field)) for contract in contracts]
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _diagnostic_check(
    check_id: str,
    status: str,
    detail: str,
    hint: str | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "detail": detail,
        "hint": hint,
    }


def _add_quote_derived_fields(snapshot: dict[str, Any]) -> None:
    bid = _number(snapshot.get("bid_price"))
    ask = _number(snapshot.get("ask_price"))
    if bid is not None and ask is not None and ask >= bid:
        midpoint = (bid + ask) / 2
        snapshot["mid_price"] = midpoint
        snapshot["bid_ask_spread"] = ask - bid
        snapshot["bid_ask_spread_pct"] = (
            (ask - bid) / midpoint * 100 if midpoint > 0 else None
        )
    else:
        snapshot["mid_price"] = None
        snapshot["bid_ask_spread"] = None
        snapshot["bid_ask_spread_pct"] = None
    snapshot["volume_open_interest_ratio"] = _safe_ratio(
        _number(snapshot.get("volume")),
        _number(snapshot.get("option_open_interest")),
    )


def _provider_datetime(code: str, value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        market = code.split(".", 1)[0].upper()
        timezone = ZoneInfo("America/New_York" if market == "US" else "Asia/Hong_Kong")
        parsed = parsed.replace(tzinfo=timezone)
    return parsed


def _encode_cursor(triggered_at: str, alert_id: str) -> str:
    payload = json.dumps(
        [triggered_at, alert_id],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid alert cursor") from error
    if (
        not isinstance(payload, list)
        or len(payload) != 2
        or not all(isinstance(value, str) and value for value in payload)
    ):
        raise ValueError("invalid alert cursor")
    return payload[0], payload[1]


def _safe_ratio(
    numerator: float | int | None,
    denominator: float | int | None,
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _normalize_code(value: str) -> str:
    code = value.strip().upper()
    if "." not in code or len(code) > 64:
        raise ValueError(f"invalid security code: {value!r}")
    return code


def _normalize_expiration(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"invalid option expiration: {value!r}") from error


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _copy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("monitoring timestamps must be timezone-aware")
    return value.isoformat(timespec="seconds")


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("monitoring timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")
