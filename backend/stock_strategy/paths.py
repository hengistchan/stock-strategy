from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = Path(__file__).resolve().parent / "web_dist"


def discover_project_root() -> Path:
    configured = os.environ.get("STOCK_STRATEGY_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = (BACKEND_ROOT.parent, Path.cwd(), *Path.cwd().parents)
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "examples").is_dir() and (resolved / "strategies").is_dir():
            return resolved
    return Path.cwd().resolve()


PROJECT_ROOT = discover_project_root()
