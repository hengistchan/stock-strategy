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
    CHANGE_RATE_5M = "change_rate_5m"
    VOLUME = "volume"
    MID_PRICE = "mid_price"
    BID_ASK_SPREAD = "bid_ask_spread"
    BID_ASK_SPREAD_PCT = "bid_ask_spread_pct"
    MA20 = "ma20"
    MA60 = "ma60"
    MA20_MA60_SPREAD_PCT = "ma20_ma60_spread_pct"
    RSI14 = "rsi14"
    OPTION_IMPLIED_VOLATILITY = "option_implied_volatility"
    HISTORICAL_VOLATILITY = "historical_volatility"
    IV_HV_PREMIUM = "iv_hv_premium"
    OPTION_OPEN_INTEREST = "option_open_interest"
    VOLUME_OPEN_INTEREST_RATIO = "volume_open_interest_ratio"
    OPTION_DELTA = "option_delta"
    OPTION_GAMMA = "option_gamma"
    OPTION_VEGA = "option_vega"
    OPTION_THETA = "option_theta"
    OPTION_RHO = "option_rho"
    DAYS_TO_EXPIRY = "days_to_expiry"
    STRIKE_DISTANCE_PCT = "strike_distance_pct"
    EXPIRY_GAMMA_RISK = "expiry_gamma_risk"
    EXPIRY_THETA_RISK = "expiry_theta_risk"
    CALL_PUT_VOLUME_RATIO = "call_put_volume_ratio"
    CALL_PUT_OPEN_INTEREST_RATIO = "call_put_open_interest_ratio"


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
        RuleMetric.CHANGE_RATE_5M,
        RuleMetric.VOLUME,
        RuleMetric.MID_PRICE,
        RuleMetric.BID_ASK_SPREAD,
        RuleMetric.BID_ASK_SPREAD_PCT,
        RuleMetric.MA20,
        RuleMetric.MA60,
        RuleMetric.MA20_MA60_SPREAD_PCT,
        RuleMetric.RSI14,
    }
)
OPTION_METRICS = frozenset(
    {
        RuleMetric.LAST_PRICE,
        RuleMetric.CHANGE_RATE,
        RuleMetric.CHANGE_RATE_5M,
        RuleMetric.VOLUME,
        RuleMetric.MID_PRICE,
        RuleMetric.BID_ASK_SPREAD,
        RuleMetric.BID_ASK_SPREAD_PCT,
        RuleMetric.OPTION_IMPLIED_VOLATILITY,
        RuleMetric.HISTORICAL_VOLATILITY,
        RuleMetric.IV_HV_PREMIUM,
        RuleMetric.OPTION_OPEN_INTEREST,
        RuleMetric.VOLUME_OPEN_INTEREST_RATIO,
        RuleMetric.OPTION_DELTA,
        RuleMetric.OPTION_GAMMA,
        RuleMetric.OPTION_VEGA,
        RuleMetric.OPTION_THETA,
        RuleMetric.OPTION_RHO,
        RuleMetric.DAYS_TO_EXPIRY,
        RuleMetric.STRIKE_DISTANCE_PCT,
        RuleMetric.EXPIRY_GAMMA_RISK,
        RuleMetric.EXPIRY_THETA_RISK,
        RuleMetric.CALL_PUT_VOLUME_RATIO,
        RuleMetric.CALL_PUT_OPEN_INTEREST_RATIO,
    }
)


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
        triggered = previous_value is not None and active and not was_active
    elif operator is RuleOperator.BELOW:
        active = value < threshold
        triggered = previous_value is not None and active and not was_active
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
    if metric in {
        RuleMetric.MID_PRICE,
        RuleMetric.BID_ASK_SPREAD,
        RuleMetric.BID_ASK_SPREAD_PCT,
    }:
        bid = _number(snapshot.get("bid_price"))
        ask = _number(snapshot.get("ask_price"))
        if bid is None or ask is None or ask < bid:
            return None
        midpoint = (bid + ask) / 2
        if metric is RuleMetric.MID_PRICE:
            return midpoint
        if metric is RuleMetric.BID_ASK_SPREAD:
            return ask - bid
        return None if midpoint <= 0 else (ask - bid) / midpoint * 100
    if metric is RuleMetric.VOLUME_OPEN_INTEREST_RATIO:
        return _positive_denominator_ratio(
            snapshot.get("volume"),
            snapshot.get("option_open_interest"),
        )
    if metric is RuleMetric.MA20_MA60_SPREAD_PCT:
        ma20 = _number(snapshot.get("ma20"))
        ma60 = _number(snapshot.get("ma60"))
        if ma20 is None or ma60 is None or ma60 == 0:
            return None
        return (ma20 - ma60) / ma60 * 100
    if metric is RuleMetric.IV_HV_PREMIUM:
        implied = _number(snapshot.get("option_implied_volatility"))
        historical = _number(snapshot.get("historical_volatility"))
        if implied is None or historical is None:
            return None
        return implied - historical
    if metric is RuleMetric.STRIKE_DISTANCE_PCT:
        underlying = _number(snapshot.get("underlying_price"))
        strike = _number(snapshot.get("strike_price"))
        if underlying is None or strike is None or strike <= 0:
            return None
        return abs(underlying - strike) / strike * 100
    if metric is RuleMetric.EXPIRY_GAMMA_RISK:
        gamma = _number(snapshot.get("option_gamma"))
        days = _number(snapshot.get("days_to_expiry"))
        if gamma is None or days is None or days < 0:
            return None
        return abs(gamma) * 100 / max(days, 1)
    if metric is RuleMetric.EXPIRY_THETA_RISK:
        theta = _number(snapshot.get("option_theta"))
        days = _number(snapshot.get("days_to_expiry"))
        if theta is None or days is None or days < 0:
            return None
        return abs(theta) / max(days, 1)
    return _number(snapshot.get(metric.value))


def _positive_denominator_ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _number(numerator)
    denominator_value = _number(denominator)
    if numerator_value is None or denominator_value is None or denominator_value <= 0:
        return None
    return numerator_value / denominator_value


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
