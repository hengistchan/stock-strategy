from __future__ import annotations

from datetime import datetime
from math import isfinite

from .models import Bar, BarType


_MINUTES: dict[BarType, int] = {
    BarType.K_1M: 1,
    BarType.K_3M: 3,
    BarType.K_5M: 5,
    BarType.K_10M: 10,
    BarType.K_15M: 15,
    BarType.K_30M: 30,
    BarType.K_60M: 60,
    BarType.K_120M: 120,
    BarType.K_180M: 180,
    BarType.K_240M: 240,
}


def bar_type_minutes(bar_type: BarType | str) -> int | None:
    return _MINUTES.get(BarType(bar_type))


def can_derive(base_type: BarType | str, target_type: BarType | str) -> bool:
    base = BarType(base_type)
    target = BarType(target_type)
    if base == target:
        return True
    if target == BarType.K_WEEK:
        return True
    if target == BarType.K_DAY:
        return base != BarType.K_WEEK
    base_minutes = bar_type_minutes(base)
    target_minutes = bar_type_minutes(target)
    return bool(
        base_minutes
        and target_minutes
        and target_minutes >= base_minutes
        and target_minutes % base_minutes == 0
    )


class IncrementalBarSeries:
    """Builds Futu-style current partial bars without looking past the driver bar."""

    def __init__(self, base_type: BarType | str, bars: list[Bar]) -> None:
        self.base_type = BarType(base_type)
        self.base_bars = bars
        self._series: dict[BarType, list[Bar]] = {}
        self._processed: dict[BarType, int] = {}
        self._day_anchors: dict[str, int] = {}

    def values(self, target_type: BarType | str, current_index: int) -> list[Bar]:
        target = BarType(target_type)
        if not can_derive(self.base_type, target):
            raise ValueError(
                f"cannot derive {target.value} from {self.base_type.value}; "
                "use the smallest strategy period as the OpenD driver"
            )
        output = self._series.setdefault(target, [])
        start = self._processed.get(target, -1) + 1
        for index in range(start, current_index + 1):
            self._append(output, target, self.base_bars[index])
        self._processed[target] = max(self._processed.get(target, -1), current_index)
        return output

    def _append(self, output: list[Bar], target: BarType, bar: Bar) -> None:
        key, bucket_date = self._bucket(target, bar.date)
        if not output or self._bucket(target, output[-1].date)[0] != key:
            previous_close = output[-1].close if output else bar.last_close
            output.append(
                Bar(
                    date=bucket_date,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    turnover=bar.turnover,
                    turnover_rate=bar.turnover_rate,
                    change_rate=_change_rate(bar.close, previous_close),
                    last_close=previous_close,
                )
            )
            return

        current = output[-1]
        turnover = _optional_sum(current.turnover, bar.turnover)
        output[-1] = Bar(
            date=current.date,
            open=current.open,
            high=max(current.high, bar.high),
            low=min(current.low, bar.low),
            close=bar.close,
            volume=current.volume + bar.volume,
            turnover=turnover,
            turnover_rate=bar.turnover_rate,
            change_rate=_change_rate(bar.close, current.last_close),
            last_close=current.last_close,
        )

    def _bucket(self, target: BarType, value: str) -> tuple[str, str]:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        date_key = moment.date().isoformat()
        if target == BarType.K_DAY:
            return date_key, date_key
        if target == BarType.K_WEEK:
            iso_year, iso_week, _ = moment.isocalendar()
            monday = moment.date().fromisocalendar(iso_year, iso_week, 1)
            return f"{iso_year}-W{iso_week:02d}", monday.isoformat()
        period = bar_type_minutes(target)
        if period is None:
            raise ValueError(f"unsupported target bar type: {target.value}")
        minute = moment.hour * 60 + moment.minute
        anchor = self._day_anchors.setdefault(date_key, minute)
        bucket_minute = anchor + ((minute - anchor) // period) * period
        bucket = moment.replace(
            hour=(bucket_minute // 60) % 24,
            minute=bucket_minute % 60,
            second=0,
            microsecond=0,
        )
        rendered = bucket.isoformat(sep=" ", timespec="seconds")
        return rendered, rendered


def _optional_sum(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return (left or 0.0) + (right or 0.0)


def _change_rate(close: float, previous_close: float | None) -> float | None:
    if previous_close is None or not isfinite(previous_close) or previous_close == 0:
        return None
    return (close / previous_close - 1) * 100
