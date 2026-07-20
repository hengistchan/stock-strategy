from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


def package_version(project_file: Path) -> str:
    with project_file.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    if len(arguments) != 1:
        print("usage: verify_release_version.py vX.Y.Z", file=sys.stderr)
        return 2
    tag = arguments[0]
    project_root = Path(__file__).resolve().parents[2]
    versions = {
        "backend/pyproject.toml": package_version(project_root / "backend" / "pyproject.toml"),
        "frontend/package.json": str(
            json.loads((project_root / "frontend" / "package.json").read_text(encoding="utf-8"))["version"]
        ),
        "backend/stock_strategy/__init__.py": source_version(
            project_root / "backend" / "stock_strategy" / "__init__.py"
        ),
    }
    if len(set(versions.values())) != 1:
        print("release versions are not aligned:", file=sys.stderr)
        for path, version_value in versions.items():
            print(f"  {path}: {version_value}", file=sys.stderr)
        return 1
    expected = f"v{next(iter(versions.values()))}"
    if tag != expected:
        print(f"release tag {tag!r} does not match package version {expected!r}", file=sys.stderr)
        return 1
    print(f"release version verified: {tag}")
    return 0


def source_version(path: Path) -> str:
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']',
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"missing __version__ in {path}")
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())
