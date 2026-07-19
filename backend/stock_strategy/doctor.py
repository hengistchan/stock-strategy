from __future__ import annotations

import argparse
import os

from .diagnostics import DiagnosticsService
from .paths import PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether Strategy Lab is ready to run OpenD stock backtests."
    )
    parser.add_argument("--opend-host", default=os.environ.get("OPEND_HOST", "127.0.0.1"))
    parser.add_argument(
        "--opend-port", type=int, default=int(os.environ.get("OPEND_PORT", "11111"))
    )
    args = parser.parse_args(argv)

    report = DiagnosticsService(
        PROJECT_ROOT,
        host=args.opend_host,
        port=args.opend_port,
    ).run()
    print("Strategy Lab diagnostics")
    print(f"Project: {PROJECT_ROOT}")
    for check in report.checks:
        marker = {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCKED"}[check.status]
        print(f"[{marker:7}] {check.id}: {check.detail}")
        if check.hint and check.status != "pass":
            print(f"          Hint: {check.hint}")
    print("\nREADY" if report.ready else "\nNOT READY")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
