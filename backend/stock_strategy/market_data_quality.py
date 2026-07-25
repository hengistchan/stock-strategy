from __future__ import annotations

from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Sequence

from .models import Bar, BarType

MARKET_TIMEZONES = {
    "US": "America/New_York",
    "HK": "Asia/Hong_Kong",
}


def build_market_data_quality_report(
    bars: Sequence[Bar],
    *,
    symbol: str,
    bar_type: BarType | str,
    autype: str,
    source: str = "opend",
) -> dict[str, Any]:
    normalized_type = BarType(bar_type)
    market = symbol.split(".", 1)[0].upper()
    duplicate_count = len(bars) - len({bar.date for bar in bars})
    suspicious_jumps = []
    for previous, current in zip(bars, bars[1:], strict=False):
        if previous.close <= 0:
            continue
        change = current.close / previous.close - 1
        if abs(change) >= 0.35:
            suspicious_jumps.append(
                {
                    "from": previous.date,
                    "to": current.date,
                    "change_pct": change * 100,
                }
            )
    missing = _missing_weekdays(bars) if normalized_type == BarType.K_DAY else []
    adjustment = autype.upper()
    return {
        "rows": len(bars),
        "duplicates": duplicate_count,
        "missing_intervals": len(missing),
        "missing_interval_samples": missing[:20],
        "timezone": MARKET_TIMEZONES.get(market, "market-local-unknown"),
        "calendar": f"{market.lower()}-weekday-approximation-v1",
        "calendar_precision": "approximate",
        "corporate_actions_applied": adjustment in {"QFQ", "HFQ"},
        "corporate_action_mode": (
            "delegated_to_opend_adjustment"
            if adjustment in {"QFQ", "HFQ"}
            else "unadjusted"
        ),
        "adjustment": adjustment,
        "suspicious_price_jumps": suspicious_jumps[:20],
        "source": source,
        "source_version": _futu_sdk_version() if source == "opend" else "unknown",
        "fx_conversion": "not_required_single_currency",
    }


def _missing_weekdays(bars: Sequence[Bar]) -> list[str]:
    if len(bars) < 2:
        return []
    observed = {datetime.fromisoformat(bar.date).date() for bar in bars}
    cursor = min(observed)
    end = max(observed)
    missing: list[str] = []
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in observed:
            missing.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return missing


def _futu_sdk_version() -> str:
    try:
        return version("futu-api")
    except PackageNotFoundError:
        return "unavailable"
