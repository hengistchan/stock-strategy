from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


CACHE_ID_PATTERN = re.compile(r"^[a-f0-9]{16}$")


class MarketDataCache:
    """Deterministic OpenD history cache shared by single runs and experiments."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.root = (self.project_root / "data" / "opend" / "cache").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def descriptor(self, request: Mapping[str, Any]) -> dict[str, Any]:
        dimensions = {
            "symbol": str(request["symbol"]).upper(),
            "start": str(request["start"]),
            "end": str(request["end"]),
            "ktype": str(request.get("ktype") or "K_DAY"),
            "autype": str(request.get("autype") or "QFQ").upper(),
            "session": str(request.get("session") or "ALL").upper(),
        }
        canonical = json.dumps(dimensions, sort_keys=True, separators=(",", ":"))
        cache_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return {
            "id": cache_id,
            **dimensions,
            "path": self.root / f"{cache_id}.csv",
            "metadata_path": self.root / f"{cache_id}.json",
        }

    def record(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        descriptor = self.descriptor(request)
        path = descriptor["path"]
        if not path.is_file():
            return None
        row_count, first_time, last_time = _inspect_csv(path)
        payload = {
            key: value
            for key, value in descriptor.items()
            if key not in {"path", "metadata_path"}
        }
        payload.update(
            path=str(path.relative_to(self.project_root)),
            bytes=path.stat().st_size,
            rows=row_count,
            first_time=first_time,
            last_time=last_time,
            updated_at=datetime.fromtimestamp(path.stat().st_mtime)
            .astimezone()
            .isoformat(timespec="seconds"),
        )
        _atomic_json_write(descriptor["metadata_path"], payload)
        return payload

    def list(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for metadata_path in self.root.glob("*.json"):
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                cache_id = str(payload["id"])
                path = self.root / f"{cache_id}.csv"
                if not CACHE_ID_PATTERN.fullmatch(cache_id) or not path.is_file():
                    continue
                payload["bytes"] = path.stat().st_size
                entries.append(payload)
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                continue
        return sorted(entries, key=lambda entry: entry.get("updated_at", ""), reverse=True)

    def delete(self, cache_id: str) -> bool:
        if not CACHE_ID_PATTERN.fullmatch(cache_id):
            raise KeyError(cache_id)
        path = (self.root / f"{cache_id}.csv").resolve()
        metadata_path = (self.root / f"{cache_id}.json").resolve()
        if path.parent != self.root or metadata_path.parent != self.root:
            raise KeyError(cache_id)
        existed = path.is_file() or metadata_path.is_file()
        path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        return existed


def _inspect_csv(path: Path) -> tuple[int, str | None, str | None]:
    row_count = 0
    first_time: str | None = None
    last_time: str | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row_count += 1
            timestamp = str(row.get("time_key") or row.get("date") or "").strip()
            if timestamp:
                first_time = first_time or timestamp
                last_time = timestamp
    return row_count, first_time, last_time


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
