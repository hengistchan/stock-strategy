from __future__ import annotations

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
    expected = f"v{package_version(Path(__file__).resolve().parents[1] / 'pyproject.toml')}"
    if tag != expected:
        print(f"release tag {tag!r} does not match package version {expected!r}", file=sys.stderr)
        return 1
    print(f"release version verified: {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
