from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Mapping

TRUSTED_EXECUTION_PROFILE = "trusted-local-v2"
RESTRICTED_EXECUTION_PROFILE = "restricted-import-v1"
MAX_CAPTURED_OUTPUT_CHARS = 12_000
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
_INHERITED_ENVIRONMENT_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SYSTEMROOT",
    "TMPDIR",
    "TZ",
)


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    cpu_seconds: int = 300
    address_space_bytes: int = 2 * 1024 * 1024 * 1024
    file_size_bytes: int = 256 * 1024 * 1024
    process_count: int = 32
    open_files: int = 128
    output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES


TRUSTED_LIMITS = ExecutionLimits()
RESTRICTED_LIMITS = ExecutionLimits(
    cpu_seconds=30,
    address_space_bytes=512 * 1024 * 1024,
    file_size_bytes=64 * 1024 * 1024,
    process_count=8,
    open_files=64,
    output_bytes=256 * 1024,
)


def build_strategy_environment(
    backend_root: Path,
    source: Mapping[str, str] | None = None,
    *,
    execution_profile: str = TRUSTED_EXECUTION_PROFILE,
    allowed_write_roots: tuple[Path, ...] = (),
) -> dict[str, str]:
    inherited = source if source is not None else os.environ
    environment = {
        key: inherited[key] for key in _INHERITED_ENVIRONMENT_KEYS if inherited.get(key)
    }
    environment.update(
        PYTHONPATH=str(backend_root.resolve()),
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        STOCK_STRATEGY_EXECUTION_PROFILE=execution_profile,
    )
    if execution_profile == RESTRICTED_EXECUTION_PROFILE:
        environment["STOCK_STRATEGY_NETWORK_DISABLED"] = "1"
        environment["STOCK_STRATEGY_ALLOWED_WRITE_ROOTS"] = os.pathsep.join(
            str(path.resolve()) for path in allowed_write_roots
        )
    return environment


def apply_resource_limits(limits: ExecutionLimits) -> None:
    if os.name != "posix":
        return
    import resource

    resources = (
        ("RLIMIT_CPU", limits.cpu_seconds),
        ("RLIMIT_AS", limits.address_space_bytes),
        ("RLIMIT_FSIZE", limits.file_size_bytes),
        ("RLIMIT_NPROC", limits.process_count),
        ("RLIMIT_NOFILE", limits.open_files),
        ("RLIMIT_CORE", 0),
    )
    for name, value in resources:
        resource_id = getattr(resource, name, None)
        if resource_id is None:
            continue
        _, hard = resource.getrlimit(resource_id)
        bounded = value if hard < 0 else min(value, hard)
        try:
            resource.setrlimit(resource_id, (bounded, bounded))
        except (OSError, ValueError):
            # Darwin exposes RLIMIT_AS/RSS but rejects changing them. Other
            # limits still apply; Linux enforces the full profile.
            continue


def subprocess_isolation_options(
    limits: ExecutionLimits | None = None,
) -> dict[str, Any]:
    if os.name != "posix":
        return {}
    options: dict[str, Any] = {"start_new_session": True}
    if limits is not None:
        options["preexec_fn"] = partial(apply_resource_limits, limits)
    return options


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


class StrategyProcessOutputLimit(RuntimeError):
    pass


class StrategyProcessRunner:
    def __init__(
        self,
        *,
        backend_root: Path,
        working_directory: Path,
        timeout_seconds: int,
        execution_profile: str = TRUSTED_EXECUTION_PROFILE,
        limits: ExecutionLimits | None = None,
    ) -> None:
        self.backend_root = backend_root.resolve()
        self.working_directory = working_directory.resolve()
        self.timeout_seconds = timeout_seconds
        self.execution_profile = execution_profile
        self.limits = limits or (
            RESTRICTED_LIMITS
            if execution_profile == RESTRICTED_EXECUTION_PROFILE
            else TRUSTED_LIMITS
        )
        self._active: dict[str, asyncio.subprocess.Process] = {}

    async def run(
        self,
        job_id: str,
        command: list[str],
        *,
        working_directory: Path | None = None,
        allowed_write_roots: tuple[Path, ...] = (),
    ) -> ProcessOutcome:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str((working_directory or self.working_directory).resolve()),
            env=build_strategy_environment(
                self.backend_root,
                execution_profile=self.execution_profile,
                allowed_write_roots=allowed_write_roots,
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **subprocess_isolation_options(self.limits),
        )
        self._active[job_id] = process
        try:
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    self._communicate(process),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError as error:
                terminate_process_tree(process)
                await process.communicate()
                raise StrategyProcessTimeout(
                    f"回测超过 {self.timeout_seconds} 秒，已终止。"
                ) from error
            except StrategyProcessOutputLimit:
                terminate_process_tree(process)
                await process.communicate()
                raise
        finally:
            self._active.pop(job_id, None)
        if process.returncode is None:
            raise RuntimeError("strategy process finished without a return code")
        return ProcessOutcome(
            returncode=process.returncode,
            stdout=stdout_bytes.decode("utf-8", errors="replace")[
                -MAX_CAPTURED_OUTPUT_CHARS:
            ],
            stderr=stderr_bytes.decode("utf-8", errors="replace")[
                -MAX_CAPTURED_OUTPUT_CHARS:
            ],
        )

    async def _communicate(
        self,
        process: asyncio.subprocess.Process,
    ) -> tuple[bytes, bytes]:
        stdout_stream = getattr(process, "stdout", None)
        stderr_stream = getattr(process, "stderr", None)
        if stdout_stream is None or stderr_stream is None:
            return await process.communicate()
        captured = {"total": 0}

        async def read_stream(
            stream: asyncio.StreamReader,
        ) -> bytes:
            result = bytearray()
            while True:
                chunk = await stream.read(16_384)
                if not chunk:
                    return bytes(result)
                captured["total"] += len(chunk)
                if captured["total"] > self.limits.output_bytes:
                    raise StrategyProcessOutputLimit("策略输出超过限制，进程已终止。")
                result.extend(chunk)

        stdout_task = asyncio.create_task(read_stream(stdout_stream))
        stderr_task = asyncio.create_task(read_stream(stderr_stream))
        wait_task = asyncio.create_task(process.wait())
        tasks = (stdout_task, stderr_task, wait_task)
        try:
            stdout, stderr, _ = await asyncio.gather(*tasks)
            return stdout, stderr
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    def cancel(self, job_id: str) -> bool:
        process = self._active.get(job_id)
        if process is None:
            return False
        terminate_process_tree(process)
        return True
