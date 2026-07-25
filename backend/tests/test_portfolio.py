import unittest

from stock_strategy.models import Bar
from stock_strategy.portfolio import PortfolioConfig, run_portfolio


def bars(base: float, count: int = 30) -> list[Bar]:
    return [
        Bar(
            date=f"2025-01-{index + 1:02d}",
            open=base + index,
            high=base + index + 1,
            low=base + index - 1,
            close=base + index + 0.5,
            volume=1_000,
        )
        for index in range(count)
    ]


class PortfolioTest(unittest.TestCase):
    def test_shared_cash_portfolio_rebalances_on_one_unified_clock(self):
        config = PortfolioConfig(
            weights={"US.AAPL": 0.6, "US.MSFT": 0.4},
            start="2025-01-01",
            end="2025-01-30",
            initial_cash=10_000,
            commission_bps=0,
            min_commission=0,
            slippage_bps=0,
            rebalance="buy_and_hold",
        )

        result = run_portfolio(
            config,
            {"US.AAPL": bars(100), "US.MSFT": bars(200)},
        )

        self.assertTrue(result["engine_contract"]["shared_cash"])
        self.assertEqual(result["period"]["bars"], 30)
        self.assertGreaterEqual(result["cash"], 0)
        self.assertEqual(
            result["cash"]
            + sum(position["market_value"] for position in result["positions"]),
            result["equity_curve"][-1]["equity"],
        )
        self.assertEqual(
            {transaction["symbol"] for transaction in result["transactions"]},
            {"US.AAPL", "US.MSFT"},
        )

    def test_mixed_currency_portfolio_is_rejected_without_fx(self):
        with self.assertRaisesRegex(ValueError, "market and currency"):
            PortfolioConfig(
                weights={"US.AAPL": 0.5, "HK.00700": 0.5},
                start="2025-01-01",
                end="2025-02-01",
            )


if __name__ == "__main__":
    unittest.main()
