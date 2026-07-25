from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .strategy_process import RESTRICTED_EXECUTION_PROFILE

_NETWORK_EVENTS = {
    "socket.__new__",
    "socket.bind",
    "socket.connect",
    "socket.getaddrinfo",
    "socket.gethostbyaddr",
    "socket.gethostbyname",
}
_PROCESS_EVENTS = {
    "os.exec",
    "os.fork",
    "os.forkpty",
    "os.posix_spawn",
    "os.spawn",
    "os.system",
    "subprocess.Popen",
}
_WRITE_EVENTS = {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.symlink"}


def install_restricted_runtime() -> bool:
    if (
        os.environ.get("STOCK_STRATEGY_EXECUTION_PROFILE")
        != RESTRICTED_EXECUTION_PROFILE
    ):
        return False
    roots = tuple(
        Path(value).resolve()
        for value in os.environ.get("STOCK_STRATEGY_ALLOWED_WRITE_ROOTS", "").split(
            os.pathsep
        )
        if value
    )
    sys.addaudithook(lambda event, args: restricted_audit(event, args, roots))
    return True


def restricted_audit(
    event: str,
    args: tuple[Any, ...],
    allowed_write_roots: tuple[Path, ...],
) -> None:
    if event in _NETWORK_EVENTS:
        raise PermissionError("Network access is disabled in restricted mode.")
    if event in _PROCESS_EVENTS or event == "ctypes.dlopen":
        raise PermissionError(
            "Process creation and native library loading are disabled in restricted mode."
        )
    if event == "open" and _open_is_write(args):
        _require_allowed(args[0], allowed_write_roots)
    elif event in _WRITE_EVENTS and args:
        _require_allowed(args[0], allowed_write_roots)
        if event == "os.rename" and len(args) > 1:
            _require_allowed(args[1], allowed_write_roots)


def _open_is_write(args: tuple[Any, ...]) -> bool:
    if len(args) < 2:
        return False
    mode = args[1]
    if isinstance(mode, str):
        return any(flag in mode for flag in ("w", "a", "x", "+"))
    if isinstance(mode, int):
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        return bool(mode & write_flags)
    return False


def _require_allowed(
    raw_path: Any,
    allowed_write_roots: tuple[Path, ...],
) -> None:
    if isinstance(raw_path, int):
        return
    path = Path(os.fsdecode(raw_path)).resolve()
    if any(path == root or root in path.parents for root in allowed_write_roots):
        return
    raise PermissionError(f"Write access outside the run directory is disabled: {path}")
