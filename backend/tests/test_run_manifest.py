import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from stock_strategy.run_manifest import (
    StrategySnapshot,
    atomic_write_json,
    create_run_manifest,
    update_run_manifest,
)


class RunManifestTest(unittest.TestCase):
    def test_manifest_binds_strategy_request_runtime_and_market_data(self):
        source = "class Strategy:\n    value = 1\n"
        snapshot = StrategySnapshot.create(
            source_path="strategies/demo.py",
            content=source,
        )
        request = {"symbol": "US.AAPL", "start": "2025-01-01"}
        manifest = create_run_manifest(
            job_id="job-1",
            created_at="2026-07-25T10:00:00+08:00",
            request=request,
            strategy=snapshot,
            futu_sdk_version="10.6.6608",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            atomic_write_json(path, manifest)
            completed = update_run_manifest(
                path,
                status="succeeded",
                started_at="2026-07-25T10:00:01+08:00",
                finished_at="2026-07-25T10:00:02+08:00",
                market_data={
                    "content_sha256": "b" * 64,
                    "bytes": 1024,
                    "rows": 252,
                },
            )
            stored = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(
            manifest["strategy_sha256"],
            hashlib.sha256(source.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(manifest["strategy_revision"], manifest["strategy_sha256"])
        self.assertEqual(len(manifest["request_sha256"]), 64)
        self.assertEqual(completed, stored)
        self.assertEqual(stored["market_data_snapshot_path"], "market-data.csv")
        self.assertEqual(stored["market_data_sha256"], "b" * 64)
        self.assertEqual(stored["market_data_rows"], 252)

    def test_snapshot_rejects_a_revision_from_different_source(self):
        with self.assertRaisesRegex(ValueError, "revision"):
            StrategySnapshot.create(
                source_path="strategies/demo.py",
                content="class Strategy: pass\n",
                revision="0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
