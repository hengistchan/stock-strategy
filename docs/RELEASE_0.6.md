# Strategy Lab 0.6

Version 0.6 makes local setup failures visible and continuously verifies the browser workbench.

- `make doctor` and `stock-doctor` check Python, Futu API, workspace access, OpenD TCP, and stock-directory access.
- `/api/diagnostics` powers an actionable bilingual status panel next to the language switch.
- Playwright now verifies versioned backtest evidence, stable workspace routes, diagnostics, and navigation in CI.
- Release validation rejects mismatched backend, frontend, and Python package versions.

This release remains stock-only, local-first, and read-only with respect to Futu trading accounts.
