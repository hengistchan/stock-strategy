from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
import uuid

from .paths import BACKEND_ROOT
from .run_manifest import atomic_write_json, atomic_write_text, sha256_bytes
from .strategy_process import (
    RESTRICTED_EXECUTION_PROFILE,
    StrategyProcessRunner,
    StrategyProcessOutputLimit,
    StrategyProcessTimeout,
)
from .strategy_repository import (
    StrategyRepository,
    analyze_strategy_compatibility,
    validate_strategy_source,
)


FIXTURE_BARS = 400
FIXTURE_SYMBOL = "US.AAPL"


class StrategyMigrationService:
    def __init__(self, project_root: Path, strategies: StrategyRepository) -> None:
        self.project_root = project_root.resolve()
        self.strategies = strategies
        self.root = (self.project_root / "runs" / "migrations").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.runner = StrategyProcessRunner(
            backend_root=BACKEND_ROOT,
            working_directory=self.project_root,
            timeout_seconds=30,
            execution_profile=RESTRICTED_EXECUTION_PROFILE,
        )

    def scan(self, content: str) -> dict[str, Any]:
        validate_strategy_source(content)
        compatibility = analyze_strategy_compatibility(content)
        return {
            "source_sha256": sha256_bytes(content.encode("utf-8")),
            "syntax_valid": True,
            "compatibility": compatibility,
            "fixture": {"status": "not_run"},
            "next_step": (
                "fix_static_findings"
                if not compatibility["supported"]
                else "run_deterministic_fixture"
            ),
        }

    async def validate_fixture(self, content: str) -> dict[str, Any]:
        report = self.scan(content)
        if not report["compatibility"]["supported"]:
            report["fixture"] = {
                "status": "blocked",
                "error": "Static compatibility findings must be resolved first.",
            }
            return report
        migration_id = (
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )
        migration_dir = self.root / migration_id
        strategy_path = migration_dir / "strategy.py"
        output_dir = migration_dir / "output"
        migration_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_text(strategy_path, content)
        command = [
            sys.executable,
            "-P",
            "-m",
            "stock_strategy",
            "--strategy",
            str(strategy_path),
            "--sample",
            "--sample-bars",
            str(FIXTURE_BARS),
            "--symbol",
            FIXTURE_SYMBOL,
            "--output",
            str(output_dir),
            "--no-chart",
        ]
        try:
            outcome = await self.runner.run(
                f"migration-{migration_id}",
                command,
                working_directory=migration_dir,
                allowed_write_roots=(output_dir,),
            )
            summary_paths = sorted(output_dir.glob("*/summary.json"))
            if outcome.returncode != 0 or not summary_paths:
                error = _last_message(outcome.stderr, outcome.stdout)
                report["fixture"] = {
                    "status": "failed",
                    "error": error,
                    "stdout": outcome.stdout,
                    "stderr": outcome.stderr,
                }
            else:
                summary = json.loads(
                    summary_paths[-1].read_text(encoding="utf-8")
                )
                report["fixture"] = {
                    "status": "passed",
                    "symbol": FIXTURE_SYMBOL,
                    "bars": FIXTURE_BARS,
                    "execution_profile": RESTRICTED_EXECUTION_PROFILE,
                    "metrics": summary.get("metrics", {}),
                    "execution_contract": summary.get("settings", {}).get(
                        "engine_contract", {}
                    ),
                }
                report["next_step"] = "save_and_run_opend_backtest"
        except (StrategyProcessTimeout, StrategyProcessOutputLimit) as error:
            report["fixture"] = {"status": "failed", "error": str(error)}
        atomic_write_json(migration_dir / "compatibility-report.json", report)
        return report

    def import_strategy(
        self, name: str, content: str, report: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        strategy = self.strategies.create(name, content=content)
        imported_report = report or self.scan(content)
        destination = self.root / f"import-{uuid.uuid4().hex}.json"
        atomic_write_json(
            destination,
            {
                **imported_report,
                "strategy_path": strategy["path"],
                "imported_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
            },
        )
        return {"strategy": strategy, "report": imported_report}


def _last_message(stderr: str, stdout: str) -> str:
    for content in (stderr, stdout):
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return "Deterministic fixture failed without an error message."
