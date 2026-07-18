from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import Bar


ALIASES = {
    "code": ("code", "symbol", "股票代码", "证券代码", "證券代碼"),
    "date": ("time_key", "date", "datetime", "time", "日期", "时间"),
    "open": ("open", "开盘", "開盤"),
    "high": ("high", "最高"),
    "low": ("low", "最低"),
    "close": ("close", "收盘", "收盤"),
    "volume": ("volume", "vol", "成交量"),
    "turnover": ("turnover", "成交额", "成交額"),
    "turnover_rate": ("turnover_rate", "换手率", "換手率"),
    "change_rate": ("change_rate", "chg_rate", "涨跌幅", "漲跌幅"),
    "last_close": ("last_close", "昨收", "前收盘", "前收盤"),
}


@dataclass(frozen=True, slots=True)
class MarketData:
    bars: list[Bar]
    symbol: str | None
    available_symbols: tuple[str, ...]
    source_format: str


def load_market_data(path: str | Path, symbol: str | None = None) -> MarketData:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Market data file not found: {source}")

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        rows = list(reader)
        return bars_from_opend_records(
            rows,
            symbol=symbol,
            fieldnames=reader.fieldnames,
        )


def load_bars(path: str | Path, symbol: str | None = None) -> list[Bar]:
    """Backwards-compatible CSV loader returning bars only."""
    return load_market_data(path, symbol=symbol).bars


def bars_from_opend_records(
    records: Iterable[Mapping[str, Any]],
    *,
    symbol: str | None = None,
    fieldnames: Iterable[str] | None = None,
) -> MarketData:
    """Convert OpenD DataFrame records or equivalent mappings to backtest bars."""
    rows = list(records)
    if not rows:
        raise ValueError("Market data contains no rows")
    names = list(fieldnames) if fieldnames is not None else list(rows[0].keys())
    columns = _resolve_columns(names)
    code_column = columns["code"]
    available_symbols = tuple(
        sorted(
            {
                str(row.get(code_column, "")).strip().upper()
                for row in rows
                if code_column and str(row.get(code_column, "")).strip()
            }
        )
    )
    requested_symbol = symbol.strip().upper() if symbol else None
    if requested_symbol and available_symbols and requested_symbol not in available_symbols:
        raise ValueError(
            f"Symbol {requested_symbol} not found; available: {', '.join(available_symbols)}"
        )
    if not requested_symbol and len(available_symbols) > 1:
        raise ValueError(
            "OpenD data contains multiple symbols; pass --symbol with one of: "
            + ", ".join(available_symbols)
        )
    resolved_symbol = requested_symbol or (available_symbols[0] if available_symbols else None)
    selected_rows = [
        row
        for row in rows
        if not code_column
        or not resolved_symbol
        or str(row.get(code_column, "")).strip().upper() == resolved_symbol
    ]
    bars = [
        _parse_row(row, columns, line_no)
        for line_no, row in enumerate(selected_rows, start=2)
    ]

    bars.sort(key=lambda bar: bar.date)
    unique = {bar.date: bar for bar in bars}
    result = list(unique.values())
    if len(result) < 30:
        raise ValueError("At least 30 valid OHLCV bars are required")
    normalized_names = {name.strip().lower() for name in names}
    source_format = "opend" if "time_key" in normalized_names else "generic-csv"
    return MarketData(
        bars=result,
        symbol=resolved_symbol,
        available_symbols=available_symbols,
        source_format=source_format,
    )


def generate_sample_bars(count: int = 880, seed: int = 20260713) -> list[Bar]:
    """Create deterministic synthetic daily bars for end-to-end smoke tests."""
    rng = random.Random(seed)
    cursor = date(2023, 1, 3)
    previous_close = 126.4
    bars: list[Bar] = []

    while len(bars) < count:
        if cursor.weekday() < 5:
            index = len(bars)
            if index < 180:
                regime = 0.0008
            elif index < 330:
                regime = -0.0005
            elif index < 620:
                regime = 0.0011
            else:
                regime = 0.00015
            cycle = math.sin(index / 31) * 0.0025
            shock = -0.075 if index == 241 else (0.058 if index == 508 else 0.0)
            overnight = rng.gauss(0, 0.004)
            intraday = regime + cycle + rng.gauss(0, 0.013) + shock
            open_price = max(8, previous_close * (1 + overnight))
            close = max(8, open_price * (1 + intraday))
            spread = abs(rng.gauss(0, 0.009)) + 0.003
            high = max(open_price, close) * (1 + spread)
            low = min(open_price, close) * (1 - spread * rng.uniform(0.75, 1.25))
            volume = round(rng.uniform(42_000_000, 80_000_000) * (1 + abs(intraday) * 9))
            bars.append(
                Bar(
                    date=cursor.isoformat(),
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=float(volume),
                )
            )
            previous_close = close
        cursor += timedelta(days=1)
    return bars


def _resolve_columns(fieldnames: Iterable[str]) -> dict[str, str | None]:
    normalized = {name.strip().lower(): name for name in fieldnames}
    result: dict[str, str | None] = {}
    for field, aliases in ALIASES.items():
        result[field] = next((normalized[name] for name in aliases if name in normalized), None)
    missing = [
        field
        for field, source in result.items()
        if source is None
        and field
        not in (
            "code",
            "volume",
            "turnover",
            "turnover_rate",
            "change_rate",
            "last_close",
        )
    ]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")
    return result


def _parse_row(
    row: Mapping[str, Any],
    columns: dict[str, str | None],
    line_no: int,
) -> Bar:
    try:
        bar_date = _normalize_timestamp(row[columns["date"]])  # type: ignore[index]
        open_price = _number(row[columns["open"]])  # type: ignore[index]
        high = _number(row[columns["high"]])  # type: ignore[index]
        low = _number(row[columns["low"]])  # type: ignore[index]
        close = _number(row[columns["close"]])  # type: ignore[index]
        volume_column = columns["volume"]
        volume = _number(row[volume_column]) if volume_column else 0.0
        turnover = _optional_number(row, columns["turnover"])
        turnover_rate = _optional_number(row, columns["turnover_rate"])
        change_rate = _optional_number(row, columns["change_rate"])
        last_close = _optional_number(row, columns["last_close"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid value on CSV line {line_no}: {error}") from error

    if not all(math.isfinite(value) for value in (open_price, high, low, close, volume)):
        raise ValueError(f"Values must be finite on CSV line {line_no}")
    if min(open_price, high, low, close) <= 0:
        raise ValueError(f"Prices must be positive on CSV line {line_no}")
    if high < max(open_price, close) or low > min(open_price, close):
        raise ValueError(f"Invalid OHLC relationship on CSV line {line_no}")
    return Bar(
        bar_date,
        open_price,
        high,
        low,
        close,
        volume,
        turnover,
        turnover_rate,
        change_rate,
        last_close,
    )


def _number(value: Any) -> float:
    return float(str(value).strip().replace(",", ""))


def _optional_number(row: Mapping[str, Any], column: str | None) -> float | None:
    if not column:
        return None
    value = row.get(column)
    if value is None or str(value).strip() in {"", "N/A", "nan", "None"}:
        return None
    result = _number(value)
    return result if math.isfinite(result) else None


def _normalize_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-").replace("T", " ")
    if len(text) == 10:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    parsed = datetime.fromisoformat(text)
    return parsed.isoformat(sep=" ", timespec="seconds")
