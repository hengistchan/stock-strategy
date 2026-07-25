import tempfile
import unittest
from pathlib import Path

from stock_strategy.experiments import ExperimentStore, expand_parameter_grid


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

        self.assertEqual(completed["status"], "succeeded")
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


if __name__ == "__main__":
    unittest.main()
