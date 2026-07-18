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
    M1 = "K_1M"
    M3 = "K_3M"
    M5 = "K_5M"
    M10 = "K_10M"
    M15 = "K_15M"
    M30 = "K_30M"
    H1 = "K_60M"
    H2 = "K_120M"
    H3 = "K_180M"
    H4 = "K_240M"
    D1 = "K_DAY"
    W1 = "K_WEEK"


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
    TURNOVER_RATE = "TURNOVER_RATE"
    CHG_RATE = "CHG_RATE"
    CHG = "CHG"


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
    AUTO = "AUTO"


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
    STOP_LMT = "STOP_LMT"
    STOP = "STOP"
    LIM_IF_TOUCHED = "LIM_IF_TOUCHED"
    MKT_IF_TOUCHED = "MKT_IF_TOUCHED"
    TRAILING_STOP_LMT = "TRAILING_STOP_LMT"
    TRAILING_STOP = "TRAILING_STOP"


class IndexOptionType(StringEnum):
    NORMAL = "NORMAL"
    SMALL = "SMALL"


class DealStatus(StringEnum):
    OK = "OK"
    CANCELLED = "CANCELLED"
    CHANGED = "CHANGED"


class CltRiskStatus(StringEnum):
    LEVEL1 = "LEVEL1"
    LEVEL2 = "LEVEL2"
    LEVEL3 = "LEVEL3"
    LEVEL4 = "LEVEL4"
    LEVEL5 = "LEVEL5"
    LEVEL6 = "LEVEL6"
    LEVEL7 = "LEVEL7"
    LEVEL8 = "LEVEL8"
    LEVEL9 = "LEVEL9"


class OptionType(StringEnum):
    ALL = "ALL"
    CALL = "CALL"
    PUT = "PUT"


class Currency(StringEnum):
    HKD = "HKD"
    USD = "USD"
    CNH = "CNH"
    JPY = "JPY"
    SGD = "SGD"
    AUD = "AUD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    MYR = "MYR"
    KRW = "KRW"
    INR = "INR"
    TWD = "TWD"


class Week(StringEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


class Moneyness(StringEnum):
    ITM = "ITM"
    OTM = "OTM"


class TradeSide(StringEnum):
    BUY = "BUY"
    SELL = "SELL"
    ALL = "ALL"


class OrderStatus(StringEnum):
    WAITING_SUBMIT = "WAITING_SUBMIT"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    FILLED_PART = "FILLED_PART"
    FILLED_ALL = "FILLED_ALL"
    CANCELLED_PART = "CANCELLED_PART"
    CANCELLED_ALL = "CANCELLED_ALL"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class TrdHours(StringEnum):
    RTH = "RTH"
    ITH = "ITH"
    CLOSED = "CLOSED"


class TrailType(StringEnum):
    RATIO = "RATIO"
    AMOUNT = "AMOUNT"


class TimeOrientation(StringEnum):
    LATER_THAN = "LATER_THAN"
    EARLIER_THAN = "EARLIER_THAN"
    NOT_LATER_THAN = "NOT_LATER_THAN"
    NOT_EARLIER_THAN = "NOT_EARLIER_THAN"


class ErrCode(StringEnum):
    ExceedReqLimit = "ExceedReqLimit"
    ReqTimeout = "ReqTimeout"
    NoQuoteRight = "NoQuoteRight"
    InvalidArgument = "InvalidArgument"
    ReqFailed = "ReqFailed"
    NoDataAvailable = "NoDataAvailable"
    EmptySymbol = "EmptySymbol"
    EmptyCode = "EmptyCode"
    Unknow = "Unknow"
    Unknown = "Unknown"


class InlinePriceType(StringEnum):
    UPPER_LIMIT = "UPPER_LIMIT"
    LOWER_LIMIT = "LOWER_LIMIT"


class OptionClass(StringEnum):
    Moneyness = "Moneyness"
    Type = "Type"
    Style = "Style"


class DTStatus(StringEnum):
    UNLIMITED = "UNLIMITED"
    EM_Call = "EM_Call"
    DT_Call = "DT_Call"


class OptionCategory(StringEnum):
    ITM = "ITM"
    OTM = "OTM"
    CALL = "CALL"
    PUT = "PUT"
    AMERICAN = "AMERICAN"
    EUROPEAN = "EUROPEAN"
    BERMUDA = "BERMUDA"


class CostPriceModel(StringEnum):
    DILUTED = "DILUTED"
    AVG = "AVG"


class FutureType(StringEnum):
    ALL = "ALL"
    MAIN = "MAIN"
    CURRENT = "CURRENT"
    NEXT = "NEXT"
    DAY = "DAY"
    MONTH = "MONTH"


class MktStatus(StringEnum):
    AUCTION = "AUCTION"
    CONTINUOUS_TRADE = "CONTINUOUS_TRADE"
    CLOSED = "CLOSED"


class USMktStatus(StringEnum):
    PRE_MARKET = "PRE_MARKET"
    RTH = "RTH"
    POST_MARKET = "POST_MARKET"
    OVERNIGHT = "OVERNIGHT"
    CLOSED = "CLOSED"


class Market(StringEnum):
    HK = "HK"
    US = "US"
    SZ = "SZ"
    SH = "SH"
    SG = "SG"
    JP = "JP"
    MY = "MY"
    CA = "CA"
    AU = "AU"
    FX = "FX"
    EU = "EU"
    KR = "KR"
    IN = "IN"
    TW = "TW"


class SymbolType(StringEnum):
    STOCK = "STOCK"
    FUTURES = "FUTURES"
    OPTION = "OPTION"
    ETF = "ETF"
    INDEX = "INDEX"
    WARRANT = "WARRANT"
    FOREX = "FOREX"
    PLATE = "PLATE"


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
    turnover: float | None = None
    turnover_rate: float | None = None
    change_rate: float | None = None
    last_close: float | None = None


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
    status: OrderStatus = OrderStatus.SUBMITTED
    filled_quantity: float = 0.0
    filled_avg_price: float = 0.0
    execution_ids: list[str] = field(default_factory=list)
    trade_session: TSType = TSType.ALL
    trail_type: TrailType | None = None
    trail_value: float | None = None
    trail_spread: float | None = None
    triggered: bool = False
    trail_reference: float | None = None
    follow_up_side: OrderSide | None = None
    follow_up_quantity: float | None = None
    group_id: str | None = None


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
