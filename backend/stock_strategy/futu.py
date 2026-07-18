from __future__ import annotations

import math
import statistics
import builtins
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from .context import get_context
from .models import (
    AlgoStrategyType,
    BarDataType,
    BarType,
    CltRiskStatus,
    Contract,
    CostPriceModel,
    Currency,
    CustomType,
    DataType,
    DealStatus,
    DTStatus,
    ErrCode,
    FutureType,
    GlobalType,
    IndexOptionType,
    InlinePriceType,
    Market,
    MktStatus,
    Moneyness,
    OptionCategory,
    OptionClass,
    OptionType,
    OrderSide,
    OrderStatus,
    OrdType,
    PositionSide,
    SymbolType,
    THType,
    TSType,
    TradeSide,
    TrailType,
    TrdHours,
    TimeOrientation,
    TimeZone,
    TimeInForce,
    USMktStatus,
    Week,
)
from .timeframes import can_derive
from .errors import APIException, DataUnavailableError, UnsupportedAPIError


class StrategyBase:
    """Base class matching the shape of Futu code strategies."""

    def initialize(self) -> None:  # pragma: no cover - user hook
        pass

    def handle_data(self) -> None:  # pragma: no cover - user hook
        raise NotImplementedError

    def register_indicator(self, *_args: Any, **_kwargs: Any) -> None:
        from .custom_indicators import register_indicator

        register_indicator(*_args, **_kwargs)

    def register_indicator_Python(self, *_args: Any, **_kwargs: Any) -> None:
        from .custom_indicators import register_indicator_Python

        register_indicator_Python(*_args, **_kwargs)


def declare_strategy_type(strategy_type: AlgoStrategyType = AlgoStrategyType.SECURITY) -> None:
    get_context().strategy_type = strategy_type.value


def declare_trig_symbol() -> Contract:
    return get_context().symbol


def show_variable(value: Any, variable_type: GlobalType = GlobalType.FLOAT) -> Any:
    del variable_type
    return value


def strategy_parameter(name: str, default: Any = None) -> Any:
    """Return a validated project-level strategy parameter for this run."""
    parameters = get_context().strategy_parameters
    if name in parameters:
        return parameters[name]
    if default is not None:
        return default
    raise KeyError(f"strategy parameter {name!r} is not configured")


def current_price(symbol: Contract, price_type: THType = THType.ALL) -> float:
    _validate_symbol(symbol)
    _validate_session(price_type)
    return get_context().current_bar.close


def current_bar_type() -> BarType:
    """Return the single OpenD K-line interval driving this backtest."""
    return get_context().bar_type


def current_session_type() -> THType:
    """Return the OpenD session scope driving this backtest."""
    return get_context().session_type


def device_time(time_zone: TimeZone = TimeZone.DEVICE_TIME_ZONE) -> datetime:
    """Return the current historical bar time in the requested Futu time zone."""
    context = get_context()
    try:
        requested_zone = TimeZone(time_zone)
    except (TypeError, ValueError) as error:
        raise UnsupportedAPIError(f"unsupported time zone: {time_zone}") from error
    try:
        current = datetime.fromisoformat(context.current_bar.date.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"current OpenD bar has an invalid timestamp: {context.current_bar.date}"
        ) from error
    market_zone = _market_time_zone(str(context.symbol))
    if current.tzinfo is None:
        current = current.replace(tzinfo=market_zone)
    return current.astimezone(_time_zone_info(requested_zone, market_zone))


def is_the_time(
    orientation: TimeOrientation,
    hour: int,
    min: int = 0,
    sec: int = 0,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    time_zone: TimeZone = TimeZone.DEVICE_TIME_ZONE,
) -> bool:
    current = device_time(time_zone)
    target = current.replace(
        year=year or current.year,
        month=month or current.month,
        day=day or current.day,
        hour=hour,
        minute=min,
        second=sec,
        microsecond=0,
    )
    normalized = TimeOrientation(orientation)
    return {
        TimeOrientation.LATER_THAN: current > target,
        TimeOrientation.EARLIER_THAN: current < target,
        TimeOrientation.NOT_LATER_THAN: current <= target,
        TimeOrientation.NOT_EARLIER_THAN: current >= target,
    }[normalized]


def is_the_day(day: list[int], time_zone: TimeZone = TimeZone.DEVICE_TIME_ZONE) -> bool:
    return device_time(time_zone).day in day


def is_the_week(
    week: list[int | Week], time_zone: TimeZone = TimeZone.DEVICE_TIME_ZONE
) -> bool:
    current = device_time(time_zone).isoweekday()
    mapping = {value: index for index, value in enumerate(Week, start=1)}
    normalized = {
        mapping[value] if isinstance(value, Week) else int(value) for value in week
    }
    return current in normalized


def is_the_month(
    month: list[int], time_zone: TimeZone = TimeZone.DEVICE_TIME_ZONE
) -> bool:
    return device_time(time_zone).month in month


def is_the_year(
    year: list[int], time_zone: TimeZone = TimeZone.DEVICE_TIME_ZONE
) -> bool:
    return device_time(time_zone).year in year


def ceil(value: float) -> int:
    return math.ceil(value)


def floor(value: float) -> int:
    return math.floor(value)


def power(base: float, exponent: float) -> float:
    return math.pow(base, exponent)


def integer_division(dividend: float, divisor: float) -> int:
    return math.floor(dividend / divisor)


def mod(dividend: float, divisor: float) -> float:
    return dividend % divisor


def math_log(arg: float, base: float = math.e) -> float:
    return math.log(arg, base)


def _market_time_zone(symbol: str) -> tzinfo:
    market = symbol.partition(".")[0]
    zones = {
        "US": "America/New_York",
        "CA": "America/Toronto",
        "HK": "Asia/Hong_Kong",
        "SH": "Asia/Shanghai",
        "SZ": "Asia/Shanghai",
        "JP": "Asia/Tokyo",
        "SG": "Asia/Singapore",
        "AU": "Australia/Sydney",
        "UK": "Europe/London",
    }
    return ZoneInfo(zones.get(market, "UTC"))


def _time_zone_info(value: TimeZone, market_zone: tzinfo) -> tzinfo:
    if value == TimeZone.DEVICE_TIME_ZONE:
        return datetime.now().astimezone().tzinfo or timezone.utc
    if value == TimeZone.MARKET_TIME_ZONE:
        return market_zone
    named_zones = {
        TimeZone.ET: "America/New_York",
        TimeZone.CT: "America/Chicago",
        TimeZone.HST: "Pacific/Honolulu",
        TimeZone.AKST: "America/Anchorage",
        TimeZone.PST: "America/Los_Angeles",
        TimeZone.MST: "America/Denver",
        TimeZone.CCT: "Asia/Shanghai",
        TimeZone.GMT: "Europe/London",
        TimeZone.CET: "Europe/Paris",
        TimeZone.EET: "Europe/Helsinki",
        TimeZone.JST: "Asia/Tokyo",
        TimeZone.KST: "Asia/Seoul",
        TimeZone.AET: "Australia/Sydney",
    }
    if value in named_zones:
        return ZoneInfo(named_zones[value])
    if value == TimeZone.UTC:
        return timezone.utc
    direction = 1 if value.value.startswith("UTC_PLUS_") else -1
    try:
        hours = int(value.value.rsplit("_", 1)[-1])
    except ValueError as error:  # pragma: no cover - enum exhaustiveness guard
        raise UnsupportedAPIError(f"unsupported time zone: {value}") from error
    return timezone(timedelta(hours=direction * hours))


def bar_open(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "open", select, bar_type)


def bar_high(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "high", select, bar_type)


def bar_low(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "low", select, bar_type)


def bar_close(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "close", select, bar_type)


def bar_volume(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    return _bar_value(symbol, "volume", select, bar_type)


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
    if not 1 <= custom_num <= 200:
        raise ValueError("custom_num must be between 1 and 200")
    if not 1 <= select <= 5:
        raise ValueError("select must be between 1 and 5 for bar_custom")
    series = get_context().bars_for(custom_bar_type)
    end = len(series) - 1 - (select - 1) * custom_num
    start = end - custom_num + 1
    if start < 0:
        return math.nan
    window = series[start : end + 1]
    if normalized_data_type == BarDataType.OPEN:
        return window[0].open
    if normalized_data_type == BarDataType.HIGH:
        return max(bar.high for bar in window)
    if normalized_data_type == BarDataType.LOW:
        return min(bar.low for bar in window)
    if normalized_data_type == BarDataType.VOLUME:
        return sum(bar.volume for bar in window)
    if normalized_data_type == BarDataType.TURNOVER:
        return _sum_required(window, "turnover")
    if normalized_data_type == BarDataType.TURNOVER_RATE:
        return _last_required(window, "turnover_rate")
    if normalized_data_type == BarDataType.CHG:
        previous = window[0].last_close
        return math.nan if previous is None else window[-1].close - previous
    if normalized_data_type == BarDataType.CHG_RATE:
        previous = window[0].last_close
        return math.nan if not previous else (window[-1].close / previous - 1) * 100
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
    if period <= 0:
        raise ValueError("period must be positive")
    if select <= 0:
        raise ValueError("select must be positive")
    values = _values(symbol, data_type, select, bar_type)
    if BarType(bar_type) == get_context().bar_type:
        field = DataType(data_type).value.lower()
        prefix = get_context().series_prefix_sums.setdefault(field, [0.0])
        while len(prefix) < get_context().current_index + 2:
            index = len(prefix) - 1
            prefix.append(prefix[-1] + float(getattr(get_context().bars[index], field)))
    if len(values) < period:
        return math.nan
    return statistics.fmean(values[-period:])


def ema(
    symbol: Contract,
    period: int = 5,
    bar_type: BarType = BarType.K_60M,
    data_type: DataType = DataType.CLOSE,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    _validate_series_request(symbol, bar_type, session_type)
    values = _values(symbol, data_type, select, bar_type)
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
    closes = _values(symbol, DataType.CLOSE, select, bar_type)
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
    closes = _values(symbol, DataType.CLOSE, select, bar_type)
    if len(closes) <= period:
        return math.nan
    returns = [math.log(current / previous) for previous, current in zip(closes[-period - 1 : -1], closes[-period:])]
    context = get_context()
    periods_per_year = _observed_periods_per_year(
        BarType(bar_type), context.bars_for(bar_type)
    )
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
    dif, _dea, _histogram = _macd(
        symbol, fast_period, slow_period, 9, select, bar_type
    )
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
    _dif, dea, _histogram = _macd(
        symbol, fast_period, slow_period, signal_period, select, bar_type
    )
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
    _dif, _dea, histogram = _macd(
        symbol, fast_period, slow_period, signal_period, select, bar_type
    )
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
    dif_now, dea_now, _ = _macd(
        symbol, fast_period, slow_period, signal_period, select, bar_type
    )
    dif_previous, dea_previous, _ = _macd(
        symbol, fast_period, slow_period, signal_period, select + 1, bar_type
    )
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
    dif_now, dea_now, _ = _macd(
        symbol, fast_period, slow_period, signal_period, select, bar_type
    )
    dif_previous, dea_previous, _ = _macd(
        symbol, fast_period, slow_period, signal_period, select + 1, bar_type
    )
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
    return _submit(
        symbol,
        qty,
        side,
        "LIMIT",
        time_in_force,
        limit_price=price,
        trade_session=order_trade_session_type,
    )


def place_stop_limit(
    symbol: Contract,
    aux_price: float,
    price: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
    order_trade_session_type: TSType = TSType.RTH,
) -> str:
    return _submit(
        symbol,
        qty,
        side,
        "STOP_LIMIT",
        time_in_force,
        limit_price=price,
        stop_price=aux_price,
        trade_session=order_trade_session_type,
    )


def place_stop(
    symbol: Contract,
    aux_price: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
) -> str:
    return _submit(symbol, qty, side, "STOP", time_in_force, stop_price=aux_price)


def place_limit_if_touched(
    symbol: Contract,
    aux_price: float,
    price: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
    order_trade_session_type: TSType = TSType.RTH,
) -> str:
    return _submit(
        symbol,
        qty,
        side,
        "LIMIT_IF_TOUCHED",
        time_in_force,
        limit_price=price,
        stop_price=aux_price,
        trade_session=order_trade_session_type,
    )


def place_market_if_touched(
    symbol: Contract,
    aux_price: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
) -> str:
    return _submit(
        symbol,
        qty,
        side,
        "MARKET_IF_TOUCHED",
        time_in_force,
        stop_price=aux_price,
    )


def place_trailing_stop(
    symbol: Contract,
    trail_type: TrailType,
    trail_value: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
) -> str:
    return _submit(
        symbol,
        qty,
        side,
        "TRAILING_STOP",
        time_in_force,
        trail_type=trail_type,
        trail_value=trail_value,
    )


def place_trailing_stop_limit(
    symbol: Contract,
    trail_type: TrailType,
    trail_value: float,
    trail_spread: float,
    qty: float,
    side: OrderSide = OrderSide.BUY,
    time_in_force: TimeInForce = TimeInForce.DAY,
    order_trade_session_type: TSType = TSType.RTH,
) -> str:
    return _submit(
        symbol,
        qty,
        side,
        "TRAILING_STOP_LIMIT",
        time_in_force,
        trade_session=order_trade_session_type,
        trail_type=trail_type,
        trail_value=trail_value,
        trail_spread=trail_spread,
    )


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


def cancel_order_by_orderid(orderid: str) -> None:
    context = get_context()
    context.broker.cancel_order(str(orderid), context.current_bar.date)


def cancel_order_by_symbol(
    symbol: Contract, side: TradeSide = TradeSide.ALL
) -> None:
    _validate_symbol(symbol)
    normalized = TradeSide(side)
    order_side = None
    if normalized == TradeSide.BUY:
        order_side = OrderSide.BUY
    elif normalized == TradeSide.SELL:
        order_side = OrderSide.SELL
    context = get_context()
    context.broker.cancel_symbol(symbol, context.current_bar.date, order_side)


def modify_order(
    orderid: str,
    qty: float,
    price: float | None = None,
    aux_price: float | None = None,
    trail_type: TrailType | None = None,
    trail_value: float | None = None,
    trail_spread: float | None = None,
) -> str:
    context = get_context()
    return context.broker.modify_order(
        str(orderid),
        context.current_bar.date,
        quantity=qty,
        price=price,
        aux_price=aux_price,
        trail_type=trail_type,
        trail_value=trail_value,
        trail_spread=trail_spread,
    )


def liquidate() -> str | None:
    return close_positions(get_context().symbol)


def cancel_and_liquidate() -> str | None:
    cancel_order_all()
    return liquidate()


def reverse_positions(symbol: Contract) -> str | None:
    _validate_symbol(symbol)
    context = get_context()
    context.broker.cancel_symbol(symbol, context.current_bar.date)
    position = context.broker.position
    if position.quantity == 0:
        return None
    if position.quantity > 0 and not context.broker.allow_short:
        raise UnsupportedAPIError(
            "reverse_positions from long to short requires allow_short=True"
        )
    quantity = abs(position.quantity)
    close_order_id = close_positions(symbol, quantity)
    if close_order_id is None:  # pragma: no cover - guarded above
        return None
    close_order = context.broker.get_order(close_order_id)
    close_order.follow_up_side = (
        OrderSide.SELL_SHORT if position.quantity > 0 else OrderSide.BUY
    )
    close_order.follow_up_quantity = quantity
    return context.broker.create_order_group(close_order_id)


def _submit(
    symbol: Contract,
    qty: float,
    side: OrderSide,
    order_type: str,
    time_in_force: TimeInForce,
    *,
    limit_price: float | None = None,
    stop_price: float | None = None,
    trade_session: TSType = TSType.ALL,
    trail_type: TrailType | None = None,
    trail_value: float | None = None,
    trail_spread: float | None = None,
) -> str:
    _validate_symbol(symbol)
    from .stock_api import lot_size

    lot = lot_size(symbol)
    normalized_qty = math.floor(float(qty) / lot) * lot
    if normalized_qty <= 0:
        raise ValueError(f"order quantity {qty} is below one tradable lot ({lot:g})")
    context = get_context()
    return context.broker.submit(
        symbol=symbol,
        side=side,
        quantity=normalized_qty,
        order_type=order_type,
        current_index=context.current_index,
        current_date=context.current_bar.date,
        time_in_force=time_in_force,
        limit_price=limit_price,
        stop_price=stop_price,
        current_price=context.current_bar.close,
        trade_session=trade_session,
        trail_type=trail_type,
        trail_value=trail_value,
        trail_spread=trail_spread,
    )


def _bar_value(
    symbol: Contract, field: str, select: int, bar_type: BarType | str
) -> float:
    _validate_symbol(symbol)
    if select <= 0:
        raise ValueError("select must be positive")
    series = get_context().bars_for(bar_type)
    index = len(series) - select
    if index < 0:
        return math.nan
    value = getattr(series[index], field)
    if value is None:
        raise UnsupportedAPIError(f"{field} is unavailable in the OpenD history input")
    return float(value)


def _values(
    symbol: Contract,
    data_type: DataType,
    select: int,
    bar_type: BarType | str,
) -> list[float]:
    _validate_symbol(symbol)
    if select <= 0:
        raise ValueError("select must be positive")
    series = get_context().bars_for(bar_type)
    end = len(series) - select
    if end < 0:
        return []
    field = data_type.value.lower()
    return [float(getattr(bar, field)) for bar in series[: end + 1]]


def _sum_required(bars: list[Any], field: str) -> float:
    values = [getattr(bar, field) for bar in bars]
    if any(value is None for value in values):
        raise DataUnavailableError(f"{field} is unavailable in the OpenD history input")
    return sum(float(value) for value in values)


def _last_required(bars: list[Any], field: str) -> float:
    value = getattr(bars[-1], field)
    if value is None:
        raise DataUnavailableError(f"{field} is unavailable in the OpenD history input")
    return float(value)


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
    bar_type: BarType | str,
) -> tuple[float, float, float]:
    closes = _values(symbol, DataType.CLOSE, select, bar_type)
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
    if not can_derive(context.bar_type, requested_bar_type):
        raise UnsupportedAPIError(
            f"requested {requested_bar_type.value}, but this backtest is driven by "
            f"{context.bar_type.value}; resampling is not implemented toward a finer period; "
            "choose the smallest strategy period as the OpenD input"
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


def _observed_periods_per_year(bar_type: BarType, bars: list[Any]) -> float:
    if bar_type == BarType.K_WEEK:
        return 52.0
    if bar_type == BarType.K_DAY:
        return 252.0
    trading_dates = {bar.date.strip()[:10] for bar in bars if bar.date.strip()}
    if not trading_dates:
        return 252.0
    return max(1.0, len(bars) / len(trading_dates)) * 252.0


def _validate_symbol(symbol: Contract) -> None:
    if str(symbol) != str(get_context().symbol):
        raise UnsupportedAPIError("a backtest supports one trigger stock at a time")


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
    "CltRiskStatus",
    "CostPriceModel",
    "Currency",
    "DTStatus",
    "ErrCode",
    "DealStatus",
    "Market",
    "MktStatus",
    "OrderStatus",
    "SymbolType",
    "TradeSide",
    "TrailType",
    "TrdHours",
    "TimeOrientation",
    "USMktStatus",
    "Week",
    "THType",
    "TSType",
    "TimeZone",
    "TimeInForce",
    "UnsupportedAPIError",
    "DataUnavailableError",
    "APIException",
    "bar_close",
    "bar_custom",
    "bar_high",
    "bar_low",
    "bar_open",
    "bar_volume",
    "cancel_order_all",
    "cancel_order_by_orderid",
    "cancel_order_by_symbol",
    "cancel_and_liquidate",
    "close_positions",
    "current_bar_type",
    "current_price",
    "current_session_type",
    "declare_strategy_type",
    "declare_trig_symbol",
    "device_time",
    "is_the_time",
    "is_the_day",
    "is_the_week",
    "is_the_month",
    "is_the_year",
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
    "place_limit_if_touched",
    "place_market",
    "place_market_if_touched",
    "place_stop",
    "place_stop_limit",
    "place_trailing_stop",
    "place_trailing_stop_limit",
    "modify_order",
    "liquidate",
    "reverse_positions",
    "position_holding_qty",
    "position_side",
    "rsi",
    "show_variable",
    "strategy_parameter",
    "ceil",
    "floor",
    "power",
    "integer_division",
    "mod",
    "math_log",
]


from . import stock_api as _stock_api
from . import stock_indicators as _stock_indicators
from . import custom_indicators as _custom_indicators

for _module in (_stock_api, _stock_indicators, _custom_indicators):
    for _name in _module.__all__:
        globals()[_name] = getattr(_module, _name)
        if _name not in __all__:
            __all__.append(_name)
