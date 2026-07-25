import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from stock_strategy.job_store import JobStore
from stock_strategy.run_manifest import sha256_file


class FakeProcess:
    returncode = 0

    async def communicate(self):
        return b"completed", b""

    def kill(self):
        return None


class JobStoreTest(unittest.IsolatedAsyncioTestCase):
    async def test_queued_job_can_be_cancelled_and_retried_with_lineage(self):
        request = {
            "strategy": "strategies/demo.py",
            "symbol": "US.AAPL",
            "start": "2025-01-01",
            "end": "2025-12-31",
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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            strategy = root / "strategies" / "demo.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass\n", encoding="utf-8")
            store = JobStore(root)
            original = store.create_job(request, strategy)
            cancelled = await store.cancel(original["id"])
            with patch.object(store, "launch") as launch:
                retried = store.retry(original["id"])

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["retry_of"], original["id"])
        self.assertEqual(retried["strategy_revision"], original["strategy_revision"])
        launch.assert_called_once_with(retried["id"])

    async def test_successful_job_remains_readable_from_immutable_evidence(self):
        request = {
            "strategy": "strategies/demo.py",
            "symbol": "US.AAPL",
            "start": "2025-01-01",
            "end": "2025-01-03",
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
        original_source = "class Strategy:\n    marker = 'original'\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            strategy = root / "strategies" / "demo.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text(original_source, encoding="utf-8")
            store = JobStore(root)
            job = store.create_job(request, strategy)

            cache_path = store.cache.descriptor(request)["path"]
            cache_path.write_text(
                "code,time_key,open,high,low,close,volume\n"
                "US.AAPL,2025-01-02 09:30:00,100,102,99,101,1000\n"
                "US.AAPL,2025-01-03 09:30:00,101,104,100,103,1200\n",
                encoding="utf-8",
            )
            run_dir = store.root / job["id"] / "output" / "run"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "symbol": "US.AAPL",
                        "metrics": {"total_return_pct": 3.0},
                        "settings": {
                            "opend": {"cache_path": str(cache_path.resolve())}
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "trades.csv").write_text(
                "trade_id,symbol\n1,US.AAPL\n", encoding="utf-8"
            )
            (run_dir / "orders.csv").write_text(
                "order_id,symbol\nSIM-000001,US.AAPL\n", encoding="utf-8"
            )
            (run_dir / "fills.csv").write_text(
                "execution_id,order_id\nSIM-EXEC-000001,SIM-000001\n",
                encoding="utf-8",
            )
            (run_dir / "equity_curve.csv").write_text(
                "date,equity,benchmark,drawdown\n"
                "2025-01-02 09:30:00,100000,100000,0\n"
                "2025-01-03 09:30:00,103000,101980,-0.5\n",
                encoding="utf-8",
            )
            (run_dir / "daily_returns.csv").write_text(
                "date,equity,return_pct\n2025-01-03,103000,3\n",
                encoding="utf-8",
            )
            (run_dir / "logs.csv").write_text(
                "date,level,message\n2025-01-03,FILL,filled\n",
                encoding="utf-8",
            )
            (run_dir / "report.svg").write_text("<svg/>", encoding="utf-8")

            with patch(
                "stock_strategy.job_store.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=FakeProcess()),
            ):
                await store.run_job(job["id"])

            completed = store.get_job(job["id"])
            (store.root / job["id"] / "job.json").unlink()
            completed_from_database = store.get_job(job["id"])
            manifest = json.loads(
                (store.root / job["id"] / "manifest.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8")
            )
            snapshot_path = root / completed["market_data_path"]
            strategy_snapshot = root / completed["strategy_snapshot_path"]

            strategy.write_text(
                "class Strategy:\n    marker = 'changed'\n", encoding="utf-8"
            )
            cache_path.unlink()
            result = store.load_result(job["id"])
            strategy_snapshot_content = strategy_snapshot.read_text(encoding="utf-8")
            snapshot_sha256 = sha256_file(snapshot_path)
            snapshot_value = str(snapshot_path)
            shared_cache_value = str(cache_path.resolve())
            result_summary_sha256 = sha256_file(run_dir / "summary.json")

        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed_from_database, completed)
        self.assertEqual(strategy_snapshot_content, original_source)
        self.assertEqual(manifest["market_data_sha256"], snapshot_sha256)
        self.assertEqual(
            set(manifest["artifacts"]),
            {
                "daily_returns.csv",
                "equity_curve.csv",
                "fills.csv",
                "logs.csv",
                "orders.csv",
                "report.svg",
                "summary.json",
                "trades.csv",
            },
        )
        self.assertEqual(
            manifest["artifacts"]["summary.json"]["path"],
            "output/run/summary.json",
        )
        self.assertEqual(
            manifest["artifacts"]["summary.json"]["sha256"],
            result_summary_sha256,
        )
        self.assertEqual(summary["settings"]["opend"]["cache_path"], snapshot_value)
        self.assertEqual(
            summary["settings"]["opend"]["shared_cache_path"],
            shared_cache_value,
        )
        self.assertEqual(result["price_series_count"], 2)
        self.assertEqual(result["price_series"][-1]["close"], 103.0)
        self.assertEqual(result["trades"][0]["symbol"], "US.AAPL")

    async def test_successful_process_without_market_snapshot_is_failed(self):
        request = {
            "strategy": "strategies/demo.py",
            "symbol": "US.AAPL",
            "start": "2025-01-01",
            "end": "2025-12-31",
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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            strategy = root / "strategies" / "demo.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass\n", encoding="utf-8")
            store = JobStore(root)
            job = store.create_job(request, strategy)
            with patch(
                "stock_strategy.job_store.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=FakeProcess()),
            ):
                with patch.object(store.cache, "record", return_value=None):
                    await store.run_job(job["id"])
            completed = store.get_job(job["id"])
            manifest = json.loads(
                (store.root / job["id"] / "manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(completed["status"], "failed")
        self.assertIn("无法冻结 OpenD 行情快照", completed["error"])
        self.assertEqual(manifest["status"], "failed")
        self.assertIsNotNone(manifest["started_at"])
        self.assertIsNotNone(manifest["finished_at"])


if __name__ == "__main__":
    unittest.main()
