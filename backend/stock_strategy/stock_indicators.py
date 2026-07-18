from __future__ import annotations

import math
import statistics
from typing import Callable

from .context import get_context
from .errors import UnsupportedAPIError
from .models import Bar, BarType, Contract, DataType, THType
from .timeframes import can_derive


def is_ma_bullish_alignment(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    values = [_ma(symbol, period, bar_type, data_type, select, session_type) for period in (5, 10, 20, 60)]
    return _finite_order(values, descending=True)


def is_ma_bearish_alignment(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    values = [_ma(symbol, period, bar_type, data_type, select, session_type) for period in (5, 10, 20, 60)]
    return _finite_order(values, descending=False)


def is_ema_bullish_alignment(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    values = [_ema(symbol, period, bar_type, data_type, select, session_type) for period in (5, 10, 20, 60)]
    return _finite_order(values, descending=True)


def is_ema_bearish_alignment(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    values = [_ema(symbol, period, bar_type, data_type, select, session_type) for period in (5, 10, 20, 60)]
    return _finite_order(values, descending=False)


def atr_tr(
    symbol: Contract,
    period: int = 14,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    del period
    bars = _bars(symbol, bar_type, select, session_type)
    if len(bars) < 2:
        return math.nan
    current, previous = bars[-1], bars[-2]
    return max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )


def atr_atr(
    symbol: Contract,
    period: int = 14,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    bars = _bars(symbol, bar_type, select, session_type)
    if period <= 0 or len(bars) <= period:
        return math.nan
    true_ranges = [
        max(bar.high - bar.low, abs(bar.high - previous.close), abs(bar.low - previous.close))
        for previous, bar in zip(bars[-period - 1 : -1], bars[-period:])
    ]
    return statistics.fmean(true_ranges)


def kdj_k(
    symbol: Contract,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    return _kdj(symbol, k_period, d_period, slowing, bar_type, select, session_type)[0]


def kdj_d(
    symbol: Contract,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    return _kdj(symbol, k_period, d_period, slowing, bar_type, select, session_type)[1]


def kdj_j(
    symbol: Contract,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    return _kdj(symbol, k_period, d_period, slowing, bar_type, select, session_type)[2]


def is_kdj_golden_cross(
    symbol: Contract,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    now = _kdj(symbol, k_period, d_period, slowing, bar_type, select, session_type)
    previous = _kdj(symbol, k_period, d_period, slowing, bar_type, select + 1, session_type)
    return _cross(now[0], now[1], previous[0], previous[1], above=True) and now[0] < 50


def is_kdj_death_cross(
    symbol: Contract,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    now = _kdj(symbol, k_period, d_period, slowing, bar_type, select, session_type)
    previous = _kdj(symbol, k_period, d_period, slowing, bar_type, select + 1, session_type)
    return _cross(now[0], now[1], previous[0], previous[1], above=False) and now[0] > 50


def is_kdj_top_divergence(
    symbol: Contract, k_period: int = 9, d_period: int = 3, slowing: int = 3,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _divergence(
        symbol,
        bar_type,
        select,
        session_type,
        lambda shift: kdj_j(symbol, k_period, d_period, slowing, bar_type, shift, session_type),
        top=True,
    )


def is_kdj_bottom_divergence(
    symbol: Contract, k_period: int = 9, d_period: int = 3, slowing: int = 3,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _divergence(
        symbol,
        bar_type,
        select,
        session_type,
        lambda shift: kdj_j(symbol, k_period, d_period, slowing, bar_type, shift, session_type),
        top=False,
    )


def is_rsi_golden_cross(
    symbol: Contract, fast_period: int = 6, slow_period: int = 12,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _cross(
        _rsi(symbol, fast_period, bar_type, select, session_type),
        _rsi(symbol, slow_period, bar_type, select, session_type),
        _rsi(symbol, fast_period, bar_type, select + 1, session_type),
        _rsi(symbol, slow_period, bar_type, select + 1, session_type),
        above=True,
    )


def is_rsi_death_cross(
    symbol: Contract, fast_period: int = 6, slow_period: int = 12,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _cross(
        _rsi(symbol, fast_period, bar_type, select, session_type),
        _rsi(symbol, slow_period, bar_type, select, session_type),
        _rsi(symbol, fast_period, bar_type, select + 1, session_type),
        _rsi(symbol, slow_period, bar_type, select + 1, session_type),
        above=False,
    )


def is_rsi_top_divergence(
    symbol: Contract, period: int = 12, bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _divergence(symbol, bar_type, select, session_type, lambda shift: _rsi(symbol, period, bar_type, shift, session_type), top=True)


def is_rsi_bottom_divergence(
    symbol: Contract, period: int = 12, bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _divergence(symbol, bar_type, select, session_type, lambda shift: _rsi(symbol, period, bar_type, shift, session_type), top=False)


def is_macd_top_divergence(
    symbol: Contract, fast_period: int = 12, slow_period: int = 26,
    signal_period: int = 9, bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    del signal_period
    return _divergence(symbol, bar_type, select, session_type, lambda shift: _macd_dif(symbol, fast_period, slow_period, bar_type, shift, session_type), top=True)


def is_macd_bottom_divergence(
    symbol: Contract, fast_period: int = 12, slow_period: int = 26,
    signal_period: int = 9, bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    del signal_period
    return _divergence(symbol, bar_type, select, session_type, lambda shift: _macd_dif(symbol, fast_period, slow_period, bar_type, shift, session_type), top=False)


def historical_volatility_30d(symbol: Contract, select: int = 2) -> float:
    bars = _bars(symbol, BarType.K_DAY, select, get_context().session_type)
    closes = [bar.close for bar in bars]
    if len(closes) < 31:
        return math.nan
    returns = [math.log(current / previous) for previous, current in zip(closes[-31:-1], closes[-30:])]
    return statistics.stdev(returns) * math.sqrt(252) * 100


def boll_mid(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    del deviation
    closes = [bar.close for bar in _bars(symbol, bar_type, select, session_type)]
    return statistics.fmean(closes[-period:]) if period > 0 and len(closes) >= period else math.nan


def boll_upper(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    mid, spread = _boll(symbol, period, deviation, bar_type, select, session_type)
    return mid + spread


def boll_lower(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    mid, spread = _boll(symbol, period, deviation, bar_type, select, session_type)
    return mid - spread


def is_boll_cross_above_upper(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _price_band_cross(symbol, period, deviation, bar_type, session_type, select, boll_upper, above=True)


def is_boll_cross_below_lower(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _price_band_cross(symbol, period, deviation, bar_type, session_type, select, boll_lower, above=False)


def is_boll_cross_above_middle(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _price_band_cross(symbol, period, deviation, bar_type, session_type, select, boll_mid, above=True)


def is_boll_cross_below_middle(
    symbol: Contract, period: int = 20, deviation: float = 2,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return _price_band_cross(symbol, period, deviation, bar_type, session_type, select, boll_mid, above=False)


def vwap(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    bars = _bars(symbol, bar_type, select, session_type)
    if not bars:
        return math.nan
    day = bars[-1].date[:10]
    session = [bar for bar in bars if bar.date[:10] == day]
    volume = sum(bar.volume for bar in session)
    if volume == 0:
        return math.nan
    return sum(((bar.high + bar.low + bar.close) / 3) * bar.volume for bar in session) / volume


def is_nine_up_structure(
    symbol: Contract, bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    closes = [bar.close for bar in _bars(symbol, bar_type, select, session_type)]
    return len(closes) >= 13 and all(closes[-offset] > closes[-offset - 4] for offset in range(1, 10))


def is_nine_down_structure(
    symbol: Contract, bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    closes = [bar.close for bar in _bars(symbol, bar_type, select, session_type)]
    return len(closes) >= 13 and all(closes[-offset] < closes[-offset - 4] for offset in range(1, 10))


def sar(
    symbol: Contract, period: int = 4, step: float = 2, maximum: float = 20,
    bar_type: BarType = BarType.K_60M, select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    bars = _bars(symbol, bar_type, select, session_type)
    if period <= 0 or len(bars) < period:
        return math.nan
    acceleration = step / 100
    maximum_acceleration = maximum / 100
    bullish = bars[1].close >= bars[0].close
    value = min(bar.low for bar in bars[:period]) if bullish else max(bar.high for bar in bars[:period])
    extreme = max(bar.high for bar in bars[:period]) if bullish else min(bar.low for bar in bars[:period])
    for bar in bars[period:]:
        value += acceleration * (extreme - value)
        if bullish:
            if bar.low < value:
                bullish = False
                value, extreme, acceleration = extreme, bar.low, step / 100
            elif bar.high > extreme:
                extreme = bar.high
                acceleration = min(maximum_acceleration, acceleration + step / 100)
        else:
            if bar.high > value:
                bullish = True
                value, extreme, acceleration = extreme, bar.high, step / 100
            elif bar.low < extreme:
                extreme = bar.low
                acceleration = min(maximum_acceleration, acceleration + step / 100)
    return value


def is_sar_up_trend(
    symbol: Contract, period: int = 4, step: float = 2, maximum: float = 20,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    value = sar(symbol, period, step, maximum, bar_type, select, session_type)
    bars = _bars(symbol, bar_type, select, session_type)
    return bool(bars and math.isfinite(value) and value < bars[-1].close)


def is_sar_down_trend(
    symbol: Contract, period: int = 4, step: float = 2, maximum: float = 20,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    value = sar(symbol, period, step, maximum, bar_type, select, session_type)
    bars = _bars(symbol, bar_type, select, session_type)
    return bool(bars and math.isfinite(value) and value > bars[-1].close)


def is_sar_bullish_reversal(
    symbol: Contract, period: int = 4, step: float = 2, maximum: float = 20,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return is_sar_down_trend(symbol, period, step, maximum, bar_type, session_type, select) and is_sar_up_trend(symbol, period, step, maximum, bar_type, session_type, select + 1)


def is_sar_bearish_reversal(
    symbol: Contract, period: int = 4, step: float = 2, maximum: float = 20,
    bar_type: BarType = BarType.K_60M, session_type: THType = THType.ALL, select: int = 2,
) -> bool:
    return is_sar_up_trend(symbol, period, step, maximum, bar_type, session_type, select) and is_sar_down_trend(symbol, period, step, maximum, bar_type, session_type, select + 1)


def _bars(
    symbol: Contract, bar_type: BarType, select: int, session_type: THType
) -> list[Bar]:
    context = get_context()
    if str(symbol) != str(context.symbol):
        raise UnsupportedAPIError("stock backtests support one trigger symbol per run")
    requested = BarType(bar_type)
    if not can_derive(context.bar_type, requested):
        raise UnsupportedAPIError(f"cannot derive {requested.value} from {context.bar_type.value}")
    if str(symbol).startswith("US.") and THType(session_type) != context.session_type:
        raise UnsupportedAPIError(
            f"requested {THType(session_type).value} but input contains {context.session_type.value}"
        )
    if context.autype != "QFQ":
        raise UnsupportedAPIError("Futu stock indicators require QFQ history")
    if select <= 0:
        raise ValueError("select must be positive")
    series = context.bars_for(requested)
    end = len(series) - select + 1
    return series[: max(0, end)]


def _ma(symbol: Contract, period: int, bar_type: BarType, data_type: DataType, select: int, session_type: THType) -> float:
    values = [float(getattr(bar, DataType(data_type).value.lower())) for bar in _bars(symbol, bar_type, select, session_type)]
    return statistics.fmean(values[-period:]) if len(values) >= period else math.nan


def _ema(symbol: Contract, period: int, bar_type: BarType, data_type: DataType, select: int, session_type: THType) -> float:
    values = [float(getattr(bar, DataType(data_type).value.lower())) for bar in _bars(symbol, bar_type, select, session_type)]
    if len(values) < period:
        return math.nan
    current = statistics.fmean(values[:period])
    alpha = 2 / (period + 1)
    for value in values[period:]:
        current = alpha * value + (1 - alpha) * current
    return current


def _rsi(symbol: Contract, period: int, bar_type: BarType, select: int, session_type: THType) -> float:
    closes = [bar.close for bar in _bars(symbol, bar_type, select, session_type)]
    if period <= 0 or len(closes) <= period:
        return math.nan
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    gains = [max(change, 0.0) for change in changes[:period]]
    losses = [max(-change, 0.0) for change in changes[:period]]
    average_gain, average_loss = statistics.fmean(gains), statistics.fmean(losses)
    for change in changes[period:]:
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
    return 100.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)


def _macd_dif(symbol: Contract, fast_period: int, slow_period: int, bar_type: BarType, select: int, session_type: THType) -> float:
    fast = _ema(symbol, fast_period, bar_type, DataType.CLOSE, select, session_type)
    slow = _ema(symbol, slow_period, bar_type, DataType.CLOSE, select, session_type)
    return fast - slow if math.isfinite(fast) and math.isfinite(slow) else math.nan


def _kdj(symbol: Contract, k_period: int, d_period: int, slowing: int, bar_type: BarType, select: int, session_type: THType) -> tuple[float, float, float]:
    bars = _bars(symbol, bar_type, select, session_type)
    if min(k_period, d_period, slowing) <= 0 or len(bars) < k_period + slowing + d_period - 2:
        return math.nan, math.nan, math.nan
    raw: list[float] = []
    for index in range(k_period - 1, len(bars)):
        window = bars[index - k_period + 1 : index + 1]
        low, high = min(bar.low for bar in window), max(bar.high for bar in window)
        raw.append((bars[index].close - low) / (high - low) * 100 if high != low else 50.0)
    slow_k = _rolling_mean(raw, slowing)
    d_values = _rolling_mean(slow_k, d_period)
    if not slow_k or not d_values:
        return math.nan, math.nan, math.nan
    k, d = slow_k[-1], d_values[-1]
    return k, d, 3 * k - 2 * d


def _rolling_mean(values: list[float], period: int) -> list[float]:
    return [statistics.fmean(values[index - period + 1 : index + 1]) for index in range(period - 1, len(values))]


def _boll(symbol: Contract, period: int, deviation: float, bar_type: BarType, select: int, session_type: THType) -> tuple[float, float]:
    closes = [bar.close for bar in _bars(symbol, bar_type, select, session_type)]
    if period <= 0 or len(closes) < period:
        return math.nan, math.nan
    window = closes[-period:]
    return statistics.fmean(window), statistics.pstdev(window) * deviation


def _price_band_cross(symbol: Contract, period: int, deviation: float, bar_type: BarType, session_type: THType, select: int, band: Callable[..., float], *, above: bool) -> bool:
    bars = _bars(symbol, bar_type, select + 1, session_type)
    current_bars = _bars(symbol, bar_type, select, session_type)
    if not bars or not current_bars:
        return False
    now_price, previous_price = current_bars[-1].close, bars[-1].close
    now_band = band(symbol, period, deviation, bar_type, select, session_type)
    previous_band = band(symbol, period, deviation, bar_type, select + 1, session_type)
    return _cross(now_price, now_band, previous_price, previous_band, above=above)


def _divergence(symbol: Contract, bar_type: BarType, select: int, session_type: THType, indicator: Callable[[int], float], *, top: bool) -> bool:
    bars = _bars(symbol, bar_type, select, session_type)
    if len(bars) < 6:
        return False
    now_price, old_price = bars[-1].close, bars[-6].close
    now_indicator, old_indicator = indicator(select), indicator(select + 5)
    if not all(math.isfinite(value) for value in (now_indicator, old_indicator)):
        return False
    return (now_price > old_price and now_indicator < old_indicator) if top else (now_price < old_price and now_indicator > old_indicator)


def _cross(now_a: float, now_b: float, previous_a: float, previous_b: float, *, above: bool) -> bool:
    if not all(math.isfinite(value) for value in (now_a, now_b, previous_a, previous_b)):
        return False
    return now_a > now_b and previous_a <= previous_b if above else now_a < now_b and previous_a >= previous_b


def _finite_order(values: list[float], *, descending: bool) -> bool:
    if not all(math.isfinite(value) for value in values):
        return False
    pairs = zip(values, values[1:])
    return all(left > right for left, right in pairs) if descending else all(left < right for left, right in pairs)


__all__ = [
    name
    for name, value in globals().items()
    if callable(value)
    and getattr(value, "__module__", None) == __name__
    and not name.startswith("_")
]
