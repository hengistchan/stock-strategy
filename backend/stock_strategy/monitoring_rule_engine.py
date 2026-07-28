"""Pure monitoring-rule decisions without persistence or runtime side effects."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .monitoring_models import (
    RuleMetric,
    RuleOperator,
    evaluate_rule,
    metric_value,
)


class MarketSession(StrEnum):
    REGULAR = "regular"
    EXTENDED = "extended"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class RuleSuppressionReason(StrEnum):
    DISABLED = "disabled"
    RECONNECTING = "reconnecting"
    STALE = "stale"
    MARKET_CLOSED = "market_closed"
    MARKET_SESSION_UNKNOWN = "market_session_unknown"
    OUTSIDE_SESSION = "outside_session"
    METRIC_UNAVAILABLE = "metric_unavailable"
    BASELINE = "baseline"
    DAILY_LIMIT = "daily_limit"
    COOLDOWN = "cooldown"


@dataclass(frozen=True, slots=True)
class RuleDecision:
    """One deterministic decision for one rule and one market observation.

    When the observation is not evaluated, ``condition_active`` preserves the
    persisted state.  A baseline is evaluated and returns its newly derived
    active state, but can never trigger.
    """

    value: float | None
    condition_active: bool
    baseline: bool
    evaluated: bool
    triggered: bool
    suppression_reason: RuleSuppressionReason | None
    trigger_date: str


def decide_rule(
    rule: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    observed_at: datetime,
    provider_time: datetime,
    is_fresh: bool,
    reconnecting: bool,
    market_session: MarketSession | str,
) -> RuleDecision:
    """Evaluate a persisted monitoring rule against one normalized snapshot.

    Both timestamps must be timezone-aware.  ``observed_at`` drives the
    operational cooldown, while ``provider_time`` supplies the market-local
    date used for the daily trigger limit.
    """

    _require_aware(observed_at, "observed_at")
    _require_aware(provider_time, "provider_time")
    session = MarketSession(market_session)
    trigger_date = provider_time.date().isoformat()
    persisted_active = bool(rule.get("condition_active", False))

    if not bool(rule.get("enabled", False)):
        return _skipped(
            RuleSuppressionReason.DISABLED,
            trigger_date,
            persisted_active,
        )
    if reconnecting:
        return _skipped(
            RuleSuppressionReason.RECONNECTING,
            trigger_date,
            persisted_active,
        )
    if not is_fresh:
        return _skipped(
            RuleSuppressionReason.STALE,
            trigger_date,
            persisted_active,
        )

    session_reason = _session_suppression(rule, session)
    if session_reason is not None:
        return _skipped(session_reason, trigger_date, persisted_active)

    metric = RuleMetric(str(rule["metric"]))
    value = metric_value(snapshot, metric)
    if value is None:
        return _skipped(
            RuleSuppressionReason.METRIC_UNAVAILABLE,
            trigger_date,
            persisted_active,
        )

    previous_value = _optional_finite_number(rule.get("last_value"))
    evaluation = evaluate_rule(
        operator=RuleOperator(str(rule["operator"])),
        threshold=float(rule["threshold"]),
        value=value,
        previous_value=previous_value,
        was_active=persisted_active,
    )

    if previous_value is None:
        return RuleDecision(
            value=evaluation.value,
            condition_active=evaluation.active,
            baseline=True,
            evaluated=True,
            triggered=False,
            suppression_reason=RuleSuppressionReason.BASELINE,
            trigger_date=trigger_date,
        )

    if not evaluation.triggered:
        return RuleDecision(
            value=evaluation.value,
            condition_active=evaluation.active,
            baseline=False,
            evaluated=True,
            triggered=False,
            suppression_reason=None,
            trigger_date=trigger_date,
        )

    if _daily_limit_reached(rule, trigger_date):
        return _suppressed_evaluation(
            evaluation.value,
            evaluation.active,
            RuleSuppressionReason.DAILY_LIMIT,
            trigger_date,
        )
    if _cooldown_active(rule, observed_at):
        return _suppressed_evaluation(
            evaluation.value,
            evaluation.active,
            RuleSuppressionReason.COOLDOWN,
            trigger_date,
        )

    return RuleDecision(
        value=evaluation.value,
        condition_active=evaluation.active,
        baseline=False,
        evaluated=True,
        triggered=True,
        suppression_reason=None,
        trigger_date=trigger_date,
    )


def _session_suppression(
    rule: Mapping[str, Any],
    market_session: MarketSession,
) -> RuleSuppressionReason | None:
    rule_session = str(rule.get("session", "regular"))
    if rule_session not in {"regular", "extended", "all"}:
        raise ValueError(f"unsupported rule session: {rule_session}")
    if market_session is MarketSession.CLOSED:
        return RuleSuppressionReason.MARKET_CLOSED
    if market_session is MarketSession.UNKNOWN:
        return RuleSuppressionReason.MARKET_SESSION_UNKNOWN
    if rule_session != "all" and rule_session != market_session.value:
        return RuleSuppressionReason.OUTSIDE_SESSION
    return None


def _daily_limit_reached(rule: Mapping[str, Any], trigger_date: str) -> bool:
    limit = _positive_int(rule.get("daily_trigger_limit", 10), "daily_trigger_limit")
    count = _nonnegative_int(rule.get("trigger_count", 0), "trigger_count")
    return rule.get("trigger_date") == trigger_date and count >= limit


def _cooldown_active(rule: Mapping[str, Any], observed_at: datetime) -> bool:
    cooldown = _nonnegative_int(rule.get("cooldown_seconds", 0), "cooldown_seconds")
    last_triggered = rule.get("last_triggered_at")
    if cooldown == 0 or last_triggered in {None, ""}:
        return False
    triggered_at = _stored_datetime(last_triggered, "last_triggered_at")
    return (observed_at - triggered_at).total_seconds() < cooldown


def _stored_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO 8601 datetime") from error
    else:
        raise ValueError(f"{field} must be an ISO 8601 datetime")
    _require_aware(parsed, field)
    return parsed


def _optional_finite_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_int(value: Any, field: str) -> int:
    parsed = _integer(value, field)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _nonnegative_int(value: Any, field: str) -> int:
    parsed = _integer(value, field)
    if parsed < 0:
        raise ValueError(f"{field} must be nonnegative")
    return parsed


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} must be an integer")
    return parsed


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _skipped(
    reason: RuleSuppressionReason,
    trigger_date: str,
    persisted_active: bool,
) -> RuleDecision:
    return RuleDecision(
        value=None,
        condition_active=persisted_active,
        baseline=False,
        evaluated=False,
        triggered=False,
        suppression_reason=reason,
        trigger_date=trigger_date,
    )


def _suppressed_evaluation(
    value: float,
    condition_active: bool,
    reason: RuleSuppressionReason,
    trigger_date: str,
) -> RuleDecision:
    return RuleDecision(
        value=value,
        condition_active=condition_active,
        baseline=False,
        evaluated=True,
        triggered=False,
        suppression_reason=reason,
        trigger_date=trigger_date,
    )
