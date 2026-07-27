"""Context-free technical indicators for live monitoring.

The low-level functions consume finite close values ordered from oldest to
newest.  The closed-bar helpers apply an explicit boundary: every bar whose
``is_closed`` flag is false is ignored, wherever it appears in the input.
Determining when a market-data bar has closed remains the caller's
responsibility.

Indicators return ``None`` until enough closed observations are available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class IndicatorBar:
    """The close value and authoritative completion state of one K-line."""

    close: float
    is_closed: bool


def closed_bar_closes(bars: Iterable[IndicatorBar]) -> tuple[float, ...]:
    """Return finite closes from completed bars, preserving input order."""

    return _finite_values(bar.close for bar in bars if bar.is_closed)


def sma(values: Iterable[float], period: int) -> float | None:
    """Return the latest simple moving average for ``period`` observations."""

    _validate_period(period)
    closes = _finite_values(values)
    if len(closes) < period:
        return None
    return math.fsum(closes[-period:]) / period


def wilder_rsi(values: Iterable[float], period: int = 14) -> float | None:
    """Return the latest RSI using Wilder's recursive smoothing.

    The initial average gain and loss use the first ``period`` changes.
    Subsequent changes use Wilder's ``(previous * (period - 1) + current) /
    period`` recurrence.  A flat series is defined as neutral RSI 50.
    """

    _validate_period(period)
    closes = _finite_values(values)
    if len(closes) <= period:
        return None

    changes = _price_changes(closes)
    initial = changes[:period]
    average_gain = math.fsum(max(change, 0.0) for change in initial) / period
    average_loss = math.fsum(max(-change, 0.0) for change in initial) / period

    for change in changes[period:]:
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period

    if average_gain == 0.0 and average_loss == 0.0:
        return 50.0
    if average_loss == 0.0:
        return 100.0
    if average_gain == 0.0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def closed_bar_sma(
    bars: Iterable[IndicatorBar],
    period: int,
) -> float | None:
    """Calculate SMA from completed K-lines only."""

    return sma(closed_bar_closes(bars), period)


def closed_bar_wilder_rsi(
    bars: Iterable[IndicatorBar],
    period: int = 14,
) -> float | None:
    """Calculate Wilder RSI from completed K-lines only."""

    return wilder_rsi(closed_bar_closes(bars), period)


def _finite_values(values: Iterable[float]) -> tuple[float, ...]:
    normalized: list[float] = []
    for index, value in enumerate(values):
        if isinstance(value, bool):
            raise ValueError(f"values[{index}] must be a finite real number")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"values[{index}] must be a finite real number") from error
        if not math.isfinite(number):
            raise ValueError(f"values[{index}] must be a finite real number")
        normalized.append(number)
    return tuple(normalized)


def _price_changes(closes: tuple[float, ...]) -> tuple[float, ...]:
    changes: list[float] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        change = current - previous
        if not math.isfinite(change):
            raise ValueError("consecutive values must have a finite difference")
        changes.append(change)
    return tuple(changes)


def _validate_period(period: int) -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("period must be a positive integer")
