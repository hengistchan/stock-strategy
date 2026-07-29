from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


class MonitoringAcceptanceScriptTest(unittest.TestCase):
    temporary_directory: tempfile.TemporaryDirectory[str]
    payload: dict[str, Any]
    evidence: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        project_root = Path(__file__).resolve().parents[2]
        output = Path(cls.temporary_directory.name) / "evidence"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(project_root / "backend")
        result = subprocess.run(
            [
                sys.executable,
                "backend/scripts/monitoring_acceptance.py",
                "--output",
                str(output),
            ],
            cwd=project_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                "monitoring acceptance failed\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        cls.payload = json.loads(result.stdout)
        evidence_path = Path(cls.payload["evidence_path"])
        cls.evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_writes_complete_http_journey_evidence(self) -> None:
        self.assertEqual(self.payload["status"], "passed")
        journey = self.evidence["journey"]
        self.assertEqual(journey["initial_watchlist_count"], 0)
        self.assertEqual(journey["watchlist_codes"], ["HK.00700", "US.AAPL"])
        self.assertEqual(
            journey["rule_metrics"],
            ["last_price", "option_implied_volatility"],
        )
        self.assertEqual(journey["underlying_scoped_rule_count"], 2)
        self.assertEqual(journey["underlying_scoped_alert_count"], 2)
        self.assertEqual(journey["baseline_alert_count"], 0)
        self.assertEqual(journey["first_edge_alert_count"], 2)
        self.assertEqual(journey["duplicate_alert_count"], 2)
        self.assertEqual(journey["out_of_order_alert_count"], 2)
        self.assertEqual(journey["alert_page_sizes"], [1, 1])
        self.assertTrue(journey["acknowledged"])
        self.assertEqual(journey["final_alert_count"], 4)

    def test_restart_persists_state_and_rebaselines_without_false_alert(self) -> None:
        journey = self.evidence["journey"]
        self.assertEqual(
            journey["restart_persisted"],
            {"watchlist": 2, "rules": 2, "alerts": 2},
        )
        self.assertEqual(journey["restart_first_batch_alert_count"], 2)
        self.assertEqual(
            self.evidence["runtime"],
            {
                "database": "temporary_sqlite_wal",
                "service": "MonitoringService",
                "events": "EventBroker",
                "http_client": "TestClient",
            },
        )

    def test_lifespan_closes_and_unsubscribes_only_exact_owned_codes(self) -> None:
        shutdown = self.evidence["shutdown"]
        expected = [
            "HK.00700",
            "US.AAPL",
            "US.AAPL260807C100000",
        ]
        self.assertEqual(shutdown["expected_owned_codes"], expected)
        for phase in ("first", "restarted"):
            self.assertEqual(shutdown[phase]["close_calls"], 1)
            self.assertEqual(shutdown[phase]["unsubscribe_calls"], [expected])
            self.assertEqual(shutdown[phase]["remaining_owned_codes"], [])

    def test_acceptance_adds_no_test_only_openapi_routes(self) -> None:
        self.assertTrue(self.evidence["openapi"]["unchanged"])
        self.assertEqual(self.evidence["openapi"]["private_test_routes"], [])
        self.assertGreater(self.evidence["openapi"]["monitoring_path_count"], 0)


if __name__ == "__main__":
    unittest.main()
