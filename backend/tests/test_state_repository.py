import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from stock_strategy.state_repository import STATE_SCHEMA_VERSION, SqliteJobRepository


class SqliteJobRepositoryTest(unittest.TestCase):
    def test_uses_wal_and_round_trips_job_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_root = root / "web"
            legacy_root.mkdir()
            repository = SqliteJobRepository(root / "state.sqlite3", legacy_root)
            payload = {
                "id": "job-1",
                "status": "queued",
                "created_at": "2026-07-25T10:00:00+08:00",
                "started_at": None,
                "finished_at": None,
                "request": {"symbol": "US.AAPL"},
            }
            repository.upsert(payload)
            loaded = repository.get("job-1")
            journal_mode = repository.journal_mode()
            with sqlite3.connect(root / "state.sqlite3") as connection:
                schema_version = connection.execute(
                    "SELECT value FROM repository_metadata WHERE key='schema_version'"
                ).fetchone()[0]

        self.assertEqual(loaded, payload)
        self.assertEqual(journal_mode, "wal")
        self.assertEqual(schema_version, str(STATE_SCHEMA_VERSION))

    def test_imports_legacy_json_once_and_ignores_malformed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_root = root / "web"
            valid_dir = legacy_root / "legacy-1"
            invalid_dir = legacy_root / "invalid"
            valid_dir.mkdir(parents=True)
            invalid_dir.mkdir()
            payload = {
                "id": "legacy-1",
                "status": "succeeded",
                "created_at": "2025-01-01T00:00:00+08:00",
            }
            (valid_dir / "job.json").write_text(json.dumps(payload), encoding="utf-8")
            (invalid_dir / "job.json").write_text("{broken", encoding="utf-8")

            repository = SqliteJobRepository(root / "state.sqlite3", legacy_root)
            self.assertEqual(repository.get("legacy-1"), payload)
            self.assertEqual(repository.import_legacy_jobs(), 0)
            self.assertEqual(repository.list(), [payload])

    def test_lazy_import_recovers_a_legacy_job_added_after_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_root = root / "web"
            legacy_root.mkdir()
            repository = SqliteJobRepository(root / "state.sqlite3", legacy_root)
            job_dir = legacy_root / "late-job"
            job_dir.mkdir()
            payload = {
                "id": "late-job",
                "status": "failed",
                "created_at": "2025-01-01T00:00:00+08:00",
            }
            (job_dir / "job.json").write_text(json.dumps(payload), encoding="utf-8")

            self.assertEqual(repository.get("late-job"), payload)
            (job_dir / "job.json").unlink()
            self.assertEqual(repository.get("late-job"), payload)

    def test_missing_job_raises_key_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_root = root / "web"
            legacy_root.mkdir()
            repository = SqliteJobRepository(root / "state.sqlite3", legacy_root)

            with self.assertRaises(KeyError):
                repository.get("missing")


if __name__ == "__main__":
    unittest.main()
