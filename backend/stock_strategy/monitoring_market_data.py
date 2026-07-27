from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from threading import RLock
from typing import Any, Protocol

from .opend import OpenDRequestError, OpenDUnavailableError

MAX_SNAPSHOT_BATCH = 400
HK_SNAPSHOT_BATCH = 20


class QuoteContextProtocol(Protocol):
    def get_market_snapshot(self, code_list: list[str]) -> tuple[int, Any]: ...

    def get_option_expiration_date(
        self,
        code: str,
        index_option_type: str = "NORMAL",
    ) -> tuple[int, Any]: ...

    def get_option_chain(
        self,
        code: str,
        index_option_type: str = "NORMAL",
        start: str | None = None,
        end: str | None = None,
        option_type: str = "ALL",
        option_cond_type: str = "ALL",
        data_filter: Any = None,
    ) -> tuple[int, Any]: ...

    def get_option_volatility(
        self,
        code: str,
        query_time_period: Any = None,
        hv_time_period: int | None = None,
    ) -> tuple[int, Any]: ...

    def get_option_exercise_probability(self, code: str) -> tuple[int, Any]: ...

    def query_subscription(self, is_all_conn: bool = True) -> tuple[int, Any]: ...

    def subscribe(
        self,
        code_list: list[str],
        subtype_list: list[str],
        **kwargs: Any,
    ) -> tuple[int, Any]: ...

    def unsubscribe(
        self,
        code_list: list[str],
        subtype_list: list[str],
        unsubscribe_all: bool = False,
    ) -> tuple[int, Any]: ...

    def close(self) -> None: ...


class MonitoringMarketDataSource(Protocol):
    def snapshots(self, codes: Iterable[str]) -> list[dict[str, Any]]: ...

    def option_expirations(self, underlying: str) -> list[dict[str, Any]]: ...

    def option_chain(
        self,
        underlying: str,
        expiration: str,
    ) -> list[dict[str, Any]]: ...

    def option_analytics(self, code: str) -> dict[str, Any]: ...

    def subscription_status(self) -> dict[str, Any]: ...

    def subscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]: ...

    def unsubscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]: ...

    def close(self) -> None: ...


class OpenDMonitoringDataSource:
    """Thread-safe OpenD adapter for stock and option monitoring data."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        context_factory: Callable[..., QuoteContextProtocol] | None = None,
        success_code: int = 0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._context_factory = context_factory
        self._success_code = success_code
        self._now = now or (lambda: datetime.now().astimezone())
        self._context: QuoteContextProtocol | None = None
        self._lock = RLock()

    def snapshots(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        requested = _normalize_codes(codes)
        if not requested:
            return []
        records: list[Mapping[str, Any]] = []
        batch_size = (
            HK_SNAPSHOT_BATCH
            if any(code.startswith("HK.") for code in requested)
            else MAX_SNAPSHOT_BATCH
        )
        for batch in _batches(requested, batch_size):
            frame = self._call("get_market_snapshot", list(batch))
            records.extend(_records(frame, "market snapshot"))
        fetched_at = self._now().isoformat(timespec="seconds")
        normalized = {
            str(record.get("code") or "").strip().upper(): _normalize_snapshot(
                record,
                fetched_at=fetched_at,
            )
            for record in records
            if record.get("code")
        }
        return [normalized[code] for code in requested if code in normalized]

    def option_expirations(self, underlying: str) -> list[dict[str, Any]]:
        code = _normalize_code(underlying)
        frame = self._call("get_option_expiration_date", code)
        values = [
            {
                "expiration": str(record.get("strike_time") or "")[:10],
                "days_to_expiry": _integer(record.get("option_expiry_date_distance")),
                "cycle": _text(record.get("expiration_cycle")),
            }
            for record in _records(frame, "option expiration dates")
        ]
        return sorted(
            (item for item in values if item["expiration"]),
            key=lambda item: str(item["expiration"]),
        )

    def option_chain(
        self,
        underlying: str,
        expiration: str,
    ) -> list[dict[str, Any]]:
        code = _normalize_code(underlying)
        frame = self._call(
            "get_option_chain",
            code,
            start=expiration,
            end=expiration,
            option_type="ALL",
        )
        contracts = [
            _normalize_option_contract(record)
            for record in _records(frame, "option chain")
        ]
        return sorted(
            contracts,
            key=lambda item: (
                float(item["strike_price"] or 0),
                str(item["option_type"]),
                str(item["code"]),
            ),
        )

    def option_analytics(self, code: str) -> dict[str, Any]:
        option_code = _normalize_code(code)
        volatility = self._call("get_option_volatility", option_code)
        probability = self._call("get_option_exercise_probability", option_code)
        volatility_rows = [
            _normalize_mapping(record)
            for record in _records(volatility, "option volatility")
        ]
        probability_rows = [
            _normalize_mapping(record)
            for record in _records(probability, "option exercise probability")
        ]
        return {
            "code": option_code,
            "volatility_history": volatility_rows,
            "exercise_probability_history": probability_rows,
        }

    def subscription_status(self) -> dict[str, Any]:
        payload = self._call("query_subscription")
        if not isinstance(payload, Mapping):
            raise OpenDRequestError(
                "OpenD returned an unexpected subscription status payload"
            )
        sub_list = payload.get("sub_list")
        normalized_subscriptions = (
            {
                str(kind): [str(code) for code in codes]
                for kind, codes in sub_list.items()
                if isinstance(codes, list)
            }
            if isinstance(sub_list, Mapping)
            else {}
        )
        return {
            "total_used": _integer(payload.get("total_used")) or 0,
            "own_used": _integer(payload.get("own_used")) or 0,
            "remaining": _integer(payload.get("remain")) or 0,
            "subscriptions": normalized_subscriptions,
        }

    def subscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        requested = _normalize_codes(codes)
        if requested:
            self._call(
                "subscribe",
                requested,
                ["QUOTE"],
                is_first_push=True,
                subscribe_push=False,
            )
        return self.subscription_status()

    def unsubscribe_quotes(self, codes: Iterable[str]) -> dict[str, Any]:
        requested = _normalize_codes(codes)
        if requested:
            self._call("unsubscribe", requested, ["QUOTE"])
        return self.subscription_status()

    def close(self) -> None:
        with self._lock:
            if self._context is not None:
                self._context.close()
                self._context = None

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            context = self._get_context()
            method = getattr(context, method_name)
            result, payload = method(*args, **kwargs)
            if result != self._success_code:
                raise OpenDRequestError(f"OpenD {method_name} failed: {payload}")
            return payload

    def _get_context(self) -> QuoteContextProtocol:
        if self._context is not None:
            return self._context
        factory = self._context_factory
        if factory is None:
            try:
                from futu import RET_OK, OpenQuoteContext
            except ImportError as error:
                raise OpenDUnavailableError(
                    "Futu SDK is not installed; install the project with the opend extra"
                ) from error
            factory = OpenQuoteContext
            self._success_code = RET_OK
        self._context = factory(
            host=self.host,
            port=self.port,
            is_async_connect=True,
        )
        return self._context


def _normalize_snapshot(
    record: Mapping[str, Any],
    *,
    fetched_at: str,
) -> dict[str, Any]:
    last_price = _number(record.get("last_price"))
    previous_close = _number(record.get("prev_close_price"))
    change_rate = (
        (last_price - previous_close) / previous_close * 100
        if last_price is not None and previous_close is not None and previous_close > 0
        else None
    )
    option_valid = bool(record.get("option_valid"))
    return {
        "code": _text(record.get("code")).upper(),
        "name": _text(record.get("name")),
        "instrument_type": "option" if option_valid else "stock",
        "source": "opend",
        "source_time": _text(record.get("update_time")) or None,
        "fetched_at": fetched_at,
        "last_price": last_price,
        "previous_close": previous_close,
        "change_rate": change_rate,
        "open_price": _number(record.get("open_price")),
        "high_price": _number(record.get("high_price")),
        "low_price": _number(record.get("low_price")),
        "volume": _number(record.get("volume")),
        "turnover": _number(record.get("turnover")),
        "turnover_rate": _number(record.get("turnover_rate")),
        "amplitude": _number(record.get("amplitude")),
        "volume_ratio": _number(record.get("volume_ratio")),
        "bid_price": _number(record.get("bid_price")),
        "ask_price": _number(record.get("ask_price")),
        "bid_volume": _number(record.get("bid_vol")),
        "ask_volume": _number(record.get("ask_vol")),
        "lot_size": _integer(record.get("lot_size")),
        "suspended": bool(record.get("suspension")),
        "security_status": _text(record.get("sec_status")),
        "option_type": _optional_text(record.get("option_type")),
        "underlying_code": _optional_text(record.get("stock_owner")),
        "strike_price": _number(record.get("option_strike_price")),
        "expiration": _optional_text(record.get("strike_time")),
        "days_to_expiry": _integer(record.get("option_expiry_date_distance")),
        "option_contract_size": _number(record.get("option_contract_size")),
        "option_open_interest": _number(record.get("option_open_interest")),
        "option_net_open_interest": _number(record.get("option_net_open_interest")),
        "option_implied_volatility": _number(record.get("option_implied_volatility")),
        "option_premium": _number(record.get("option_premium")),
        "option_delta": _number(record.get("option_delta")),
        "option_gamma": _number(record.get("option_gamma")),
        "option_vega": _number(record.get("option_vega")),
        "option_theta": _number(record.get("option_theta")),
        "option_rho": _number(record.get("option_rho")),
    }


def _normalize_option_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "code": _text(record.get("code")).upper(),
        "name": _text(record.get("name")),
        "underlying_code": _text(record.get("stock_owner")).upper(),
        "option_type": _text(record.get("option_type")),
        "expiration": _text(record.get("strike_time"))[:10],
        "strike_price": _number(record.get("strike_price")),
        "lot_size": _integer(record.get("lot_size")),
        "suspended": bool(record.get("suspension")),
        "expiration_cycle": _optional_text(record.get("expiration_cycle")),
        "standard_type": _optional_text(record.get("option_standard_type")),
        "settlement_mode": _optional_text(record.get("option_settlement_mode")),
    }


def _records(frame: Any, label: str) -> list[Mapping[str, Any]]:
    if not hasattr(frame, "to_dict"):
        raise OpenDRequestError(f"OpenD returned unexpected {label} data")
    values = frame.to_dict("records")
    if not isinstance(values, list):
        raise OpenDRequestError(f"OpenD returned unexpected {label} records")
    return [value for value in values if isinstance(value, Mapping)]


def _normalize_mapping(record: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_value(value) for key, value in record.items()}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    number = _number(value)
    return number if number is not None else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return None if not text or text == "N/A" else text


def _normalize_code(value: str) -> str:
    code = value.strip().upper()
    if "." not in code or len(code) > 64:
        raise ValueError(f"invalid OpenD security code: {value!r}")
    return code


def _normalize_codes(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(_normalize_code(value) for value in values))


def _batches(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]
