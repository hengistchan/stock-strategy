import unittest
from pathlib import Path

from stock_strategy.strategy_parameters import load_parameter_definitions


class DemoStrategyTest(unittest.TestCase):
    def test_exposes_intraday_recovery_experiment(self) -> None:
        strategy = Path(__file__).parents[2] / "strategies" / "demo.py"

        definitions = load_parameter_definitions(strategy)

        self.assertEqual(
            definitions,
            [
                {
                    "name": "min_session_recovery",
                    "label": "日内修复位置",
                    "description": "第二底信号收盘至少回到当日已形成价格区间的位置；0 表示关闭过滤。",
                    "type": "float",
                    "label_i18n": {"en-US": "Intraday recovery level"},
                    "description_i18n": {
                        "en-US": "Minimum close location within the session range formed so far; 0 disables the filter."
                    },
                    "min": 0.0,
                    "max": 0.8,
                    "step": 0.05,
                    "default": 0.5,
                    "candidates": [0.0, 0.5, 0.67],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
