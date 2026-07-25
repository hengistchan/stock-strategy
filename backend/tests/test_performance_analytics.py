import unittest

from stock_strategy.models import DailyReturn, EquityPoint, Trade
from stock_strategy.performance_analytics import (
    build_performance_analysis,
    max_consecutive_losses,
    max_drawdown_duration_days,
)


class PerformanceAnalyticsTest(unittest.TestCase):
    def test_builds_distributions_period_returns_and_rolling_windows(self):
        equity = 100_000.0
        benchmark = 100_000.0
        curve = []
        daily = []
        for day in range(1, 31):
            daily_return = 0.01 if day % 3 else -0.015
            benchmark_return = 0.004 if day % 2 else -0.002
            equity *= 1 + daily_return
            benchmark *= 1 + benchmark_return
            curve.append(
                EquityPoint(
                    f"2025-01-{day:02d}",
                    equity,
                    benchmark,
                    min(0.0, equity / 105_000 - 1),
                )
            )
            daily.append(
                DailyReturn(
                    f"2025-01-{day:02d}", equity, daily_return * 100
                )
            )

        analysis = build_performance_analysis(
            equity_curve=curve,
            daily_returns=daily,
            trades=[],
            symbol="US.TEST",
            initial_cash=100_000,
        )

        self.assertEqual(analysis["return_distribution"]["count"], 30)
        self.assertLess(
            analysis["return_distribution"]["p10"],
            analysis["return_distribution"]["p90"],
        )
        self.assertEqual(analysis["monthly_returns"][0]["period"], "2025-01")
        self.assertEqual(analysis["yearly_returns"][0]["period"], "2025")
        self.assertEqual(len(analysis["rolling"]), 11)
        self.assertEqual(
            {row["bucket"] for row in analysis["attribution"]["market_regime"]},
            {"up", "down"},
        )

    def test_loss_streak_and_drawdown_duration_are_sequence_aware(self):
        trades = [
            self._trade(10),
            self._trade(-2),
            self._trade(-3),
            self._trade(1),
            self._trade(-1),
        ]
        curve = [
            EquityPoint("2025-01-01", 100, 100, 0),
            EquityPoint("2025-01-02", 99, 100, -0.01),
            EquityPoint("2025-01-03", 98, 100, -0.02),
            EquityPoint("2025-01-04", 101, 100, 0),
            EquityPoint("2025-01-05", 100, 100, -0.01),
        ]

        self.assertEqual(max_consecutive_losses(trades), 2)
        self.assertEqual(max_drawdown_duration_days(curve), 2)

    @staticmethod
    def _trade(net_pnl: float) -> Trade:
        return Trade(
            trade_id=1,
            symbol="US.TEST",
            side="LONG",
            entry_date="2025-01-01",
            exit_date="2025-01-02",
            entry_price=100,
            exit_price=101,
            quantity=1,
            gross_pnl=net_pnl,
            fees=0,
            net_pnl=net_pnl,
            return_pct=net_pnl,
            bars_held=1,
            exit_reason="signal",
        )


if __name__ == "__main__":
    unittest.main()
