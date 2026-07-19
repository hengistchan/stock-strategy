from __future__ import annotations

import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from typing import Any, Callable


HISTORY_SESSIONS = frozenset({"ALL", "RTH", "ETH"})


class OpenDUnavailableError(RuntimeError):
    pass


class OpenDRequestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenDHistory:
    records: list[dict[str, Any]]
    fieldnames: tuple[str, ...]
    pages: int


@dataclass(frozen=True, slots=True)
class OpenDSymbol:
    code: str
    name: str
    market: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "name": self.name, "market": self.market}


class OpenDSymbolDirectory:
    """Cache and search the US/HK stock directory exposed by OpenD."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        ttl_seconds: float = 300,
        loader: Callable[[], list[OpenDSymbol]] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._loader = loader or (
            lambda: fetch_stock_directory(host=host, port=port)
        )
        self._symbols: list[OpenDSymbol] = []
        self._loaded_at = 0.0
        self._lock = Lock()

    def search(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        normalized = query.strip()
        if not normalized:
            return []
        symbols = self._load()
        return [item.to_dict() for item in match_stock_symbols(symbols, normalized, limit)]

    def resolve(self, codes: list[str]) -> list[dict[str, str]]:
        """Resolve exact Futu codes while preserving the requested order."""
        requested = list(dict.fromkeys(code.strip().upper() for code in codes if code.strip()))
        inventory = {symbol.code: symbol for symbol in self._load()}
        return [inventory[code].to_dict() for code in requested if code in inventory]

    def _load(self) -> list[OpenDSymbol]:
        now = monotonic()
        if self._symbols and now - self._loaded_at < self._ttl_seconds:
            return self._symbols
        with self._lock:
            now = monotonic()
            if self._symbols and now - self._loaded_at < self._ttl_seconds:
                return self._symbols
            loaded = self._loader()
            self._symbols = loaded
            self._loaded_at = now
            return loaded


def fetch_stock_directory(
    *,
    markets: tuple[str, ...] = ("US", "HK"),
    host: str = "127.0.0.1",
    port: int = 11111,
    context_factory: Callable[..., Any] | None = None,
    success_code: int = 0,
) -> list[OpenDSymbol]:
    """Read stock codes and localized names from OpenD basic information."""
    stock_type: Any = "STOCK"
    if context_factory is None:
        try:
            from futu import OpenQuoteContext, RET_OK, SecurityType
        except ImportError as error:
            raise OpenDUnavailableError(
                "Futu SDK is not installed; install the project with the opend extra"
            ) from error
        context_factory = OpenQuoteContext
        success_code = RET_OK
        stock_type = SecurityType.STOCK

    context = context_factory(host=host, port=port)
    symbols: dict[str, OpenDSymbol] = {}
    try:
        for market in markets:
            ret, frame = context.get_stock_basicinfo(
                market, stock_type=stock_type
            )
            if ret != success_code:
                raise OpenDRequestError(
                    f"OpenD get_stock_basicinfo failed for {market}: {frame}"
                )
            if not hasattr(frame, "to_dict"):
                raise OpenDRequestError(
                    "OpenD returned an unexpected stock directory payload"
                )
            for raw in frame.to_dict("records"):
                code = str(raw.get("code") or "").strip().upper()
                name = str(raw.get("name") or "").strip()
                if not code or not name or bool(raw.get("delisting", False)):
                    continue
                normalized_market = code.split(".", 1)[0]
                symbols[code] = OpenDSymbol(
                    code=code,
                    name=name,
                    market=normalized_market,
                )
    finally:
        context.close()
    return sorted(symbols.values(), key=lambda item: item.code)


def match_stock_symbols(
    symbols: list[OpenDSymbol], query: str, limit: int = 8
) -> list[OpenDSymbol]:
    """Rank exact, prefix, substring and typo-tolerant code/name matches."""
    normalized_query = _search_text(query)
    compact_query = _compact_search_text(query)
    ranked: list[tuple[tuple[float, int, str], OpenDSymbol]] = []
    for symbol in symbols:
        code = _search_text(symbol.code)
        local_code = code.split(".", 1)[-1]
        name = _search_text(symbol.name)
        compact_code = _compact_search_text(symbol.code)
        compact_name = _compact_search_text(symbol.name)

        if normalized_query == code or normalized_query == local_code:
            score = (0.0, len(code), code)
        elif code.startswith(normalized_query) or local_code.startswith(normalized_query):
            score = (1.0, len(code), code)
        elif normalized_query == name:
            score = (2.0, len(name), code)
        elif name.startswith(normalized_query):
            score = (3.0, len(name), code)
        elif normalized_query in code or normalized_query in local_code:
            score = (4.0, len(code), code)
        elif normalized_query in name:
            score = (5.0, len(name), code)
        else:
            compact_local_code = _compact_search_text(local_code)
            code_similarity = SequenceMatcher(
                None, compact_query, compact_local_code
            ).ratio()
            if len(compact_query) == len(compact_local_code):
                code_similarity += 0.12
            elif abs(len(compact_query) - len(compact_local_code)) == 1:
                code_similarity -= 0.08
            similarity = max(
                code_similarity,
                SequenceMatcher(None, compact_query, compact_code).ratio(),
                SequenceMatcher(None, compact_query, compact_name).ratio(),
            )
            if len(compact_query) < 2 or similarity < 0.58:
                continue
            score = (6.0 - similarity, len(code), code)
        ranked.append((score, symbol))
    ranked.sort(key=lambda item: item[0])
    return [item[1] for item in ranked[: max(1, limit)]]


def _search_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _compact_search_text(value: str) -> str:
    return re.sub(r"[\s._-]+", "", _search_text(value))


def fetch_stock_metadata(
    symbol: str,
    *,
    host: str = "127.0.0.1",
    port: int = 11111,
    context_factory: Callable[..., Any] | None = None,
    success_code: int = 0,
) -> dict[str, Any]:
    """Read stock lot, tick and classification metadata from OpenD."""
    if context_factory is None:
        try:
            from futu import OpenQuoteContext, RET_OK
        except ImportError as error:
            raise OpenDUnavailableError(
                "Futu SDK is not installed; install the project with the opend extra"
            ) from error
        context_factory = OpenQuoteContext
        success_code = RET_OK
    context = context_factory(host=host, port=port)
    try:
        ret, frame = context.get_market_snapshot([symbol])
        if ret != success_code:
            raise OpenDRequestError(f"OpenD get_market_snapshot failed: {frame}")
        if not hasattr(frame, "to_dict"):
            raise OpenDRequestError("OpenD returned an unexpected stock metadata payload")
        records = frame.to_dict("records")
        if not records:
            raise OpenDRequestError(f"OpenD returned no stock metadata for {symbol}")
        record = dict(records[0])
        return {
            key: record[key]
            for key in (
                "name",
                "lot_size",
                "price_spread",
                "stock_type",
                "suspension",
                "is_marginable",
                "is_shortable",
            )
            if key in record
        }
    finally:
        context.close()


def fetch_history_kline(
    symbol: str,
    *,
    start: str,
    end: str,
    ktype: str = "K_DAY",
    autype: str = "qfq",
    session: str = "ALL",
    host: str = "127.0.0.1",
    port: int = 11111,
    max_count: int = 1000,
    context_factory: Callable[..., Any] | None = None,
    success_code: int = 0,
) -> OpenDHistory:
    """Fetch every OpenD history page and return records without Pandas coupling."""
    normalized_session = session.upper()
    if normalized_session not in HISTORY_SESSIONS:
        supported = ", ".join(sorted(HISTORY_SESSIONS))
        raise ValueError(f"unsupported OpenD history session {session!r}; expected {supported}")

    if context_factory is None:
        try:
            from futu import OpenQuoteContext, RET_OK
        except ImportError as error:
            raise OpenDUnavailableError(
                "Futu SDK is not installed; install the project with the opend extra"
            ) from error
        context_factory = OpenQuoteContext
        success_code = RET_OK

    context = context_factory(host=host, port=port)
    records: list[dict[str, Any]] = []
    fieldnames: list[str] = []
    page_req_key: Any = None
    seen_page_keys: set[str] = set()
    pages = 0
    try:
        while True:
            ret, frame, next_page_key = context.request_history_kline(
                symbol,
                start=start,
                end=end,
                ktype=ktype,
                autype=autype,
                extended_time=normalized_session != "RTH",
                session=normalized_session,
                max_count=max_count,
                page_req_key=page_req_key,
            )
            if ret != success_code:
                raise OpenDRequestError(f"OpenD request_history_kline failed: {frame}")
            if not hasattr(frame, "to_dict") or not hasattr(frame, "columns"):
                raise OpenDRequestError("OpenD returned an unexpected history payload")
            pages += 1
            for name in frame.columns:
                column = str(name)
                if column not in fieldnames:
                    fieldnames.append(column)
            records.extend(frame.to_dict("records"))
            if not next_page_key:
                break
            page_marker = repr(next_page_key)
            if page_marker in seen_page_keys:
                raise OpenDRequestError("OpenD returned a repeated pagination key")
            seen_page_keys.add(page_marker)
            page_req_key = next_page_key
    finally:
        context.close()

    if not records:
        raise OpenDRequestError(
            f"OpenD returned no history for {symbol} between {start} and {end}"
        )
    return OpenDHistory(records=records, fieldnames=tuple(fieldnames), pages=pages)


def write_history_csv(history: OpenDHistory, path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(history.fieldnames))
        writer.writeheader()
        writer.writerows(history.records)
    return target
