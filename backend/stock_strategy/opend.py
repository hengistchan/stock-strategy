from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
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
