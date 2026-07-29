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
        self.assertEqual(alert["source"], "opend")
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

    def test_daily_trigger_limit_is_atomic_and_resets_on_a_new_market_date(self):
        rule = self.repository.create_rule(
            {
                **_rule_payload(),
                "daily_trigger_limit": 1,
                "session": "all",
            }
        )

        first, first_alert, applied = self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-27T10:00:05+08:00",
            provider_time="2026-07-27 10:00:04",
            observation_key="day-1-crossing-1",
            value=3.2,
            condition_active=True,
            alert=_alert_payload(
                alert_id="day-1-alert-1",
                dedupe_key="rule-1:day-1-crossing-1",
                triggered_at="2026-07-27T10:00:05+08:00",
            ),
            triggered_at="2026-07-27T10:00:05+08:00",
            trigger_date="2026-07-27",
            increment_trigger=True,
        )
        self.assertTrue(applied)
        self.assertIsNotNone(first_alert)
        self.assertEqual(first["trigger_count"], 1)
        self.assertEqual(first["trigger_date"], "2026-07-27")

        self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-27T10:01:05+08:00",
            provider_time="2026-07-27 10:01:04",
            observation_key="day-1-reset",
            value=2.0,
            condition_active=False,
            alert=None,
            trigger_date="2026-07-27",
        )
        limited, limited_alert, _ = self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-27T10:02:05+08:00",
            provider_time="2026-07-27 10:02:04",
            observation_key="day-1-crossing-2",
            value=3.4,
            condition_active=True,
            alert=_alert_payload(
                alert_id="day-1-alert-2",
                dedupe_key="rule-1:day-1-crossing-2",
                triggered_at="2026-07-27T10:02:05+08:00",
            ),
            triggered_at="2026-07-27T10:02:05+08:00",
            trigger_date="2026-07-27",
            increment_trigger=True,
        )
        self.assertIsNone(limited_alert)
        self.assertEqual(limited["trigger_count"], 1)
        self.assertEqual(len(self.repository.list_alerts()), 1)

        self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-28T10:00:05+08:00",
            provider_time="2026-07-28 10:00:04",
            observation_key="day-2-reset",
            value=2.0,
            condition_active=False,
            alert=None,
            trigger_date="2026-07-28",
        )
        next_day, next_alert, _ = self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-28T10:01:05+08:00",
            provider_time="2026-07-28 10:01:04",
            observation_key="day-2-crossing-1",
            value=3.5,
            condition_active=True,
            alert=_alert_payload(
                alert_id="day-2-alert-1",
                dedupe_key="rule-1:day-2-crossing-1",
                triggered_at="2026-07-28T10:01:05+08:00",
            ),
            triggered_at="2026-07-28T10:01:05+08:00",
            trigger_date="2026-07-28",
            increment_trigger=True,
        )
        self.assertIsNotNone(next_alert)
        self.assertEqual(next_day["trigger_count"], 1)
        self.assertEqual(len(self.repository.list_alerts()), 2)

    def test_alert_ledger_pages_by_stable_time_and_id_cursor(self):
        for alert_id, triggered_at in (
            ("alert-c", "2026-07-27T10:02:00+08:00"),
            ("alert-b", "2026-07-27T10:01:00+08:00"),
            ("alert-a", "2026-07-27T10:01:00+08:00"),
        ):
            self.repository.create_alert(
                _alert_payload(
                    alert_id=alert_id,
                    dedupe_key=f"rule-1:{alert_id}",
                    triggered_at=triggered_at,
                )
            )

        first, first_has_more = self.repository.list_alerts_page(limit=2)
        second, second_has_more = self.repository.list_alerts_page(
            before=(first[-1]["triggered_at"], first[-1]["id"]),
            limit=2,
        )

        self.assertEqual([alert["id"] for alert in first], ["alert-c", "alert-b"])
        self.assertTrue(first_has_more)
        self.assertEqual([alert["id"] for alert in second], ["alert-a"])
        self.assertFalse(second_has_more)

    def test_underlying_scope_groups_stock_and_option_rules_and_alert_pages(self):
        stock_rule = self.repository.create_rule(_rule_payload())
        option_rule = self.repository.create_rule(_option_rule_payload())
        hk_rule = self.repository.create_rule(
            {
                **_rule_payload(),
                "id": "rule-hk",
                "name": "Tencent move",
                "code": "HK.00700",
                "underlying_code": "HK.00700",
            }
        )

        for alert_id, rule, triggered_at in (
            ("alert-option", option_rule, "2026-07-27T10:02:00+08:00"),
            ("alert-stock", stock_rule, "2026-07-27T10:01:00+08:00"),
            ("alert-hk", hk_rule, "2026-07-27T10:00:00+08:00"),
        ):
            self.repository.create_alert(
                {
                    **_alert_payload(
                        alert_id=alert_id,
                        dedupe_key=f"{rule['id']}:{alert_id}",
                        triggered_at=triggered_at,
                    ),
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "code": rule["code"],
                    "underlying_code": rule["underlying_code"],
                    "snapshot": {
                        "instrument_type": rule["instrument_type"],
                        "underlying_code": rule["underlying_code"],
                    },
                }
            )

        scoped_rules = self.repository.list_rules(
            underlying_code="US.AAPL",
            enabled=True,
        )
        first, has_more = self.repository.list_alerts_page(
            underlying_code="US.AAPL",
            limit=1,
        )
        second, second_has_more = self.repository.list_alerts_page(
            underlying_code="US.AAPL",
            before=(first[-1]["triggered_at"], first[-1]["id"]),
            limit=1,
        )

        self.assertEqual(
            {rule["id"] for rule in scoped_rules},
            {"rule-1", "rule-option"},
        )
        self.assertEqual(
            self.repository.list_rules(code=option_rule["code"]),
            [option_rule],
        )
        self.assertEqual([alert["id"] for alert in first], ["alert-option"])
        self.assertTrue(has_more)
        self.assertEqual([alert["id"] for alert in second], ["alert-stock"])
        self.assertFalse(second_has_more)

    def test_rejects_a_distinct_observation_with_the_same_provider_time(self):
        rule = self.repository.create_rule(_rule_payload())
        first, _, _ = self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-27T10:00:05+08:00",
            provider_time="2026-07-27 10:00:04",
            observation_key="observation-1",
            value=2.9,
            condition_active=False,
            alert=None,
        )
        duplicate_time, alert, applied = self.repository.record_evaluation(
            rule["id"],
            evaluated_at="2026-07-27T10:00:06+08:00",
            provider_time="2026-07-27 10:00:04",
            observation_key="observation-2",
            value=3.2,
            condition_active=True,
            alert=None,
        )

        self.assertFalse(applied)
        self.assertIsNone(alert)
        self.assertEqual(duplicate_time, first)

    def test_definition_change_resets_daily_delivery_state(self):
        rule = self.repository.create_rule(
            {
                **_rule_payload(),
                "trigger_date": "2026-07-27",
                "trigger_count": 4,
            }
        )

        changed = self.repository.update_rule(
            rule["id"],
            {
                "threshold": 4,
                "updated_at": "2026-07-27T10:03:00+08:00",
            },
        )

        self.assertIsNone(changed["trigger_date"])
        self.assertEqual(changed["trigger_count"], 0)

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
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                INSERT INTO jobs VALUES (
                    'job-existing', 'succeeded',
                    '2026-07-26T10:00:00+08:00',
                    '2026-07-26T10:01:00+08:00',
                    '{"id":"job-existing","status":"succeeded"}'
                );
                CREATE TABLE experiments (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    strategy_path TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                INSERT INTO experiments VALUES (
                    'experiment-existing', 'succeeded',
                    '2026-07-26T10:00:00+08:00',
                    '2026-07-26T10:02:00+08:00',
                    'examples/ma_cross.py', 'sharpe_ratio',
                    '{"id":"experiment-existing","status":"succeeded"}'
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
            connection.execute(
                """
                INSERT INTO monitor_alerts(
                    id, dedupe_key, rule_id, rule_name, code, triggered_at,
                    acknowledged_at, severity, metric, operator, threshold,
                    value, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "alert-legacy",
                    "rule-1:legacy",
                    "rule-1",
                    "Apple daily move",
                    "US.AAPL",
                    "2026-07-27T10:00:05+08:00",
                    None,
                    "warning",
                    "change_rate",
                    "above",
                    3,
                    3.2,
                    '{"instrument_type":"stock","last_price":339.15}',
                ),
            )

        migrated = MonitoringRepository(database_path)
        rule = migrated.get_rule("rule-1")
        alert = migrated.list_alerts()[0]
        with sqlite3.connect(database_path) as connection:
            version = connection.execute(
                """
                SELECT value FROM repository_metadata
                WHERE key='monitoring_schema_version'
                """
            ).fetchone()[0]
            jobs = connection.execute("SELECT id, payload_json FROM jobs").fetchall()
            experiments = connection.execute(
                "SELECT id, payload_json FROM experiments"
            ).fetchall()

        self.assertEqual(rule["name"], "Apple daily move")
        self.assertEqual(rule["underlying_code"], "US.AAPL")
        self.assertEqual(alert["underlying_code"], "US.AAPL")
        self.assertIsNone(rule["last_observation_key"])
        self.assertEqual(rule["daily_trigger_limit"], 10)
        self.assertEqual(rule["session"], "regular")
        self.assertEqual(rule["trigger_count"], 0)
        self.assertEqual(version, str(MONITORING_SCHEMA_VERSION))
        self.assertEqual(
            jobs,
            [
                (
                    "job-existing",
                    '{"id":"job-existing","status":"succeeded"}',
                )
            ],
        )
        self.assertEqual(
            experiments,
            [
                (
                    "experiment-existing",
                    '{"id":"experiment-existing","status":"succeeded"}',
                )
            ],
        )


def _alert_payload(
    *,
    alert_id: str,
    dedupe_key: str,
    triggered_at: str,
) -> dict[str, object]:
    return {
        "id": alert_id,
        "dedupe_key": dedupe_key,
        "rule_id": "rule-1",
        "rule_name": "Apple daily move",
        "code": "US.AAPL",
        "triggered_at": triggered_at,
        "severity": "warning",
        "metric": "change_rate",
        "operator": "above",
        "threshold": 3,
        "value": 3.2,
        "snapshot": {"last_price": 339.15},
    }


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


def _option_rule_payload() -> dict[str, object]:
    return {
        **_rule_payload(),
        "id": "rule-option",
        "name": "Apple call IV",
        "code": "US.AAPL260731C100000",
        "underlying_code": "US.AAPL",
        "instrument_type": "option",
        "metric": "option_implied_volatility",
        "threshold": 30,
    }


if __name__ == "__main__":
    unittest.main()
