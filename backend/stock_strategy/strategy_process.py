from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import signal
from typing import Any, Mapping


TRUSTED_EXECUTION_PROFILE = "trusted-local-v1"
MAX_CAPTURED_OUTPUT_CHARS = 12_000
_INHERITED_ENVIRONMENT_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SYSTEMROOT",
    "TMPDIR",
    "TZ",
)


def build_strategy_environment(
    backend_root: Path,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    inherited = source if source is not None else os.environ
    environment = {
        key: inherited[key]
        for key in _INHERITED_ENVIRONMENT_KEYS
        if inherited.get(key)
    }
    environment.update(
        PYTHONPATH=str(backend_root.resolve()),
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        STOCK_STRATEGY_EXECUTION_PROFILE=TRUSTED_EXECUTION_PROFILE,
    )
    return environment


def subprocess_isolation_options() -> dict[str, Any]:
    return {"start_new_session": True} if os.name == "posix" else {}


def terminate_process_tree(process: Any) -> None:
    pid = getattr(process, "pid", None)
    if os.name == "posix" and isinstance(pid, int):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    process.kill()


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str


class StrategyProcessTimeout(TimeoutError):
    pass


class StrategyProcessRunner:
    def __init__(
        self,
        *,
        backend_root: Path,
        working_directory: Path,
        timeout_seconds: int,
    ) -> None:
        self.backend_root = backend_root.resolve()
        self.working_directory = working_directory.resolve()
        self.timeout_seconds = timeout_seconds
        self._active: dict[str, asyncio.subprocess.Process] = {}

    async def run(self, job_id: str, command: list[str]) -> ProcessOutcome:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(self.working_directory),
            env=build_strategy_environment(self.backend_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **subprocess_isolation_options(),
        )
        self._active[job_id] = process
        try:
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError as error:
                terminate_process_tree(process)
                await process.communicate()
                raise StrategyProcessTimeout(
                    f"回测超过 {self.timeout_seconds} 秒，已终止。"
                ) from error
        finally:
            self._active.pop(job_id, None)
        return ProcessOutcome(
            returncode=int(process.returncode),
            stdout=stdout_bytes.decode("utf-8", errors="replace")[
                -MAX_CAPTURED_OUTPUT_CHARS:
            ],
            stderr=stderr_bytes.decode("utf-8", errors="replace")[
                -MAX_CAPTURED_OUTPUT_CHARS:
            ],
        )

    def cancel(self, job_id: str) -> bool:
        process = self._active.get(job_id)
        if process is None:
            return False
        terminate_process_tree(process)
        return True
