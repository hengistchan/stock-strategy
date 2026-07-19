import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from stock_strategy.diagnostics import DiagnosticsService


def make_workspace(root: Path) -> None:
    for name in ("examples", "strategies", "data", "runs"):
        (root / name).mkdir()


class DiagnosticsServiceTest(unittest.TestCase):
    def test_ready_report_covers_runtime_workspace_and_opend_quote_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_workspace(root)
            report = DiagnosticsService(
                root,
                host="127.0.0.1",
                port=11111,
                connection_probe=lambda host, port: True,
                package_version_probe=lambda package: "10.6.6608",
                quote_probe=lambda: "OpenD stock directory readable · 1 probe result(s)",
            ).run()

        self.assertTrue(report.ready)
        self.assertEqual([check.id for check in report.checks], [
            "python", "futu_api", "workspace", "opend", "quote_directory"
        ])
        self.assertTrue(all(check.status == "pass" for check in report.checks))

    def test_quote_check_is_blocked_when_sdk_and_opend_are_unavailable(self):
        def missing_package(_package: str) -> str:
            raise PackageNotFoundError("futu-api")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_workspace(root)
            report = DiagnosticsService(
                root,
                connection_probe=lambda host, port: False,
                package_version_probe=missing_package,
                quote_probe=lambda: self.fail("blocked quote probe must not run"),
            ).run()

        statuses = {check.id: check.status for check in report.checks}
        self.assertFalse(report.ready)
        self.assertEqual(statuses["futu_api"], "fail")
        self.assertEqual(statuses["opend"], "fail")
        self.assertEqual(statuses["quote_directory"], "blocked")

    def test_missing_source_workspace_directory_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_workspace(root)
            (root / "examples").rmdir()
            report = DiagnosticsService(
                root,
                connection_probe=lambda host, port: True,
                package_version_probe=lambda package: "10.6.6608",
                quote_probe=lambda: "readable",
            ).run()

        workspace = next(check for check in report.checks if check.id == "workspace")
        self.assertEqual(workspace.status, "fail")
        self.assertIn("examples/ missing", workspace.detail)

    def test_generated_data_and_run_directories_may_be_created_on_first_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "examples").mkdir()
            (root / "strategies").mkdir()
            report = DiagnosticsService(
                root,
                connection_probe=lambda host, port: True,
                package_version_probe=lambda package: "10.6.6608",
                quote_probe=lambda: "readable",
            ).run()

        workspace = next(check for check in report.checks if check.id == "workspace")
        self.assertEqual(workspace.status, "pass")
        self.assertIn("will create data/, runs/", workspace.detail)
