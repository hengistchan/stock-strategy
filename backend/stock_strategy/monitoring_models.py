from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any, Mapping


class InstrumentType(StrEnum):
    STOCK = "stock"
    OPTION = "option"


class RuleMetric(StrEnum):
    LAST_PRICE = "last_price"
    CHANGE_RATE = "change_rate"
    VOLUME = "volume"
    BID_ASK_SPREAD_PCT = "bid_ask_spread_pct"
    OPTION_IMPLIED_VOLATILITY = "option_implied_volatility"
    OPTION_OPEN_INTEREST = "option_open_interest"
    VOLUME_OPEN_INTEREST_RATIO = "volume_open_interest_ratio"
    OPTION_DELTA = "option_delta"
    OPTION_GAMMA = "option_gamma"
    OPTION_VEGA = "option_vega"
    OPTION_THETA = "option_theta"
    OPTION_RHO = "option_rho"
    DAYS_TO_EXPIRY = "days_to_expiry"


class RuleOperator(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class RuleSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


STOCK_METRICS = frozenset(
    {
        RuleMetric.LAST_PRICE,
        RuleMetric.CHANGE_RATE,
        RuleMetric.VOLUME,
        RuleMetric.BID_ASK_SPREAD_PCT,
    }
)
OPTION_METRICS = frozenset(RuleMetric)


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    value: float
    active: bool
    triggered: bool


def validate_rule_metric(
    instrument_type: InstrumentType,
    metric: RuleMetric,
) -> None:
    supported = (
        STOCK_METRICS if instrument_type is InstrumentType.STOCK else OPTION_METRICS
    )
    if metric not in supported:
        raise ValueError(
            f"{metric.value} is not available for {instrument_type.value} instruments"
        )


def evaluate_rule(
    *,
    operator: RuleOperator,
    threshold: float,
    value: float,
    previous_value: float | None,
    was_active: bool,
) -> RuleEvaluation:
    if not isfinite(threshold) or not isfinite(value):
        raise ValueError("monitor rule values must be finite")
    if previous_value is not None and not isfinite(previous_value):
        previous_value = None

    if operator is RuleOperator.ABOVE:
        active = value > threshold
        triggered = active and not was_active
    elif operator is RuleOperator.BELOW:
        active = value < threshold
        triggered = active and not was_active
    elif operator is RuleOperator.CROSSES_ABOVE:
        active = value > threshold
        triggered = (
            previous_value is not None
            and previous_value <= threshold
            and value > threshold
        )
    else:
        active = value < threshold
        triggered = (
            previous_value is not None
            and previous_value >= threshold
            and value < threshold
        )
    return RuleEvaluation(value=value, active=active, triggered=triggered)


def metric_value(
    snapshot: Mapping[str, Any],
    metric: RuleMetric,
) -> float | None:
    if metric is RuleMetric.BID_ASK_SPREAD_PCT:
        bid = _number(snapshot.get("bid_price"))
        ask = _number(snapshot.get("ask_price"))
        if bid is None or ask is None or ask < bid:
            return None
        midpoint = (bid + ask) / 2
        return None if midpoint <= 0 else (ask - bid) / midpoint * 100
    if metric is RuleMetric.VOLUME_OPEN_INTEREST_RATIO:
        volume = _number(snapshot.get("volume"))
        open_interest = _number(snapshot.get("option_open_interest"))
        if volume is None or open_interest is None or open_interest <= 0:
            return None
        return volume / open_interest
    return _number(snapshot.get(metric.value))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
