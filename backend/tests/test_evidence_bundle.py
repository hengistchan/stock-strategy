import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from stock_strategy.evidence_bundle import (
    REQUIRED_OUTPUT_FILES,
    EvidenceBundleError,
    EvidenceBundleService,
)
from stock_strategy.job_store import JobStore
from stock_strategy.run_manifest import sha256_bytes


class EvidenceBundleTest(unittest.TestCase):
    def test_export_and_import_round_trip_verified_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            jobs_root = root / "runs" / "web"
            job, job_dir, run_dir = self._write_job(jobs_root)
            service = EvidenceBundleService(root, jobs_root)

            bundle = service.export(job, job_dir, run_dir)
            store = JobStore(root)
            imported = store.import_evidence_bundle(bundle.read_bytes())
            imported_dir = jobs_root / imported["id"]

            self.assertEqual(imported["status"], "succeeded")
            self.assertEqual(imported["source_job_id"], job["id"])
            self.assertEqual(
                imported["execution_profile"], "imported-evidence-read-only"
            )
            self.assertEqual(
                (imported_dir / "strategy.py").read_text(encoding="utf-8"),
                "class Strategy: pass\n",
            )
            self.assertTrue(
                (imported_dir / "output" / "imported" / "summary.json").is_file()
            )
            self.assertEqual(store.get_job(imported["id"]), imported)

    def test_import_rejects_path_traversal_before_extraction(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("../outside", b"unsafe")
            archive.writestr("bundle.json", b"{}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            service = EvidenceBundleService(root, root / "runs" / "web")
            with self.assertRaisesRegex(EvidenceBundleError, "unsafe"):
                service.import_bundle(payload.getvalue())

    @staticmethod
    def _write_job(
        jobs_root: Path,
    ) -> tuple[dict[str, object], Path, Path]:
        job_id = "source-job"
        job_dir = jobs_root / job_id
        run_dir = job_dir / "output" / "run"
        run_dir.mkdir(parents=True)
        strategy = b"class Strategy: pass\n"
        market_data = (
            b"code,time_key,open,high,low,close,volume\n"
            b"US.TEST,2025-01-01,100,101,99,100,1000\n"
        )
        request = {
            "strategy": "strategies/demo.py",
            "symbol": "US.TEST",
            "start": "2025-01-01",
            "end": "2025-01-02",
            "ktype": "K_DAY",
            "autype": "QFQ",
            "session": "ALL",
            "initial_cash": 100_000,
            "commission_bps": 3,
            "min_commission": 1,
            "slippage_bps": 5,
            "warmup_bars": 0,
            "allow_short": False,
        }
        output = {
            name: (
                b'{"symbol":"US.TEST","metrics":{},"settings":{}}'
                if name == "summary.json"
                else b"<svg/>"
                if name == "report.svg"
                else b"<!doctype html>"
                if name == "report.html"
                else b""
            )
            for name in REQUIRED_OUTPUT_FILES
        }
        for name, content in output.items():
            (run_dir / name).write_bytes(content)
        manifest = {
            "schema_version": 1,
            "job_id": job_id,
            "status": "succeeded",
            "strategy_source_path": "strategies/demo.py",
            "strategy_revision": sha256_bytes(strategy),
            "strategy_sha256": sha256_bytes(strategy),
            "market_data_sha256": sha256_bytes(market_data),
            "market_data_bytes": len(market_data),
            "market_data_rows": 1,
            "artifacts": {
                name: {
                    "path": f"output/run/{name}",
                    "sha256": sha256_bytes(content),
                    "bytes": len(content),
                }
                for name, content in output.items()
            },
        }
        job = {
            "id": job_id,
            "status": "succeeded",
            "created_at": "2025-01-01T00:00:00+00:00",
            "started_at": "2025-01-01T00:00:01+00:00",
            "finished_at": "2025-01-01T00:00:02+00:00",
            "request": request,
            "strategy_path": "strategies/demo.py",
            "strategy_revision": sha256_bytes(strategy),
            "strategy_snapshot_path": "runs/web/source-job/strategy.py",
            "market_data_path": "runs/web/source-job/market-data.csv",
            "execution_profile": "trusted-local-v1",
            "retry_of": None,
            "run_dir": str(run_dir),
            "stdout": "",
            "stderr": "",
            "error": None,
        }
        (job_dir / "strategy.py").write_bytes(strategy)
        (job_dir / "market-data.csv").write_bytes(market_data)
        (job_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
        (job_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
        return job, job_dir, run_dir


if __name__ == "__main__":
    unittest.main()
