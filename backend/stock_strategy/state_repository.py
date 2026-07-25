from __future__ import annotations

import builtins
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .job_lifecycle import InvalidJobTransition, validate_job_transition

STATE_SCHEMA_VERSION = 2


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
        serialized = json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":")
        )
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
        statement = "SELECT payload_json FROM jobs ORDER BY created_at DESC, id DESC"
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

    def transition(
        self,
        job_id: str,
        target_status: str,
        updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            payload = json.loads(str(row["payload_json"]))
            current_status = str(payload["status"])
            validate_job_transition(current_status, target_status)
            payload.update(dict(updates or {}), status=target_status)
            created_at = str(payload.get("created_at") or "")
            updated_at = str(
                payload.get("finished_at")
                or payload.get("started_at")
                or payload.get("created_at")
                or ""
            )
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, created_at = ?, updated_at = ?, payload_json = ?
                WHERE id = ? AND status = ?
                """,
                (
                    target_status,
                    created_at,
                    updated_at,
                    serialized,
                    job_id,
                    current_status,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidJobTransition(f"job {job_id} changed during transition")
            connection.commit()
            return payload
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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


class SqliteExperimentRepository:
    """Transactional experiment metadata with normalized run/job relations."""

    def __init__(self, database_path: Path, legacy_experiments_root: Path) -> None:
        self.database_path = database_path.resolve()
        self.legacy_experiments_root = legacy_experiments_root.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.import_legacy_experiments()

    def upsert(self, payload: Mapping[str, Any]) -> None:
        experiment = dict(payload)
        experiment_id = str(experiment["id"])
        status = str(experiment["status"])
        created_at = str(experiment.get("created_at") or "")
        updated_at = str(
            experiment.get("finished_at")
            or experiment.get("started_at")
            or experiment.get("created_at")
            or ""
        )
        serialized = _serialize(experiment)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO experiments(
                    id, status, created_at, updated_at, strategy_path,
                    objective, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    strategy_path = excluded.strategy_path,
                    objective = excluded.objective,
                    payload_json = excluded.payload_json
                """,
                (
                    experiment_id,
                    status,
                    created_at,
                    updated_at,
                    str(experiment.get("strategy_path") or ""),
                    str(experiment.get("objective") or ""),
                    serialized,
                ),
            )
            connection.execute(
                "DELETE FROM experiment_runs WHERE experiment_id = ?",
                (experiment_id,),
            )
            for run in experiment.get("runs", []):
                run_index = int(run["index"])
                connection.execute(
                    """
                    INSERT INTO experiment_runs(
                        experiment_id, run_index, symbol, job_id, status,
                        rank, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment_id,
                        run_index,
                        run.get("symbol"),
                        run.get("job_id"),
                        str(run.get("status") or ""),
                        run.get("rank"),
                        _serialize(run),
                    ),
                )
                for phase_name, phase in (run.get("phases") or {}).items():
                    connection.execute(
                        """
                        INSERT INTO experiment_phases(
                            experiment_id, run_index, phase_name, job_id,
                            status, payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            experiment_id,
                            run_index,
                            str(phase_name),
                            phase.get("job_id"),
                            str(phase.get("status") or ""),
                            _serialize(phase),
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, experiment_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
        if row is None:
            legacy = self._read_legacy_experiment(experiment_id)
            if legacy is None:
                raise KeyError(experiment_id)
            self.upsert(legacy)
            return legacy
        return json.loads(str(row["payload_json"]))

    def list(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        statement = (
            "SELECT payload_json FROM experiments ORDER BY created_at DESC, id DESC"
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

    def related_jobs(self, experiment_id: str) -> builtins.list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT job_id
                FROM experiment_phases
                WHERE experiment_id = ? AND job_id IS NOT NULL
                ORDER BY job_id
                """,
                (experiment_id,),
            ).fetchall()
        return [str(row["job_id"]) for row in rows]

    def import_legacy_experiments(self) -> int:
        imported = 0
        with self._connect() as connection:
            existing = {
                str(row["id"])
                for row in connection.execute("SELECT id FROM experiments").fetchall()
            }
        for path in self.legacy_experiments_root.glob("*/experiment.json"):
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
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    strategy_path TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS experiments_status_created_idx
                    ON experiments(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS experiments_strategy_created_idx
                    ON experiments(strategy_path, created_at DESC);
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    experiment_id TEXT NOT NULL,
                    run_index INTEGER NOT NULL,
                    symbol TEXT,
                    job_id TEXT,
                    status TEXT NOT NULL,
                    rank INTEGER,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(experiment_id, run_index),
                    FOREIGN KEY(experiment_id)
                        REFERENCES experiments(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS experiment_runs_job_idx
                    ON experiment_runs(job_id);
                CREATE TABLE IF NOT EXISTS experiment_phases (
                    experiment_id TEXT NOT NULL,
                    run_index INTEGER NOT NULL,
                    phase_name TEXT NOT NULL,
                    job_id TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(experiment_id, run_index, phase_name),
                    FOREIGN KEY(experiment_id, run_index)
                        REFERENCES experiment_runs(experiment_id, run_index)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS experiment_phases_job_idx
                    ON experiment_phases(job_id);
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

    def _read_legacy_experiment(
        self,
        experiment_id: str,
    ) -> dict[str, Any] | None:
        path = self.legacy_experiments_root / experiment_id / "experiment.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or str(payload.get("id")) != experiment_id:
            return None
        return payload


def _serialize(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))
