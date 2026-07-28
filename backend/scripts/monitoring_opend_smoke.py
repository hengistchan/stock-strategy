#!/usr/bin/env python3
"""Collect real OpenD stock-and-option monitoring smoke evidence."""

from __future__ import annotations

import argparse
import json
import math
import socket
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Condition
from typing import Any, NoReturn, Protocol

PASSED_EXIT_CODE = 0
FAILED_EXIT_CODE = 1
DEFAULT_BLOCKED_EXIT_CODE = 2
SUBTYPE_QUOTE = "QUOTE"
REGULAR_TRADING_STATES = frozenset({"MORNING", "AFTERNOON", "OPEN", "TRADING"})
MINIMUM_SUBSCRIPTION_SECONDS = 60.5


@dataclass(frozen=True, slots=True)
class MarketSpec:
    market: str
    underlying: str
    state_field: str


MARKETS = (
    MarketSpec("US", "US.AAPL", "market_us"),
    MarketSpec("HK", "HK.00700", "market_hk"),
)


class QuoteContext(Protocol):
    def get_global_state(self) -> tuple[int, Any]: ...

    def get_option_expiration_date(self, code: str) -> tuple[int, Any]: ...

    def get_option_chain(self, code: str, **kwargs: Any) -> tuple[int, Any]: ...

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, Any]: ...

    def query_subscription(self, is_all_conn: bool = True) -> tuple[int, Any]: ...

    def set_handler(self, handler: Any) -> int: ...

    def subscribe(
        self,
        codes: list[str],
        subtypes: list[str],
        **kwargs: Any,
    ) -> tuple[int, Any]: ...

    def unsubscribe(
        self,
        codes: list[str],
        subtypes: list[str],
        unsubscribe_all: bool = False,
    ) -> tuple[int, Any]: ...

    def close(self) -> None: ...


ContextFactory = Callable[..., QuoteContext]
HandlerFactory = Callable[["QuotePushCollector"], Any]


class SmokeBlocked(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


class SmokeFailed(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


class QuotePushCollector:
    """Thread-safe proof that a push after the cached first push is newer."""

    def __init__(
        self,
        expected_codes: list[str],
        baseline_timestamps: Mapping[str, str],
    ) -> None:
        self.expected_codes = frozenset(expected_codes)
        self._baseline = {
            code: _parse_provider_timestamp(value, "snapshot.update_time")
            for code, value in baseline_timestamps.items()
        }
        self._first_push: dict[str, datetime] = {}
        self._fresh: dict[str, datetime] = {}
        self._errors: list[str] = []
        self._condition = Condition()

    def ingest(self, frame: Any) -> None:
        try:
            records = _records(frame, "quote push")
            with self._condition:
                cached_codes = self.expected_codes.difference(self._first_push)
                for record in records:
                    code = _required_text(record, "code", "quote push").upper()
                    if code not in self.expected_codes:
                        continue
                    timestamp = _push_timestamp(record)
                    if code in cached_codes:
                        previous = self._first_push.get(code)
                        if previous is None or timestamp > previous:
                            self._first_push[code] = timestamp
                        continue
                    reference = max(
                        self._baseline.get(code, timestamp),
                        self._first_push.get(code, timestamp),
                    )
                    if timestamp > reference:
                        self._fresh[code] = timestamp
                self._condition.notify_all()
        except SmokeFailed as error:
            self.record_error(f"{error.stage}:{error.reason}")

    def record_error(self, reason: str) -> None:
        with self._condition:
            self._errors.append(reason)
            self._condition.notify_all()

    def wait_for_fresh(self, timeout_seconds: float) -> bool:
        with self._condition:
            self._condition.wait_for(
                lambda: bool(self._errors) or self.expected_codes.issubset(self._fresh),
                timeout=max(timeout_seconds, 0.0),
            )
            return not self._errors and self.expected_codes.issubset(self._fresh)

    def evidence(self) -> dict[str, Any]:
        with self._condition:
            return {
                "cached_first_push_provider_timestamps": {
                    code: value.isoformat(sep=" ")
                    for code, value in sorted(self._first_push.items())
                },
                "fresh_provider_timestamps": {
                    code: value.isoformat(sep=" ")
                    for code, value in sorted(self._fresh.items())
                },
                "pending_codes": sorted(self.expected_codes.difference(self._fresh)),
                "mapping_errors": list(self._errors),
            }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument(
        "--market",
        choices=("US", "HK", "all"),
        default="all",
        help="Run one independently passable market or collect both for diagnostics.",
    )
    parser.add_argument("--push-timeout", type=float, default=60.0)
    parser.add_argument("--output", default="runs/acceptance")
    parser.add_argument(
        "--blocked-exit-code",
        type=int,
        choices=(0, DEFAULT_BLOCKED_EXIT_CODE),
        default=DEFAULT_BLOCKED_EXIT_CODE,
        help="Use 0 for an informational gate or 2 to make blocked distinguishable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        print("port must be between 1 and 65535", file=sys.stderr)
        return FAILED_EXIT_CODE
    if args.push_timeout < 0:
        print("push timeout must be nonnegative", file=sys.stderr)
        return FAILED_EXIT_CODE
    market_specs = select_market_specs(args.market)

    project_root = Path(__file__).resolve().parents[2]
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    def now() -> datetime:
        return datetime.now().astimezone()

    try:
        context_factory, handler_factory, success_code, sdk_version = (
            _load_futu_dependencies()
        )
        evidence = run_smoke(
            context_factory=context_factory,
            handler_factory=handler_factory,
            success_code=success_code,
            sdk_version=sdk_version,
            host=args.host,
            port=args.port,
            push_timeout_seconds=args.push_timeout,
            now=now,
            market_specs=market_specs,
        )
    except ImportError:
        evidence = _environment_blocked_evidence(
            reason="futu_sdk_unavailable",
            sdk_version=_sdk_version(),
            host=args.host,
            port=args.port,
            now=now,
            market_specs=market_specs,
        )

    try:
        evidence_path = write_evidence(evidence, output_dir, now=now)
    except OSError as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "stage": "write_evidence",
                    "reason": type(error).__name__,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return FAILED_EXIT_CODE

    output = {
        **evidence,
        "evidence_path": str(evidence_path),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return exit_code_for(
        str(evidence["status"]),
        blocked_exit_code=args.blocked_exit_code,
    )


def run_smoke(
    *,
    context_factory: ContextFactory,
    handler_factory: HandlerFactory,
    success_code: int,
    sdk_version: str | None,
    host: str = "127.0.0.1",
    port: int = 11111,
    push_timeout_seconds: float = 60.0,
    now: Callable[[], datetime] | None = None,
    preflight: Callable[[str, int], bool] | None = None,
    monotonic_clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    minimum_subscription_seconds: float = MINIMUM_SUBSCRIPTION_SECONDS,
    market_specs: Sequence[MarketSpec] | None = None,
) -> dict[str, Any]:
    if minimum_subscription_seconds < 0:
        raise ValueError("minimum subscription duration must be nonnegative")
    selected_markets = tuple(MARKETS if market_specs is None else market_specs)
    if not selected_markets:
        raise ValueError("at least one market must be selected")
    clock = now or (lambda: datetime.now().astimezone())
    monotonic = monotonic_clock or time.monotonic
    sleeper = sleep or time.sleep
    started_at = clock().isoformat()
    probe = preflight or _tcp_preflight
    if not probe(host, port):
        return _environment_blocked_evidence(
            reason="opend_unreachable",
            sdk_version=sdk_version,
            host=host,
            port=port,
            now=clock,
            started_at=started_at,
            market_specs=selected_markets,
        )

    markets = [
        _run_market(
            spec,
            context_factory=context_factory,
            handler_factory=handler_factory,
            success_code=success_code,
            host=host,
            port=port,
            push_timeout_seconds=push_timeout_seconds,
            monotonic_clock=monotonic,
            sleep=sleeper,
            minimum_subscription_seconds=minimum_subscription_seconds,
        )
        for spec in selected_markets
    ]
    return _evidence_payload(
        markets=markets,
        sdk_version=sdk_version,
        host=host,
        port=port,
        started_at=started_at,
        finished_at=clock().isoformat(),
    )


def _run_market(
    spec: MarketSpec,
    *,
    context_factory: ContextFactory,
    handler_factory: HandlerFactory,
    success_code: int,
    host: str,
    port: int,
    push_timeout_seconds: float,
    monotonic_clock: Callable[[], float],
    sleep: Callable[[float], None],
    minimum_subscription_seconds: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "market": spec.market,
        "underlying": spec.underlying,
        "status": "failed",
        "stage": "context",
        "reason": "not_started",
        "opend_version": None,
        "market_state": None,
        "expiration": None,
        "atm_contracts": {},
        "snapshots": [],
        "generic_subscription_usage": {
            "scope": "all_connections_all_security_types",
            "before": None,
            "after_subscribe": None,
        },
        "push": None,
        "cleanup": {
            "unsubscribe_all": False,
            "unsubscribe_attempted_codes": [],
            "unsubscribed_codes": [],
            "minimum_subscription_seconds": minimum_subscription_seconds,
            "waited_before_unsubscribe_seconds": 0.0,
            "context_closed": False,
        },
    }
    context: QuoteContext | None = None
    attempted_codes: list[str] = []
    subscription_succeeded = False
    subscribed_at: float | None = None
    cleanup_errors: list[str] = []
    try:
        try:
            context = context_factory(
                host=host,
                port=port,
                is_async_connect=True,
            )
        except Exception as error:
            _raise_context_error(error)
        assert context is not None

        global_state = _mapping(
            _call(context, "global_state", "get_global_state", success_code),
            "global state",
        )
        result["opend_version"] = _required_text(
            global_state,
            "server_ver",
            "global state",
        )
        result["market_state"] = _required_text(
            global_state,
            spec.state_field,
            "global state",
        ).upper()
        quote_logged_in = _required_boolean(
            global_state,
            "qot_logined",
            "global state",
        )
        if not quote_logged_in:
            raise SmokeBlocked("global_state", "quote_server_not_logged_in")

        expiration_frame = _call(
            context,
            "option_expirations",
            "get_option_expiration_date",
            success_code,
            spec.underlying,
        )
        expiration = _nearest_expiration(expiration_frame)
        result["expiration"] = expiration

        chain_frame = _call(
            context,
            "option_chain",
            "get_option_chain",
            success_code,
            spec.underlying,
            start=expiration,
            end=expiration,
            option_type="ALL",
        )
        contracts = _option_contracts(chain_frame, spec.underlying)

        reference_frame = _call(
            context,
            "underlying_snapshot",
            "get_market_snapshot",
            success_code,
            [spec.underlying],
        )
        reference = _snapshot_map(reference_frame, [spec.underlying])
        spot = _required_positive_number(
            reference[spec.underlying],
            "last_price",
            "underlying snapshot",
        )
        call_contract = _nearest_contract(contracts, "CALL", spot)
        put_contract = _nearest_contract(contracts, "PUT", spot)
        selected_codes = [
            spec.underlying,
            str(call_contract["code"]),
            str(put_contract["code"]),
        ]
        result["atm_contracts"] = {
            "reference_underlying_price": spot,
            "call": call_contract,
            "put": put_contract,
        }

        snapshot_frame = _call(
            context,
            "selected_snapshots",
            "get_market_snapshot",
            success_code,
            selected_codes,
        )
        snapshots = _snapshot_map(snapshot_frame, selected_codes)
        result["snapshots"] = [
            _snapshot_evidence(
                snapshots[code],
                option=code != spec.underlying,
            )
            for code in selected_codes
        ]
        baseline_timestamps = {
            item["code"]: item["provider_time"] for item in result["snapshots"]
        }

        before = _generic_subscription_usage(
            _call(
                context,
                "subscription_status",
                "query_subscription",
                success_code,
                is_all_conn=True,
            )
        )
        result["generic_subscription_usage"]["before"] = before

        market_state = str(result["market_state"])
        if market_state not in REGULAR_TRADING_STATES:
            raise SmokeBlocked(
                "market_state",
                f"market_not_in_regular_trading:{market_state}",
            )

        collector = QuotePushCollector(selected_codes, baseline_timestamps)
        handler_result = context.set_handler(handler_factory(collector))
        if handler_result != success_code:
            raise SmokeFailed("set_handler", "quote_handler_rejected")

        attempted_codes = list(selected_codes)
        result["cleanup"]["unsubscribe_attempted_codes"] = list(attempted_codes)
        subscribed_at = monotonic_clock()
        _call(
            context,
            "subscribe",
            "subscribe",
            success_code,
            attempted_codes,
            [SUBTYPE_QUOTE],
            is_first_push=True,
            subscribe_push=True,
        )
        subscription_succeeded = True
        result["generic_subscription_usage"]["after_subscribe"] = (
            _generic_subscription_usage(
                _call(
                    context,
                    "subscription_status_after_subscribe",
                    "query_subscription",
                    success_code,
                    is_all_conn=True,
                )
            )
        )

        fresh = collector.wait_for_fresh(push_timeout_seconds)
        result["push"] = collector.evidence()
        if result["push"]["mapping_errors"]:
            raise SmokeFailed("quote_push", "push_field_mapping_failed")
        if not fresh:
            raise SmokeBlocked(
                "quote_push",
                "fresh_provider_timestamp_timeout",
            )

        result.update(status="passed", stage="complete", reason=None)
    except SmokeBlocked as error:
        result.update(status="blocked", stage=error.stage, reason=error.reason)
    except SmokeFailed as error:
        result.update(status="failed", stage=error.stage, reason=error.reason)
    except Exception as error:
        result.update(
            status="failed",
            stage="unexpected",
            reason=f"unexpected_{type(error).__name__}",
        )
    finally:
        if context is not None and attempted_codes:
            if subscription_succeeded and subscribed_at is not None:
                elapsed = max(0.0, monotonic_clock() - subscribed_at)
                remaining = max(0.0, minimum_subscription_seconds - elapsed)
                if remaining:
                    try:
                        sleep(remaining)
                        result["cleanup"]["waited_before_unsubscribe_seconds"] = (
                            remaining
                        )
                    except Exception:
                        cleanup_errors.append("cleanup_wait_raised")
            try:
                response = context.unsubscribe(
                    attempted_codes,
                    [SUBTYPE_QUOTE],
                    unsubscribe_all=False,
                )
                if (
                    not isinstance(response, tuple)
                    or len(response) != 2
                    or response[0] != success_code
                ):
                    cleanup_errors.append("unsubscribe_failed")
                else:
                    result["cleanup"]["unsubscribed_codes"] = list(attempted_codes)
            except Exception:
                cleanup_errors.append("unsubscribe_raised")
        if context is not None:
            try:
                context.close()
                result["cleanup"]["context_closed"] = True
            except Exception:
                cleanup_errors.append("close_raised")
        if cleanup_errors:
            result.update(
                status="failed",
                stage="cleanup",
                reason=",".join(cleanup_errors),
            )
            result["cleanup"]["errors"] = cleanup_errors
    return result


def _call(
    context: QuoteContext,
    stage: str,
    method_name: str,
    success_code: int,
    *args: Any,
    **kwargs: Any,
) -> Any:
    try:
        response = getattr(context, method_name)(*args, **kwargs)
    except Exception as error:
        _raise_request_exception(stage, error)
    if not isinstance(response, tuple) or len(response) != 2:
        raise SmokeFailed(stage, "unexpected_opend_response_shape")
    result, payload = response
    if result != success_code:
        reason = _blocked_api_reason(payload)
        if reason is not None:
            raise SmokeBlocked(stage, reason)
        raise SmokeFailed(stage, "opend_request_failed")
    return payload


def _nearest_expiration(frame: Any) -> str:
    records = _records(frame, "option expirations")
    if not records:
        raise SmokeBlocked("option_expirations", "no_option_expirations")
    expirations: list[str] = []
    for record in records:
        value = _required_text(record, "strike_time", "option expiration")[:10]
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise SmokeFailed(
                "option_expirations",
                "invalid_expiration_date",
            ) from error
        expirations.append(value)
    return min(expirations)


def _option_contracts(frame: Any, underlying: str) -> list[dict[str, Any]]:
    records = _records(frame, "option chain")
    if not records:
        raise SmokeBlocked("option_chain", "empty_option_chain")
    contracts: list[dict[str, Any]] = []
    for record in records:
        code = _required_text(record, "code", "option chain").upper()
        owner = _required_text(record, "stock_owner", "option chain").upper()
        option_type = _required_text(record, "option_type", "option chain").upper()
        strike = _required_positive_number(record, "strike_price", "option chain")
        if owner != underlying:
            raise SmokeFailed("option_chain", "underlying_mapping_mismatch")
        if option_type not in {"CALL", "PUT"}:
            continue
        contracts.append(
            {
                "code": code,
                "option_type": option_type,
                "strike_price": strike,
            }
        )
    if not contracts:
        raise SmokeBlocked("option_chain", "no_call_or_put_contracts")
    return contracts


def _nearest_contract(
    contracts: list[dict[str, Any]],
    option_type: str,
    spot: float,
) -> dict[str, Any]:
    matching = [
        contract for contract in contracts if contract["option_type"] == option_type
    ]
    if not matching:
        raise SmokeBlocked(
            "option_chain",
            f"no_{option_type.lower()}_contract",
        )
    return min(
        matching,
        key=lambda contract: (
            abs(float(contract["strike_price"]) - spot),
            float(contract["strike_price"]),
            str(contract["code"]),
        ),
    )


def _snapshot_map(
    frame: Any, expected_codes: list[str]
) -> dict[str, Mapping[str, Any]]:
    records = _records(frame, "market snapshot")
    mapped: dict[str, Mapping[str, Any]] = {}
    for record in records:
        code = _required_text(record, "code", "market snapshot").upper()
        mapped[code] = record
    missing = sorted(set(expected_codes).difference(mapped))
    if missing:
        raise SmokeBlocked("market_snapshot", "selected_snapshot_unavailable")
    return mapped


def _snapshot_evidence(
    record: Mapping[str, Any],
    *,
    option: bool,
) -> dict[str, Any]:
    required_fields = {
        "code",
        "update_time",
        "last_price",
        "bid_price",
        "ask_price",
        "volume",
    }
    if option:
        required_fields.update(
            {
                "option_valid",
                "option_implied_volatility",
                "option_open_interest",
                "option_delta",
                "option_gamma",
                "option_vega",
                "option_theta",
                "option_rho",
                "option_expiry_date_distance",
            }
        )
    _require_fields(record, required_fields, "market snapshot")
    provider_time = _required_text(
        record,
        "update_time",
        "market snapshot",
    )
    _parse_provider_timestamp(provider_time, "market snapshot.update_time")
    evidence = {
        "code": _required_text(record, "code", "market snapshot").upper(),
        "provider_time": provider_time,
        "last_price": _number(record.get("last_price")),
        "bid_price": _number(record.get("bid_price")),
        "ask_price": _number(record.get("ask_price")),
        "volume": _number(record.get("volume")),
    }
    if evidence["last_price"] is None:
        raise SmokeBlocked("market_snapshot", "last_price_unavailable")
    if option:
        option_fields = {
            "option_implied_volatility": _number(
                record.get("option_implied_volatility")
            ),
            "option_open_interest": _number(record.get("option_open_interest")),
            "option_delta": _number(record.get("option_delta")),
            "option_gamma": _number(record.get("option_gamma")),
            "option_vega": _number(record.get("option_vega")),
            "option_theta": _number(record.get("option_theta")),
            "option_rho": _number(record.get("option_rho")),
            "days_to_expiry": _integer(record.get("option_expiry_date_distance")),
        }
        if any(value is None for value in option_fields.values()):
            raise SmokeBlocked(
                "market_snapshot",
                "option_monitoring_fields_unavailable",
            )
        evidence.update(option_fields)
    return evidence


def _generic_subscription_usage(payload: Any) -> dict[str, int]:
    mapping = _mapping(payload, "subscription status")
    _require_fields(
        mapping,
        {"total_used", "own_used", "remain"},
        "subscription status",
    )
    values = {
        "generic_total_used": _required_nonnegative_int(
            mapping,
            "total_used",
            "subscription status",
        ),
        "generic_own_used": _required_nonnegative_int(
            mapping,
            "own_used",
            "subscription status",
        ),
        "generic_remaining": _required_nonnegative_int(
            mapping,
            "remain",
            "subscription status",
        ),
    }
    return values


def _push_timestamp(record: Mapping[str, Any]) -> datetime:
    update_time = _text(record.get("update_time"))
    if update_time:
        return _parse_provider_timestamp(update_time, "quote push.update_time")
    data_date = _required_text(record, "data_date", "quote push")
    data_time = _required_text(record, "data_time", "quote push")
    return _parse_provider_timestamp(
        f"{data_date} {data_time}",
        "quote push provider time",
    )


def _parse_provider_timestamp(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SmokeFailed("field_mapping", f"invalid_{field}") from error


def _records(frame: Any, label: str) -> list[Mapping[str, Any]]:
    if not hasattr(frame, "to_dict"):
        raise SmokeFailed("field_mapping", f"unexpected_{label}_shape")
    values = frame.to_dict("records")
    if not isinstance(values, list):
        raise SmokeFailed("field_mapping", f"unexpected_{label}_records")
    if any(not isinstance(value, Mapping) for value in values):
        raise SmokeFailed("field_mapping", f"invalid_{label}_record")
    return list(values)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SmokeFailed("field_mapping", f"unexpected_{label}_shape")
    return value


def _require_fields(
    value: Mapping[str, Any],
    fields: set[str],
    label: str,
) -> None:
    missing = sorted(fields.difference(value))
    if missing:
        raise SmokeFailed(
            "field_mapping",
            f"missing_{label.replace(' ', '_')}_fields:{','.join(missing)}",
        )


def _required_text(value: Mapping[str, Any], field: str, label: str) -> str:
    if field not in value:
        raise SmokeFailed(
            "field_mapping",
            f"missing_{label.replace(' ', '_')}_field:{field}",
        )
    text = _text(value.get(field))
    if not text:
        raise SmokeFailed(
            "field_mapping",
            f"empty_{label.replace(' ', '_')}_field:{field}",
        )
    return text


def _required_boolean(value: Mapping[str, Any], field: str, label: str) -> bool:
    if field not in value:
        raise SmokeFailed(
            "field_mapping",
            f"missing_{label.replace(' ', '_')}_field:{field}",
        )
    raw = value.get(field)
    if isinstance(raw, bool):
        return raw
    if raw in {0, 1, "0", "1"}:
        return str(raw) == "1"
    raise SmokeFailed(
        "field_mapping",
        f"invalid_{label.replace(' ', '_')}_field:{field}",
    )


def _required_positive_number(
    value: Mapping[str, Any],
    field: str,
    label: str,
) -> float:
    if field not in value:
        raise SmokeFailed(
            "field_mapping",
            f"missing_{label.replace(' ', '_')}_field:{field}",
        )
    number = _number(value.get(field))
    if number is None or number <= 0:
        raise SmokeBlocked(
            label.replace(" ", "_"),
            f"{field}_unavailable",
        )
    return number


def _required_nonnegative_int(
    value: Mapping[str, Any],
    field: str,
    label: str,
) -> int:
    number = _integer(value.get(field))
    if number is None or number < 0:
        raise SmokeFailed(
            "field_mapping",
            f"invalid_{label.replace(' ', '_')}_field:{field}",
        )
    return number


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "n/a"} else text


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _blocked_api_reason(payload: Any) -> str | None:
    message = str(payload).lower()
    categories = (
        (
            "quote_permission_unavailable",
            ("permission", "authority", "no right", "权限", "行情权"),
        ),
        (
            "subscription_capacity_unavailable",
            ("quota", "capacity", "订阅额度", "订阅上限"),
        ),
        (
            "opend_unavailable",
            (
                "not connected",
                "connection",
                "connect fail",
                "未连接",
                "连接失败",
            ),
        ),
        ("opend_timeout", ("timeout", "timed out", "超时")),
        ("market_data_unavailable", ("no data", "empty data", "无数据")),
    )
    for reason, markers in categories:
        if any(marker in message for marker in markers):
            return reason
    return None


def _raise_request_exception(stage: str, error: Exception) -> NoReturn:
    reason = _blocked_api_reason(error)
    if reason is not None:
        raise SmokeBlocked(stage, reason) from error
    raise SmokeFailed(stage, f"request_{type(error).__name__}") from error


def _raise_context_error(error: Exception) -> NoReturn:
    reason = _blocked_api_reason(error)
    if reason is not None:
        raise SmokeBlocked("context", reason) from error
    raise SmokeFailed("context", f"context_{type(error).__name__}") from error


def _tcp_preflight(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _load_futu_dependencies() -> tuple[ContextFactory, HandlerFactory, int, str | None]:
    from futu import RET_OK, OpenQuoteContext, StockQuoteHandlerBase

    def handler_factory(collector: QuotePushCollector) -> Any:
        class SmokeQuoteHandler(StockQuoteHandlerBase):
            def on_recv_rsp(self, rsp_pb: Any) -> tuple[int, Any]:
                result, payload = super().on_recv_rsp(rsp_pb)
                if result == RET_OK:
                    collector.ingest(payload)
                else:
                    collector.record_error("quote_push_decode_failed")
                return result, payload

        return SmokeQuoteHandler()

    return OpenQuoteContext, handler_factory, RET_OK, _sdk_version()


def _sdk_version() -> str | None:
    try:
        return version("futu-api")
    except PackageNotFoundError:
        return None


def _environment_blocked_evidence(
    *,
    reason: str,
    sdk_version: str | None,
    host: str,
    port: int,
    now: Callable[[], datetime],
    started_at: str | None = None,
    market_specs: Sequence[MarketSpec] = MARKETS,
) -> dict[str, Any]:
    markets = [
        {
            "market": spec.market,
            "underlying": spec.underlying,
            "status": "blocked",
            "stage": "environment",
            "reason": reason,
            "cleanup": {
                "unsubscribe_all": False,
                "unsubscribe_attempted_codes": [],
                "unsubscribed_codes": [],
                "minimum_subscription_seconds": MINIMUM_SUBSCRIPTION_SECONDS,
                "waited_before_unsubscribe_seconds": 0.0,
                "context_closed": False,
            },
        }
        for spec in market_specs
    ]
    started = started_at or now().isoformat()
    return _evidence_payload(
        markets=markets,
        sdk_version=sdk_version,
        host=host,
        port=port,
        started_at=started,
        finished_at=now().isoformat(),
    )


def _evidence_payload(
    *,
    markets: list[dict[str, Any]],
    sdk_version: str | None,
    host: str,
    port: int,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    counts = {
        status: sum(result["status"] == status for result in markets)
        for status in ("passed", "blocked", "failed")
    }
    status = (
        "failed" if counts["failed"] else "blocked" if counts["blocked"] else "passed"
    )
    return {
        "schema_version": 1,
        "kind": "monitoring_opend_smoke",
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "sdk": {"name": "futu-api", "version": sdk_version},
        "opend": {"host": host, "port": port},
        "summary": counts,
        "markets": markets,
    }


def write_evidence(
    evidence: Mapping[str, Any],
    output_dir: Path,
    *,
    now: Callable[[], datetime] | None = None,
) -> Path:
    clock = now or (lambda: datetime.now().astimezone())
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = clock().strftime("%Y%m%d-%H%M%S-%f")
    path = output_dir / f"{stamp}-monitoring-opend-smoke.json"
    path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def exit_code_for(status: str, *, blocked_exit_code: int) -> int:
    if status == "passed":
        return PASSED_EXIT_CODE
    if status == "blocked":
        return blocked_exit_code
    return FAILED_EXIT_CODE


def select_market_specs(value: str) -> tuple[MarketSpec, ...]:
    if value == "all":
        return MARKETS
    return tuple(spec for spec in MARKETS if spec.market == value)


if __name__ == "__main__":
    raise SystemExit(main())
