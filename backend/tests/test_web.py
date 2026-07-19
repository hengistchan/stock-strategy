import tempfile
import unittest
from datetime import date
import json
from pathlib import Path

from fastapi.testclient import TestClient

from stock_strategy.job_store import JobStore, last_error
from stock_strategy.result_reader import read_downsampled_equity_curve
from stock_strategy.web import create_app, list_strategies, resolve_strategy
from stock_strategy.web_models import BacktestRequest


class FakeSymbolDirectory:
    def __init__(self):
        self.requests = []

    def search(self, query, limit):
        self.requests.append((query, limit))
        return [{"code": "US.AAPL", "name": "Apple", "market": "US"}]

    def resolve(self, codes):
        self.requests.append(("resolve", codes))
        return [
            {"code": code, "name": {"US.AAPL": "苹果", "HK.00700": "腾讯控股"}[code], "market": code.split(".")[0]}
            for code in codes
        ]


class WebTest(unittest.TestCase):
    def test_symbol_search_uses_the_opend_directory(self):
        directory = FakeSymbolDirectory()
        app = create_app(
            opend_probe=lambda host, port: True,
            symbol_directory=directory,
        )
        with TestClient(app) as client:
            response = client.get("/api/symbols", params={"q": "appl", "limit": 6})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(directory.requests, [("appl", 6)])
        self.assertEqual(response.json()["symbols"][0]["code"], "US.AAPL")

    def test_symbol_resolver_batches_exact_opend_codes(self):
        directory = FakeSymbolDirectory()
        app = create_app(
            opend_probe=lambda host, port: True,
            symbol_directory=directory,
        )
        with TestClient(app) as client:
            response = client.get(
                "/api/symbols/resolve",
                params=[("codes", "us.aapl"), ("codes", "HK.00700")],
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(directory.requests, [("resolve", ["US.AAPL", "HK.00700"])])
        self.assertEqual(
            [item["name"] for item in response.json()["symbols"]],
            ["苹果", "腾讯控股"],
        )

    def test_equity_display_sampling_preserves_extremes_without_loading_all_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "equity_curve.csv"
            rows = ["date,equity,benchmark,drawdown"]
            for index in range(20):
                equity = 500 if index == 7 else 100 + index
                drawdown = -0.9 if index == 13 else -index / 100
                rows.append(f"2025-01-{index + 1:02d},{equity},{100 + index},{drawdown}")
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            sampled, total = read_downsampled_equity_curve(path, max_points=8)

        self.assertEqual(total, 20)
        self.assertEqual(sampled[0]["date"], "2025-01-01")
        self.assertEqual(sampled[-1]["date"], "2025-01-20")
        self.assertIn(500.0, [row["equity"] for row in sampled])
        self.assertIn(-0.9, [row["drawdown"] for row in sampled])

    def test_failure_summary_prefers_strategy_stderr_over_opend_stdout(self):
        self.assertEqual(
            last_error(
                "回测失败：requested K_DAY, but this backtest contains K_5M bars\n",
                "OpenD disconnected: CallClose\n",
            ),
            "回测失败：requested K_DAY, but this backtest contains K_5M bars",
        )

    def test_home_config_and_health_render(self):
        with tempfile.TemporaryDirectory() as directory:
            frontend_root = Path(directory)
            (frontend_root / "index.html").write_text(
                '<div id="root">Strategy Lab</div>', encoding="utf-8"
            )
            app = create_app(
                opend_probe=lambda host, port: True,
                frontend_root=frontend_root,
            )
            with TestClient(app) as client:
                home = client.get("/")
                experiments_page = client.get("/experiments")
                missing_api = client.get("/api/not-a-route")
                health = client.get("/api/health")
                config = client.get("/api/config")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.headers["cache-control"], "no-cache")
        self.assertIn("Strategy Lab", home.text)
        self.assertIn('id="root"', home.text)
        self.assertEqual(experiments_page.status_code, 200)
        self.assertIn('id="root"', experiments_page.text)
        self.assertEqual(missing_api.status_code, 404)
        self.assertEqual(missing_api.headers["content-type"], "application/json")
        self.assertTrue(health.json()["opend"]["connected"])
        self.assertIn("examples/ma_cross.py", [item["path"] for item in config.json()["strategies"]])
        example = next(item for item in config.json()["strategies"] if item["path"] == "examples/ma_cross.py")
        self.assertTrue(example["readonly"])
        self.assertEqual(len(example["revision"]), 64)
        self.assertEqual(
            [parameter["name"] for parameter in example["parameters"]],
            ["fast_period", "slow_period", "capital_fraction"],
        )
        self.assertEqual(
            example["parameters"][0]["label_i18n"]["en-US"],
            "Fast moving-average period",
        )
        self.assertEqual(config.json()["session_types"], ["ALL", "RTH", "ETH"])

    def test_request_rejects_invalid_symbol_and_date_range(self):
        app = create_app(opend_probe=lambda host, port: True)
        with TestClient(app) as client:
            invalid_symbol = client.post(
                "/api/jobs",
                json={
                    "strategy": "examples/ma_cross.py",
                    "symbol": "AAPL",
                    "start": "2025-01-01",
                    "end": "2025-02-01",
                },
            )
            invalid_range = client.post(
                "/api/jobs",
                json={
                    "strategy": "examples/ma_cross.py",
                    "symbol": "US.AAPL",
                    "start": "2025-02-01",
                    "end": "2025-01-01",
                },
            )
            invalid_session = client.post(
                "/api/jobs",
                json={
                    "strategy": "examples/ma_cross.py",
                    "symbol": "US.AAPL",
                    "start": "2025-01-01",
                    "end": "2025-02-01",
                    "session": "OVERNIGHT",
                },
            )
            unsupported_monthly = client.post(
                "/api/jobs",
                json={
                    "strategy": "examples/ma_cross.py",
                    "symbol": "US.AAPL",
                    "start": "2025-01-01",
                    "end": "2025-02-01",
                    "ktype": "K_MON",
                },
            )
            unknown_parameter = client.post(
                "/api/jobs",
                json={
                    "strategy": "examples/ma_cross.py",
                    "symbol": "US.AAPL",
                    "start": "2025-01-01",
                    "end": "2025-02-01",
                    "parameters": {"not_declared": 10},
                },
            )
            unknown_experiment_parameter = client.post(
                "/api/experiments",
                json={
                    "name": "invalid grid",
                    "base": {
                        "strategy": "examples/ma_cross.py",
                        "symbol": "US.AAPL",
                        "start": "2025-01-01",
                        "end": "2025-02-01",
                    },
                    "parameter_grid": {"not_declared": [10, 20]},
                },
            )
        self.assertEqual(invalid_symbol.status_code, 422)
        self.assertEqual(invalid_range.status_code, 422)
        self.assertEqual(invalid_session.status_code, 422)
        self.assertEqual(unsupported_monthly.status_code, 422)
        self.assertEqual(unknown_parameter.status_code, 422)
        self.assertEqual(unknown_experiment_parameter.status_code, 422)

    def test_non_stock_manual_api_is_blocked_before_a_job_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "strategies" / "multi.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.fast = BarType.K_1M
        self.slow = BarType.K_5M

    def handle_data(self):
        future_previous_settle(self.symbol)
        bar_close(self.symbol, bar_type=self.fast)
        bar_close(self.symbol, bar_type=self.slow)
""",
                encoding="utf-8",
            )
            app = create_app(project_root=root, opend_probe=lambda host, port: True)
            with TestClient(app) as client:
                response = client.post(
                    "/api/jobs",
                    json={
                        "strategy": "strategies/multi.py",
                        "symbol": "US.AAPL",
                        "start": "2025-01-01",
                        "end": "2025-02-01",
                        "ktype": "K_1M",
                    },
                )
                jobs = client.get("/api/jobs").json()["jobs"]

        self.assertEqual(response.status_code, 422)
        self.assertIn("future_previous_settle", response.json()["detail"])
        self.assertEqual(jobs, [])

    def test_multi_period_stock_strategy_selects_smallest_opend_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "strategies" / "multi.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text(
                """
class Strategy(StrategyBase):
    def initialize(self):
        self.symbol = declare_trig_symbol()
        self.fast = BarType.K_1M
        self.slow = BarType.K_15M
        self.session = THType.RTH
    def handle_data(self):
        bar_close(self.symbol, bar_type=self.fast, session_type=self.session)
        bar_close(self.symbol, bar_type=self.slow, session_type=self.session)
""",
                encoding="utf-8",
            )
            app = create_app(project_root=root, opend_probe=lambda host, port: True)
            with TestClient(app) as client:
                config = client.get("/api/config").json()
                response = client.post(
                    "/api/jobs",
                    json={
                        "strategy": "strategies/multi.py",
                        "symbol": "US.AAPL",
                        "start": "2025-01-01",
                        "end": "2025-02-01",
                        "ktype": "K_5M",
                        "session": "RTH",
                    },
                )
        compatibility = next(
            item["compatibility"]
            for item in config["strategies"]
            if item["path"] == "strategies/multi.py"
        )
        self.assertTrue(compatibility["supported"])
        self.assertEqual(compatibility["driver_bar_type"], "K_1M")
        self.assertEqual(compatibility["required_session"], "RTH")
        self.assertEqual(response.status_code, 422)
        self.assertIn("最细周期为 K_1M", response.json()["detail"])

    def test_strategy_paths_stay_inside_allowed_folders(self):
        project_root = Path(__file__).parents[2]
        strategies = list_strategies(project_root)
        self.assertTrue(any(item["path"] == "examples/ma_cross.py" for item in strategies))
        self.assertEqual(
            resolve_strategy(project_root, "examples/ma_cross.py"),
            (project_root / "examples/ma_cross.py").resolve(),
        )
        with self.assertRaisesRegex(ValueError, "策略文件"):
            resolve_strategy(project_root, "backend/stock_strategy/cli.py")

    def test_job_command_uses_only_opend_market_data(self):
        project_root = Path(__file__).parents[2]
        request = BacktestRequest(
            strategy="examples/ma_cross.py",
            symbol="US.AAPL",
            start=date(2024, 1, 1),
            end=date(2025, 12, 31),
            ktype="K_5M",
            autype="HFQ",
            session="RTH",
            liquidate_on_end=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs" / "web").mkdir(parents=True)
            (root / "examples").mkdir()
            strategy = root / "examples" / "ma_cross.py"
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            store = JobStore(root)
            job = store.create_job(request, strategy)
            command = store.build_command(job)
            stored_request = job["request"]
            legacy_job = {**job, "request": dict(job["request"])}
            legacy_job["request"].pop("session")
            legacy_job["request"].pop("liquidate_on_end")
            legacy_command = store.build_command(legacy_job)
        self.assertIn("--opend", command)
        self.assertNotIn("--data", command)
        self.assertIn("--opend-cache", command)
        self.assertIn("--opend-host", command)
        self.assertIn("127.0.0.1", command)
        self.assertEqual(command[command.index("--ktype") + 1], "K_5M")
        self.assertEqual(command[command.index("--autype") + 1], "HFQ")
        self.assertEqual(command[command.index("--session") + 1], "RTH")
        self.assertIn("--liquidate-on-end", command)
        self.assertEqual(stored_request["session"], "RTH")
        self.assertTrue(stored_request["liquidate_on_end"])
        self.assertEqual(legacy_command[legacy_command.index("--session") + 1], "ALL")
        self.assertNotIn("--liquidate-on-end", legacy_command)

    def test_job_command_serializes_parameters_and_shares_market_cache(self):
        request = BacktestRequest(
            strategy="examples/strategy.py",
            symbol="US.AAPL",
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            parameters={"period": 20, "fraction": 0.9},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            store = JobStore(root)
            first = store.build_command(store.create_job(request, strategy))
            second = store.build_command(store.create_job(request, strategy))

        first_cache = first[first.index("--opend-cache") + 1]
        second_cache = second[second.index("--opend-cache") + 1]
        self.assertEqual(first_cache, second_cache)
        self.assertIn("period=20", first)
        self.assertIn("fraction=0.9", first)

    def test_result_returns_sanitized_ohlcv_from_the_job_opend_cache(self):
        request = BacktestRequest(
            strategy="examples/ma_cross.py",
            symbol="US.AAPL",
            start=date(2025, 1, 1),
            end=date(2025, 1, 3),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "ma_cross.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            store = JobStore(root)
            job = store.create_job(request, strategy)
            run_dir = store.root / job["id"] / "output" / "run"
            run_dir.mkdir(parents=True)
            cache_path = root / "data" / "opend" / "web" / "prices.csv"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(
                "code,name,time_key,open,close,high,low,volume,pe_ratio\n"
                "US.AAPL,Apple,2025-01-02 00:00:00,100,102,103,99,1200,30\n"
                "HK.00700,Tencent,2025-01-02 00:00:00,400,405,406,399,900,20\n"
                "US.AAPL,Apple,2025-01-03 00:00:00,102,101,104,100,1500,29\n",
                encoding="utf-8",
            )
            summary = {
                "symbol": "US.AAPL",
                "settings": {"opend": {"cache_path": str(cache_path)}},
            }
            (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (run_dir / "trades.csv").write_text("trade_id,symbol\n", encoding="utf-8")
            (run_dir / "equity_curve.csv").write_text("date,equity\n", encoding="utf-8")
            job.update(status="succeeded", run_dir=str(run_dir))
            store._write_job(job)

            result = store.load_result(job["id"])
            window = store.load_price_window(job["id"], offset=1, limit=1)

        self.assertEqual(len(result["price_series"]), 2)
        self.assertEqual(result["price_series_offset"], 0)
        self.assertEqual(result["price_series_count"], 2)
        self.assertEqual(len(result["price_overview"]), 2)
        self.assertEqual(
            set(result["price_series"][0]),
            {"date", "open", "high", "low", "close", "volume"},
        )
        self.assertEqual(result["price_series"][0]["close"], 102.0)
        self.assertEqual(result["price_series"][1]["volume"], 1500.0)

        self.assertEqual(window["offset"], 1)
        self.assertEqual(window["total"], 2)
        self.assertEqual(window["points"][0]["close"], 101.0)

    def test_strategy_api_creates_reads_and_atomically_saves_user_strategy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = root / "examples" / "ma_cross.py"
            example.parent.mkdir(parents=True)
            example.write_text("class Strategy:\n    pass\n", encoding="utf-8")
            app = create_app(project_root=root, opend_probe=lambda host, port: True)
            with TestClient(app) as client:
                created = client.post(
                    "/api/strategies",
                    json={"name": "my_strategy", "template_path": "examples/ma_cross.py"},
                )
                loaded = client.get("/api/strategies/strategies/my_strategy.py")
                revision = loaded.json()["revision"]
                saved = client.put(
                    "/api/strategies/strategies/my_strategy.py",
                    json={
                        "content": "class Strategy:\n    value = 2\n",
                        "expected_revision": revision,
                    },
                )

            self.assertEqual(created.status_code, 201)
            self.assertFalse(created.json()["readonly"])
            self.assertEqual(loaded.status_code, 200)
            self.assertEqual(saved.status_code, 200)
            self.assertNotEqual(saved.json()["revision"], revision)
            self.assertEqual(
                (root / "strategies" / "my_strategy.py").read_text(encoding="utf-8"),
                "class Strategy:\n    value = 2\n",
            )

    def test_strategy_api_rejects_invalid_source_stale_revision_and_example_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = root / "examples" / "ma_cross.py"
            example.parent.mkdir(parents=True)
            example.write_text("class Strategy:\n    pass\n", encoding="utf-8")
            app = create_app(project_root=root, opend_probe=lambda host, port: True)
            with TestClient(app) as client:
                created = client.post("/api/strategies", json={"name": "guarded"})
                path = created.json()["path"]
                revision = created.json()["revision"]
                invalid = client.put(
                    f"/api/strategies/{path}",
                    json={
                        "content": "class Strategy(:\n    pass\n",
                        "expected_revision": revision,
                    },
                )
                saved = client.put(
                    f"/api/strategies/{path}",
                    json={
                        "content": "class Strategy:\n    value = 1\n",
                        "expected_revision": revision,
                    },
                )
                stale = client.put(
                    f"/api/strategies/{path}",
                    json={
                        "content": "class Strategy:\n    value = 2\n",
                        "expected_revision": revision,
                    },
                )
                readonly = client.put(
                    "/api/strategies/examples/ma_cross.py",
                    json={
                        "content": "class Strategy:\n    value = 3\n",
                        "expected_revision": "0" * 64,
                    },
                )

            self.assertEqual(invalid.status_code, 422)
            self.assertIn("Python 语法错误", invalid.json()["detail"])
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(readonly.status_code, 403)
            self.assertEqual(example.read_text(encoding="utf-8"), "class Strategy:\n    pass\n")


if __name__ == "__main__":
    unittest.main()
