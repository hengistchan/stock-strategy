import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from stock_strategy.market_cache import MarketDataCache


class MarketDataCacheTest(unittest.TestCase):
    def test_cache_key_is_deterministic_and_inventory_can_be_deleted(self):
        request = {
            "symbol": "US.AAPL",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "ktype": "K_DAY",
            "autype": "QFQ",
            "session": "ALL",
        }
        with tempfile.TemporaryDirectory() as directory:
            cache = MarketDataCache(Path(directory), futu_sdk_version="10.6.6608")
            first = cache.descriptor(request)
            second = cache.descriptor(dict(reversed(list(request.items()))))
            self.assertEqual(first["id"], second["id"])

            with first["path"].open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["code", "time_key", "close"]
                )
                writer.writeheader()
                writer.writerow(
                    {"code": "US.AAPL", "time_key": "2024-01-02", "close": 100}
                )
                writer.writerow(
                    {"code": "US.AAPL", "time_key": "2024-01-03", "close": 101}
                )
            entry = cache.record(request)
            inventory = cache.list()

            self.assertEqual(entry["rows"], 2)
            self.assertEqual(entry["cache_schema_version"], 1)
            self.assertEqual(entry["data_adapter_version"], 1)
            self.assertEqual(entry["futu_sdk_version"], "10.6.6608")
            self.assertEqual(
                entry["content_sha256"],
                hashlib.sha256(first["path"].read_bytes()).hexdigest(),
            )
            self.assertEqual(inventory[0]["first_time"], "2024-01-02")
            self.assertTrue(cache.delete(first["id"]))
            self.assertEqual(cache.list(), [])

    def test_cache_identity_changes_with_sdk_and_preserves_legacy_inventory(self):
        request = {
            "symbol": "US.AAPL",
            "start": "2024-01-01",
            "end": "2024-12-31",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            old_sdk = MarketDataCache(root, futu_sdk_version="10.6.1")
            new_sdk = MarketDataCache(root, futu_sdk_version="10.7.0")
            self.assertNotEqual(
                old_sdk.descriptor(request)["id"],
                new_sdk.descriptor(request)["id"],
            )

            legacy_id = "0123456789abcdef"
            legacy_csv = old_sdk.root / f"{legacy_id}.csv"
            legacy_csv.write_text(
                "code,time_key,close\nUS.AAPL,2024-01-02,100\n",
                encoding="utf-8",
            )
            (old_sdk.root / f"{legacy_id}.json").write_text(
                json.dumps(
                    {
                        "id": legacy_id,
                        "symbol": "US.AAPL",
                        "path": str(legacy_csv.relative_to(root)),
                        "updated_at": "2024-01-02T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            inventory = old_sdk.list()

        self.assertEqual(inventory[0]["id"], legacy_id)
        self.assertNotIn("cache_schema_version", inventory[0])


if __name__ == "__main__":
    unittest.main()
