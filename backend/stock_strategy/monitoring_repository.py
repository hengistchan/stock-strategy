from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .database import connect_database, initialize_repository_metadata


class MonitoringRepository:
    """Durable watchlists, alert rules, and alert evidence in the shared WAL DB."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_instrument(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        instrument = dict(payload)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO monitored_instruments(
                    code, name, market, instrument_type, underlying_code,
                    enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    market = excluded.market,
                    instrument_type = excluded.instrument_type,
                    underlying_code = excluded.underlying_code,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    instrument["code"],
                    instrument["name"],
                    instrument["market"],
                    instrument["instrument_type"],
                    instrument.get("underlying_code"),
                    int(bool(instrument.get("enabled", True))),
                    instrument["created_at"],
                    instrument["updated_at"],
                ),
            )
        return self.get_instrument(str(instrument["code"]))

    def get_instrument(self, code: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM monitored_instruments WHERE code = ?",
                (code,),
            ).fetchone()
        if row is None:
            raise KeyError(code)
        return _instrument_payload(row)

    def list_instruments(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM monitored_instruments
                ORDER BY created_at, code
                """
            ).fetchall()
        return [_instrument_payload(row) for row in rows]

    def delete_instrument(self, code: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monitored_instruments WHERE code = ?",
                (code,),
            )
        if cursor.rowcount != 1:
            raise KeyError(code)

    def create_rule(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        rule = dict(payload)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO monitor_rules(
                    id, name, code, instrument_type, metric, operator,
                    threshold, severity, cooldown_seconds, enabled,
                    created_at, updated_at, last_evaluated_at,
                    last_triggered_at, last_value, condition_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule["id"],
                    rule["name"],
                    rule["code"],
                    rule["instrument_type"],
                    rule["metric"],
                    rule["operator"],
                    rule["threshold"],
                    rule["severity"],
                    rule["cooldown_seconds"],
                    int(bool(rule.get("enabled", True))),
                    rule["created_at"],
                    rule["updated_at"],
                    rule.get("last_evaluated_at"),
                    rule.get("last_triggered_at"),
                    rule.get("last_value"),
                    int(bool(rule.get("condition_active", False))),
                ),
            )
        return self.get_rule(str(rule["id"]))

    def get_rule(self, rule_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM monitor_rules WHERE id = ?",
                (rule_id,),
            ).fetchone()
        if row is None:
            raise KeyError(rule_id)
        return _rule_payload(row)

    def list_rules(
        self,
        *,
        code: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if code is not None:
            clauses.append("code = ?")
            parameters.append(code)
        if enabled is not None:
            clauses.append("enabled = ?")
            parameters.append(int(enabled))
        statement = "SELECT * FROM monitor_rules"
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        statement += " ORDER BY created_at DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [_rule_payload(row) for row in rows]

    def update_rule(
        self,
        rule_id: str,
        updates: Mapping[str, Any],
    ) -> dict[str, Any]:
        current = self.get_rule(rule_id)
        merged = {**current, **dict(updates)}
        reset_fields = {"code", "instrument_type", "metric", "operator", "threshold"}
        if reset_fields.intersection(updates):
            merged.update(
                last_evaluated_at=None,
                last_triggered_at=None,
                last_value=None,
                condition_active=False,
            )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitor_rules SET
                    name = ?, code = ?, instrument_type = ?, metric = ?,
                    operator = ?, threshold = ?, severity = ?,
                    cooldown_seconds = ?, enabled = ?, updated_at = ?,
                    last_evaluated_at = ?, last_triggered_at = ?,
                    last_value = ?, condition_active = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    merged["code"],
                    merged["instrument_type"],
                    merged["metric"],
                    merged["operator"],
                    merged["threshold"],
                    merged["severity"],
                    merged["cooldown_seconds"],
                    int(bool(merged["enabled"])),
                    merged["updated_at"],
                    merged.get("last_evaluated_at"),
                    merged.get("last_triggered_at"),
                    merged.get("last_value"),
                    int(bool(merged.get("condition_active"))),
                    rule_id,
                ),
            )
        return self.get_rule(rule_id)

    def update_rule_state(
        self,
        rule_id: str,
        *,
        evaluated_at: str,
        value: float,
        condition_active: bool,
        triggered_at: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE monitor_rules SET
                    last_evaluated_at = ?,
                    last_value = ?,
                    condition_active = ?,
                    last_triggered_at = COALESCE(?, last_triggered_at)
                WHERE id = ?
                """,
                (
                    evaluated_at,
                    value,
                    int(condition_active),
                    triggered_at,
                    rule_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(rule_id)
        return self.get_rule(rule_id)

    def delete_rule(self, rule_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monitor_rules WHERE id = ?",
                (rule_id,),
            )
        if cursor.rowcount != 1:
            raise KeyError(rule_id)

    def create_alert(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        alert = dict(payload)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO monitor_alerts(
                    id, dedupe_key, rule_id, rule_name, code, triggered_at,
                    acknowledged_at, severity, metric, operator, threshold,
                    value, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["id"],
                    alert["dedupe_key"],
                    alert["rule_id"],
                    alert["rule_name"],
                    alert["code"],
                    alert["triggered_at"],
                    alert.get("acknowledged_at"),
                    alert["severity"],
                    alert["metric"],
                    alert["operator"],
                    alert["threshold"],
                    alert["value"],
                    json.dumps(
                        alert.get("snapshot", {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                "SELECT * FROM monitor_alerts WHERE dedupe_key = ?",
                (alert["dedupe_key"],),
            ).fetchone()
        if row is None:
            raise RuntimeError("monitor alert was not persisted")
        return _alert_payload(row), created

    def list_alerts(
        self,
        *,
        code: str | None = None,
        unacknowledged_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("alert limit must be between 1 and 500")
        clauses: list[str] = []
        parameters: list[Any] = []
        if code is not None:
            clauses.append("code = ?")
            parameters.append(code)
        if unacknowledged_only:
            clauses.append("acknowledged_at IS NULL")
        statement = "SELECT * FROM monitor_alerts"
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        statement += " ORDER BY triggered_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [_alert_payload(row) for row in rows]

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_at: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE monitor_alerts
                SET acknowledged_at = COALESCE(acknowledged_at, ?)
                WHERE id = ?
                """,
                (acknowledged_at, alert_id),
            )
            row = connection.execute(
                "SELECT * FROM monitor_alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()
        if cursor.rowcount != 1 or row is None:
            raise KeyError(alert_id)
        return _alert_payload(row)

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0]).lower()

    def _initialize(self) -> None:
        with self._connect() as connection:
            initialize_repository_metadata(connection)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitored_instruments (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    instrument_type TEXT NOT NULL
                        CHECK(instrument_type IN ('stock', 'option')),
                    underlying_code TEXT,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS monitored_instruments_type_idx
                    ON monitored_instruments(instrument_type, enabled, code);

                CREATE TABLE IF NOT EXISTS monitor_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    instrument_type TEXT NOT NULL
                        CHECK(instrument_type IN ('stock', 'option')),
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    severity TEXT NOT NULL
                        CHECK(severity IN ('info', 'warning', 'critical')),
                    cooldown_seconds INTEGER NOT NULL
                        CHECK(cooldown_seconds BETWEEN 0 AND 86400),
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_evaluated_at TEXT,
                    last_triggered_at TEXT,
                    last_value REAL,
                    condition_active INTEGER NOT NULL DEFAULT 0
                        CHECK(condition_active IN (0, 1))
                );
                CREATE INDEX IF NOT EXISTS monitor_rules_target_idx
                    ON monitor_rules(code, enabled, created_at DESC);

                CREATE TABLE IF NOT EXISTS monitor_alerts (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    triggered_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    severity TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    value REAL NOT NULL,
                    snapshot_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS monitor_alerts_time_idx
                    ON monitor_alerts(triggered_at DESC);
                CREATE INDEX IF NOT EXISTS monitor_alerts_target_idx
                    ON monitor_alerts(code, triggered_at DESC);
                CREATE INDEX IF NOT EXISTS monitor_alerts_unread_idx
                    ON monitor_alerts(acknowledged_at, triggered_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.database_path)


def _instrument_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "code": str(row["code"]),
        "name": str(row["name"]),
        "market": str(row["market"]),
        "instrument_type": str(row["instrument_type"]),
        "underlying_code": row["underlying_code"],
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _rule_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "code": str(row["code"]),
        "instrument_type": str(row["instrument_type"]),
        "metric": str(row["metric"]),
        "operator": str(row["operator"]),
        "threshold": float(row["threshold"]),
        "severity": str(row["severity"]),
        "cooldown_seconds": int(row["cooldown_seconds"]),
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "last_evaluated_at": row["last_evaluated_at"],
        "last_triggered_at": row["last_triggered_at"],
        "last_value": (
            float(row["last_value"]) if row["last_value"] is not None else None
        ),
        "condition_active": bool(row["condition_active"]),
    }


def _alert_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "dedupe_key": str(row["dedupe_key"]),
        "rule_id": str(row["rule_id"]),
        "rule_name": str(row["rule_name"]),
        "code": str(row["code"]),
        "triggered_at": str(row["triggered_at"]),
        "acknowledged_at": row["acknowledged_at"],
        "severity": str(row["severity"]),
        "metric": str(row["metric"]),
        "operator": str(row["operator"]),
        "threshold": float(row["threshold"]),
        "value": float(row["value"]),
        "snapshot": json.loads(str(row["snapshot_json"])),
    }
