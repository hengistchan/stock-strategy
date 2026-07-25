from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_strategy.web import create_app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the Strategy Lab OpenAPI contract."
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app(opend_probe=lambda _host, _port: False).openapi()
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
