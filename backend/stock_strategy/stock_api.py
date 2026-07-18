from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .context import get_context
from .errors import DataUnavailableError, UnsupportedAPIError
from .models import (
    BarDataType,
    BarType,
    CltRiskStatus,
    Contract,
    CostPriceModel,
    Currency,
    DTStatus,
    DealStatus,
    Market,
    MktStatus,
    Order,
    OrderSide,
    OrderStatus,
    OrdType,
    PositionSide,
    SymbolType,
    THType,
    TimeZone,
    TSType,
    TradeSide,
    TrdHours,
    USMktStatus,
)


def get_symbol_name(symbol: Contract) -> str:
    _validate_symbol(symbol)
    return str(get_context().market_metadata.get("name") or get_symbol_code(symbol))


def get_symbol_code(symbol: Contract) -> str:
    _validate_symbol(symbol)
    return str(symbol).partition(".")[2]


def get_symbol_market(symbol: Contract) -> Market:
    _validate_symbol(symbol)
    try:
        return Market(str(symbol).partition(".")[0])
    except ValueError as error:
        raise UnsupportedAPIError(f"unsupported stock market: {symbol}") from error


def get_symbol_type(symbol: Contract) -> SymbolType:
    _validate_symbol(symbol)
    value = get_context().market_metadata.get("stock_type")
    if value:
        aliases = {"STOCK": "STOCK", "ETF": "ETF", "INDEX": "INDEX"}
        normalized = aliases.get(str(value).upper(), str(value).upper())
        try:
            return SymbolType(normalized)
        except ValueError:
            pass
    return SymbolType.STOCK


def get_symbol_currency(symbol: Contract) -> Currency:
    market = get_symbol_market(symbol)
    values = {
        Market.HK: Currency.HKD,
        Market.US: Currency.USD,
        Market.SZ: Currency.CNH,
        Market.SH: Currency.CNH,
        Market.SG: Currency.SGD,
        Market.JP: Currency.JPY,
        Market.MY: Currency.MYR,
        Market.CA: Currency.CAD,
        Market.AU: Currency.AUD,
        Market.EU: Currency.EUR,
        Market.KR: Currency.KRW,
        Market.IN: Currency.INR,
        Market.TW: Currency.TWD,
    }
    try:
        return values[market]
    except KeyError as error:
        raise UnsupportedAPIError(f"currency is unavailable for market {market}") from error


def lot_size(symbol: Contract) -> float:
    _validate_symbol(symbol)
    configured = get_context().market_metadata.get("lot_size")
    if configured not in (None, ""):
        return float(configured)
    market = get_symbol_market(symbol)
    if market in {Market.US, Market.CA, Market.AU}:
        return 1.0
    if market in {Market.SH, Market.SZ}:
        return 100.0
    raise DataUnavailableError(
        f"lot_size for {symbol} requires OpenD stock_basicinfo metadata"
    )


def min_tick(symbol: Contract) -> float:
    _validate_symbol(symbol)
    configured = get_context().market_metadata.get("price_spread")
    if configured not in (None, "", 0, 0.0):
        return float(configured)
    price = get_context().current_bar.close
    market = get_symbol_market(symbol)
    if market == Market.US:
        return 0.0001 if price < 1 else 0.01
    if market in {Market.SH, Market.SZ}:
        return 0.01
    if market == Market.HK:
        return _hk_tick(price)
    return 0.01


def is_suspended(symbol: Contract) -> bool:
    _validate_symbol(symbol)
    return bool(get_context().market_metadata.get("suspension", False))


def contract_multiplier(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("contract_multiplier") or 1.0)


def amplitude(symbol: Contract, session_type: THType = THType.ALL) -> float:
    _validate_symbol(symbol)
    _validate_session(session_type)
    bar = get_context().current_bar
    baseline = bar.last_close or bar.open
    return (bar.high - bar.low) / baseline * 100 if baseline else math.nan


def bar_turnover(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    return _bar_field(symbol, bar_type, select, session_type, "turnover")


def bar_turnover_rate(
    symbol: Contract,
    bar_type: BarType = BarType.K_DAY,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    return _bar_field(symbol, bar_type, select, session_type, "turnover_rate")


def bar_chg(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    bar = _selected_bar(symbol, bar_type, select, session_type)
    return math.nan if bar is None or bar.last_close is None else bar.close - bar.last_close


def bar_chg_rate(
    symbol: Contract,
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    bar = _selected_bar(symbol, bar_type, select, session_type)
    if bar is None or not bar.last_close:
        return math.nan
    return (bar.close / bar.last_close - 1) * 100


def volume_ratio(symbol: Contract) -> float:
    _validate_symbol(symbol)
    configured = get_context().market_metadata.get("volume_ratio")
    if configured not in (None, ""):
        return float(configured)
    daily = get_context().bars_for(BarType.K_DAY)
    if len(daily) < 6:
        return math.nan
    average = sum(bar.volume for bar in daily[-6:-1]) / 5
    return daily[-1].volume / average if average else math.nan


def mid_price(symbol: Contract) -> float:
    return (bid(symbol) + ask(symbol)) / 2


def bid(symbol: Contract, level: int = 1) -> float:
    _validate_level(level)
    return get_context().current_bar.close - min_tick(symbol) * (level - 0.5)


def ask(symbol: Contract, level: int = 1) -> float:
    _validate_level(level)
    return get_context().current_bar.close + min_tick(symbol) * (level - 0.5)


def bid_qty(symbol: Contract, level: int = 1) -> float:
    _validate_symbol(symbol)
    _validate_level(level)
    return get_context().current_bar.volume / 2


def ask_qty(symbol: Contract, level: int = 1) -> float:
    return bid_qty(symbol, level)


def bid_order_qty(symbol: Contract, level: int = 1) -> int:
    return 1 if bid_qty(symbol, level) > 0 else 0


def ask_order_qty(symbol: Contract, level: int = 1) -> int:
    return 1 if ask_qty(symbol, level) > 0 else 0


def rate_ratio(symbol: Contract) -> float:
    denominator = ask_qty(symbol) + bid_qty(symbol)
    return (bid_qty(symbol) - ask_qty(symbol)) / denominator * 100 if denominator else 0.0


def market_status(symbol: Contract) -> MktStatus:
    _validate_symbol(symbol)
    moment = _market_moment()
    minutes = moment.hour * 60 + moment.minute
    market = get_symbol_market(symbol)
    if moment.weekday() >= 5:
        return MktStatus.CLOSED
    if market in {Market.US, Market.CA}:
        return MktStatus.CONTINUOUS_TRADE if 570 <= minutes < 960 else MktStatus.CLOSED
    if market in {Market.HK, Market.SH, Market.SZ}:
        active = 570 <= minutes < 720 or 780 <= minutes < 960
        return MktStatus.CONTINUOUS_TRADE if active else MktStatus.CLOSED
    return MktStatus.CONTINUOUS_TRADE


def USmarket_status(symbol: Contract) -> USMktStatus:
    _validate_symbol(symbol)
    if get_symbol_market(symbol) != Market.US:
        raise UnsupportedAPIError("USmarket_status only accepts US stocks")
    moment = _market_moment()
    minutes = moment.hour * 60 + moment.minute
    if moment.weekday() >= 5:
        return USMktStatus.CLOSED
    if 240 <= minutes < 570:
        return USMktStatus.PRE_MARKET
    if 570 <= minutes < 960:
        return USMktStatus.RTH
    if 960 <= minutes < 1200:
        return USMktStatus.POST_MARKET
    if minutes >= 1200 or minutes < 240:
        return USMktStatus.OVERNIGHT
    return USMktStatus.CLOSED


def net_asset(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    context = get_context()
    return context.broker.equity(context.current_bar.close)


def market_value_security(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return abs(get_context().broker.position.quantity * get_context().current_bar.close)


def market_value_long(currency: Currency = Currency.HKD) -> float:
    return market_value_security(currency) if get_context().broker.position.quantity > 0 else 0.0


def market_value_short(currency: Currency = Currency.HKD) -> float:
    return market_value_security(currency) if get_context().broker.position.quantity < 0 else 0.0


def total_cash(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return get_context().broker.cash


def cash(currency: Currency = Currency.HKD) -> float:
    return total_cash(currency)


def asset_unrealized_pl(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return position_unrealized_pl(get_context().symbol)


def total_cash_withdrawable(currency: Currency = Currency.HKD) -> float:
    return max(0.0, total_cash(currency))


def cash_withdrawable(currency: Currency = Currency.HKD) -> float:
    return total_cash_withdrawable(currency)


def asset_in_transit(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return 0.0


def interest_incurring_amount(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return min(0.0, get_context().broker.cash)


def frozen_fund(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return get_context().broker.reserved_buy_cash


def available_fund(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return get_context().broker.available_cash


def asset_realized_pl(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return sum(trade.net_pnl for trade in get_context().broker.trades)


def max_buying_power(currency: Currency = Currency.HKD) -> float:
    return available_fund(currency)


def short_buying_power(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return available_fund(currency) if get_context().broker.allow_short else 0.0


def cash_buying_power(currency: Currency = Currency.HKD) -> float:
    return available_fund(currency)


def initial_DTBP(currency: Currency = Currency.HKD) -> float:
    return cash_buying_power(currency)


def remaining_DTBP(currency: Currency = Currency.HKD) -> float:
    return cash_buying_power(currency)


def DT_call_amount(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return 0.0


def day_trades_left() -> int:
    return 999_999


def DT_status() -> DTStatus:
    return DTStatus.UNLIMITED


def risk_status() -> CltRiskStatus:
    return CltRiskStatus.LEVEL1


def initial_margin(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return market_value_security(currency)


def margin_call_margin(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return 0.0


def maintenance_margin(currency: Currency = Currency.HKD) -> float:
    _validate_currency(currency)
    return market_value_security(currency) * 0.25


def is_marginable(symbol: Contract) -> bool:
    _validate_symbol(symbol)
    return bool(get_context().market_metadata.get("is_marginable", False))


def is_shortable(symbol: Contract) -> bool:
    _validate_symbol(symbol)
    configured = get_context().market_metadata.get("is_shortable")
    return get_context().broker.allow_short and configured is not False


def short_pool_remaining(symbol: Contract) -> float:
    _validate_symbol(symbol)
    configured = get_context().market_metadata.get("short_pool_remaining")
    if configured not in (None, ""):
        return float(configured)
    return float(max_qty_to_sell_short(symbol))


def initial_marginratio_long(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("initial_marginratio_long") or 1.0)


def initial_marginratio_short(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("initial_marginratio_short") or 1.5)


def short_interest_rate(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("short_interest_rate") or 0.0)


def maint_marginratio_long(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("maint_marginratio_long") or 0.25)


def maint_marginratio_short(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("maint_marginratio_short") or 0.3)


def mc_marginratio_long(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("mc_marginratio_long") or 0.2)


def mc_marginratio_short(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return float(get_context().market_metadata.get("mc_marginratio_short") or 0.2)


def max_qty_to_buy_on_margin(
    symbol: Contract,
    order_type: OrdType = OrdType.LMT,
    price: float = 0,
    order_trade_session_type: TSType = TSType.ALL,
) -> int:
    return max_qty_to_buy_on_cash(symbol, order_type, price, order_trade_session_type)


def max_qty_to_buy_on_cash(
    symbol: Contract,
    order_type: OrdType = OrdType.LMT,
    price: float = 0,
    order_trade_session_type: TSType = TSType.ALL,
) -> int:
    del order_type, order_trade_session_type
    _validate_symbol(symbol)
    return get_context().broker.max_cash_buy_quantity(price or get_context().current_bar.close)


def max_qty_to_sell(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return get_context().broker.max_sell_quantity()


def max_qty_to_buyback(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return max(0.0, -get_context().broker.position.quantity)


def max_qty_to_sell_short(
    symbol: Contract,
    order_type: OrdType = OrdType.LMT,
    price: float = 0,
    order_trade_session_type: TSType = TSType.ETH,
) -> int:
    del order_type, order_trade_session_type
    _validate_symbol(symbol)
    if not get_context().broker.allow_short:
        return 0
    return get_context().broker.max_cash_buy_quantity(price or get_context().current_bar.close)


def position_market_cap(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return abs(get_context().broker.position.quantity * get_context().current_bar.close)


def position_side(symbol: Contract) -> PositionSide:
    _validate_symbol(symbol)
    return get_context().broker.position.side


def position_holding_qty(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return abs(get_context().broker.position.quantity)


def position_pl_amount(
    symbol: Contract, cost_price_model: CostPriceModel = CostPriceModel.AVG
) -> float:
    del cost_price_model
    return position_unrealized_pl(symbol) + position_realized_pl(symbol)


def position_pl_ratio(symbol: Contract) -> float:
    _validate_symbol(symbol)
    position = get_context().broker.position
    basis = abs(position.quantity) * position.average_price
    return position_pl_amount(symbol) / basis * 100 if basis else 0.0


def position_today_pl(symbol: Contract) -> float:
    _validate_symbol(symbol)
    today = get_context().current_bar.date[:10]
    return sum(trade.net_pnl for trade in get_context().broker.trades if trade.exit_date[:10] == today)


def position_cost(
    symbol: Contract, cost_price_model: CostPriceModel = CostPriceModel.AVG
) -> float:
    del cost_price_model
    _validate_symbol(symbol)
    return get_context().broker.position.average_price


def position_today_turnover(
    symbol: Contract, side: TradeSide = TradeSide.ALL
) -> float:
    return sum(fill.price * fill.quantity for fill in _today_fills(symbol, side))


def position_today_volume(symbol: Contract, side: TradeSide = TradeSide.ALL) -> float:
    return sum(fill.quantity for fill in _today_fills(symbol, side))


def available_qty(symbol: Contract) -> float:
    return max_qty_to_sell(symbol)


def position_unrealized_pl(symbol: Contract) -> float:
    _validate_symbol(symbol)
    context = get_context()
    position = context.broker.position
    if position.quantity > 0:
        return (context.current_bar.close - position.average_price) * position.quantity
    if position.quantity < 0:
        return (position.average_price - context.current_bar.close) * abs(position.quantity)
    return 0.0


def position_realized_pl(symbol: Contract) -> float:
    _validate_symbol(symbol)
    return sum(trade.net_pnl for trade in get_context().broker.trades)


def get_position_symbol() -> list[Contract]:
    return [get_context().symbol] if get_context().broker.position.quantity else []


def request_orderid(
    symbol: Contract | str = "",
    status: Iterable[str | OrderStatus] = (),
    start: str = "",
    end: str = "",
    time_zone: Any = None,
) -> list[str]:
    del time_zone
    statuses = {OrderStatus(value) for value in status}
    orders = list(get_context().broker.orders.values())
    return [
        order.order_id
        for order in reversed(orders)
        if (not symbol or str(order.symbol) == str(symbol))
        and (not statuses or order.status in statuses)
        and _within(order.submitted_date, start, end)
    ]


def order_status(orderid: str) -> OrderStatus:
    return _order(orderid).status


def order_symbol(orderid: str) -> Contract:
    return _order(orderid).symbol


def order_price(orderid: str) -> float:
    return float(_order(orderid).limit_price or 0.0)


def order_filled_avg_price(orderid: str) -> float:
    return _order(orderid).filled_avg_price


def order_qty(orderid: str) -> float:
    return _order(orderid).quantity


def order_filled_qty(orderid: str) -> float:
    return _order(orderid).filled_quantity


def order_executionid(orderid: str) -> list[str]:
    return list(_order(orderid).execution_ids)


def order_side(orderid: str) -> OrderSide:
    return _order(orderid).side


def order_aux_price(orderid: str) -> float:
    return float(_order(orderid).stop_price or 0.0)


def order_types(orderid: str) -> OrdType:
    mapping = {
        "MARKET": OrdType.MKT,
        "LIMIT": OrdType.LMT,
        "STOP": OrdType.STOP,
        "STOP_LIMIT": OrdType.STOP_LMT,
        "LIMIT_IF_TOUCHED": OrdType.LIM_IF_TOUCHED,
        "MARKET_IF_TOUCHED": OrdType.MKT_IF_TOUCHED,
        "TRAILING_STOP_LIMIT": OrdType.TRAILING_STOP_LMT,
        "TRAILING_STOP": OrdType.TRAILING_STOP,
    }
    return mapping[_order(orderid).order_type]


def order_trail_type(orderid: str) -> Any:
    return _order(orderid).trail_type


def order_trail_value(orderid: str) -> float:
    return float(_order(orderid).trail_value or 0.0)


def order_trail_spread(orderid: str) -> float:
    return float(_order(orderid).trail_spread or 0.0)


def order_filled_outside_rth(orderid: str) -> bool:
    return _order(orderid).trade_session != TSType.RTH


def order_time_in_force(orderid: str) -> Any:
    return _order(orderid).time_in_force


def order_create_time(
    orderid: str, time_zone: TimeZone = TimeZone.MARKET_TIME_ZONE
) -> datetime:
    return _historical_time(_order(orderid).submitted_date, time_zone)


def get_orderid_by_groupid(groupid: str) -> dict[str, str]:
    try:
        return dict(get_context().broker.order_groups[str(groupid)])
    except KeyError as error:
        raise KeyError(f"unknown order group id: {groupid}") from error


def request_executionid(
    symbol: Contract | str = "",
    start: str = "",
    end: str = "",
    time_zone: Any = None,
) -> list[str]:
    del time_zone
    fills = reversed(get_context().broker.fills)
    return [
        fill.execution_id
        for fill in fills
        if (not symbol or str(get_context().symbol) == str(symbol))
        and _within(fill.date, start, end)
    ]


def execution_status(executionid: str) -> DealStatus:
    _fill(executionid)
    return DealStatus.OK


def execution_symbol(executionid: str) -> Contract:
    _fill(executionid)
    return get_context().symbol


def execution_price(executionid: str) -> float:
    return _fill(executionid).price


def execution_qty(executionid: str) -> float:
    return _fill(executionid).quantity


def execution_side(executionid: str) -> OrderSide:
    return _fill(executionid).side


def execution_orderid(executionid: str) -> str:
    return _fill(executionid).order_id


def execution_time(
    executionid: str, time_zone: TimeZone = TimeZone.MARKET_TIME_ZONE
) -> datetime:
    return _historical_time(_fill(executionid).date, time_zone)


def alert(title: str = "", content: str = "") -> None:
    context = get_context()
    context.broker._log(context.current_bar.date, "ALERT", f"{title}: {content}".strip(": "))


def add_to_watchlist(symbol: Contract, watchlist: str = "") -> None:
    _validate_symbol(symbol)
    alert("watchlist", f"{symbol} -> {watchlist or 'default'}")


def quit_strategy() -> None:
    get_context().quit_requested = True


def _selected_bar(
    symbol: Contract,
    bar_type: BarType,
    select: int,
    session_type: THType,
) -> Any:
    _validate_symbol(symbol)
    _validate_session(session_type)
    if select <= 0:
        raise ValueError("select must be positive")
    series = get_context().bars_for(bar_type)
    index = len(series) - select
    return None if index < 0 else series[index]


def _bar_field(
    symbol: Contract,
    bar_type: BarType,
    select: int,
    session_type: THType,
    field: str,
) -> float:
    bar = _selected_bar(symbol, bar_type, select, session_type)
    if bar is None:
        return math.nan
    value = getattr(bar, field)
    if value is None:
        raise DataUnavailableError(f"{field} is not present in the OpenD history data")
    return float(value)


def _validate_symbol(symbol: Contract | str) -> None:
    if str(symbol) != str(get_context().symbol):
        raise UnsupportedAPIError("stock backtests support one trigger symbol per run")


def _validate_session(session_type: THType | str) -> None:
    context = get_context()
    if not str(context.symbol).startswith("US."):
        return
    if THType(session_type) != context.session_type:
        raise UnsupportedAPIError(
            f"requested {THType(session_type).value} but input contains {context.session_type.value}"
        )


def _validate_currency(currency: Currency | str) -> None:
    Currency(currency)


def _validate_level(level: int) -> None:
    if not 1 <= int(level) <= 10:
        raise ValueError("order-book level must be between 1 and 10")


def _historical_time(value: str, requested: TimeZone | str) -> datetime:
    current = datetime.fromisoformat(value.replace("Z", "+00:00"))
    market_zone = _market_time_zone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=market_zone)
    return current.astimezone(_time_zone_info(TimeZone(requested), market_zone))


def _market_time_zone() -> tzinfo:
    market = str(get_context().symbol).partition(".")[0]
    return ZoneInfo(
        {
            "US": "America/New_York",
            "CA": "America/Toronto",
            "HK": "Asia/Hong_Kong",
            "SH": "Asia/Shanghai",
            "SZ": "Asia/Shanghai",
            "JP": "Asia/Tokyo",
            "SG": "Asia/Singapore",
            "AU": "Australia/Sydney",
            "UK": "Europe/London",
        }.get(market, "UTC")
    )


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
    hours = int(value.value.rsplit("_", 1)[-1])
    return timezone(timedelta(hours=direction * hours))


def _market_moment() -> datetime:
    return datetime.fromisoformat(get_context().current_bar.date.replace("Z", "+00:00"))


def _hk_tick(price: float) -> float:
    for maximum, tick in (
        (0.25, 0.001),
        (0.5, 0.005),
        (10, 0.01),
        (20, 0.02),
        (100, 0.05),
        (200, 0.1),
        (500, 0.2),
        (1000, 0.5),
        (2000, 1.0),
        (5000, 2.0),
        (math.inf, 5.0),
    ):
        if price <= maximum:
            return tick
    return 5.0


def _order(orderid: str) -> Order:
    return get_context().broker.get_order(str(orderid))


def _fill(executionid: str) -> Any:
    return get_context().broker.get_fill(str(executionid))


def _today_fills(symbol: Contract, side: TradeSide) -> list[Any]:
    _validate_symbol(symbol)
    today = get_context().current_bar.date[:10]
    normalized = TradeSide(side)
    allowed = {
        TradeSide.BUY: {OrderSide.BUY, OrderSide.BUY_BACK},
        TradeSide.SELL: {OrderSide.SELL, OrderSide.SELL_SHORT},
        TradeSide.ALL: set(OrderSide),
    }[normalized]
    return [
        fill
        for fill in get_context().broker.fills
        if fill.date[:10] == today and fill.side in allowed
    ]


def _within(value: str, start: str, end: str) -> bool:
    return (not start or value >= start) and (not end or value <= end + (" 23:59:59" if len(end) == 10 else ""))


__all__ = [
    name
    for name, value in globals().items()
    if callable(value)
    and getattr(value, "__module__", None) == __name__
    and not name.startswith("_")
]
