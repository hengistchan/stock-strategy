from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class BarType(StringEnum):
    K_1M = "K_1M"
    K_3M = "K_3M"
    K_5M = "K_5M"
    K_10M = "K_10M"
    K_15M = "K_15M"
    K_30M = "K_30M"
    K_60M = "K_60M"
    K_120M = "K_120M"
    K_180M = "K_180M"
    K_240M = "K_240M"
    K_DAY = "K_DAY"
    K_WEEK = "K_WEEK"


class DataType(StringEnum):
    CLOSE = "CLOSE"
    OPEN = "OPEN"
    HIGH = "HIGH"
    LOW = "LOW"
    VOLUME = "VOLUME"


class BarDataType(StringEnum):
    CLOSE = "CLOSE"
    OPEN = "OPEN"
    HIGH = "HIGH"
    LOW = "LOW"
    VOLUME = "VOLUME"
    TURNOVER = "TURNOVER"


class CustomType(StringEnum):
    K_1M = "K_1M"
    K_60M = "K_60M"
    K_DAY = "K_DAY"
    M1 = "M1"
    H1 = "H1"
    D1 = "D1"


class THType(StringEnum):
    RTH = "RTH"
    ETH = "ETH"
    ALL = "ALL"


class TSType(StringEnum):
    RTH = "RTH"
    ETH = "ETH"
    ALL = "ALL"
    OVERNIGHT = "OVERNIGHT"


class TimeZone(StringEnum):
    DEVICE_TIME_ZONE = "DEVICE_TIME_ZONE"
    MARKET_TIME_ZONE = "MARKET_TIME_ZONE"
    ET = "ET"
    CT = "CT"
    HST = "HST"
    AKST = "AKST"
    PST = "PST"
    MST = "MST"
    CCT = "CCT"
    GMT = "GMT"
    CET = "CET"
    EET = "EET"
    JST = "JST"
    KST = "KST"
    AET = "AET"
    UTC_MINUS_11 = "UTC_MINUS_11"
    UTC_MINUS_10 = "UTC_MINUS_10"
    UTC_MINUS_9 = "UTC_MINUS_9"
    UTC_MINUS_8 = "UTC_MINUS_8"
    UTC_MINUS_7 = "UTC_MINUS_7"
    UTC_MINUS_6 = "UTC_MINUS_6"
    UTC_MINUS_5 = "UTC_MINUS_5"
    UTC_MINUS_4 = "UTC_MINUS_4"
    UTC_MINUS_3 = "UTC_MINUS_3"
    UTC_MINUS_2 = "UTC_MINUS_2"
    UTC_MINUS_1 = "UTC_MINUS_1"
    UTC = "UTC"
    UTC_PLUS_1 = "UTC_PLUS_1"
    UTC_PLUS_2 = "UTC_PLUS_2"
    UTC_PLUS_3 = "UTC_PLUS_3"
    UTC_PLUS_4 = "UTC_PLUS_4"
    UTC_PLUS_5 = "UTC_PLUS_5"
    UTC_PLUS_6 = "UTC_PLUS_6"
    UTC_PLUS_7 = "UTC_PLUS_7"
    UTC_PLUS_8 = "UTC_PLUS_8"
    UTC_PLUS_9 = "UTC_PLUS_9"
    UTC_PLUS_10 = "UTC_PLUS_10"
    UTC_PLUS_11 = "UTC_PLUS_11"
    UTC_PLUS_12 = "UTC_PLUS_12"


class OrderSide(StringEnum):
    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"
    BUY_BACK = "BUY_BACK"


class PositionSide(StringEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class TimeInForce(StringEnum):
    DAY = "DAY"
    GTC = "GTC"


class AlgoStrategyType(StringEnum):
    SECURITY = "SECURITY"
    FUTURE = "FUTURE"


class GlobalType(StringEnum):
    FLOAT = "FLOAT"
    INT = "INT"
    BOOL = "BOOL"


class OrdType(StringEnum):
    LMT = "LMT"
    MKT = "MKT"
    STOP = "STOP"


class Contract(str):
    """Futu-compatible symbol wrapper, e.g. Contract('US.AAPL')."""

    def __new__(cls, symbol: str) -> Contract:
        normalized = symbol.strip().upper()
        if "." not in normalized:
            raise ValueError("Contract must use MARKET.SYMBOL format, e.g. US.AAPL")
        return super().__new__(cls, normalized)


@dataclass(frozen=True, slots=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Order:
    order_id: str
    symbol: Contract
    side: OrderSide
    quantity: float
    order_type: str
    submitted_index: int
    submitted_date: str
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    stop_price: float | None = None
    exit_reason: str = "signal"
    active_date: str | None = None
    reserved_cash: float = 0.0


@dataclass(slots=True)
class Trade:
    trade_id: int
    symbol: str
    side: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    fees: float
    net_pnl: float
    return_pct: float
    bars_held: int
    exit_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EquityPoint:
    date: str
    equity: float
    benchmark: float
    drawdown: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Metrics:
    initial_equity: float
    final_equity: float
    total_return_pct: float
    benchmark_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate_pct: float
    profit_factor: float | None
    total_trades: int
    exposure_pct: float
    total_fees: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogEntry:
    date: str
    level: str
    message: str


@dataclass(slots=True)
class Position:
    quantity: float = 0.0
    average_price: float = 0.0
    entry_date: str = ""
    entry_index: int = 0
    entry_fees: float = 0.0

    @property
    def side(self) -> PositionSide:
        if self.quantity > 0:
            return PositionSide.LONG
        if self.quantity < 0:
            return PositionSide.SHORT
        return PositionSide.NONE


@dataclass(slots=True)
class BacktestArtifacts:
    output_dir: str
    summary_path: str
    trades_path: str
    equity_path: str
    chart_path: str | None = None


@dataclass(slots=True)
class BacktestResult:
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    bar_count: int
    metrics: Metrics
    settings: dict[str, Any] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    logs: list[LogEntry] = field(default_factory=list)
    artifacts: BacktestArtifacts | None = None
