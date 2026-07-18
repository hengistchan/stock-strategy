from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from .broker import Broker
from .models import Bar, BarType, Contract, THType


@dataclass(slots=True)
class ExecutionContext:
    bars: list[Bar]
    symbol: Contract
    broker: Broker
    current_index: int = 0
    strategy_type: str = "SECURITY"
    bar_type: BarType = BarType.K_DAY
    session_type: THType = THType.ALL
    autype: str = "QFQ"
    strategy_parameters: dict[str, Any] = field(default_factory=dict)
    series_prefix_sums: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.bar_type = BarType(self.bar_type)
        self.session_type = THType(self.session_type)
        self.autype = str(self.autype).upper()

    @property
    def current_bar(self) -> Bar:
        return self.bars[self.current_index]


_ACTIVE_CONTEXT: ContextVar[ExecutionContext | None] = ContextVar(
    "stock_strategy_active_context", default=None
)


def get_context() -> ExecutionContext:
    context = _ACTIVE_CONTEXT.get()
    if context is None:
        raise RuntimeError("Futu-compatible API called outside an active backtest")
    return context


@contextmanager
def activate_context(context: ExecutionContext) -> Iterator[ExecutionContext]:
    token = _ACTIVE_CONTEXT.set(context)
    try:
        yield context
    finally:
        _ACTIVE_CONTEXT.reset(token)
