import tempfile
import unittest
from pathlib import Path

from stock_strategy.experiments import (
    ExperimentStore,
    build_walk_forward_windows,
    expand_parameter_grid,
)


class FakeJobStore:
    def __init__(self, root: Path):
        self.root = root
        self.jobs = {}
        self.strategy_sources = []

    def create_job(
        self,
        request,
        strategy_path,
        *,
        strategy_source=None,
        strategy_revision=None,
    ):
        job_id = f"job-{len(self.jobs) + 1}"
        self.strategy_sources.append((strategy_source, strategy_revision))
        self.jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "request": dict(request),
            "strategy_path": str(strategy_path),
        }
        return self.jobs[job_id]

    async def run_job(self, job_id):
        self.jobs[job_id]["status"] = "succeeded"

    def get_job(self, job_id):
        return self.jobs[job_id]

    def load_result(self, job_id):
        fast = self.jobs[job_id]["request"]["parameters"]["fast"]
        return {
            "summary": {
                "metrics": {
                    "total_return_pct": fast * 2,
                    "sharpe_ratio": fast / 10,
                    "max_drawdown_pct": -fast,
                    "total_trades": fast,
                    "total_fees": fast / 10,
                    "exposure_pct": 50,
                }
            }
        }


class PartiallyFailingJobStore(FakeJobStore):
    async def run_job(self, job_id):
        fast = self.jobs[job_id]["request"]["parameters"]["fast"]
        self.jobs[job_id]["status"] = "failed" if fast == 10 else "succeeded"
        if fast == 10:
            self.jobs[job_id]["error"] = "candidate failed"


class WindowAwareJobStore(FakeJobStore):
    def load_result(self, job_id):
        request = self.jobs[job_id]["request"]
        fast = request["parameters"]["fast"]
        year = int(str(request["start"])[:4])
        sharpe = fast / 10 if year == 2022 else -fast / 10
        return {
            "summary": {
                "metrics": {
                    "total_return_pct": sharpe * 5,
                    "sharpe_ratio": sharpe,
                    "max_drawdown_pct": -fast,
                    "total_trades": fast,
                    "total_fees": fast / 10,
                    "exposure_pct": 50,
                }
            }
        }


class BatchJobStore(FakeJobStore):
    def load_result(self, job_id):
        symbol = self.jobs[job_id]["request"]["symbol"]
        score = {"US.AAPL": 2.0, "US.MSFT": 1.0, "US.TSLA": -0.5}[symbol]
        return {
            "summary": {
                "metrics": {
                    "total_return_pct": score * 10,
                    "sharpe_ratio": score,
                    "max_drawdown_pct": -abs(score * 3),
                    "total_trades": 12,
                    "total_fees": 5,
                    "exposure_pct": 50,
                }
            }
        }


class ExperimentsTest(unittest.IsolatedAsyncioTestCase):
    def test_grid_expansion_is_deterministic_and_bounded(self):
        self.assertEqual(
            expand_parameter_grid({"fast": [10, 20], "slow": [40, 60]}),
            [
                {"fast": 10, "slow": 40},
                {"fast": 10, "slow": 60},
                {"fast": 20, "slow": 40},
                {"fast": 20, "slow": 60},
            ],
        )
        with self.assertRaisesRegex(ValueError, "maximum"):
            expand_parameter_grid({"a": list(range(7)), "b": list(range(7))})

    def test_walk_forward_windows_use_only_past_data_for_each_fold(self):
        self.assertEqual(
            build_walk_forward_windows(
                {"start": "2022-01-01", "end": "2022-01-12"},
                2,
            ),
            [
                {
                    "train": {"start": "2022-01-01", "end": "2022-01-04"},
                    "validation": {
                        "start": "2022-01-05",
                        "end": "2022-01-08",
                    },
                },
                {
                    "train": {"start": "2022-01-01", "end": "2022-01-08"},
                    "validation": {
                        "start": "2022-01-09",
                        "end": "2022-01-12",
                    },
                },
            ],
        )

    async def test_experiment_runs_candidates_and_ranks_objective(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            jobs = FakeJobStore(root)
            store = ExperimentStore(root, jobs)
            experiment = store.create(
                name="moving average search",
                base_request={"symbol": "US.AAPL", "parameters": {"slow": 60}},
                parameter_grid={"fast": [10, 20]},
                strategy_path=strategy,
                objective="sharpe_ratio",
            )
            frozen_source = (store._directory(experiment["id"]) / "strategy.py").read_text(
                encoding="utf-8"
            )
            strategy.write_text("class Strategy:\n    version = 2\n", encoding="utf-8")
            await store._run(experiment["id"])
            completed = store.get(experiment["id"])
            (store._directory(experiment["id"]) / "experiment.json").unlink()
            database_copy = store.get(experiment["id"])

        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(database_copy, completed)
        self.assertEqual(completed["progress"], {"completed": 2, "total": 2})
        ranked = sorted(completed["runs"], key=lambda run: run["rank"])
        self.assertEqual(ranked[0]["parameters"], {"fast": 20})
        self.assertEqual(jobs.jobs["job-2"]["request"]["parameters"]["slow"], 60)
        self.assertEqual(frozen_source, "class Strategy: pass")
        self.assertEqual(
            [source for source, _revision in jobs.strategy_sources],
            ["class Strategy: pass", "class Strategy: pass"],
        )
        self.assertTrue(
            all(
                revision == completed["strategy_revision"]
                for _source, revision in jobs.strategy_sources
            )
        )

    async def test_constraints_filter_ranking_and_pareto_marks_tradeoffs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            store = ExperimentStore(root, FakeJobStore(root))
            experiment = store.create(
                name="constrained search",
                base_request={"symbol": "US.AAPL", "parameters": {}},
                parameter_grid={"fast": [10, 20]},
                strategy_path=strategy,
                objective="sharpe_ratio",
                constraints=[
                    {"metric": "max_drawdown_pct", "op": ">=", "value": -15}
                ],
            )

            await store._run(experiment["id"])
            completed = store.get(experiment["id"])

        eligible = next(run for run in completed["runs"] if run["rank"] == 1)
        constrained = next(run for run in completed["runs"] if run["rank"] is None)
        self.assertEqual(eligible["parameters"], {"fast": 10})
        self.assertTrue(eligible["constraints_satisfied"])
        self.assertFalse(constrained["constraints_satisfied"])
        self.assertEqual(
            constrained["constraint_violations"][0]["metric"],
            "max_drawdown_pct",
        )
        self.assertTrue(eligible["pareto_optimal"])

    async def test_batch_validation_runs_symbols_independently_and_aggregates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            jobs = BatchJobStore(root)
            store = ExperimentStore(root, jobs)
            experiment = store.create(
                name="stock pool",
                base_request={"symbol": "US.AAPL", "parameters": {}},
                parameter_grid={},
                strategy_path=strategy,
                objective="sharpe_ratio",
                symbols=["US.AAPL", "US.MSFT", "US.TSLA"],
            )

            await store._run(experiment["id"])
            completed = store.get(experiment["id"])

        self.assertEqual(
            [jobs.jobs[f"job-{index}"]["request"]["symbol"] for index in range(1, 4)],
            ["US.AAPL", "US.MSFT", "US.TSLA"],
        )
        self.assertEqual(completed["kind"], "batch_validation")
        self.assertEqual(completed["research_summary"]["positive_symbol_ratio"], 2 / 3)
        self.assertEqual(completed["research_summary"]["median_return_pct"], 10)
        self.assertEqual(completed["research_summary"]["worst_symbol"], "US.TSLA")

    async def test_experiment_writes_publish_progress_events(self):
        async def connected() -> bool:
            return False

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            store = ExperimentStore(root, FakeJobStore(root))
            stream = store.events.stream(connected)
            await anext(stream)
            experiment = store.create(
                name="event test",
                base_request={"symbol": "US.AAPL"},
                parameter_grid={"fast": [10]},
                strategy_path=strategy,
                objective="sharpe_ratio",
            )
            update = await anext(stream)
            await stream.aclose()

        self.assertIn("event: experiment.updated", update)
        self.assertIn(f'"id":"{experiment["id"]}"', update)
        self.assertIn('"total":1', update)

    async def test_partial_candidate_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            store = ExperimentStore(root, PartiallyFailingJobStore(root))
            experiment = store.create(
                name="partial experiment",
                base_request={"symbol": "US.AAPL", "parameters": {}},
                parameter_grid={"fast": [10, 20]},
                strategy_path=strategy,
                objective="sharpe_ratio",
            )

            await store._run(experiment["id"])
            completed = store.get(experiment["id"])

        self.assertEqual(completed["status"], "completed_with_errors")
        self.assertEqual(
            [run["status"] for run in completed["runs"]],
            ["failed", "succeeded"],
        )

    async def test_validation_selects_parameters_and_test_runs_only_the_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            jobs = WindowAwareJobStore(root)
            store = ExperimentStore(root, jobs)
            experiment = store.create(
                name="out of sample",
                base_request={
                    "symbol": "US.AAPL",
                    "start": "2022-01-01",
                    "end": "2022-12-31",
                    "parameters": {},
                },
                validation_window={"start": "2023-01-01", "end": "2023-12-31"},
                test_window={"start": "2024-01-01", "end": "2024-12-31"},
                parameter_grid={"fast": [10, 20]},
                strategy_path=strategy,
                objective="sharpe_ratio",
            )

            await store._run(experiment["id"])
            completed = store.get(experiment["id"])

        selected = next(run for run in completed["runs"] if run["rank"] == 1)
        self.assertEqual(selected["parameters"], {"fast": 10})
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(len(jobs.jobs), 5)
        self.assertIn("test", selected["phases"])
        self.assertNotIn("test", completed["runs"][1]["phases"])
        self.assertEqual(
            completed["research_summary"]["mode"],
            "train_validation_test",
        )
        self.assertTrue(completed["research_summary"]["out_of_sample"])

    async def test_walk_forward_ranks_aggregate_validation_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy = root / "examples" / "strategy.py"
            strategy.parent.mkdir(parents=True)
            strategy.write_text("class Strategy: pass", encoding="utf-8")
            jobs = WindowAwareJobStore(root)
            store = ExperimentStore(root, jobs)
            experiment = store.create(
                name="walk forward",
                base_request={
                    "symbol": "US.AAPL",
                    "start": "2022-01-01",
                    "end": "2022-12-31",
                    "parameters": {},
                },
                walk_forward_folds=2,
                parameter_grid={"fast": [10, 20]},
                strategy_path=strategy,
                objective="sharpe_ratio",
            )

            await store._run(experiment["id"])
            completed = store.get(experiment["id"])

        selected = next(run for run in completed["runs"] if run["rank"] == 1)
        self.assertEqual(selected["parameters"], {"fast": 20})
        self.assertEqual(len(jobs.jobs), 8)
        self.assertEqual(completed["research_summary"]["mode"], "walk_forward")
        self.assertEqual(
            len(completed["research_summary"]["window_results"]),
            2,
        )
        self.assertEqual(
            completed["research_summary"]["parameter_stability"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
