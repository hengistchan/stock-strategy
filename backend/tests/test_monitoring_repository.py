from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from stock_strategy.monitoring_repository import (
    MONITORING_SCHEMA_VERSION,
    MonitoringRepository,
)


class MonitoringRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = MonitoringRepository(self.root / "state.sqlite3")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_persists_watchlist_in_shared_wal_database(self):
        created = self.repository.upsert_instrument(
            {
                "code": "US.AAPL",
                "name": "Apple",
                "market": "US",
                "instrument_type": "stock",
                "underlying_code": None,
                "enabled": True,
                "created_at": "2026-07-27T10:00:00+08:00",
                "updated_at": "2026-07-27T10:00:00+08:00",
            }
        )
        updated = self.repository.upsert_instrument(
            {
                **created,
                "name": "苹果",
                "updated_at": "2026-07-27T10:01:00+08:00",
            }
        )
        with sqlite3.connect(self.root / "state.sqlite3") as connection:
            monitoring_schema_version = connection.execute(
                """
                SELECT value FROM repository_metadata
                WHERE key='monitoring_schema_version'
                """
            ).fetchone()[0]

        self.assertEqual(self.repository.journal_mode(), "wal")
        self.assertEqual(
            monitoring_schema_version,
            str(MONITORING_SCHEMA_VERSION),
        )
        self.assertEqual(updated["name"], "苹果")
        self.assertEqual(self.repository.list_instruments(), [updated])

        self.repository.delete_instrument("US.AAPL")
        self.assertEqual(self.repository.list_instruments(), [])
        with self.assertRaises(KeyError):
            self.repository.delete_instrument("US.AAPL")

    def test_round_trips_rule_state_and_resets_evaluation_after_definition_change(self):
        rule = self.repository.create_rule(_rule_payload())
        evaluated = self.repository.update_rule_state(
            rule["id"],
            evaluated_at="2026-07-27T10:00:05+08:00",
            value=31.2,
            condition_active=True,
            triggered_at="2026-07-27T10:00:05+08:00",
        )

        self.assertEqual(evaluated["last_value"], 31.2)
        self.assertTrue(evaluated["condition_active"])
        self.assertEqual(
            self.repository.list_rules(code="US.AAPL", enabled=True),
            [evaluated],
        )

        renamed = self.repository.update_rule(
            rule["id"],
            {
                "name": "Apple move",
                "updated_at": "2026-07-27T10:01:00+08:00",
            },
        )
        self.assertEqual(renamed["last_value"], 31.2)

        changed = self.repository.update_rule(
            rule["id"],
            {
                "threshold": 35,
                "updated_at": "2026-07-27T10:02:00+08:00",
            },
        )
        self.assertIsNone(changed["last_value"])
        self.assertIsNone(changed["last_triggered_at"])
        self.assertFalse(changed["condition_active"])

    def test_alerts_are_idempotent_acknowledgeable_and_survive_rule_deletion(self):
        rule = self.repository.create_rule(_rule_payload())
        payload = {
            "id": "alert-1",
            "dedupe_key": "rule-1:2026-07-27T10:00:05+08:00",
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "code": rule["code"],
            "triggered_at": "2026-07-27T10:00:05+08:00",
            "acknowledged_at": None,
            "severity": "warning",
            "metric": "change_rate",
            "operator": "above",
            "threshold": 3,
            "value": 3.2,
            "snapshot": {"last_price": 339.15, "source": "opend"},
        }

        alert, created = self.repository.create_alert(payload)
        duplicate, duplicate_created = self.repository.create_alert(
            {**payload, "id": "alert-duplicate"}
        )

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate["id"], alert["id"])
        self.assertEqual(
            self.repository.list_alerts(unacknowledged_only=True),
            [alert],
        )

        acknowledged = self.repository.acknowledge_alert(
            alert["id"],
            "2026-07-27T10:01:00+08:00",
        )
        self.assertIsNotNone(acknowledged["acknowledged_at"])
        self.assertEqual(
            self.repository.list_alerts(unacknowledged_only=True),
            [],
        )

        self.repository.delete_rule(rule["id"])
        self.assertEqual(self.repository.list_alerts(), [acknowledged])

    def test_evaluation_and_alert_are_atomic_and_ignore_duplicate_observations(self):
        rule = self.repository.create_rule(_rule_payload())
        alert_payload = {
            "id": "alert-atomic",
            "dedupe_key": "rule-1:observation-1",
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "code": rule["code"],
            "triggered_at": "2026-07-27T10:00:05+08:00",
            "severity": "warning",
            "metric": "change_rate",
            "operator": "above",
            "threshold": 3,
            "value": 3.2,
            "provider_time": "2026-07-27 10:00:04",
            "received_at": "2026-07-27T10:00:05+08:00",
            "snapshot": {"last_price": 339.15},
        }

        updated, alert, applied = self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-27T10:00:05+08:00",
            provider_time="2026-07-27 10:00:04",
            observation_key="observation-1",
            value=3.2,
            condition_active=True,
            alert=alert_payload,
            triggered_at=alert_payload["triggered_at"],
        )
        duplicate_rule, duplicate_alert, duplicate_applied = (
            self.repository.record_evaluation(
                rule["id"],
                evaluated_at="2026-07-27T10:00:06+08:00",
                provider_time="2026-07-27 10:00:04",
                observation_key="observation-1",
                value=3.2,
                condition_active=True,
                alert={**alert_payload, "id": "alert-duplicate"},
                triggered_at=alert_payload["triggered_at"],
            )
        )

        self.assertTrue(applied)
        self.assertEqual(updated["last_observation_key"], "observation-1")
        self.assertEqual(alert["provider_time"], "2026-07-27 10:00:04")
        self.assertFalse(duplicate_applied)
        self.assertIsNone(duplicate_alert)
        self.assertEqual(duplicate_rule, updated)
        self.assertEqual(len(self.repository.list_alerts()), 1)

    def test_failed_alert_insert_rolls_back_rule_state(self):
        rule = self.repository.create_rule(_rule_payload())

        with self.assertRaises(KeyError):
            self.repository.record_evaluation(
                rule["id"],
                evaluated_at="2026-07-27T10:00:05+08:00",
                provider_time="2026-07-27 10:00:04",
                observation_key="observation-broken",
                value=3.2,
                condition_active=True,
                alert={"id": "missing-required-fields"},
                triggered_at="2026-07-27T10:00:05+08:00",
            )

        unchanged = self.repository.get_rule(rule["id"])
        self.assertIsNone(unchanged["last_observation_key"])
        self.assertIsNone(unchanged["last_value"])
        self.assertEqual(self.repository.list_alerts(), [])

    def test_migrates_monitoring_v1_without_losing_rules_or_alerts(self):
        legacy_root = self.root / "legacy"
        legacy_root.mkdir()
        database_path = legacy_root / "state.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE repository_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT INTO repository_metadata VALUES ('schema_version', '2');
                INSERT INTO repository_metadata
                    VALUES ('monitoring_schema_version', '1');
                CREATE TABLE monitor_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    severity TEXT NOT NULL,
                    cooldown_seconds INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_evaluated_at TEXT,
                    last_triggered_at TEXT,
                    last_value REAL,
                    condition_active INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE monitor_alerts (
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
                CREATE TABLE monitored_instruments (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    underlying_code TEXT,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            payload = _rule_payload()
            connection.execute(
                """
                INSERT INTO monitor_rules VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                tuple(payload.values())[:16],
            )

        migrated = MonitoringRepository(database_path)
        rule = migrated.get_rule("rule-1")
        with sqlite3.connect(database_path) as connection:
            version = connection.execute(
                """
                SELECT value FROM repository_metadata
                WHERE key='monitoring_schema_version'
                """
            ).fetchone()[0]

        self.assertEqual(rule["name"], "Apple daily move")
        self.assertIsNone(rule["last_observation_key"])
        self.assertEqual(version, str(MONITORING_SCHEMA_VERSION))


def _rule_payload() -> dict[str, object]:
    return {
        "id": "rule-1",
        "name": "Apple daily move",
        "code": "US.AAPL",
        "instrument_type": "stock",
        "metric": "change_rate",
        "operator": "above",
        "threshold": 3,
        "severity": "warning",
        "cooldown_seconds": 300,
        "enabled": True,
        "created_at": "2026-07-27T10:00:00+08:00",
        "updated_at": "2026-07-27T10:00:00+08:00",
        "last_evaluated_at": None,
        "last_triggered_at": None,
        "last_value": None,
        "condition_active": False,
        "last_observation_key": None,
        "last_provider_time": None,
    }


if __name__ == "__main__":
    unittest.main()
