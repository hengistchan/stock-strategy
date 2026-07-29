# Stock and option monitoring

Strategy Lab includes a read-only monitoring workspace for US and Hong Kong
stocks and listed options. It uses Futu OpenD as the only live market-data
source. The monitoring subsystem never unlocks an account, places an order, or
falls back to simulated or third-party quotes.

## Runtime architecture

```text
OpenD
  -> normalized snapshots, option chains, bars, and market state
  -> exact-target subscription planner
  -> bounded monitoring supervisor and in-memory latest-value cache
  -> deterministic rule engine
  -> atomic SQLite rule state + immutable alert evidence
  -> REST read model + SSE invalidation events
  -> React monitor workspace
```

The supervisor starts and stops with the FastAPI lifespan. An empty workspace
does not open OpenD. Once an enabled watchlist item or rule exists, the
supervisor reconciles only the exact stock or option contract targets it owns.
It does not subscribe to an entire option chain.

The shared `runs/state.sqlite3` database uses WAL mode. Monitoring has an
independent component schema version so its migrations cannot advance or
rewrite the backtest/experiment schema version. Watchlist entries, rule
definitions, rule state, daily delivery counters, and alert evidence survive
process restarts.

The provided `compose.yaml` mounts the host `runs/` directory at `/app/runs`,
so the same SQLite state also survives container replacement and restart.

## Market-data semantics

- Option-chain discovery is static contract metadata. Dynamic price, bid/ask,
  volume, open interest, implied volatility, and Greeks come from batched
  snapshots.
- US/HK snapshot batching respects the stricter Hong Kong option limit.
- Futu implied-volatility values are already percentage points: `20` is
  displayed as `20%`, not `2,000%`.
- Option open interest is labelled `daily/as-of`; it is not presented as a
  tick-by-tick value.
- A generic `query_subscription` result is labelled as generic all-security
  subscription usage. It is never presented as an option-specific quota.
- Missing values remain unavailable (`—`) rather than becoming zero.
- Crossed bid/ask markets do not produce a synthetic midpoint or spread.
- MA and Wilder RSI consume only bars explicitly marked closed. The latest
  history bar is conservatively treated as open.

## Rule behavior

Stock rules cover price, daily and five-minute change, volume, midpoint,
spread, MA20, MA60, MA20/MA60 spread, and RSI14.

Option rules additionally cover volume/open-interest ratio, implied and
historical volatility, IV-HV premium, all five Greeks, days to expiry, strike
distance, expiry-weighted gamma/theta risk, and call/put volume and
open-interest imbalance.

Every rule has an explicit regular/extended/all-session scope, cooldown,
severity, and daily delivery limit. The first valid observation establishes a
baseline and cannot alert. Later alerts require a false-to-true edge. Duplicate
or out-of-order provider timestamps, sustained true conditions, stale data,
reconnection baselines, closed markets, and data outside the selected session
do not alert.

Rule state and an alert snapshot are written in one SQLite transaction. The
immutable alert ledger stores the value, threshold, full normalized snapshot,
OpenD provider time, local receipt time, source, and a deterministic dedupe
identity. SSE is only a prompt to refresh this durable read model.

## HTTP surface

All endpoints remain behind the existing local API-token middleware:

- `/api/monitoring/status`
- `/api/monitoring/diagnostics`
- `/api/monitoring/watchlist`
- `/api/monitoring/underlyings/{code}/snapshot`
- `/api/monitoring/underlyings/{code}/bars`
- `/api/monitoring/underlyings/{code}/option-expirations`
- `/api/monitoring/underlyings/{code}/option-chain`
- `/api/monitoring/contracts/{code}`
- `/api/monitoring/rules`
- `/api/monitoring/alerts`

Permission denial, generic subscription exhaustion, OpenD unavailability,
stale data, market closure, and missing fields are distinct states. No
production endpoint exposes order placement, trade execution, or account
unlocking.

## Verification

The deterministic release ladder is:

```bash
make api-schema-check
make test
make quality
make acceptance
make monitor-acceptance
make package
cd frontend && npm run test:e2e
cd frontend && npm run test:e2e:integrated
make opend-smoke
```

`monitor-acceptance` uses a temporary SQLite database and a deterministic fake
OpenD gateway but crosses the real service, repository, HTTP, and SSE
boundaries. The integrated browser test crosses React, generated API client,
FastAPI, the monitoring supervisor, SQLite, and SSE.

`opend-smoke` is separate because it depends on local permissions, market
hours, and OpenD. US and Hong Kong must be validated independently because
their regular sessions do not overlap:

```bash
make opend-smoke OPEND_SMOKE_MARKET=US
make opend-smoke OPEND_SMOKE_MARKET=HK
```

Each run writes a redacted JSON evidence file under `runs/acceptance/`.
`OPEND_SMOKE_MARKET=all` remains useful as a diagnostic summary, but is not a
single pass/fail release gate. A missing permission, closed market, or
unavailable OpenD is reported as `blocked`; a mapping, API, freshness, or
cleanup defect is `failed`. Static option-chain access alone cannot produce a
live-pass result.

The smoke test only releases subscriptions it created and never calls
`unsubscribe_all`.

## Deliberate boundaries

This release does not provide automatic trading, option historical backtests,
third-party alert delivery, or live account/position risk. Those require
separate trading, historical-data, notification, and account-security
contracts rather than extensions to the read-only monitor.
