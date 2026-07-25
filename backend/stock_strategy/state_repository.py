from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


STATE_SCHEMA_VERSION = 1


class SqliteJobRepository:
    """Transactional job metadata; artifact JSON remains a compatibility mirror."""

    def __init__(self, database_path: Path, legacy_jobs_root: Path) -> None:
        self.database_path = database_path.resolve()
        self.legacy_jobs_root = legacy_jobs_root.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.import_legacy_jobs()

    def upsert(self, payload: Mapping[str, Any]) -> None:
        job_id = str(payload["id"])
        status = str(payload["status"])
        created_at = str(payload.get("created_at") or "")
        updated_at = str(
            payload.get("finished_at")
            or payload.get("started_at")
            or payload.get("created_at")
            or ""
        )
        serialized = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(id, status, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (job_id, status, created_at, updated_at, serialized),
            )

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            legacy = self._read_legacy_job(job_id)
            if legacy is None:
                raise KeyError(job_id)
            self.upsert(legacy)
            return legacy
        return json.loads(str(row["payload_json"]))

    def list(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        statement = (
            "SELECT payload_json FROM jobs "
            "ORDER BY created_at DESC, id DESC"
        )
        parameters: tuple[int, ...] = ()
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            statement += " LIMIT ?"
            parameters = (limit,)
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [json.loads(str(row["payload_json"])) for row in rows]

    def delete(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def import_legacy_jobs(self) -> int:
        imported = 0
        existing = self._existing_ids()
        for path in self.legacy_jobs_root.glob("*/job.json"):
            if path.parent.name in existing:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if (
                    not isinstance(payload, dict)
                    or str(payload.get("id")) != path.parent.name
                    or not payload.get("status")
                ):
                    continue
                self.upsert(payload)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            existing.add(path.parent.name)
            imported += 1
        return imported

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0]).lower()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS repository_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_status_created_idx
                    ON jobs(status, created_at DESC);
                """
            )
            connection.execute(
                """
                INSERT INTO repository_metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(STATE_SCHEMA_VERSION),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=5,
            isolation_level="DEFERRED",
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _existing_ids(self) -> set[str]:
        with self._connect() as connection:
            return {
                str(row["id"])
                for row in connection.execute("SELECT id FROM jobs").fetchall()
            }

    def _read_legacy_job(self, job_id: str) -> dict[str, Any] | None:
        path = self.legacy_jobs_root / job_id / "job.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or str(payload.get("id")) != job_id:
            return None
        return payload
