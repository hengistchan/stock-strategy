from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from stock_strategy.application_models import BacktestSpec
from stock_strategy.execution_service import ExecutionService
from stock_strategy.strategy_repository import StrategyRepository


class FakeJobStore:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.launched: list[str] = []

    def create_job(
        self,
        request,
        strategy_path,
        *,
        strategy_source=None,
        strategy_revision=None,
    ):
        self.created.append(
            {
                "request": request,
                "strategy_path": strategy_path,
                "strategy_source": strategy_source,
                "strategy_revision": strategy_revision,
            }
        )
        return {"id": "job-1", "status": "queued", "request": request}

    def launch(self, job_id: str) -> None:
        self.launched.append(job_id)


class ExecutionServiceTest(unittest.TestCase):
    def test_application_service_accepts_framework_independent_specs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "strategies" / "independent.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text(
                "STRATEGY_PARAMETERS = {\n"
                '    "period": {"type": "int", "default": 10, "min": 2}\n'
                "}\n"
                "class Strategy:\n"
                "    pass\n",
                encoding="utf-8",
            )
            jobs = FakeJobStore()
            service = ExecutionService(
                StrategyRepository(root),
                jobs,  # type: ignore[arg-type]
                object(),  # type: ignore[arg-type]
            )

            created = service.create_backtest(
                BacktestSpec(
                    strategy="strategies/independent.py",
                    symbol="US.AAPL",
                    start=date(2025, 1, 2),
                    end=date(2025, 2, 3),
                    parameters={"period": 20},
                )
            )

        request = jobs.created[0]["request"]
        self.assertEqual(created["id"], "job-1")
        self.assertEqual(request["start"], "2025-01-02")
        self.assertEqual(request["end"], "2025-02-03")
        self.assertEqual(request["parameters"], {"period": 20})
        self.assertEqual(jobs.launched, ["job-1"])


if __name__ == "__main__":
    unittest.main()
