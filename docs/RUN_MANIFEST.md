# Run manifest

Every Web backtest created after v0.6.0 owns an immutable input evidence set:

```text
runs/web/<job-id>/
├── job.json
├── manifest.json
├── request.json
├── strategy.py
├── market-data.csv
└── output/<run>/
    ├── summary.json
    ├── orders.csv
    ├── fills.csv
    ├── trades.csv
    ├── equity_curve.csv
    ├── daily_returns.csv
    ├── logs.jsonl
    ├── report.html
    └── report.svg
```

`strategy.py` is written before the job enters the queue. The subprocess always executes this file, so saving the workspace strategy after submission cannot change the run.

`market-data.csv` is copied from the versioned OpenD cache after the data request completes. Its SHA-256 must equal the cache metadata hash; otherwise the job fails rather than publishing an unreproducible result.

`manifest.json` schema version 1 records:

- application, Python, Futu SDK, engine-contract, cache-schema, and data-adapter versions;
- the `trusted-local-v2` execution profile and resource-bound strategy subprocess;
- the original strategy path, immutable revision, snapshot path, and SHA-256;
- the canonical request SHA-256;
- the market-data snapshot path, SHA-256, byte size, and row count;
- queued, running, and terminal timestamps and status.
- relative path, SHA-256, and byte size for every result artifact.

Existing jobs without a manifest remain readable through the legacy path contract. New jobs never fall back from a missing snapshot to mutable workspace source.
