import unittest

from stock_strategy.market_data_quality import build_market_data_quality_report
from stock_strategy.models import Bar


class MarketDataQualityTest(unittest.TestCase):
    def test_reports_adjustment_gaps_timezone_and_suspicious_jumps(self):
        bars = [
            Bar("2025-01-02", 100, 101, 99, 100, 1_000),
            Bar("2025-01-06", 150, 151, 149, 150, 1_000),
        ]

        report = build_market_data_quality_report(
            bars,
            symbol="US.AAPL",
            bar_type="K_DAY",
            autype="QFQ",
        )

        self.assertEqual(report["timezone"], "America/New_York")
        self.assertTrue(report["corporate_actions_applied"])
        self.assertEqual(report["missing_interval_samples"], ["2025-01-03"])
        self.assertEqual(report["suspicious_price_jumps"][0]["change_pct"], 50)
        self.assertEqual(report["calendar_precision"], "approximate")

    def test_unadjusted_data_does_not_claim_corporate_actions(self):
        bars = [
            Bar("2025-01-02", 100, 101, 99, 100, 1_000),
            Bar("2025-01-03", 101, 102, 100, 101, 1_000),
        ]
        report = build_market_data_quality_report(
            bars,
            symbol="HK.00700",
            bar_type="K_DAY",
            autype="NONE",
        )
        self.assertFalse(report["corporate_actions_applied"])
        self.assertEqual(report["corporate_action_mode"], "unadjusted")


if __name__ == "__main__":
    unittest.main()
