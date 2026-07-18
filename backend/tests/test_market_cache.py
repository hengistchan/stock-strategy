import csv
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
            cache = MarketDataCache(Path(directory))
            first = cache.descriptor(request)
            second = cache.descriptor(dict(reversed(list(request.items()))))
            self.assertEqual(first["id"], second["id"])

            with first["path"].open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["code", "time_key", "close"])
                writer.writeheader()
                writer.writerow({"code": "US.AAPL", "time_key": "2024-01-02", "close": 100})
                writer.writerow({"code": "US.AAPL", "time_key": "2024-01-03", "close": 101})
            entry = cache.record(request)
            inventory = cache.list()

            self.assertEqual(entry["rows"], 2)
            self.assertEqual(inventory[0]["first_time"], "2024-01-02")
            self.assertTrue(cache.delete(first["id"]))
            self.assertEqual(cache.list(), [])


if __name__ == "__main__":
    unittest.main()
