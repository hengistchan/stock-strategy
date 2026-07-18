# Single-symbol backtest contract

## Input checks

- OpenD history DataFrame CSV: require `code`, `time_key`, `open`, `close`, `high`, `low`; accept `volume` and ignore non-execution fields such as `name`, `turnover`, `pe_ratio`, `turnover_rate`, `change_rate`, and `last_close`.
- OpenD direct mode: require one symbol, explicit start/end dates, a reachable read-only quote context, and the optional `opend` dependency. Follow every pagination key, close the context on success or failure, and save a raw cache when reproducibility matters.
- Generic CSV: require `date`, `open`, `high`, `low`, `close`; require an explicit symbol when no `code` column exists.
- Keep exactly one symbol. Preserve full `time_key` so intraday bars on the same date are not deduplicated.
- Treat the supplied rows as the driving bar interval. For multi-period stock strategies, use the smallest requested `BarType`; the engine incrementally derives coarser bars without future data.
- Keep one US session scope (`RTH`, `ETH`, or `ALL`) for the run. Match it to the strategy's declared `THType`.
- Require at least 30 valid bars. Ensure prices are positive and `low <= open/close <= high`.

## Execution model

- Call `handle_data()` after the current bar closes.
- Expose `select=1` as the current partial target-period bar and `select=2` as the previous target-period bar.
- Fill a submitted market order no earlier than the next bar open.
- Evaluate limit and stop orders against the next bar's OHLC range.
- Apply commission and slippage to cash, equity, and trade P&L.
- Cancel pending orders and close an open position at the final close with slippage.
- Default to long-only. Enable shorts explicitly.

## Output contract

Each run directory contains:

- `summary.json`: settings, period, and metrics.
- `trades.csv`: closed trades, prices, fees, net P&L, holding bars, and exit reason.
- `equity_curve.csv`: strategy equity, benchmark equity, and drawdown by bar.
- `report.svg`: strategy/benchmark curve, drawdown, and per-trade P&L.

## Interpretation guardrails

- Compare return with the benchmark; positive absolute return can still be material underperformance.
- Read drawdown with return. A higher return does not compensate automatically for an unacceptable drawdown.
- Treat Sharpe cautiously for short intraday samples or sparse trading.
- Read win rate together with profit factor and trade count. A high win rate can hide large losses.
- Inspect total fees and exposure to identify churn or idle-capital effects.
- Treat fewer than roughly 20 closed trades as weak evidence unless the strategy is intentionally low-frequency and covers multiple regimes.
- If profit factor is infinite, confirm that the sample has no losing trade instead of treating infinity as stable.
- Never use deterministic sample data for a market conclusion.

## Failure handling

- Unsupported Futu API: report the exact API and consult `docs/FUTU_COMPATIBILITY.md`; do not fabricate a substitute value.
- No trades: inspect warmup, data range, indicator periods, and signal crossings.
- Multiple symbols: rerun with `--symbol`; never merge bars from different securities.
- Missing OpenD data: try the running local OpenD read-only history endpoint first; otherwise request an exported CSV or a DataFrame-to-records handoff. Do not silently replace it with web prices.
- Mismatched symbol or period: stop and correct the input before interpreting metrics.
