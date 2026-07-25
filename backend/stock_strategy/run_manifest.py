from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
from typing import Any, Mapping

from . import __version__
from .market_cache import CACHE_SCHEMA_VERSION, DATA_ADAPTER_VERSION
from .runtime import ENGINE_CONTRACT_VERSION
from .strategy_process import TRUSTED_EXECUTION_PROFILE


RUN_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class StrategySnapshot:
    source_path: str
    content: str
    revision: str

    @classmethod
    def create(
        cls,
        *,
        source_path: str,
        content: str,
        revision: str | None = None,
    ) -> StrategySnapshot:
        digest = sha256_bytes(content.encode("utf-8"))
        if revision is not None and revision != digest:
            raise ValueError("strategy revision does not match the supplied source")
        return cls(source_path=source_path, content=content, revision=digest)


def create_run_manifest(
    *,
    job_id: str,
    created_at: str,
    request: Mapping[str, Any],
    strategy: StrategySnapshot,
    futu_sdk_version: str,
) -> dict[str, Any]:
    request_bytes = canonical_json_bytes(request)
    return {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "job_id": job_id,
        "status": "queued",
        "created_at": created_at,
        "started_at": None,
        "finished_at": None,
        "application_version": __version__,
        "python_version": platform.python_version(),
        "futu_sdk_version": futu_sdk_version,
        "engine_contract_version": ENGINE_CONTRACT_VERSION,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "data_adapter_version": DATA_ADAPTER_VERSION,
        "execution_profile": TRUSTED_EXECUTION_PROFILE,
        "request_sha256": sha256_bytes(request_bytes),
        "strategy_source_path": strategy.source_path,
        "strategy_snapshot_path": "strategy.py",
        "strategy_revision": strategy.revision,
        "strategy_sha256": strategy.revision,
        "market_data_snapshot_path": None,
        "market_data_sha256": None,
        "market_data_bytes": None,
        "market_data_rows": None,
        "artifacts": {},
    }


def update_run_manifest(
    path: Path,
    *,
    status: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    market_data: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if status is not None:
        payload["status"] = status
    if started_at is not None:
        payload["started_at"] = started_at
    if finished_at is not None:
        payload["finished_at"] = finished_at
    if market_data is not None:
        payload.update(
            market_data_snapshot_path="market-data.csv",
            market_data_sha256=market_data["content_sha256"],
            market_data_bytes=market_data["bytes"],
            market_data_rows=market_data["rows"],
        )
    if artifacts is not None:
        payload["artifacts"] = dict(artifacts)
    atomic_write_json(path, payload)
    return payload


def artifact_inventory(run_dir: Path, job_dir: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(run_dir.iterdir()):
        if not path.is_file():
            continue
        inventory[path.name] = {
            "path": str(path.relative_to(job_dir)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return inventory


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
