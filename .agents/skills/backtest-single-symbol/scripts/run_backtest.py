#!/usr/bin/env python3
"""Run the local single-symbol backtester and emit its structured summary."""

from __future__ import print_function

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run one strategy with the local stock-strategy engine."
    )
    parser.add_argument("--strategy", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data")
    source.add_argument("--sample", action="store_true")
    source.add_argument("--opend", action="store_true")
    parser.add_argument("--symbol")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--ktype", default="K_DAY")
    parser.add_argument("--autype", choices=("QFQ", "HFQ", "NONE"), default="QFQ")
    parser.add_argument("--opend-host", default="127.0.0.1")
    parser.add_argument("--opend-port", type=int, default=11111)
    parser.add_argument("--opend-cache")
    parser.add_argument("--project-root")
    parser.add_argument("--python", dest="python_executable")
    parser.add_argument("--output")
    parser.add_argument("--initial-cash", type=float, default=100000)
    parser.add_argument("--commission-bps", type=float, default=3)
    parser.add_argument("--min-commission", type=float, default=1)
    parser.add_argument("--slippage-bps", type=float, default=5)
    parser.add_argument("--warmup-bars", type=int, default=60)
    parser.add_argument("--sample-bars", type=int, default=880)
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--no-chart", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    project_root = (
        Path(args.project_root).expanduser().resolve()
        if args.project_root
        else discover_project_root()
    )
    backend_root = project_root / "backend"
    if not (backend_root / "stock_strategy" / "__main__.py").exists():
        return fail("stock-strategy project not found", project_root=str(project_root))

    strategy = resolve_input_path(args.strategy, project_root)
    if not strategy.is_file():
        return fail("strategy file not found", strategy=str(strategy))
    data = None
    if args.data:
        data = resolve_input_path(args.data, project_root)
        if not data.is_file():
            return fail("market data file not found", data=str(data))
    if args.opend and (not args.symbol or not args.start or not args.end):
        return fail("--opend requires --symbol, --start, and --end")

    python_executable = find_python(
        args.python_executable,
        project_root=project_root,
        require_futu=args.opend,
    )
    if not python_executable:
        return fail(
            "compatible Python not found",
            hint=(
                "install ./backend[opend] in the project virtualenv"
                if args.opend
                else "pass --python or set STOCK_STRATEGY_PYTHON"
            ),
        )

    output_base = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (project_root / "runs").resolve()
    )
    output_base.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_base.iterdir() if path.is_dir()}

    command = [
        python_executable,
        "-m",
        "stock_strategy",
        "--strategy",
        str(strategy),
        "--output",
        str(output_base),
        "--initial-cash",
        str(args.initial_cash),
        "--commission-bps",
        str(args.commission_bps),
        "--min-commission",
        str(args.min_commission),
        "--slippage-bps",
        str(args.slippage_bps),
        "--warmup-bars",
        str(args.warmup_bars),
    ]
    if data:
        command.extend(["--data", str(data)])
    elif args.opend:
        command.extend(
            [
                "--opend",
                "--symbol",
                args.symbol,
                "--start",
                args.start,
                "--end",
                args.end,
                "--ktype",
                args.ktype,
                "--autype",
                args.autype,
                "--opend-host",
                args.opend_host,
                "--opend-port",
                str(args.opend_port),
            ]
        )
        if args.opend_cache:
            cache_path = resolve_output_path(args.opend_cache, project_root)
            command.extend(["--opend-cache", str(cache_path)])
    else:
        command.extend(["--sample", "--sample-bars", str(args.sample_bars)])
    if args.symbol and not args.opend:
        command.extend(["--symbol", args.symbol])
    if args.allow_short:
        command.append("--allow-short")
    if args.no_chart:
        command.append("--no-chart")

    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(backend_root)
        if not existing_pythonpath
        else str(backend_root) + os.pathsep + existing_pythonpath
    )
    completed = subprocess.run(
        command,
        cwd=str(project_root),
        env=environment,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return fail(
            "backtest command failed",
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            command=command,
        )

    after = {path.resolve() for path in output_base.iterdir() if path.is_dir()}
    created = sorted(after - before, key=lambda path: path.stat().st_mtime)
    if not created:
        return fail("backtest completed but no new run directory was found")
    run_dir = created[-1]
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return fail("run directory has no summary.json", run_dir=str(run_dir))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = {
        "status": "ok",
        "run_dir": str(run_dir),
        "summary_path": str(summary_path),
        "trades_path": str(run_dir / "trades.csv"),
        "equity_curve_path": str(run_dir / "equity_curve.csv"),
        "report_path": str(run_dir / "report.svg") if not args.no_chart else None,
        "summary": summary,
    }
    if not args.json_only and completed.stdout:
        print(completed.stdout.rstrip())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def discover_project_root():
    """Find the nearest parent containing the local backtest package."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend" / "stock_strategy" / "__main__.py").is_file():
            return parent
    return Path.cwd().resolve()


def resolve_input_path(value, project_root):
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    current_candidate = (Path.cwd() / path).resolve()
    if current_candidate.exists():
        return current_candidate
    return (project_root / path).resolve()


def resolve_output_path(value, project_root):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def find_python(explicit=None, project_root=None, require_futu=False):
    candidates = []
    if explicit:
        candidates.append(explicit)
    environment_python = os.environ.get("STOCK_STRATEGY_PYTHON")
    if environment_python:
        candidates.append(environment_python)
    if project_root:
        candidates.append(str(Path(project_root) / ".venv/bin/python"))
    candidates.append(sys.executable)
    candidates.extend(
        candidate
        for name in ("python3.13", "python3.12", "python3.11")
        for candidate in [shutil.which(name)]
        if candidate
    )
    candidates.append(
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
        )
    )
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate).expanduser()
        if len(candidate_path.parts) == 1:
            located = shutil.which(str(candidate_path))
            if not located:
                continue
            candidate_path = Path(located)
        executable = str(candidate_path.absolute())
        if executable in seen:
            continue
        seen.add(executable)
        if not Path(executable).is_file():
            continue
        try:
            probe = "import sys; raise SystemExit(sys.version_info < (3, 11))"
            if require_futu:
                probe = "import futu; " + probe
            check = subprocess.run(
                [executable, "-c", probe],
                capture_output=True,
            )
        except OSError:
            continue
        if check.returncode == 0:
            return executable
    return None


def fail(message, **details):
    payload = {"status": "error", "error": message}
    payload.update(details)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
