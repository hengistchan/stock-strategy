from __future__ import annotations

import math
import statistics
from typing import Any

from .context import get_context
from .models import (
    AlgoStrategyType,
    BarDataType,
    BarType,
    Contract,
    CustomType,
    DataType,
    GlobalType,
    OrderSide,
    OrdType,
    PositionSide,
    THType,
    TSType,
    TimeInForce,
)


class UnsupportedAPIError(NotImplementedError):
    pass


class StrategyBase:
    """Base class matching the shape of Futu code strategies."""

    def initialize(self) -> None:  # pragma: no cover - user hook
        pass

    def handle_data(self) -> None:  # pragma: no cover - user hook
        raise NotImplementedError

    def register_indicator(self, *_args: Any, **_kwargs: Any) -> None:
        raise UnsupportedAPIError(
            "register_indicator/get_MyLang_indicator is not supported in the MVP; "
            "use built-in ma/ema/rsi/macd APIs"
        )

    def register_indicator_Python(self, *_args: Any, **_kwargs: Any) -> None:
        raise UnsupportedAPIError(
            "register_indicator_Python is not supported in the MVP"
        )


def declare_strategy_type(strategy_type: AlgoStrategyType = AlgoStrategyType.SECURITY) -> None:
    get_context().strategy_type = strategy_type.value


def declare_trig_symbol() -> Contract:
    return get_context().symbol


def show_variable(value: Any, variable_type: GlobalType = GlobalType.FLOAT) -> Any:
    del variable_type
    return value


def current_price(symbol: Contract, price_type: THType = THType.ALL) -> float:
    _validate_symbol(symbol)
    _validate_session(price_type)
    return get_context().current_bar.close


def bar_open(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "open", select)


def bar_high(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "high", select)


def bar_low(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "low", select)


def bar_close(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "close", select)


def bar_volume(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "volume", select)


def bar_custom(
    symbol: Contract,
    data_type: BarDataType = BarDataType.CLOSE,
    custom_num: int = 4,
    custom_type: str = "K_60M",
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    custom_bar_type = _custom_bar_type(custom_type)
    _validate_series_request(symbol, custom_bar_type, session_type)
    try:
        normalized_data_type = BarDataType(data_type)
    except (TypeError, ValueError) as error:
        raise UnsupportedAPIError(f"unsupported bar_custom data type: {data_type}") from error
    if normalized_data_type == BarDataType.TURNOVER:
        raise UnsupportedAPIError(
            "bar_custom TURNOVER requires turnover data, which the OHLCV MVP does not retain"
        )
    if not 1 <= custom_num <= 200:
        raise ValueError("custom_num must be between 1 and 200")
    if not 1 <= select <= 5:
        raise ValueError("select must be between 1 and 5 for bar_custom")
    context = get_context()
    end = context.current_index - (select - 1) * custom_num
    start = end - custom_num + 1
    if start < 0:
        return math.nan
    window = context.bars[start : end + 1]
    if normalized_data_type == BarDataType.OPEN:
        return window[0].open
    if normalized_data_type == BarDataType.HIGH:
        return max(bar.high for bar in window)
    if normalized_data_type == BarDataType.LOW:
        return min(bar.low for bar in window)
    if normalized_data_type == BarDataType.VOLUME:
        return sum(bar.volume for bar in window)
    if normalized_data_type == BarDataType.CLOSE:
        return window[-1].close
    raise UnsupportedAPIError(f"unsupported bar_custom data type: {normalized_data_type}")


def ma(
    symbol: Contract,
    period: int = 5,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    values = _values(symbol, data_type, select)
    if period <= 0:
        raise ValueError("period must be positive")
    return statistics.fmean(values[-period:]) if len(values) >= period else math.nan


def ema(
    symbol: Contract,
    period: int = 5,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    values = _values(symbol, data_type, select)
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return math.nan
    return _ema_series(values, period)[-1]


def rsi(
    symbol: Contract,
    period: int = 12,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    closes = _values(symbol, DataType.CLOSE, select)
    if period <= 0:
        raise ValueError("period must be positive")
    if len(closes) <= period:
        return math.nan
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes[:period], closes[1 : period + 1]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = statistics.fmean(gains)
    average_loss = statistics.fmean(losses)
    for previous, current in zip(closes[period:-1], closes[period + 1 :]):
        change = current - previous
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
    if average_loss == 0:
        return 100.0
    return 100 - 100 / (1 + average_gain / average_loss)


def historical_volatility(
    symbol: Contract,
    period: int = 20,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    closes = _values(symbol, DataType.CLOSE, select)
    if len(closes) <= period:
        return math.nan
    returns = [math.log(current / previous) for previous, current in zip(closes[-period - 1 : -1], closes[-period:])]
    periods_per_year = _observed_periods_per_year(get_context())
    return statistics.stdev(returns) * math.sqrt(periods_per_year) * 100 if len(returns) > 1 else 0.0


def macd_dif(
    symbol: Contract,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    del signal_period
    dif, _dea, _histogram = _macd(symbol, fast_period, slow_period, 9, select)
    return dif


def macd_dea(
    symbol: Contract,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    _dif, dea, _histogram = _macd(symbol, fast_period, slow_period, signal_period, select)
    return dea


def macd_macd(
    symbol: Contract,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    _dif, _dea, histogram = _macd(symbol, fast_period, slow_period, signal_period, select)
    return histogram


def is_macd_golden_cross(
    symbol: Contract,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    _validate_series_request(symbol, bar_type, session_type)
    dif_now, dea_now, _ = _macd(symbol, fast_period, slow_period, signal_period, select)
    dif_previous, dea_previous, _ = _macd(symbol, fast_period, slow_period, signal_period, select + 1)
    return all(math.isfinite(value) for value in (dif_now, dea_now, dif_previous, dea_previous)) and dif_now > dea_now and dif_previous <= dea_previous


def is_macd_death_cross(
    symbol: Contract,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    bar_type: BarType = BarType.K_60M,
    session_type: THType = THType.ALL,
    select: int = 2,
) -> bool:
    _validate_series_request(symbol, bar_type, session_type)
    dif_now, dea_now, _ = _macd(symbol, fast_period, slow_period, signal_period, select)
    dif_previous, dea_previous, _ = _macd(symbol, fast_period, slow_period, signal_period, select + 1)
    return all(math.isfinite(value) for value in (dif_now, dea_now, dif_previous, dea_previous)) and dif_now < dea_now and dif_previous >= dea_previous


def position_holding_qty(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return abs(get_context().broker.position.quantity)


def position_side(symbol: Contract) -> PositionSide:
    _validate_symbol(symbol)
    return get_context().broker.position.side


def max_qty_to_buy_on_cash(
    symbol: Contract,
    order_type: OrdType = OrdType.LMT,
    price: float = 0,
    order_trade_session_type: TSType = TSType.ALL,
) -> int:
    del order_type, order_trade_session_type
    _validate_symbol(symbol)
    mark_price = price or get_context().current_bar.close
    return get_context().broker.max_cash_buy_quantity(mark_price)


def max_qty_to_sell(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return get_context().broker.max_sell_quantity()


def place_market(
    symbol: Contract,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
) -> str:
    return _submit(symbol, qty, side, "MARKET", time_in_force)


def place_limit(
    symbol: Contract,
    price: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
    order_trade_session_type: TSType = TSType.ALL,
) -> str:
    del order_trade_session_type
    return _submit(symbol, qty, side, "LIMIT", time_in_force, limit_price=price)


def place_stop(
    symbol: Contract,
    aux_price: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
) -> str:
    return _submit(symbol, qty, side, "STOP", time_in_force, stop_price=aux_price)


def close_positions(symbol: Contract, qty: float | None = None) -> str | None:
    _validate_symbol(symbol)
    position = get_context().broker.position
    if position.quantity == 0:
        return None
    close_qty = abs(position.quantity) if qty is None else min(abs(position.quantity), abs(qty))
    side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY_BACK
    return _submit(symbol, close_qty, side, "MARKET", TimeInForce.DAY)


def cancel_order_all() -> None:
    context = get_context()
    context.broker.cancel_all(context.current_bar.date)


def _submit(
    symbol: Contract,
    qty: float,
    side: OrderSide,
    order_type: str,
    time_in_force: TimeInForce,
    *,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> str:
    _validate_symbol(symbol)
    context = get_context()
    return context.broker.submit(
        symbol=symbol,
        side=side,
        quantity=qty,
        order_type=order_type,
        current_index=context.current_index,
        current_date=context.current_bar.date,
        time_in_force=time_in_force,
        limit_price=limit_price,
        stop_price=stop_price,
        current_price=context.current_bar.close,
    )


def _bar_value(symbol: Contract, field: str, select: int) -> float:
    _validate_symbol(symbol)
    index = get_context().current_index - (select - 1)
    if select <= 0:
        raise ValueError("select must be positive")
    if index < 0:
        return math.nan
    return float(getattr(get_context().bars[index], field))


def _values(symbol: Contract, data_type: DataType, select: int) -> list[float]:
    _validate_symbol(symbol)
    if select <= 0:
        raise ValueError("select must be positive")
    context = get_context()
    end = context.current_index - (select - 1)
    if end < 0:
        return []
    field = data_type.value.lower()
    return [float(getattr(bar, field)) for bar in context.bars[: end + 1]]


def _ema_series(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    seed = statistics.fmean(values[:period])
    output = [seed]
    for value in values[period:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _macd(
    symbol: Contract,
    fast_period: int,
    slow_period: int,
    signal_period: int,
    select: int,
) -> tuple[float, float, float]:
    closes = _values(symbol, DataType.CLOSE, select)
    if min(fast_period, slow_period, signal_period) <= 0:
        raise ValueError("MACD periods must be positive")
    if len(closes) < slow_period + signal_period - 1:
        return math.nan, math.nan, math.nan
    fast = _full_ema(closes, fast_period)
    slow = _full_ema(closes, slow_period)
    dif_values = [
        fast[index] - slow[index]
        for index in range(len(closes))
        if math.isfinite(fast[index]) and math.isfinite(slow[index])
    ]
    if len(dif_values) < signal_period:
        return math.nan, math.nan, math.nan
    dif = dif_values[-1]
    dea = _ema_series(dif_values, signal_period)[-1]
    return dif, dea, (dif - dea) * 2


def _full_ema(values: list[float], period: int) -> list[float]:
    output = [math.nan] * len(values)
    if len(values) < period:
        return output
    seed = statistics.fmean(values[:period])
    output[period - 1] = seed
    alpha = 2 / (period + 1)
    for index in range(period, len(values)):
        output[index] = alpha * values[index] + (1 - alpha) * output[index - 1]
    return output


def _validate_series_request(
    symbol: Contract,
    bar_type: BarType | str,
    session_type: THType | str,
) -> None:
    _validate_symbol(symbol)
    context = get_context()
    try:
        requested_bar_type = BarType(bar_type)
    except (TypeError, ValueError) as error:
        raise UnsupportedAPIError(f"unsupported bar type: {bar_type}") from error
    if requested_bar_type != context.bar_type:
        raise UnsupportedAPIError(
            f"requested {requested_bar_type.value}, but this backtest contains "
            f"{context.bar_type.value} bars; resampling is not implemented"
        )
    _validate_session(session_type)
    if context.autype.upper() != "QFQ":
        raise UnsupportedAPIError(
            "Futu bar and indicator APIs require QFQ data; "
            f"this backtest uses {context.autype.upper()}"
        )


def _validate_session(session_type: THType | str) -> None:
    context = get_context()
    # The manual defines THType filtering only for US securities. Other
    # markets ignore this argument, so enforcing it there would be stricter
    # than Futu itself.
    if not str(context.symbol).startswith("US."):
        return
    try:
        requested_session = THType(session_type)
    except (TypeError, ValueError) as error:
        raise UnsupportedAPIError(f"unsupported market session: {session_type}") from error
    if requested_session != context.session_type:
        raise UnsupportedAPIError(
            f"requested {requested_session.value} session, but this backtest "
            f"contains {context.session_type.value} bars; session filtering is not implemented"
        )


def _custom_bar_type(custom_type: Any) -> BarType:
    value = getattr(custom_type, "value", custom_type)
    aliases = {"M1": "K_1M", "H1": "K_60M", "D1": "K_DAY"}
    normalized = aliases.get(str(value), str(value))
    if normalized not in {"K_1M", "K_60M", "K_DAY"}:
        raise UnsupportedAPIError(f"unsupported custom bar type: {value}")
    return BarType(normalized)


def _observed_periods_per_year(context: Any) -> float:
    if context.bar_type == BarType.K_WEEK:
        return 52.0
    if context.bar_type == BarType.K_DAY:
        return 252.0
    trading_dates = {bar.date.strip()[:10] for bar in context.bars if bar.date.strip()}
    if not trading_dates:
        return 252.0
    return max(1.0, len(context.bars) / len(trading_dates)) * 252.0


def _validate_symbol(symbol: Contract) -> None:
    if str(symbol) != str(get_context().symbol):
        raise UnsupportedAPIError("MVP supports one trigger symbol per backtest")


__all__ = [
    "AlgoStrategyType",
    "BarDataType",
    "BarType",
    "Contract",
    "CustomType",
    "DataType",
    "GlobalType",
    "OrderSide",
    "OrdType",
    "PositionSide",
    "StrategyBase",
    "THType",
    "TSType",
    "TimeInForce",
    "UnsupportedAPIError",
    "bar_close",
    "bar_custom",
    "bar_high",
    "bar_low",
    "bar_open",
    "bar_volume",
    "cancel_order_all",
    "close_positions",
    "current_price",
    "declare_strategy_type",
    "declare_trig_symbol",
    "ema",
    "historical_volatility",
    "is_macd_death_cross",
    "is_macd_golden_cross",
    "ma",
    "macd_dea",
    "macd_dif",
    "macd_macd",
    "max_qty_to_buy_on_cash",
    "max_qty_to_sell",
    "place_limit",
    "place_market",
    "place_stop",
    "position_holding_qty",
    "position_side",
    "rsi",
    "show_variable",
]
