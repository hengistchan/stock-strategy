from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping


def build_backtest_command(
    job: Mapping[str, Any],
    *,
    strategy_path: Path,
    cache_path: Path,
    output_path: Path,
    opend_host: str,
    opend_port: int,
) -> list[str]:
    request = job["request"]
    command = [
        sys.executable,
        "-P",
        "-m",
        "stock_strategy",
        "--strategy",
        str(strategy_path),
        "--opend",
        "--symbol",
        str(request["symbol"]),
        "--start",
        str(request["start"]),
        "--end",
        str(request["end"]),
        "--ktype",
        str(request["ktype"]),
        "--autype",
        str(request["autype"]),
        "--session",
        str(request.get("session") or "ALL"),
        "--initial-cash",
        str(request["initial_cash"]),
        "--commission-bps",
        str(request["commission_bps"]),
        "--min-commission",
        str(request["min_commission"]),
        "--slippage-bps",
        str(request["slippage_bps"]),
        "--fee-model",
        str(request.get("fee_model", "simple")),
        "--slippage-model",
        str(request.get("slippage_model", "bps")),
        "--execution-model",
        str(request.get("execution_model", "deterministic")),
        "--max-volume-participation",
        str(request.get("max_volume_participation", 0.1)),
        "--spread-bps",
        str(request.get("spread_bps", 0)),
        "--impact-bps",
        str(request.get("impact_bps", 0)),
        "--fixed-tick",
        str(request.get("fixed_tick", 0)),
        "--warmup-bars",
        str(request["warmup_bars"]),
        "--opend-cache",
        str(cache_path),
        "--opend-host",
        opend_host,
        "--opend-port",
        str(opend_port),
        "--output",
        str(output_path),
    ]
    for name, value in sorted((request.get("parameters") or {}).items()):
        command.extend(
            ["--parameter", f"{name}={json.dumps(value, ensure_ascii=False)}"]
        )
    if request.get("refresh_cache", False):
        command.append("--refresh-opend-cache")
    if request["allow_short"]:
        command.append("--allow-short")
    if request.get("liquidate_on_end", False):
        command.append("--liquidate-on-end")
    return command
