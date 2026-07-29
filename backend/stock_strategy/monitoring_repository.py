from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .database import (
    connect_database,
    ensure_repository_metadata,
    set_component_schema_version,
)

MONITORING_SCHEMA_VERSION = 5


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
        underlying_code = rule.get("underlying_code")
        if not underlying_code and rule["instrument_type"] == "stock":
            underlying_code = rule["code"]
        if not underlying_code:
            raise ValueError("rule underlying_code is required")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO monitor_rules(
                    id, name, code, underlying_code, instrument_type, metric, operator,
                    threshold, severity, cooldown_seconds, daily_trigger_limit,
                    session, enabled,
                    created_at, updated_at, last_evaluated_at,
                    last_triggered_at, last_value, condition_active,
                    last_observation_key, last_provider_time,
                    trigger_date, trigger_count
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    rule["id"],
                    rule["name"],
                    rule["code"],
                    underlying_code,
                    rule["instrument_type"],
                    rule["metric"],
                    rule["operator"],
                    rule["threshold"],
                    rule["severity"],
                    rule["cooldown_seconds"],
                    rule.get("daily_trigger_limit", 10),
                    rule.get("session", "regular"),
                    int(bool(rule.get("enabled", True))),
                    rule["created_at"],
                    rule["updated_at"],
                    rule.get("last_evaluated_at"),
                    rule.get("last_triggered_at"),
                    rule.get("last_value"),
                    int(bool(rule.get("condition_active", False))),
                    rule.get("last_observation_key"),
                    rule.get("last_provider_time"),
                    rule.get("trigger_date"),
                    rule.get("trigger_count", 0),
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
        underlying_code: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if code is not None:
            clauses.append("code = ?")
            parameters.append(code)
        if underlying_code is not None:
            clauses.append("underlying_code = ?")
            parameters.append(underlying_code)
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
                last_observation_key=None,
                last_provider_time=None,
                trigger_date=None,
                trigger_count=0,
            )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitor_rules SET
                    name = ?, code = ?, instrument_type = ?, metric = ?,
                    operator = ?, threshold = ?, severity = ?,
                    cooldown_seconds = ?, daily_trigger_limit = ?,
                    session = ?, enabled = ?, updated_at = ?,
                    last_evaluated_at = ?, last_triggered_at = ?,
                    last_value = ?, condition_active = ?,
                    last_observation_key = ?, last_provider_time = ?,
                    trigger_date = ?, trigger_count = ?
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
                    merged["daily_trigger_limit"],
                    merged["session"],
                    int(bool(merged["enabled"])),
                    merged["updated_at"],
                    merged.get("last_evaluated_at"),
                    merged.get("last_triggered_at"),
                    merged.get("last_value"),
                    int(bool(merged.get("condition_active"))),
                    merged.get("last_observation_key"),
                    merged.get("last_provider_time"),
                    merged.get("trigger_date"),
                    merged.get("trigger_count", 0),
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
        rule, _alert, _applied = self.record_evaluation(
            rule_id,
            evaluated_at=evaluated_at,
            provider_time=evaluated_at,
            observation_key=f"legacy:{rule_id}:{evaluated_at}",
            value=value,
            condition_active=condition_active,
            alert=None,
            triggered_at=triggered_at,
        )
        return rule

    def record_evaluation(
        self,
        rule_id: str,
        *,
        evaluated_at: str,
        provider_time: str,
        observation_key: str,
        value: float,
        condition_active: bool,
        alert: Mapping[str, Any] | None,
        triggered_at: str | None = None,
        trigger_date: str | None = None,
        increment_trigger: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
        """Atomically persist rule state and immutable alert evidence."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                "SELECT * FROM monitor_rules WHERE id = ?",
                (rule_id,),
            ).fetchone()
            if current_row is None:
                raise KeyError(rule_id)
            current = _rule_payload(current_row)
            if current.get("last_observation_key") == observation_key:
                connection.commit()
                return current, None, False
            last_provider_time = current.get("last_provider_time")
            if last_provider_time and provider_time <= str(last_provider_time):
                connection.commit()
                return current, None, False

            current_trigger_date = current.get("trigger_date")
            trigger_count = int(current.get("trigger_count") or 0)
            if trigger_date is not None and trigger_date != current_trigger_date:
                trigger_count = 0
            daily_trigger_limit = int(current["daily_trigger_limit"])
            may_trigger = increment_trigger and trigger_count < daily_trigger_limit

            persisted_alert: dict[str, Any] | None = None
            alert_created = False
            if alert is not None and (not increment_trigger or may_trigger):
                persisted_alert, alert_created = _insert_alert(connection, alert)
            if increment_trigger and alert_created:
                trigger_count += 1
            effective_triggered_at = triggered_at if alert_created else None
            connection.execute(
                """
                UPDATE monitor_rules SET
                    last_evaluated_at = ?,
                    last_value = ?,
                    condition_active = ?,
                    last_triggered_at = COALESCE(?, last_triggered_at),
                    last_observation_key = ?,
                    last_provider_time = ?,
                    trigger_date = COALESCE(?, trigger_date),
                    trigger_count = ?
                WHERE id = ?
                """,
                (
                    evaluated_at,
                    value,
                    int(condition_active),
                    effective_triggered_at,
                    observation_key,
                    provider_time,
                    trigger_date,
                    trigger_count,
                    rule_id,
                ),
            )
            updated_row = connection.execute(
                "SELECT * FROM monitor_rules WHERE id = ?",
                (rule_id,),
            ).fetchone()
            if updated_row is None:
                raise KeyError(rule_id)
            connection.commit()
            return _rule_payload(updated_row), persisted_alert, True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def delete_rule(self, rule_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monitor_rules WHERE id = ?",
                (rule_id,),
            )
        if cursor.rowcount != 1:
            raise KeyError(rule_id)

    def create_alert(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._connect() as connection:
            return _insert_alert(connection, payload)

    def list_alerts(
        self,
        *,
        code: str | None = None,
        underlying_code: str | None = None,
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
        if underlying_code is not None:
            clauses.append("underlying_code = ?")
            parameters.append(underlying_code)
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

    def list_alerts_page(
        self,
        *,
        code: str | None = None,
        underlying_code: str | None = None,
        unacknowledged_only: bool = False,
        before: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], bool]:
        if limit < 1 or limit > 100:
            raise ValueError("alert page limit must be between 1 and 100")
        clauses: list[str] = []
        parameters: list[Any] = []
        if code is not None:
            clauses.append("code = ?")
            parameters.append(code)
        if underlying_code is not None:
            clauses.append("underlying_code = ?")
            parameters.append(underlying_code)
        if unacknowledged_only:
            clauses.append("acknowledged_at IS NULL")
        if before is not None:
            triggered_at, alert_id = before
            clauses.append("(triggered_at < ? OR (triggered_at = ? AND id < ?))")
            parameters.extend((triggered_at, triggered_at, alert_id))
        statement = "SELECT * FROM monitor_alerts"
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        statement += " ORDER BY triggered_at DESC, id DESC LIMIT ?"
        parameters.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        has_more = len(rows) > limit
        return [_alert_payload(row) for row in rows[:limit]], has_more

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
            ensure_repository_metadata(connection)
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
                    underlying_code TEXT NOT NULL,
                    instrument_type TEXT NOT NULL
                        CHECK(instrument_type IN ('stock', 'option')),
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    severity TEXT NOT NULL
                        CHECK(severity IN ('info', 'warning', 'critical')),
                    cooldown_seconds INTEGER NOT NULL
                        CHECK(cooldown_seconds BETWEEN 0 AND 86400),
                    daily_trigger_limit INTEGER NOT NULL DEFAULT 10
                        CHECK(daily_trigger_limit BETWEEN 1 AND 1000),
                    session TEXT NOT NULL DEFAULT 'regular'
                        CHECK(session IN ('regular', 'extended', 'all')),
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_evaluated_at TEXT,
                    last_triggered_at TEXT,
                    last_value REAL,
                    condition_active INTEGER NOT NULL DEFAULT 0
                        CHECK(condition_active IN (0, 1)),
                    last_observation_key TEXT,
                    last_provider_time TEXT,
                    trigger_date TEXT,
                    trigger_count INTEGER NOT NULL DEFAULT 0
                        CHECK(trigger_count >= 0)
                );
                CREATE INDEX IF NOT EXISTS monitor_rules_target_idx
                    ON monitor_rules(code, enabled, created_at DESC);

                CREATE TABLE IF NOT EXISTS monitor_alerts (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    underlying_code TEXT NOT NULL,
                    triggered_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    severity TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    value REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'opend',
                    provider_time TEXT,
                    received_at TEXT,
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
            _ensure_column(
                connection,
                "monitor_rules",
                "underlying_code",
                "TEXT",
            )
            _ensure_column(
                connection,
                "monitor_rules",
                "last_observation_key",
                "TEXT",
            )
            _ensure_column(
                connection,
                "monitor_rules",
                "last_provider_time",
                "TEXT",
            )
            _ensure_column(
                connection,
                "monitor_rules",
                "daily_trigger_limit",
                "INTEGER NOT NULL DEFAULT 10",
            )
            _ensure_column(
                connection,
                "monitor_rules",
                "session",
                "TEXT NOT NULL DEFAULT 'regular'",
            )
            _ensure_column(
                connection,
                "monitor_rules",
                "trigger_date",
                "TEXT",
            )
            _ensure_column(
                connection,
                "monitor_rules",
                "trigger_count",
                "INTEGER NOT NULL DEFAULT 0",
            )
            _ensure_column(
                connection,
                "monitor_alerts",
                "underlying_code",
                "TEXT",
            )
            _ensure_column(
                connection,
                "monitor_alerts",
                "source",
                "TEXT NOT NULL DEFAULT 'opend'",
            )
            _ensure_column(
                connection,
                "monitor_alerts",
                "provider_time",
                "TEXT",
            )
            _ensure_column(
                connection,
                "monitor_alerts",
                "received_at",
                "TEXT",
            )
            _backfill_underlying_codes(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS monitor_rules_underlying_idx
                ON monitor_rules(underlying_code, enabled, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS monitor_alerts_underlying_idx
                ON monitor_alerts(underlying_code, triggered_at DESC)
                """
            )
            connection.execute(
                """
                UPDATE monitor_alerts
                SET provider_time = COALESCE(provider_time, triggered_at),
                    received_at = COALESCE(received_at, triggered_at)
                """
            )
            set_component_schema_version(
                connection,
                key="monitoring_schema_version",
                version=MONITORING_SCHEMA_VERSION,
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
        "underlying_code": (
            str(row["underlying_code"]) if row["underlying_code"] is not None else None
        ),
        "instrument_type": str(row["instrument_type"]),
        "metric": str(row["metric"]),
        "operator": str(row["operator"]),
        "threshold": float(row["threshold"]),
        "severity": str(row["severity"]),
        "cooldown_seconds": int(row["cooldown_seconds"]),
        "daily_trigger_limit": int(row["daily_trigger_limit"]),
        "session": str(row["session"]),
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "last_evaluated_at": row["last_evaluated_at"],
        "last_triggered_at": row["last_triggered_at"],
        "last_value": (
            float(row["last_value"]) if row["last_value"] is not None else None
        ),
        "condition_active": bool(row["condition_active"]),
        "last_observation_key": row["last_observation_key"],
        "last_provider_time": row["last_provider_time"],
        "trigger_date": row["trigger_date"],
        "trigger_count": int(row["trigger_count"]),
    }


def _alert_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "dedupe_key": str(row["dedupe_key"]),
        "rule_id": str(row["rule_id"]),
        "rule_name": str(row["rule_name"]),
        "code": str(row["code"]),
        "underlying_code": (
            str(row["underlying_code"]) if row["underlying_code"] is not None else None
        ),
        "triggered_at": str(row["triggered_at"]),
        "acknowledged_at": row["acknowledged_at"],
        "severity": str(row["severity"]),
        "metric": str(row["metric"]),
        "operator": str(row["operator"]),
        "threshold": float(row["threshold"]),
        "value": float(row["value"]),
        "source": str(row["source"]),
        "provider_time": str(row["provider_time"]),
        "received_at": str(row["received_at"]),
        "snapshot": json.loads(str(row["snapshot_json"])),
    }


def _insert_alert(
    connection: sqlite3.Connection,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    alert = dict(payload)
    underlying_code = _alert_underlying_code(alert)
    provider_time = alert.get("provider_time") or alert["triggered_at"]
    received_at = alert.get("received_at") or alert["triggered_at"]
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO monitor_alerts(
            id, dedupe_key, rule_id, rule_name, code, underlying_code, triggered_at,
            acknowledged_at, severity, metric, operator, threshold,
            value, source, provider_time, received_at, snapshot_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert["id"],
            alert["dedupe_key"],
            alert["rule_id"],
            alert["rule_name"],
            alert["code"],
            underlying_code,
            alert["triggered_at"],
            alert.get("acknowledged_at"),
            alert["severity"],
            alert["metric"],
            alert["operator"],
            alert["threshold"],
            alert["value"],
            alert.get("source") or "opend",
            provider_time,
            received_at,
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


def _alert_underlying_code(alert: Mapping[str, Any]) -> str:
    explicit = alert.get("underlying_code")
    if isinstance(explicit, str) and explicit:
        return explicit
    snapshot = alert.get("snapshot")
    if isinstance(snapshot, Mapping):
        snapshot_underlying = snapshot.get("underlying_code")
        if isinstance(snapshot_underlying, str) and snapshot_underlying:
            return snapshot_underlying
        if snapshot.get("instrument_type") == "option":
            raise ValueError("option alert underlying_code is required")
    return str(alert["code"])


def _backfill_underlying_codes(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE monitor_rules
        SET underlying_code = code
        WHERE underlying_code IS NULL AND instrument_type = 'stock'
        """
    )
    connection.execute(
        """
        UPDATE monitor_rules
        SET underlying_code = (
            SELECT monitored_instruments.underlying_code
            FROM monitored_instruments
            WHERE monitored_instruments.code = monitor_rules.code
        )
        WHERE underlying_code IS NULL AND instrument_type = 'option'
        """
    )
    connection.execute(
        """
        UPDATE monitor_alerts
        SET underlying_code = (
            SELECT monitor_rules.underlying_code
            FROM monitor_rules
            WHERE monitor_rules.id = monitor_alerts.rule_id
        )
        WHERE underlying_code IS NULL
        """
    )
    rows = connection.execute(
        """
        SELECT id, code, snapshot_json
        FROM monitor_alerts
        WHERE underlying_code IS NULL
        """
    ).fetchall()
    for row in rows:
        try:
            snapshot = json.loads(str(row["snapshot_json"]))
        except (TypeError, ValueError):
            snapshot = {}
        underlying_code = (
            snapshot.get("underlying_code") if isinstance(snapshot, Mapping) else None
        )
        if not underlying_code and (
            not isinstance(snapshot, Mapping)
            or snapshot.get("instrument_type") != "option"
        ):
            underlying_code = str(row["code"])
        if underlying_code:
            connection.execute(
                """
                UPDATE monitor_alerts
                SET underlying_code = ?
                WHERE id = ?
                """,
                (str(underlying_code), str(row["id"])),
            )


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
