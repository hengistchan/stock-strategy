#!/usr/bin/env python3
"""Run the repeatable MVP acceptance gate with an OpenD-shaped data fixture."""

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta
import xml.etree.ElementTree as ElementTree


MINIMUM_PYTHON = (3, 11)
ACCEPTANCE_SYMBOL = "US.ACCEPT"
BAR_COUNT = 300


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run unit tests and a full OpenD-format backtest acceptance check."
    )
    parser.add_argument("--python", dest="python_executable")
    parser.add_argument("--output", default="runs/acceptance")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    python_executable = find_python(args.python_executable, project_root=project_root)
    if not python_executable:
        return fail(
            "Python 3.11+ not found",
            hint="install ./backend[opend,web,test] in Python 3.11+ or pass --python",
        )

    tests = run_command(
        [
            python_executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "backend/tests",
            "-v",
        ],
        project_root,
        pythonpath=backend_root,
    )
    if tests.returncode != 0:
        return fail(
            "unit-test gate failed",
            stdout=tests.stdout.strip(),
            stderr=tests.stderr.strip(),
        )
    test_count = parse_test_count(tests.stdout + "\n" + tests.stderr)

    output_base = (project_root / args.output).resolve()
    output_base.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_base.iterdir() if path.is_dir()}

    with tempfile.TemporaryDirectory(prefix="stock-strategy-acceptance-") as directory:
        data_path = Path(directory) / "opend-history.csv"
        write_opend_fixture(data_path)
        backtest = run_command(
            [
                python_executable,
                "-m",
                "stock_strategy",
                "--strategy",
                "examples/ma_cross.py",
                "--data",
                str(data_path),
                "--output",
                str(output_base),
            ],
            project_root,
            pythonpath=backend_root,
        )
    if backtest.returncode != 0:
        return fail(
            "OpenD end-to-end gate failed",
            stdout=backtest.stdout.strip(),
            stderr=backtest.stderr.strip(),
        )

    after = {path.resolve() for path in output_base.iterdir() if path.is_dir()}
    created = sorted(after - before, key=lambda path: path.stat().st_mtime)
    if not created:
        return fail("backtest passed but no new run directory was created")
    run_dir = created[-1]

    try:
        evidence = verify_run(run_dir)
    except (AssertionError, KeyError, OSError, ValueError) as error:
        return fail("artifact verification failed", error=str(error), run_dir=str(run_dir))

    payload = {
        "status": "passed",
        "python": python_executable,
        "unit_tests": test_count,
        "opend_e2e": evidence,
        "run_dir": str(run_dir),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def write_opend_fixture(path):
    fieldnames = [
        "code",
        "name",
        "time_key",
        "open",
        "close",
        "high",
        "low",
        "volume",
        "turnover",
    ]
    cursor = date(2024, 1, 2)
    previous_close = 100.0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(BAR_COUNT):
            while cursor.weekday() >= 5:
                cursor += timedelta(days=1)
            if index < 80:
                drift = 0.004
            elif index < 160:
                drift = -0.0045
            elif index < 240:
                drift = 0.005
            else:
                drift = -0.0035
            open_price = previous_close * (1 + 0.0015 * math.sin(index / 5))
            close = open_price * (1 + drift + 0.001 * math.cos(index / 4))
            high = max(open_price, close) * 1.006
            low = min(open_price, close) * 0.994
            volume = 1_000_000 + index * 1_000
            writer.writerow(
                {
                    "code": ACCEPTANCE_SYMBOL,
                    "name": "Acceptance Fixture",
                    "time_key": datetime.combine(cursor, time(16, 0)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "open": round(open_price, 4),
                    "close": round(close, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "volume": volume,
                    "turnover": round(volume * close, 2),
                }
            )
            previous_close = close
            cursor += timedelta(days=1)


def verify_run(run_dir):
    summary_path = run_dir / "summary.json"
    trades_path = run_dir / "trades.csv"
    equity_path = run_dir / "equity_curve.csv"
    report_path = run_dir / "report.svg"
    for path in (summary_path, trades_path, equity_path, report_path):
        assert path.is_file(), "missing artifact: {0}".format(path.name)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["symbol"] == ACCEPTANCE_SYMBOL, "OpenD symbol inference mismatch"
    assert summary["period"]["bars"] == BAR_COUNT, "OpenD bar count mismatch"
    assert summary["settings"]["data_source_format"] == "opend", "format not detected"
    assert summary["metrics"]["total_trades"] > 0, "strategy produced no trades"

    with trades_path.open("r", encoding="utf-8", newline="") as handle:
        trades = list(csv.DictReader(handle))
    assert len(trades) == summary["metrics"]["total_trades"], "trade count mismatch"

    with equity_path.open("r", encoding="utf-8", newline="") as handle:
        equity = list(csv.DictReader(handle))
    assert len(equity) == BAR_COUNT, "equity curve length mismatch"
    final_equity = float(equity[-1]["equity"])
    expected_equity = float(summary["metrics"]["final_equity"])
    assert math.isclose(final_equity, expected_equity, rel_tol=1e-12), (
        "final equity mismatch"
    )
    ElementTree.parse(report_path)

    return {
        "symbol": summary["symbol"],
        "bars": summary["period"]["bars"],
        "data_source_format": summary["settings"]["data_source_format"],
        "total_trades": summary["metrics"]["total_trades"],
        "final_equity": summary["metrics"]["final_equity"],
        "artifacts": [path.name for path in (summary_path, trades_path, equity_path, report_path)],
    }


def find_python(explicit=None, project_root=None):
    candidates = []
    if explicit:
        candidates.append(explicit)
    environment_python = os.environ.get("STOCK_STRATEGY_PYTHON")
    if environment_python:
        candidates.append(environment_python)
    if project_root:
        candidates.append(str(Path(project_root) / ".venv/bin/python"))
    candidates.append(sys.executable)
    for name in ("python3.13", "python3.12", "python3.11"):
        candidate = shutil.which(name)
        if candidate:
            candidates.append(candidate)
    candidates.append(
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
        )
    )

    seen = set()
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if len(path.parts) == 1:
            located = shutil.which(str(path))
            if not located:
                continue
            path = Path(located)
        path = path.absolute()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            probe = subprocess.run(
                [
                    str(path),
                    "-c",
                    "import fastapi, httpx2, sys; print('%d.%d' % sys.version_info[:2])",
                ],
                text=True,
                capture_output=True,
            )
            version = tuple(int(part) for part in probe.stdout.strip().split("."))
        except (OSError, ValueError):
            continue
        if probe.returncode == 0 and version >= MINIMUM_PYTHON:
            return str(path)
    return None


def run_command(command, cwd, *, pythonpath):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = (
        str(pythonpath) + os.pathsep + environment.get("PYTHONPATH", "")
    )
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=environment,
        text=True,
        capture_output=True,
    )


def parse_test_count(output):
    match = re.search(r"Ran (\d+) tests?", output)
    return int(match.group(1)) if match else None


def fail(message, **details):
    payload = {"status": "failed", "message": message, **details}
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
