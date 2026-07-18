"""Local Futu-style script backtester."""

from .runtime import BacktestConfig, BacktestResult, run_backtest

__all__ = ["BacktestConfig", "BacktestResult", "run_backtest"]
__version__ = "0.3.0"
