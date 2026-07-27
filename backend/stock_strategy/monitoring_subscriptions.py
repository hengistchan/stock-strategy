from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

_EXACT_SECURITY_CODE = re.compile(r"^[A-Z]{2,4}\.[A-Z0-9]+$")
_EXACT_SUBTYPE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True, order=True, slots=True)
class SubscriptionTarget:
    """One exact OpenD-style security/subtype pair.

    A target can identify either a stock or one option contract. Deliberately,
    there is no target form for an underlying's complete option chain.
    """

    code: str
    subtype: str = "QUOTE"

    def __post_init__(self) -> None:
        normalized_code = self.code.strip().upper()
        normalized_subtype = self.subtype.strip().upper()
        if not _EXACT_SECURITY_CODE.fullmatch(normalized_code):
            raise ValueError(
                "subscription target must be one exact security code such as "
                "US.AAPL or US.AAPL260731C95000"
            )
        if not _EXACT_SUBTYPE.fullmatch(normalized_subtype):
            raise ValueError("subscription subtype must be one exact subtype")
        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "subtype", normalized_subtype)


class SubscriptionIntentSource(IntEnum):
    """Business priority for competing requests for generic subscriptions."""

    TEMPORARY_PAGE_INTEREST = 10
    WATCHLIST = 20
    PERSISTENT_RULE = 30


@dataclass(frozen=True, slots=True)
class SubscriptionIntent:
    target: SubscriptionTarget
    source: SubscriptionIntentSource
    expires_at: float | None = None

    def __post_init__(self) -> None:
        if self.source is SubscriptionIntentSource.TEMPORARY_PAGE_INTEREST:
            if self.expires_at is None or not math.isfinite(self.expires_at):
                raise ValueError(
                    "temporary page subscription intent requires a finite expiry"
                )
        elif self.expires_at is not None:
            raise ValueError("persistent subscription intents cannot expire")

    @classmethod
    def persistent_rule(
        cls,
        code: str,
        *,
        subtype: str = "QUOTE",
    ) -> SubscriptionIntent:
        return cls(
            target=SubscriptionTarget(code, subtype),
            source=SubscriptionIntentSource.PERSISTENT_RULE,
        )

    @classmethod
    def watchlist(
        cls,
        code: str,
        *,
        subtype: str = "QUOTE",
    ) -> SubscriptionIntent:
        return cls(
            target=SubscriptionTarget(code, subtype),
            source=SubscriptionIntentSource.WATCHLIST,
        )

    @classmethod
    def temporary_page_interest(
        cls,
        code: str,
        *,
        now: float,
        ttl_seconds: float,
        subtype: str = "QUOTE",
    ) -> SubscriptionIntent:
        if not math.isfinite(now):
            raise ValueError("temporary page interest requires a finite clock value")
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("temporary page interest TTL must be positive and finite")
        return cls(
            target=SubscriptionTarget(code, subtype),
            source=SubscriptionIntentSource.TEMPORARY_PAGE_INTEREST,
            expires_at=now + ttl_seconds,
        )

    def is_active(self, *, now: float) -> bool:
        if not math.isfinite(now):
            raise ValueError("subscription planning requires a finite clock value")
        return self.expires_at is None or now < self.expires_at


@dataclass(frozen=True, slots=True)
class GenericSubscriptionBudget:
    """Generic query_subscription usage, shared by all security types."""

    generic_total_used: int
    generic_own_used: int
    generic_remaining: int

    def __post_init__(self) -> None:
        values = (
            self.generic_total_used,
            self.generic_own_used,
            self.generic_remaining,
        )
        if any(isinstance(value, bool) or value < 0 for value in values):
            raise ValueError("generic subscription usage cannot be negative")
        if self.generic_own_used > self.generic_total_used:
            raise ValueError(
                "generic own subscription usage cannot exceed generic total usage"
            )


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    desired: frozenset[SubscriptionTarget]
    actual_owned: frozenset[SubscriptionTarget]
    retained: frozenset[SubscriptionTarget]
    to_subscribe: tuple[SubscriptionTarget, ...]
    to_unsubscribe: tuple[SubscriptionTarget, ...]
    deferred: tuple[SubscriptionTarget, ...]
    expired_intents: tuple[SubscriptionIntent, ...]


class SubscriptionPlanner:
    """Plan a safe desired/actual reconciliation without performing I/O."""

    def plan(
        self,
        *,
        intents: Iterable[SubscriptionIntent],
        actual_owned: Iterable[SubscriptionTarget],
        budget: GenericSubscriptionBudget,
        now: float,
    ) -> SubscriptionPlan:
        if not math.isfinite(now):
            raise ValueError("subscription planning requires a finite clock value")

        active_by_target: dict[SubscriptionTarget, SubscriptionIntent] = {}
        expired: list[SubscriptionIntent] = []
        for intent in intents:
            if not intent.is_active(now=now):
                expired.append(intent)
                continue
            current = active_by_target.get(intent.target)
            if current is None or intent.source > current.source:
                active_by_target[intent.target] = intent

        desired = frozenset(active_by_target)
        actual = frozenset(actual_owned)
        retained = desired & actual
        to_unsubscribe = tuple(sorted(actual - desired))

        candidates = sorted(
            desired - actual,
            key=lambda target: (
                -int(active_by_target[target].source),
                target.code,
                target.subtype,
            ),
        )
        available = budget.generic_remaining
        to_subscribe = tuple(candidates[:available])
        deferred = tuple(candidates[available:])

        return SubscriptionPlan(
            desired=desired,
            actual_owned=actual,
            retained=retained,
            to_subscribe=to_subscribe,
            to_unsubscribe=to_unsubscribe,
            deferred=deferred,
            expired_intents=tuple(sorted(expired, key=_intent_sort_key)),
        )


def _intent_sort_key(
    intent: SubscriptionIntent,
) -> tuple[str, str, int, float]:
    return (
        intent.target.code,
        intent.target.subtype,
        -int(intent.source),
        intent.expires_at if intent.expires_at is not None else math.inf,
    )
