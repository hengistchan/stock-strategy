import unittest

from stock_strategy.strategy_parameters import (
    StrategyParameterError,
    extract_parameter_definitions,
    parse_parameter_assignment,
    resolve_parameter_values,
)


SOURCE = '''
STRATEGY_PARAMETERS = {
    "period": {
        "label": "周期",
        "type": "int",
        "default": 20,
        "min": 2,
        "max": 120,
        "candidates": [10, 20, 40],
    },
    "fraction": {
        "type": "float",
        "default": 0.9,
        "min": 0.1,
        "max": 1.0,
    },
}
'''


class StrategyParametersTest(unittest.TestCase):
    def test_literal_schema_is_normalized_and_values_are_resolved(self):
        definitions = extract_parameter_definitions(SOURCE)
        values = resolve_parameter_values(definitions, {"period": 40})

        self.assertEqual([item["name"] for item in definitions], ["period", "fraction"])
        self.assertEqual(definitions[0]["candidates"], [10, 20, 40])
        self.assertEqual(values, {"period": 40, "fraction": 0.9})

    def test_dynamic_schema_and_unknown_or_out_of_range_values_are_rejected(self):
        with self.assertRaisesRegex(StrategyParameterError, "literal dictionary"):
            extract_parameter_definitions("STRATEGY_PARAMETERS = dict(period={})")

        definitions = extract_parameter_definitions(SOURCE)
        with self.assertRaisesRegex(StrategyParameterError, "unknown"):
            resolve_parameter_values(definitions, {"missing": 1})
        with self.assertRaisesRegex(StrategyParameterError, ">= 2"):
            resolve_parameter_values(definitions, {"period": 1})

    def test_cli_assignment_uses_json_scalars(self):
        self.assertEqual(parse_parameter_assignment("period=30"), ("period", 30))
        self.assertEqual(parse_parameter_assignment("enabled=true"), ("enabled", True))
        self.assertEqual(parse_parameter_assignment("name=trend"), ("name", "trend"))


if __name__ == "__main__":
    unittest.main()
