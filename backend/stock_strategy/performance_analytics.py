from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Sequence

from .models import DailyReturn, EquityPoint, Trade

ROLLING_WINDOW_DAYS = 63
MIN_ROLLING_DAYS = 20


def build_performance_analysis(
    *,
    equity_curve: Sequence[EquityPoint],
    daily_returns: Sequence[DailyReturn],
    trades: Sequence[Trade],
    symbol: str,
    initial_cash: float,
) -> dict[str, Any]:
    daily_points = _daily_closing_points(equity_curve)
    strategy_returns = [point.return_pct / 100 for point in daily_returns]
    benchmark_returns = _benchmark_returns(daily_points, initial_cash)
    return {
        "return_distribution": _distribution(strategy_returns, percentage=True),
        "drawdown_distribution": _distribution(
            [point.drawdown for point in daily_points], percentage=True
        ),
        "trade_pnl_distribution": _distribution(
            [trade.net_pnl for trade in trades], percentage=False
        ),
        "monthly_returns": _period_returns(daily_returns, 7),
        "yearly_returns": _period_returns(daily_returns, 4),
        "rolling": _rolling_analysis(daily_returns),
        "attribution": {
            "weekday": _calendar_attribution(daily_returns, "%A"),
            "month": _calendar_attribution(daily_returns, "%m"),
            "session": _session_attribution(equity_curve, symbol),
            "market_regime": _market_regime_attribution(
                strategy_returns, benchmark_returns
            ),
        },
    }


def benchmark_statistics(
    *,
    equity_curve: Sequence[EquityPoint],
    daily_returns: Sequence[DailyReturn],
    initial_cash: float,
) -> dict[str, float | None]:
    daily_points = _daily_closing_points(equity_curve)
    strategy = [point.return_pct / 100 for point in daily_returns]
    benchmark = _benchmark_returns(daily_points, initial_cash)
    paired = list(zip(strategy, benchmark, strict=False))
    if len(paired) < 2:
        return {"alpha_pct": None, "beta": None, "information_ratio": None}
    strategy_values = [item[0] for item in paired]
    benchmark_values = [item[1] for item in paired]
    benchmark_variance = statistics.variance(benchmark_values)
    beta = (
        _sample_covariance(strategy_values, benchmark_values) / benchmark_variance
        if benchmark_variance
        else None
    )
    alpha = (
        (statistics.fmean(strategy_values) - beta * statistics.fmean(benchmark_values))
        * 252
        * 100
        if beta is not None
        else None
    )
    active = [
        strategy_return - benchmark_return
        for strategy_return, benchmark_return in paired
    ]
    active_std = statistics.stdev(active)
    information_ratio = (
        statistics.fmean(active) / active_std * math.sqrt(252) if active_std else None
    )
    return {
        "alpha_pct": alpha,
        "beta": beta,
        "information_ratio": information_ratio,
    }


def max_drawdown_duration_days(equity_curve: Sequence[EquityPoint]) -> int:
    duration = 0
    maximum = 0
    for point in _daily_closing_points(equity_curve):
        if point.drawdown < -1e-12:
            duration += 1
            maximum = max(maximum, duration)
        else:
            duration = 0
    return maximum


def max_consecutive_losses(trades: Sequence[Trade]) -> int:
    current = 0
    maximum = 0
    for trade in trades:
        if trade.net_pnl < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _daily_closing_points(
    equity_curve: Sequence[EquityPoint],
) -> list[EquityPoint]:
    by_date: dict[str, EquityPoint] = {}
    for point in equity_curve:
        by_date[point.date.strip()[:10]] = point
    return list(by_date.values())


def _benchmark_returns(
    daily_points: Sequence[EquityPoint], initial_cash: float
) -> list[float]:
    previous = initial_cash
    result: list[float] = []
    for point in daily_points:
        result.append(point.benchmark / previous - 1 if previous else 0.0)
        previous = point.benchmark
    return result


def _sample_covariance(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    return sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=False)
    ) / (len(left) - 1)


def _distribution(values: Sequence[float], *, percentage: bool) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "unit": "percent" if percentage else "currency",
            "min": None,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
            "mean": None,
            "std": None,
        }
    scale = 100 if percentage else 1
    ordered = sorted(values)
    return {
        "count": len(values),
        "unit": "percent" if percentage else "currency",
        "min": ordered[0] * scale,
        "p10": _quantile(ordered, 0.1) * scale,
        "p25": _quantile(ordered, 0.25) * scale,
        "median": _quantile(ordered, 0.5) * scale,
        "p75": _quantile(ordered, 0.75) * scale,
        "p90": _quantile(ordered, 0.9) * scale,
        "max": ordered[-1] * scale,
        "mean": statistics.fmean(ordered) * scale,
        "std": (statistics.stdev(ordered) * scale if len(ordered) > 1 else 0.0),
    }


def _quantile(ordered: Sequence[float], probability: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _period_returns(
    daily_returns: Sequence[DailyReturn], prefix_length: int
) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for point in daily_returns:
        grouped[point.date[:prefix_length]].append(point.return_pct / 100)
    return [
        {
            "period": period,
            "return_pct": (_compound(returns) - 1) * 100,
            "observations": len(returns),
        }
        for period, returns in grouped.items()
    ]


def _rolling_analysis(
    daily_returns: Sequence[DailyReturn],
) -> list[dict[str, float | str | None]]:
    result: list[dict[str, float | str | None]] = []
    for index in range(MIN_ROLLING_DAYS - 1, len(daily_returns)):
        start = max(0, index - ROLLING_WINDOW_DAYS + 1)
        window = daily_returns[start : index + 1]
        values = [point.return_pct / 100 for point in window]
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        sharpe = statistics.fmean(values) / std * math.sqrt(252) if std else None
        wealth = 1.0
        peak = 1.0
        drawdown = 0.0
        for value in values:
            wealth *= 1 + value
            peak = max(peak, wealth)
            drawdown = min(drawdown, wealth / peak - 1)
        result.append(
            {
                "date": window[-1].date,
                "window_days": len(window),
                "sharpe_ratio": sharpe,
                "max_drawdown_pct": drawdown * 100,
                "return_pct": (wealth - 1) * 100,
            }
        )
    return result


def _calendar_attribution(
    daily_returns: Sequence[DailyReturn], date_format: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for point in daily_returns:
        key = datetime.strptime(point.date[:10], "%Y-%m-%d").strftime(date_format)
        grouped[key].append(point.return_pct / 100)
    return _attribution_rows(grouped)


def _session_attribution(
    equity_curve: Sequence[EquityPoint], symbol: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    previous: float | None = None
    for point in equity_curve:
        if previous is None:
            previous = point.equity
            continue
        value = point.equity / previous - 1 if previous else 0.0
        previous = point.equity
        timestamp = _parse_timestamp(point.date)
        if timestamp is None or len(point.date.strip()) <= 10:
            grouped["daily"].append(value)
            continue
        minutes = timestamp.hour * 60 + timestamp.minute
        if symbol.upper().startswith("US."):
            regular = 570 <= minutes <= 960
        elif symbol.upper().startswith("HK."):
            regular = 570 <= minutes <= 720 or 780 <= minutes <= 960
        else:
            regular = True
        grouped["regular" if regular else "extended"].append(value)
    return _attribution_rows(grouped)


def _market_regime_attribution(
    strategy_returns: Sequence[float], benchmark_returns: Sequence[float]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for strategy_return, benchmark_return in zip(
        strategy_returns, benchmark_returns, strict=False
    ):
        if benchmark_return > 0.0005:
            regime = "up"
        elif benchmark_return < -0.0005:
            regime = "down"
        else:
            regime = "flat"
        grouped[regime].append(strategy_return)
    return _attribution_rows(grouped)


def _attribution_rows(
    grouped: dict[str, list[float]],
) -> list[dict[str, Any]]:
    return [
        {
            "bucket": bucket,
            "return_pct": (_compound(values) - 1) * 100,
            "average_return_pct": statistics.fmean(values) * 100,
            "positive_rate_pct": (
                sum(value > 0 for value in values) / len(values) * 100
            ),
            "observations": len(values),
        }
        for bucket, values in grouped.items()
    ]


def _compound(values: Iterable[float]) -> float:
    result = 1.0
    for value in values:
        result *= 1 + value
    return result


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None
