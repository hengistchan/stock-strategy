# Architecture review completion — 2026-07-26

## Outcome

The three-stage architecture program is complete for the project's declared
scope: local, stock-only strategy research backed exclusively by Futu OpenD
market data. Existing strategy scripts, HTTP callers, legacy JSON metadata, and
historical evidence remain readable.

## Review mapping

| Review area | Completed implementation |
| --- | --- |
| Reproducibility | Every queued run freezes `strategy.py`, `request.json`, market data, hashes, runtime versions, and an engine-contract manifest. |
| Market-data cache | Cache identity includes schema and adapter versions, requested fields, timezone semantics, Futu SDK version, and a content SHA-256. |
| Evaluation correctness | Warmup and evaluation windows are separate; daily close returns drive risk metrics; short samples omit CAGR. |
| Execution realism | Pluggable US/HK fee attribution, spread/slippage models, conservative fills, and volume participation are available without changing legacy defaults. |
| Audit evidence | Orders, fills, trades, equity, daily returns, logs, HTML/SVG reports, and manifest hashes are required before success; verified ZIP export/import is supported. |
| Job reliability | SQLite WAL is authoritative, transitions are atomic, interrupted work is reconciled, process groups can be cancelled, and retries create immutable lineage. |
| Service architecture | HTTP DTOs map to application commands; domain routers, structured errors, typed OpenAPI clients, SSE events, and durable entity URLs are separated. |
| Research robustness | Train/validation/test, walk-forward folds, parameter-neighbour stability, constraints, Pareto marking, and stock-pool validation are supported. |
| Strategy lineage | Saves create immutable versions; runs and experiments retain revision relationships; historical versions can be inspected and restored. |
| Portfolio foundation | Same-currency stocks share a unified clock, cash pool, position book, fees, risk metrics, and explicit rebalancing rules. |
| Data transparency | Adjustment mode, source version, duplicate rows, suspected gaps, timezone, suspicious jumps, and alignment loss are reported. |
| Futu migration | Imported stock strategies pass static compatibility scanning and a deterministic restricted fixture before being saved. |
| Strategy SDK | Signals, sizing, risk, exits, and order execution compose through typed protocols and immutable decisions. |
| Security | Remote binding requires explicit opt-in and a strong token; trusted runs have process/resource/output limits; imported fixtures deny network, subprocesses, and out-of-scope writes. |
| Engineering gates | Python 3.11/3.12 CI, Ruff, mypy, branch coverage, Bandit, dependency audit, Broker property tests, frontend checks, E2E, wheel inspection, and generated-API parity are enforced. |

## Deliberate product boundaries

- The compatibility target is the stock portion of the supplied Futu
  quantitative manual. Futures, options, FX trading, account connectivity, and
  live order placement remain out of scope.
- Corporate-action handling is delegated to the requested OpenD adjustment
  mode (`QFQ`, `HFQ`, or unadjusted). The application records that contract and
  never claims that it independently reconstructed corporate actions.
- The current quality report uses an approximate weekday calendar. Holiday
  gaps are labelled as suspected rather than confirmed; no synthetic bar is
  inserted.
- Portfolio runs reject mixed-market currency conversion instead of applying a
  fabricated or spot FX rate.
- A retry creates a new queued job with `retry_of` lineage. It does not mutate a
  failed evidence record back into a transient `retrying` state.
- `restricted-import-v1` is defence in depth for deterministic migration
  fixtures, not a replacement for an operating-system sandbox. Formal OpenD
  runs still execute only user-trusted local strategies.

## Release gates

The repository is ready only when all of these commands pass from a clean
checkout:

```bash
make api-schema-check
make test
make quality
make acceptance
make package
cd frontend && npm run test:e2e
```

`make acceptance` also verifies that a deterministic stock backtest produces
the complete evidence bundle, while `make package` verifies that the wheel
contains the production workbench.
