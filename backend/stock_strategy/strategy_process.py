from __future__ import annotations

import os
from pathlib import Path
import signal
from typing import Any, Mapping


TRUSTED_EXECUTION_PROFILE = "trusted-local-v1"
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
