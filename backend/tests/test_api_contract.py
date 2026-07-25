from __future__ import annotations

import unittest

from stock_strategy.web import create_app


class ApiContractTest(unittest.TestCase):
    def test_openapi_describes_success_and_structured_error_contracts(self):
        schema = create_app(opend_probe=lambda _host, _port: False).openapi()

        self.assertEqual(schema["servers"], [{"url": "/"}])
        self.assertEqual(
            schema["paths"]["/api/jobs"]["post"]["responses"]["202"]["content"][
                "application/json"
            ]["schema"]["$ref"],
            "#/components/schemas/BacktestJob",
        )
        self.assertEqual(
            schema["paths"]["/api/jobs"]["post"]["responses"]["422"]["content"][
                "application/json"
            ]["schema"]["$ref"],
            "#/components/schemas/ErrorResponse",
        )
        self.assertIn("BacktestRequest", schema["components"]["schemas"])
        self.assertIn("ExperimentResponse", schema["components"]["schemas"])
        self.assertIn("StrategyDocument", schema["components"]["schemas"])
        self.assertIn("CacheResponse", schema["components"]["schemas"])
        self.assertIn("/api/migrations/scan", schema["paths"])
        self.assertIn("/api/migrations/fixture", schema["paths"])
        self.assertIn("/api/migrations/import", schema["paths"])


if __name__ == "__main__":
    unittest.main()
