import tempfile
import unittest
from pathlib import Path

from stock_strategy.strategy_migration import StrategyMigrationService
from stock_strategy.strategy_repository import StrategyRepository

SUPPORTED_SOURCE = """
from stock_strategy.futu import *

class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()

    def handle_data(self):
        bar_close(self.symbol, BarType.K_DAY)
"""


class StrategyMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_scan_reports_unsupported_names_with_line_and_suggestion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            service = StrategyMigrationService(root, StrategyRepository(root))

            report = service.scan(
                SUPPORTED_SOURCE.replace(
                    "bar_close(self.symbol, BarType.K_DAY)",
                    "future_only_api(self.symbol)",
                )
            )

        self.assertFalse(report["compatibility"]["supported"])
        finding = report["compatibility"]["findings"][0]
        self.assertEqual(finding["name"], "future_only_api")
        self.assertIsInstance(finding["line"], int)
        self.assertTrue(finding["suggestion"])
        self.assertEqual(report["next_step"], "fix_static_findings")

    async def test_deterministic_fixture_passes_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository = StrategyRepository(root)
            service = StrategyMigrationService(root, repository)

            report = await service.validate_fixture(SUPPORTED_SOURCE)
            imported = service.import_strategy(
                "migrated_strategy", SUPPORTED_SOURCE, report
            )

        self.assertEqual(report["fixture"]["status"], "passed")
        self.assertEqual(report["fixture"]["bars"], 400)
        self.assertEqual(report["next_step"], "save_and_run_opend_backtest")
        self.assertEqual(
            imported["strategy"]["path"], "strategies/migrated_strategy.py"
        )


if __name__ == "__main__":
    unittest.main()
