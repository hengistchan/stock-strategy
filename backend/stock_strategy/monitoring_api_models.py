from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .application_models import SYMBOL_PATTERN
from .monitoring_models import (
    InstrumentType,
    RuleMetric,
    RuleOperator,
    RuleSeverity,
)


class MonitoringApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class MonitorInstrumentRequest(BaseModel):
    code: str = Field(pattern=SYMBOL_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    instrument_type: InstrumentType = InstrumentType.STOCK
    underlying_code: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    enabled: bool = True

    @field_validator("code", "underlying_code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("instrument name cannot be blank")
            return normalized
        return value


class MonitorInstrumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("instrument name cannot be blank")
            return normalized
        return value


class MarketSnapshot(MonitoringApiModel):
    code: str
    name: str = ""
    instrument_type: InstrumentType
    source: Literal["opend"] = "opend"
    source_time: str | None = None
    fetched_at: str
    last_price: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    volume: float | None = None


class MonitoredInstrument(MonitoringApiModel):
    code: str
    name: str
    market: str
    instrument_type: InstrumentType
    underlying_code: str | None
    enabled: bool
    created_at: str
    updated_at: str
    snapshot: MarketSnapshot | None = None
    freshness: Literal[
        "live",
        "stale",
        "market_closed",
        "unavailable",
    ] = "unavailable"


class WatchlistResponse(BaseModel):
    instruments: list[MonitoredInstrument]


class SnapshotResponse(BaseModel):
    snapshot: MarketSnapshot
    freshness: Literal["live", "stale", "market_closed", "unavailable"]
    market_state: str
    age_seconds: float | None


class OptionExpiration(MonitoringApiModel):
    expiration: str
    days_to_expiry: int | None = None
    cycle: str = ""


class OptionExpirationsResponse(BaseModel):
    underlying: str
    expirations: list[OptionExpiration]
    fetched_at: str


class OptionContract(MonitoringApiModel):
    code: str
    name: str
    underlying_code: str
    option_type: Literal["CALL", "PUT"] | None
    expiration: str
    strike_price: float | None


class OptionChainResponse(BaseModel):
    underlying: str
    expiration: str
    underlying_snapshot: MarketSnapshot
    contracts: list[OptionContract]
    summary: dict[str, float | int | None]
    fetched_at: str
    source: Literal["opend"] = "opend"


class OptionContractResponse(BaseModel):
    contract: OptionContract
    analytics: dict[str, Any]
    freshness: Literal["live", "stale", "market_closed", "unavailable"]


class MonitorBar(MonitoringApiModel):
    code: str
    source_time: str | None
    ktype: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    is_closed: bool


class MonitorBarsResponse(BaseModel):
    code: str
    ktype: str
    bars: list[MonitorBar]


class MonitorRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(pattern=SYMBOL_PATTERN)
    instrument_type: InstrumentType
    metric: RuleMetric
    operator: RuleOperator
    threshold: float = Field(allow_inf_nan=False)
    severity: RuleSeverity = RuleSeverity.WARNING
    cooldown_seconds: int = Field(default=300, ge=0, le=86_400)
    daily_trigger_limit: int = Field(default=10, ge=1, le=1_000)
    session: Literal["regular", "extended", "all"] = "regular"
    enabled: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_rule_code(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_rule_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("rule name cannot be blank")
            return normalized
        return value


class MonitorRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    metric: RuleMetric | None = None
    operator: RuleOperator | None = None
    threshold: float | None = Field(default=None, allow_inf_nan=False)
    severity: RuleSeverity | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86_400)
    daily_trigger_limit: int | None = Field(default=None, ge=1, le=1_000)
    session: Literal["regular", "extended", "all"] | None = None
    enabled: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_rule_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("rule name cannot be blank")
            return normalized
        return value


class MonitorRule(MonitoringApiModel):
    id: str
    name: str
    code: str
    instrument_type: InstrumentType
    metric: RuleMetric
    operator: RuleOperator
    threshold: float
    severity: RuleSeverity
    cooldown_seconds: int
    daily_trigger_limit: int
    session: Literal["regular", "extended", "all"]
    enabled: bool
    created_at: str
    updated_at: str


class MonitorRulesResponse(BaseModel):
    rules: list[MonitorRule]


class MonitorAlert(MonitoringApiModel):
    id: str
    dedupe_key: str
    rule_id: str
    rule_name: str
    code: str
    triggered_at: str
    acknowledged_at: str | None
    severity: RuleSeverity
    metric: RuleMetric
    operator: RuleOperator
    threshold: float
    value: float
    source: Literal["opend"]
    provider_time: str
    received_at: str
    snapshot: dict[str, Any]


class MonitorAlertsResponse(BaseModel):
    alerts: list[MonitorAlert]
    next_cursor: str | None


class MonitoringStatusResponse(MonitoringApiModel):
    phase: Literal[
        "stopped",
        "starting",
        "ready",
        "degraded",
        "reconnecting",
    ]
    rules_paused: bool
    last_success_at: str | None
    last_error: str | None
    market_states: dict[str, str]
    generic_subscription_budget: dict[str, Any] | None
    freshness: dict[str, str]


class MonitoringDiagnosticCheck(BaseModel):
    id: str
    status: Literal["pass", "fail", "blocked"]
    detail: str
    hint: str | None = None


class MonitoringDiagnosticsResponse(BaseModel):
    ready: bool
    checks: list[MonitoringDiagnosticCheck]
