from __future__ import annotations

from datetime import datetime
import io
import json
from pathlib import Path, PurePosixPath
import shutil
from typing import Any, Mapping
import uuid
import zipfile

from .run_manifest import atomic_write_json, canonical_json_bytes, sha256_bytes


EVIDENCE_BUNDLE_SCHEMA_VERSION = 1
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_FILES = 64
REQUIRED_JOB_FILES = {
    "manifest.json",
    "strategy.py",
    "request.json",
    "market-data.csv",
    "market-data-manifest.json",
    "job.json",
}
REQUIRED_OUTPUT_FILES = {
    "summary.json",
    "orders.csv",
    "fills.csv",
    "trades.csv",
    "daily_returns.csv",
    "equity_curve.csv",
    "logs.csv",
    "logs.jsonl",
    "report.html",
    "report.svg",
}


class EvidenceBundleError(ValueError):
    pass


class EvidenceBundleService:
    def __init__(self, project_root: Path, jobs_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.jobs_root = jobs_root.resolve()
        self.exports_root = (self.project_root / "runs" / "exports").resolve()
        self.exports_root.mkdir(parents=True, exist_ok=True)

    def export(self, job: Mapping[str, Any], job_dir: Path, run_dir: Path) -> Path:
        if str(job.get("status")) != "succeeded":
            raise EvidenceBundleError("only succeeded backtests can be exported")
        files = self._verified_export_files(job_dir, run_dir)
        bundle_payload = {
            "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
            "source_job_id": str(job["id"]),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "files": {
                name: {"sha256": sha256_bytes(content), "bytes": len(content)}
                for name, content in sorted(files.items())
            },
        }
        destination = self.exports_root / f"{job['id']}.evidence.zip"
        temporary = destination.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                self._write_zip_entry(
                    archive,
                    "bundle.json",
                    canonical_json_bytes(bundle_payload),
                )
                for name, content in sorted(files.items()):
                    self._write_zip_entry(archive, name, content)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def import_bundle(self, content: bytes) -> dict[str, Any]:
        if not content:
            raise EvidenceBundleError("evidence bundle is empty")
        if len(content) > MAX_BUNDLE_BYTES:
            raise EvidenceBundleError("evidence bundle exceeds the 512 MiB limit")
        files = self._read_and_verify_bundle(content)
        source_job = _load_json(files["job.json"], "job.json")
        request = _load_json(files["request.json"], "request.json")
        manifest = _load_json(files["manifest.json"], "manifest.json")
        source_job_id = str(manifest.get("job_id") or source_job.get("id") or "unknown")
        imported_id = (
            f"imported-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:6]}"
        )
        job_dir = (self.jobs_root / imported_id).resolve()
        if self.jobs_root not in job_dir.parents:
            raise EvidenceBundleError("invalid imported job path")
        staging = (self.jobs_root.parent / f".import-{uuid.uuid4().hex}").resolve()
        run_dir = staging / "output" / "imported"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            for name in ("strategy.py", "request.json", "market-data.csv"):
                (staging / name).write_bytes(files[name])
            for name, payload in files.items():
                if name.startswith("output/"):
                    (run_dir / name.removeprefix("output/")).write_bytes(payload)

            now = datetime.now().astimezone().isoformat(timespec="seconds")
            imported_manifest = dict(manifest)
            imported_manifest.update(
                job_id=imported_id,
                source_job_id=source_job_id,
                status="succeeded",
                imported_at=now,
                execution_profile="imported-evidence-read-only",
            )
            atomic_write_json(staging / "manifest.json", imported_manifest)
            payload = {
                "id": imported_id,
                "status": "succeeded",
                "created_at": now,
                "started_at": source_job.get("started_at"),
                "finished_at": source_job.get("finished_at") or now,
                "request": request,
                "strategy_path": str(
                    manifest.get("strategy_source_path") or "imported/strategy.py"
                ),
                "strategy_revision": manifest.get("strategy_revision"),
                "strategy_snapshot_path": str(
                    (self.jobs_root / imported_id / "strategy.py").relative_to(
                        self.project_root
                    )
                ),
                "market_data_path": str(
                    (self.jobs_root / imported_id / "market-data.csv").relative_to(
                        self.project_root
                    )
                ),
                "execution_profile": "imported-evidence-read-only",
                "retry_of": None,
                "source_job_id": source_job_id,
                "run_dir": str(
                    (self.jobs_root / imported_id / "output" / "imported").resolve()
                ),
                "stdout": "",
                "stderr": "",
                "error": None,
            }
            atomic_write_json(staging / "job.json", payload)
            staging.replace(job_dir)
            return payload
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _verified_export_files(
        self, job_dir: Path, run_dir: Path
    ) -> dict[str, bytes]:
        manifest = _load_json(
            (job_dir / "manifest.json").read_bytes(), "manifest.json"
        )
        files = {
            name: (job_dir / name).read_bytes()
            for name in REQUIRED_JOB_FILES - {"market-data-manifest.json"}
        }
        if sha256_bytes(files["strategy.py"]) != manifest.get("strategy_sha256"):
            raise EvidenceBundleError("strategy snapshot hash does not match manifest")
        if sha256_bytes(files["market-data.csv"]) != manifest.get(
            "market_data_sha256"
        ):
            raise EvidenceBundleError("market-data snapshot hash does not match manifest")
        market_manifest = {
            key: manifest.get(key)
            for key in (
                "market_data_snapshot_path",
                "market_data_sha256",
                "market_data_bytes",
                "market_data_rows",
                "cache_schema_version",
                "data_adapter_version",
                "futu_sdk_version",
            )
        }
        files["market-data-manifest.json"] = canonical_json_bytes(market_manifest)
        artifact_manifest = manifest.get("artifacts")
        if not isinstance(artifact_manifest, dict):
            raise EvidenceBundleError("manifest has no artifact inventory")
        for name in REQUIRED_OUTPUT_FILES:
            path = run_dir / name
            entry = artifact_manifest.get(name)
            if not path.is_file() or not isinstance(entry, dict):
                raise EvidenceBundleError(f"missing evidence artifact: {name}")
            content = path.read_bytes()
            if sha256_bytes(content) != entry.get("sha256"):
                raise EvidenceBundleError(f"artifact hash mismatch: {name}")
            files[f"output/{name}"] = content
        return files

    def _read_and_verify_bundle(self, content: bytes) -> dict[str, bytes]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(content), "r")
        except zipfile.BadZipFile as error:
            raise EvidenceBundleError("invalid evidence ZIP") from error
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_BUNDLE_FILES:
                raise EvidenceBundleError("evidence bundle contains too many files")
            total_size = 0
            names: set[str] = set()
            for info in infos:
                self._validate_entry(info)
                total_size += info.file_size
                if total_size > MAX_BUNDLE_BYTES:
                    raise EvidenceBundleError(
                        "evidence bundle expands beyond the 512 MiB limit"
                    )
                if info.filename in names:
                    raise EvidenceBundleError(
                        f"duplicate evidence entry: {info.filename}"
                    )
                names.add(info.filename)
            if "bundle.json" not in names:
                raise EvidenceBundleError("evidence bundle has no bundle.json")
            bundle = _load_json(archive.read("bundle.json"), "bundle.json")
            if bundle.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
                raise EvidenceBundleError("unsupported evidence bundle schema")
            inventory = bundle.get("files")
            if not isinstance(inventory, dict):
                raise EvidenceBundleError("invalid evidence file inventory")
            if set(inventory) != names - {"bundle.json"}:
                raise EvidenceBundleError("evidence inventory does not match ZIP entries")
            if not REQUIRED_JOB_FILES.issubset(inventory):
                raise EvidenceBundleError("evidence bundle is missing job snapshots")
            if not {
                f"output/{name}" for name in REQUIRED_OUTPUT_FILES
            }.issubset(inventory):
                raise EvidenceBundleError("evidence bundle is missing run artifacts")
            files: dict[str, bytes] = {}
            for name, expected in inventory.items():
                if not isinstance(expected, dict):
                    raise EvidenceBundleError(f"invalid inventory entry: {name}")
                payload = archive.read(name)
                if len(payload) != expected.get("bytes"):
                    raise EvidenceBundleError(f"evidence size mismatch: {name}")
                if sha256_bytes(payload) != expected.get("sha256"):
                    raise EvidenceBundleError(f"evidence hash mismatch: {name}")
                files[name] = payload
            self._verify_internal_manifest(files)
            return files

    @staticmethod
    def _verify_internal_manifest(files: Mapping[str, bytes]) -> None:
        manifest = _load_json(files["manifest.json"], "manifest.json")
        if sha256_bytes(files["strategy.py"]) != manifest.get("strategy_sha256"):
            raise EvidenceBundleError("imported strategy hash does not match manifest")
        if sha256_bytes(files["market-data.csv"]) != manifest.get(
            "market_data_sha256"
        ):
            raise EvidenceBundleError("imported market-data hash does not match manifest")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise EvidenceBundleError("imported manifest has no artifact inventory")
        for name in REQUIRED_OUTPUT_FILES:
            entry = artifacts.get(name)
            if not isinstance(entry, dict):
                raise EvidenceBundleError(f"artifact inventory is missing {name}")
            if sha256_bytes(files[f"output/{name}"]) != entry.get("sha256"):
                raise EvidenceBundleError(f"imported artifact hash mismatch: {name}")

    @staticmethod
    def _validate_entry(info: zipfile.ZipInfo) -> None:
        path = PurePosixPath(info.filename)
        if (
            info.is_dir()
            or info.flag_bits & 0x1
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in info.filename
            or not path.parts
        ):
            raise EvidenceBundleError(f"unsafe evidence entry: {info.filename}")
        file_type = (info.external_attr >> 16) & 0o170000
        if file_type == 0o120000:
            raise EvidenceBundleError(f"symlinks are not allowed: {info.filename}")

    @staticmethod
    def _write_zip_entry(
        archive: zipfile.ZipFile, name: str, content: bytes
    ) -> None:
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100600 << 16
        archive.writestr(info, content)


def _load_json(content: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceBundleError(f"invalid JSON in {label}") from error
    if not isinstance(payload, dict):
        raise EvidenceBundleError(f"{label} must contain a JSON object")
    return payload
