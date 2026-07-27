import math
import unittest

from stock_strategy.technical_indicators import (
    IndicatorBar,
    closed_bar_closes,
    closed_bar_sma,
    closed_bar_wilder_rsi,
    sma,
    wilder_rsi,
)


class TechnicalIndicatorsTest(unittest.TestCase):
    def test_sma_uses_latest_fixed_window(self) -> None:
        self.assertEqual(sma([1.0, 2.0, 3.0, 4.0, 8.0], period=3), 5.0)

    def test_wilder_rsi_matches_reference_vector(self) -> None:
        closes = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
            46.03,
            46.41,
            46.22,
            45.64,
            46.21,
        ]

        result = wilder_rsi(closes, period=14)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result or 0.0, 62.880718309962404, places=12)

    def test_insufficient_observations_return_none(self) -> None:
        self.assertIsNone(sma([1.0, 2.0], period=3))
        self.assertIsNone(wilder_rsi([1.0, 2.0, 3.0], period=3))

    def test_period_must_be_a_positive_integer(self) -> None:
        for invalid in (0, -1, True):
            with self.subTest(period=invalid):
                with self.assertRaisesRegex(
                    ValueError,
                    "period must be a positive integer",
                ):
                    sma([1.0], period=invalid)
                with self.assertRaisesRegex(
                    ValueError,
                    "period must be a positive integer",
                ):
                    wilder_rsi([1.0, 2.0], period=invalid)

    def test_non_finite_values_are_rejected(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(value=invalid):
                with self.assertRaisesRegex(ValueError, "finite real number"):
                    sma([1.0, invalid], period=2)
                with self.assertRaisesRegex(ValueError, "finite real number"):
                    wilder_rsi([1.0, invalid], period=1)
                with self.assertRaisesRegex(ValueError, "finite real number"):
                    closed_bar_sma(
                        [IndicatorBar(close=invalid, is_closed=True)],
                        period=1,
                    )

    def test_period_one_rsi_has_explicit_directional_semantics(self) -> None:
        self.assertEqual(wilder_rsi([10.0, 11.0], period=1), 100.0)
        self.assertEqual(wilder_rsi([10.0, 9.0], period=1), 0.0)
        self.assertEqual(wilder_rsi([10.0, 10.0], period=1), 50.0)

    def test_rsi_boundaries_for_monotonic_and_flat_series(self) -> None:
        self.assertEqual(wilder_rsi([1.0, 2.0, 3.0, 4.0], period=3), 100.0)
        self.assertEqual(wilder_rsi([4.0, 3.0, 2.0, 1.0], period=3), 0.0)
        self.assertEqual(wilder_rsi([2.0, 2.0, 2.0, 2.0], period=3), 50.0)

    def test_closed_bar_filter_ignores_every_unfinished_bar(self) -> None:
        bars = [
            IndicatorBar(close=1.0, is_closed=True),
            IndicatorBar(close=100.0, is_closed=False),
            IndicatorBar(close=2.0, is_closed=True),
            IndicatorBar(close=-100.0, is_closed=False),
            IndicatorBar(close=3.0, is_closed=True),
        ]

        self.assertEqual(closed_bar_closes(bars), (1.0, 2.0, 3.0))
        self.assertEqual(closed_bar_sma(bars, period=2), 2.5)
        self.assertEqual(closed_bar_wilder_rsi(bars, period=2), 100.0)

    def test_unfinished_last_bar_does_not_change_indicators(self) -> None:
        bars = [
            IndicatorBar(close=1.0, is_closed=True),
            IndicatorBar(close=2.0, is_closed=True),
            IndicatorBar(close=1.0, is_closed=True),
            IndicatorBar(close=2.0, is_closed=True),
            IndicatorBar(close=1_000.0, is_closed=False),
        ]

        self.assertEqual(closed_bar_sma(bars, period=3), 5.0 / 3.0)
        self.assertEqual(closed_bar_wilder_rsi(bars, period=2), 75.0)


if __name__ == "__main__":
    unittest.main()
