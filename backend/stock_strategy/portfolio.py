from __future__ import annotations

import hashlib
import json
import math
import statistics
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .data import bars_from_opend_records
from .market_data_quality import build_market_data_quality_report
from .models import Bar
from .opend import OpenDHistory, fetch_history_kline
from .run_manifest import atomic_write_json


@dataclass(frozen=True, slots=True)
class PortfolioConfig:
    weights: Mapping[str, float]
    start: str
    end: str
    initial_cash: float = 100_000
    commission_bps: float = 3
    min_commission: float = 1
    slippage_bps: float = 5
    rebalance: str = "monthly"
    ktype: str = "K_DAY"
    autype: str = "QFQ"
    session: str = "ALL"

    def __post_init__(self) -> None:
        normalized = {
            symbol.upper(): float(weight) for symbol, weight in self.weights.items()
        }
        if len(normalized) < 2:
            raise ValueError("portfolio requires at least two symbols")
        if len({symbol.split(".", 1)[0] for symbol in normalized}) != 1:
            raise ValueError("portfolio symbols must share one market and currency")
        if any(
            not math.isfinite(weight) or weight <= 0 for weight in normalized.values()
        ):
            raise ValueError("portfolio weights must be positive finite values")
        total = sum(normalized.values())
        if total <= 0:
            raise ValueError("portfolio weights cannot sum to zero")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.rebalance not in {"buy_and_hold", "monthly", "quarterly"}:
            raise ValueError("unsupported portfolio rebalance frequency")
        if self.ktype != "K_DAY":
            raise ValueError("portfolio foundation currently requires K_DAY data")
        object.__setattr__(
            self,
            "weights",
            {symbol: weight / total for symbol, weight in normalized.items()},
        )


class PortfolioService:
    """OpenD-backed shared-cash portfolio backtest and evidence persistence."""

    def __init__(
        self,
        project_root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        history_loader=fetch_history_kline,
    ) -> None:
        self.project_root = project_root.resolve()
        self.root = (self.project_root / "runs" / "portfolios").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.host = host
        self.port = port
        self.history_loader = history_loader

    def run(self, config: PortfolioConfig) -> dict[str, Any]:
        histories: dict[str, list[Bar]] = {}
        data_hashes: dict[str, str] = {}
        for symbol in config.weights:
            history: OpenDHistory = self.history_loader(
                symbol,
                start=config.start,
                end=config.end,
                ktype=config.ktype,
                autype=config.autype.lower(),
                session=config.session,
                host=self.host,
                port=self.port,
            )
            market_data = bars_from_opend_records(
                history.records,
                symbol=symbol,
                fieldnames=history.fieldnames,
            )
            histories[symbol] = market_data.bars
            data_hashes[symbol] = _bars_hash(market_data.bars)
        result = run_portfolio(config, histories)
        run_id = (
            f"portfolio-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:6]}"
        )
        payload = {
            "id": run_id,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "opend",
            "request": {
                **asdict(config),
                "weights": dict(config.weights),
            },
            "market_data_sha256": data_hashes,
            **result,
        }
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=False)
        atomic_write_json(directory / "portfolio.json", payload)
        return payload


def run_portfolio(
    config: PortfolioConfig,
    histories: Mapping[str, Sequence[Bar]],
) -> dict[str, Any]:
    missing = sorted(set(config.weights) - set(histories))
    if missing:
        raise ValueError("missing portfolio histories: " + ", ".join(missing))
    by_symbol = {
        symbol: {bar.date: bar for bar in histories[symbol]}
        for symbol in config.weights
    }
    common_dates = sorted(
        set.intersection(*(set(series) for series in by_symbol.values()))
    )
    if len(common_dates) < 20:
        raise ValueError("portfolio requires at least 20 aligned trading bars")

    cash = float(config.initial_cash)
    positions = {symbol: 0 for symbol in config.weights}
    total_fees = 0.0
    gross_turnover = 0.0
    transactions: list[dict[str, Any]] = []
    curve: list[dict[str, float | str]] = []
    peak = config.initial_cash
    benchmark_origin = {
        symbol: by_symbol[symbol][common_dates[0]].close for symbol in config.weights
    }
    previous_period: tuple[int, int] | None = None

    for index, timestamp in enumerate(common_dates):
        bars = {symbol: by_symbol[symbol][timestamp] for symbol in config.weights}
        parsed = datetime.fromisoformat(timestamp)
        current_period = _rebalance_period(parsed, config.rebalance)
        should_rebalance = index == 0 or (
            config.rebalance != "buy_and_hold" and current_period != previous_period
        )
        if should_rebalance:
            cash, fees, turnover, executed = _rebalance(
                timestamp=timestamp,
                cash=cash,
                positions=positions,
                bars=bars,
                weights=config.weights,
                commission_bps=config.commission_bps,
                min_commission=config.min_commission,
                slippage_bps=config.slippage_bps,
            )
            total_fees += fees
            gross_turnover += turnover
            transactions.extend(executed)
        previous_period = current_period

        equity = cash + sum(
            positions[symbol] * bars[symbol].close for symbol in config.weights
        )
        peak = max(peak, equity)
        benchmark = config.initial_cash * sum(
            config.weights[symbol] * bars[symbol].close / benchmark_origin[symbol]
            for symbol in config.weights
        )
        curve.append(
            {
                "date": timestamp,
                "equity": equity,
                "benchmark": benchmark,
                "drawdown": equity / peak - 1 if peak else 0,
            }
        )

    final_prices = {
        symbol: by_symbol[symbol][common_dates[-1]].close for symbol in config.weights
    }
    metrics = _portfolio_metrics(
        curve,
        initial_cash=config.initial_cash,
        total_fees=total_fees,
        gross_turnover=gross_turnover,
    )
    return {
        "metrics": metrics,
        "period": {
            "start": common_dates[0],
            "end": common_dates[-1],
            "bars": len(common_dates),
        },
        "weights": dict(config.weights),
        "positions": [
            {
                "symbol": symbol,
                "quantity": positions[symbol],
                "mark_price": final_prices[symbol],
                "market_value": positions[symbol] * final_prices[symbol],
            }
            for symbol in config.weights
        ],
        "cash": cash,
        "transactions": transactions,
        "equity_curve": curve,
        "engine_contract": {
            "shared_cash": True,
            "unified_clock": "intersection-of-opend-bars",
            "integer_shares": True,
            "execution": "rebalance-at-period-first-open",
            "currency": next(iter(config.weights)).split(".", 1)[0],
            "fx_conversion": "rejected-unless-single-market-currency",
        },
        "data_quality": {
            "symbols": {
                symbol: build_market_data_quality_report(
                    list(histories[symbol]),
                    symbol=symbol,
                    bar_type=config.ktype,
                    autype=config.autype,
                    source="opend",
                )
                for symbol in config.weights
            },
            "aligned_common_bars": len(common_dates),
            "alignment": "intersection",
        },
    }


def _rebalance(
    *,
    timestamp: str,
    cash: float,
    positions: dict[str, int],
    bars: Mapping[str, Bar],
    weights: Mapping[str, float],
    commission_bps: float,
    min_commission: float,
    slippage_bps: float,
) -> tuple[float, float, float, list[dict[str, Any]]]:
    equity = cash + sum(positions[symbol] * bars[symbol].open for symbol in weights)
    target_quantities = {
        symbol: max(0, math.floor(equity * weights[symbol] / bars[symbol].open))
        for symbol in weights
    }
    fees = 0.0
    turnover = 0.0
    transactions: list[dict[str, Any]] = []

    for symbol in weights:
        quantity = positions[symbol] - target_quantities[symbol]
        if quantity <= 0:
            continue
        price = bars[symbol].open * (1 - slippage_bps / 10_000)
        fee = max(min_commission, price * quantity * commission_bps / 10_000)
        cash += price * quantity - fee
        positions[symbol] -= quantity
        fees += fee
        turnover += price * quantity
        transactions.append(
            _transaction(timestamp, symbol, "SELL", quantity, price, fee)
        )

    for symbol in weights:
        desired = target_quantities[symbol] - positions[symbol]
        if desired <= 0:
            continue
        price = bars[symbol].open * (1 + slippage_bps / 10_000)
        quantity = desired
        while quantity > 0:
            fee = max(min_commission, price * quantity * commission_bps / 10_000)
            if price * quantity + fee <= cash + 1e-9:
                break
            quantity -= 1
        if quantity <= 0:
            continue
        fee = max(min_commission, price * quantity * commission_bps / 10_000)
        cash -= price * quantity + fee
        positions[symbol] += quantity
        fees += fee
        turnover += price * quantity
        transactions.append(
            _transaction(timestamp, symbol, "BUY", quantity, price, fee)
        )
    return cash, fees, turnover, transactions


def _transaction(
    timestamp: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    fee: float,
) -> dict[str, Any]:
    return {
        "date": timestamp,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "fee": fee,
        "notional": price * quantity,
    }


def _portfolio_metrics(
    curve: Sequence[Mapping[str, Any]],
    *,
    initial_cash: float,
    total_fees: float,
    gross_turnover: float,
) -> dict[str, float]:
    equities = [float(point["equity"]) for point in curve]
    returns = [
        equities[index] / equities[index - 1] - 1
        for index in range(1, len(equities))
        if equities[index - 1]
    ]
    sharpe = (
        statistics.fmean(returns) / statistics.stdev(returns) * math.sqrt(252)
        if len(returns) > 1 and statistics.stdev(returns) > 0
        else 0.0
    )
    return {
        "total_return_pct": (equities[-1] / initial_cash - 1) * 100,
        "benchmark_return_pct": (float(curve[-1]["benchmark"]) / initial_cash - 1)
        * 100,
        "max_drawdown_pct": min(float(point["drawdown"]) for point in curve) * 100,
        "sharpe_ratio": sharpe,
        "annualized_volatility_pct": (
            statistics.stdev(returns) * math.sqrt(252) * 100
            if len(returns) > 1
            else 0.0
        ),
        "total_fees": total_fees,
        "turnover_pct": gross_turnover / initial_cash * 100,
    }


def _rebalance_period(value: datetime, frequency: str) -> tuple[int, int]:
    if frequency == "quarterly":
        return value.year, (value.month - 1) // 3
    return value.year, value.month


def _bars_hash(bars: Sequence[Bar]) -> str:
    payload = json.dumps(
        [
            [bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume]
            for bar in bars
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
