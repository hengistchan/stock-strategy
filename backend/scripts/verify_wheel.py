#!/usr/bin/env python3
"""Verify that a wheel contains exactly the current production frontend files."""

import argparse
from pathlib import Path
from zipfile import ZipFile


PACKAGE_PREFIX = "stock_strategy/web_dist/"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", help="Wheel path; defaults to backend/dist/*.whl")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backend_root = Path(__file__).resolve().parents[1]
    wheel_path = _resolve_wheel(args.wheel, backend_root)
    web_root = backend_root / "stock_strategy" / "web_dist"
    expected = {
        path.relative_to(web_root).as_posix()
        for path in web_root.rglob("*")
        if path.is_file()
    }
    if "index.html" not in expected or not any(
        name.startswith("assets/") for name in expected
    ):
        raise SystemExit("production frontend is missing; run the Vite build first")

    with ZipFile(wheel_path) as archive:
        actual = {
            name.removeprefix(PACKAGE_PREFIX)
            for name in archive.namelist()
            if name.startswith(PACKAGE_PREFIX) and not name.endswith("/")
        }

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("stale/unexpected: " + ", ".join(unexpected))
        raise SystemExit(f"wheel frontend mismatch in {wheel_path}: " + "; ".join(details))

    print(f"verified {len(expected)} production frontend files in {wheel_path}")
    return 0


def _resolve_wheel(value: str | None, backend_root: Path) -> Path:
    if value:
        wheel = Path(value).expanduser().resolve()
        if not wheel.is_file():
            raise SystemExit(f"wheel not found: {wheel}")
        return wheel
    wheels = sorted((backend_root / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(
            f"expected exactly one wheel in {backend_root / 'dist'}, found {len(wheels)}"
        )
    return wheels[0]


if __name__ == "__main__":
    raise SystemExit(main())
