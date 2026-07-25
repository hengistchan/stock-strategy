"""Composable building blocks for Futu-style stock strategies."""

from .components import (
    AllowAllRiskPolicy,
    DailyRiskPolicy,
    FixedRiskSizer,
    FractionalBuyingPowerSizer,
    StructuralExitPolicy,
)
from .models import (
    AccountState,
    ExecutionReceipt,
    ExitDecision,
    OrderProposal,
    PositionState,
    RiskDecision,
    Signal,
    SignalContext,
)
from .pipeline import PipelineDecision, StrategyPipeline
from .protocols import (
    ExitPolicy,
    OrderExecutor,
    PositionSizer,
    RiskPolicy,
    SignalModel,
)

__all__ = [
    "AccountState",
    "AllowAllRiskPolicy",
    "DailyRiskPolicy",
    "ExecutionReceipt",
    "ExitDecision",
    "ExitPolicy",
    "FixedRiskSizer",
    "FractionalBuyingPowerSizer",
    "OrderExecutor",
    "OrderProposal",
    "PipelineDecision",
    "PositionSizer",
    "PositionState",
    "RiskDecision",
    "RiskPolicy",
    "Signal",
    "SignalContext",
    "SignalModel",
    "StrategyPipeline",
    "StructuralExitPolicy",
]
