from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from stock_strategy.database import STATE_SCHEMA_VERSION
from stock_strategy.monitoring_repository import MonitoringRepository


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
            schema_version = connection.execute(
                "SELECT value FROM repository_metadata WHERE key='schema_version'"
            ).fetchone()[0]

        self.assertEqual(self.repository.journal_mode(), "wal")
        self.assertEqual(schema_version, str(STATE_SCHEMA_VERSION))
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
    }


if __name__ == "__main__":
    unittest.main()
