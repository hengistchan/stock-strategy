import os
import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from stock_strategy.strategy_process import (
    TRUSTED_EXECUTION_PROFILE,
    StrategyProcessRunner,
    StrategyProcessTimeout,
    build_strategy_environment,
    subprocess_isolation_options,
    terminate_process_tree,
)


class StrategyProcessTest(unittest.TestCase):
    def test_environment_uses_an_allowlist_and_replaces_pythonpath(self):
        environment = build_strategy_environment(
            Path("/project/backend"),
            {
                "HOME": "/tmp/home",
                "PATH": "/usr/bin",
                "PYTHONPATH": "/untrusted/injection",
                "STRATEGY_LAB_API_TOKEN": "secret-token",
                "AWS_SECRET_ACCESS_KEY": "cloud-secret",
            },
        )

        self.assertEqual(environment["HOME"], "/tmp/home")
        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["PYTHONPATH"], "/project/backend")
        self.assertEqual(
            environment["STOCK_STRATEGY_EXECUTION_PROFILE"],
            TRUSTED_EXECUTION_PROFILE,
        )
        self.assertNotIn("STRATEGY_LAB_API_TOKEN", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)

    def test_posix_process_group_is_terminated_as_one_unit(self):
        process = Mock(pid=1234)
        with patch("stock_strategy.strategy_process.os.name", "posix"):
            with patch(
                "stock_strategy.strategy_process.os.getpgid",
                return_value=4321,
            ):
                with patch("stock_strategy.strategy_process.os.killpg") as killpg:
                    terminate_process_tree(process)

        killpg.assert_called_once()
        process.kill.assert_not_called()

    def test_subprocess_starts_a_new_session_on_posix(self):
        with patch("stock_strategy.strategy_process.os.name", "posix"):
            self.assertEqual(subprocess_isolation_options(), {"start_new_session": True})
        with patch("stock_strategy.strategy_process.os.name", "nt"):
            self.assertEqual(subprocess_isolation_options(), {})


class FakeTimeoutProcess:
    def __init__(self):
        self.pid = None
        self.returncode = -9
        self.communicate_calls = 0
        self.killed = False

    async def communicate(self):
        self.communicate_calls += 1
        if self.communicate_calls == 1:
            await asyncio.Event().wait()
        return b"", b""

    def kill(self):
        self.killed = True


class StrategyProcessRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_terminates_process_and_removes_registration(self):
        process = FakeTimeoutProcess()
        runner = StrategyProcessRunner(
            backend_root=Path("/project/backend"),
            working_directory=Path("/project"),
            timeout_seconds=0.001,
        )
        with patch(
            "stock_strategy.strategy_process.asyncio.create_subprocess_exec",
            return_value=process,
        ):
            with self.assertRaises(StrategyProcessTimeout):
                await runner.run("job-1", ["python", "-V"])

        self.assertTrue(process.killed)
        self.assertEqual(process.communicate_calls, 2)
        self.assertFalse(runner.cancel("job-1"))
