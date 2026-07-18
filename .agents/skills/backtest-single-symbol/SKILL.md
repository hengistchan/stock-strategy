---
name: backtest-single-symbol
description: Run and interpret a reproducible single-symbol quantitative backtest with the local stock-strategy engine and Futu/OpenD OHLCV data. Use when the user asks to backtest one ticker or security, evaluate a Futu-style StrategyBase script, compare a strategy with buy-and-hold, inspect trades, drawdown, costs, or exposure, or iterate one symbol's strategy parameters. Do not use for portfolio backtests, multi-symbol allocation, or live order execution.
---

# Backtest One Symbol

Run one strategy against one symbol and return an evidence-backed research result. Never treat synthetic data as market evidence or send live orders.

## Establish the inputs

Resolve these inputs from the request and workspace before asking the user:

- Symbol in Futu form, such as `US.AAPL` or `HK.00700`.
- Strategy script path, or explicit rules that can be implemented as a `StrategyBase` script.
- OpenD CSV path, or a running OpenD host/port plus symbol and date range. Accept generic OHLCV CSV only when `--symbol` is explicit.
- Optional capital, commission, minimum commission, slippage, warmup, short-selling, and output directory settings.

If the strategy rules or real market data are missing and cannot be found locally, request only the missing input. Use `--sample` solely to verify plumbing; never use its metrics as the answer to a security research request.

## Inspect before running

1. Locate the project root. The Python package lives under `backend/`; for the bundled script, the workspace root is derived from this Skill's path. Override it with `--project-root` only when needed.
2. Confirm the strategy uses APIs supported by `docs/FUTU_COMPATIBILITY.md`.
3. Confirm OpenD data contains `code`, `time_key`, `open`, `close`, `high`, `low`, and optionally `volume`. Preserve OpenD timestamps without timezone conversion.
4. Reject mixed-symbol input unless the requested `--symbol` selects exactly one symbol.
5. Keep next-bar execution, fees, and slippage enabled. Do not silently set costs to zero.

Read [references/report-contract.md](references/report-contract.md) before diagnosing input failures or interpreting results.

## Run the backtest

Use the deterministic wrapper so paths, Python version, output discovery, and summary parsing stay consistent:

```bash
python3 .agents/skills/backtest-single-symbol/scripts/run_backtest.py \
  --strategy strategies/my_strategy.py \
  --data data/US.AAPL-opend.csv \
  --symbol US.AAPL \
  --json-only
```

When OpenD is running and the project virtualenv has the `opend` extra, fetch every history page directly and retain a raw cache:

```bash
python3 .agents/skills/backtest-single-symbol/scripts/run_backtest.py \
  --strategy examples/ma_cross.py \
  --opend \
  --symbol US.AAPL \
  --start 2024-01-01 \
  --end 2025-12-31 \
  --ktype K_DAY \
  --autype QFQ \
  --opend-cache data/opend/US.AAPL-K_DAY-2024-2025.csv \
  --json-only
```

Add execution assumptions only when specified or justified:

```bash
  --initial-cash 100000 \
  --commission-bps 3 \
  --min-commission 1 \
  --slippage-bps 5 \
  --warmup-bars 60
```

When `python3` is older than 3.11, the wrapper searches the project `.venv` and other compatible interpreters. Install backend dependencies with `.venv/bin/python -m pip install -e './backend[opend,web,test]'`. OpenD mode selects an interpreter that can import the Futu SDK. Set `STOCK_STRATEGY_PYTHON` or pass `--python` if discovery fails.

## Verify the run

Treat the run as complete only after checking all of the following:

- The wrapper returns `status: ok` and an absolute run directory.
- `summary.json` reports the requested symbol, expected date range, bar count, and `data_source_format`.
- `trades.csv` and `equity_curve.csv` exist; `report.svg` exists unless `--no-chart` was requested.
- The ending equity in the curve matches `final_equity` in the summary within rounding tolerance.
- A zero-trade run is diagnosed, not presented as a successful strategy evaluation. Check warmup, indicator availability, signal conditions, and date coverage.

## Interpret and report

Lead with the result, then give the evidence:

- Total and annualized return versus buy-and-hold.
- Maximum drawdown and Sharpe ratio.
- Trade count, win rate, profit factor, exposure, and total fees.
- The main driver of outperformance or underperformance visible in trades and the equity curve.
- Data, execution, and sample-size limitations.

Do not issue buy/sell advice. Distinguish a mechanically correct backtest from a robust strategy.

## Iterate safely

Change one hypothesis or parameter group at a time and retain each run directory. Compare runs on return, drawdown, Sharpe, turnover, and fees. Flag repeated tuning on the same period as in-sample optimization and request an out-of-sample period before claiming improvement.
