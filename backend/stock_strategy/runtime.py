from __future__ import annotations

import inspect
import math
import statistics
import types
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import futu
from .broker import Broker
from .context import ExecutionContext, activate_context
from .models import BacktestResult, Bar, BarType, Contract, EquityPoint, Metrics, THType
from .strategy_parameters import load_parameter_definitions, resolve_parameter_values


class StrategyLoadError(RuntimeError):
    pass


class StrategyExecutionError(RuntimeError):
    pass


ENGINE_CONTRACT_VERSION = 3


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    strategy_path: str | Path
    symbol: str = "US.AAPL"
    initial_cash: float = 100_000.0
    commission_bps: float = 3.0
    min_commission: float = 1.0
    slippage_bps: float = 5.0
    warmup_bars: int = 0
    allow_short: bool = False
    bar_type: BarType | str = BarType.K_DAY
    session_type: THType | str = THType.ALL
    autype: str = "QFQ"
    liquidate_on_end: bool = False
    strategy_parameters: dict[str, Any] = field(default_factory=dict)
    market_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "bar_type", BarType(self.bar_type))
        except (TypeError, ValueError) as error:
            raise ValueError(f"unsupported bar_type: {self.bar_type}") from error
        try:
            object.__setattr__(self, "session_type", THType(self.session_type))
        except (TypeError, ValueError) as error:
            raise ValueError(f"unsupported session_type: {self.session_type}") from error
        normalized_autype = str(self.autype).upper()
        if normalized_autype not in {"QFQ", "HFQ", "NONE"}:
            raise ValueError(f"unsupported autype: {self.autype}")
        object.__setattr__(self, "autype", normalized_autype)
        object.__setattr__(self, "strategy_parameters", dict(self.strategy_parameters))
        object.__setattr__(self, "market_metadata", dict(self.market_metadata))


def run_backtest(config: BacktestConfig, bars: list[Bar]) -> BacktestResult:
    if len(bars) < 2:
        raise ValueError("at least two bars are required")
    if config.warmup_bars < 0:
        raise ValueError("warmup_bars cannot be negative")
    if config.warmup_bars >= len(bars) - 1:
        raise ValueError("warmup_bars must leave at least two executable bars")

    parameter_definitions = load_parameter_definitions(config.strategy_path)
    strategy_parameters = resolve_parameter_values(
        parameter_definitions, config.strategy_parameters
    )
    symbol = Contract(config.symbol)
    broker = Broker(
        initial_cash=config.initial_cash,
        commission_bps=config.commission_bps,
        min_commission=config.min_commission,
        slippage_bps=config.slippage_bps,
        allow_short=config.allow_short,
        bar_type=config.bar_type,
    )
    context = ExecutionContext(
        bars=bars,
        symbol=symbol,
        broker=broker,
        bar_type=config.bar_type,
        session_type=config.session_type,
        autype=config.autype,
        strategy_parameters=strategy_parameters,
        market_metadata=config.market_metadata,
    )
    equity_curve: list[EquityPoint] = []
    exposed_bars = 0
    first_close = bars[0].close
    peak_equity = config.initial_cash

    with activate_context(context):
        strategy_class = load_strategy_class(config.strategy_path)
        strategy = strategy_class()
        try:
            strategy.initialize()
        except Exception as error:
            raise StrategyExecutionError(f"strategy initialize() failed: {error}") from error

        for index, bar in enumerate(bars):
            context.current_index = index
            broker.process_bar(bar, index)
            if index >= config.warmup_bars and not context.quit_requested:
                try:
                    strategy.handle_data()
                except Exception as error:
                    raise StrategyExecutionError(
                        f"handle_data() failed on {bar.date} (bar {index}): {error}"
                    ) from error

            equity = broker.equity(bar.close)
            benchmark = config.initial_cash * bar.close / first_close
            peak_equity = max(peak_equity, equity)
            drawdown = equity / peak_equity - 1 if peak_equity else 0.0
            equity_curve.append(EquityPoint(bar.date, equity, benchmark, drawdown))
            if broker.position.quantity != 0:
                exposed_bars += 1

        context.current_index = len(bars) - 1
        if config.liquidate_on_end:
            broker.liquidate(symbol, bars[-1], len(bars) - 1)

    final_equity = broker.equity(bars[-1].close)
    equity_curve[-1].equity = final_equity
    equity_curve[-1].drawdown = final_equity / peak_equity - 1 if peak_equity else 0.0
    metrics = calculate_metrics(
        equity_curve=equity_curve,
        trades=broker.trades,
        initial_cash=config.initial_cash,
        exposed_bars=exposed_bars,
        total_fees=broker.total_fees,
        bar_type=config.bar_type,
    )
    path = Path(config.strategy_path)
    ending_position = _ending_position(broker, bars[-1].close)
    return BacktestResult(
        strategy_name=path.stem,
        symbol=str(symbol),
        start_date=bars[0].date,
        end_date=bars[-1].date,
        bar_count=len(bars),
        metrics=metrics,
        settings={
            **asdict(config),
            "strategy_parameters": strategy_parameters,
            "strategy_parameter_definitions": parameter_definitions,
            "strategy_path": str(path),
            "ending_position": ending_position,
            "engine_contract": {
                "version": ENGINE_CONTRACT_VERSION,
                "strict_single_period": False,
                "driver_bar_type": config.bar_type.value,
                "coarser_periods": "incremental-no-lookahead",
                "day_order_scope": "trading-day",
                "end_position_policy": (
                    "liquidate" if config.liquidate_on_end else "mark-to-market"
                ),
            },
        },
        trades=broker.trades,
        equity_curve=equity_curve,
        logs=broker.logs,
    )


def load_strategy_class(path: str | Path) -> type[futu.StrategyBase]:
    strategy_path = Path(path)
    if not strategy_path.exists():
        raise StrategyLoadError(f"strategy file not found: {strategy_path}")
    if strategy_path.suffix != ".py":
        raise StrategyLoadError("strategy file must be a .py file")

    module_name = f"user_strategy_{strategy_path.stem}"
    module = types.ModuleType(module_name)
    module.__file__ = str(strategy_path)
    for name in futu.__all__:
        module.__dict__[name] = getattr(futu, name)
    try:
        code = compile(strategy_path.read_text(encoding="utf-8"), str(strategy_path), "exec")
        exec(code, module.__dict__)
    except Exception as error:
        raise StrategyLoadError(f"could not load strategy {strategy_path}: {error}") from error

    preferred = module.__dict__.get("Strategy")
    if inspect.isclass(preferred) and issubclass(preferred, futu.StrategyBase):
        return preferred
    candidates = [
        value
        for value in module.__dict__.values()
        if inspect.isclass(value)
        and value is not futu.StrategyBase
        and issubclass(value, futu.StrategyBase)
        and value.__module__ == module_name
    ]
    if len(candidates) != 1:
        raise StrategyLoadError(
            "strategy file must define exactly one StrategyBase subclass, preferably named Strategy"
        )
    return candidates[0]


def calculate_metrics(
    *,
    equity_curve: list[EquityPoint],
    trades: list[Any],
    initial_cash: float,
    exposed_bars: int,
    total_fees: float,
    bar_type: BarType,
) -> Metrics:
    final_equity = equity_curve[-1].equity
    total_return = final_equity / initial_cash - 1
    benchmark_return = equity_curve[-1].benchmark / initial_cash - 1
    start = datetime.fromisoformat(equity_curve[0].date.replace(" ", "T"))
    end = datetime.fromisoformat(equity_curve[-1].date.replace(" ", "T"))
    elapsed_days = (end - start).total_seconds() / 86_400
    years = max(elapsed_days / 365.25, 1 / 365.25)
    annualized = (final_equity / initial_cash) ** (1 / years) - 1 if final_equity > 0 else -1.0

    returns: list[float] = []
    previous = initial_cash
    for point in equity_curve:
        returns.append(point.equity / previous - 1 if previous else 0.0)
        previous = point.equity
    return_std = statistics.stdev(returns) if len(returns) > 1 else 0.0
    sharpe = (
        statistics.fmean(returns)
        / return_std
        * math.sqrt(
            _observed_periods_per_year(
                bar_type,
                [point.date for point in equity_curve],
            )
        )
        if return_std
        else 0.0
    )

    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [-trade.net_pnl for trade in trades if trade.net_pnl < 0]
    if losses:
        profit_factor: float | None = sum(wins) / sum(losses)
    elif wins:
        profit_factor = None
    else:
        profit_factor = 0.0

    return Metrics(
        initial_equity=initial_cash,
        final_equity=final_equity,
        total_return_pct=total_return * 100,
        benchmark_return_pct=benchmark_return * 100,
        annualized_return_pct=annualized * 100,
        max_drawdown_pct=min(point.drawdown for point in equity_curve) * 100,
        sharpe_ratio=sharpe,
        win_rate_pct=(len(wins) / len(trades) * 100) if trades else 0.0,
        profit_factor=profit_factor,
        total_trades=len(trades),
        exposure_pct=exposed_bars / len(equity_curve) * 100,
        total_fees=total_fees,
    )


def _ending_position(broker: Broker, mark_price: float) -> dict[str, float | str]:
    position = broker.position
    quantity = position.quantity
    if quantity > 0:
        unrealized_pnl = (mark_price - position.average_price) * quantity
    elif quantity < 0:
        unrealized_pnl = (position.average_price - mark_price) * abs(quantity)
    else:
        unrealized_pnl = 0.0
    return {
        "quantity": quantity,
        "side": position.side.value,
        "average_price": position.average_price,
        "mark_price": mark_price,
        "unrealized_pnl": unrealized_pnl,
    }


def _observed_periods_per_year(bar_type: BarType, dates: list[str]) -> float:
    if bar_type == BarType.K_WEEK:
        return 52.0
    if bar_type == BarType.K_DAY:
        return 252.0
    trading_dates = {value.strip()[:10] for value in dates if value.strip()}
    if not trading_dates:
        return 252.0
    return max(1.0, len(dates) / len(trading_dates)) * 252.0
