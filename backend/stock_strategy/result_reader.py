from __future__ import annotations

import csv
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any


INITIAL_PRICE_WINDOW = 1_200
MAX_PRICE_WINDOW = 2_000
PRICE_OVERVIEW_POINTS = 1_000
EQUITY_DISPLAY_POINTS = 1_800


def load_result_payload(
    *, project_root: Path, jobs_root: Path, job: dict[str, Any]
) -> dict[str, Any]:
    run_dir = validated_run_dir(jobs_root, job)
    summary = read_summary(run_dir)
    price_count = opend_price_count(project_root, summary)
    price_offset = max(0, price_count - INITIAL_PRICE_WINDOW)
    equity_curve, equity_count = read_downsampled_equity_curve(
        run_dir / "equity_curve.csv", EQUITY_DISPLAY_POINTS
    )
    job_id = str(job["id"])
    return {
        "job": job,
        "summary": summary,
        "price_series": load_opend_price_window(
            project_root, summary, price_offset, INITIAL_PRICE_WINDOW
        ),
        "price_series_offset": price_offset,
        "price_series_count": price_count,
        "price_overview": load_opend_price_overview(
            project_root, summary, PRICE_OVERVIEW_POINTS
        ),
        "trades": read_csv(run_dir / "trades.csv"),
        "equity_curve": equity_curve,
        "equity_curve_count": equity_count,
        "report_url": f"/api/jobs/{job_id}/report.svg",
    }


def load_price_window_payload(
    *,
    project_root: Path,
    jobs_root: Path,
    job: dict[str, Any],
    offset: int,
    limit: int,
) -> dict[str, Any]:
    run_dir = validated_run_dir(jobs_root, job)
    summary = read_summary(run_dir)
    total = opend_price_count(project_root, summary)
    bounded_offset = min(offset, total)
    return {
        "offset": bounded_offset,
        "total": total,
        "points": load_opend_price_window(
            project_root, summary, bounded_offset, limit
        ),
    }


def validated_run_dir(jobs_root: Path, job: dict[str, Any]) -> Path:
    if job["status"] != "succeeded" or not job.get("run_dir"):
        raise RuntimeError("回测结果尚未可用。")
    run_dir = Path(job["run_dir"]).resolve()
    if jobs_root not in run_dir.parents:
        raise RuntimeError("运行目录超出 Web 工作区。")
    return run_dir


def read_summary(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, Any]]:
    resolved = path.resolve()
    return list(_read_csv_cached(str(resolved), resolved.stat().st_mtime_ns))


@lru_cache(maxsize=16)
def _read_csv_cached(
    path_value: str, modified_at: int
) -> tuple[dict[str, Any], ...]:
    del modified_at
    path = Path(path_value)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return tuple(
            {key: _coerce(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
        )


def _resolve_opend_price_source(
    project_root: Path, summary: dict[str, Any]
) -> tuple[Path, str]:
    opend = summary.get("settings", {}).get("opend", {})
    cache_value = opend.get("cache_path")
    if not cache_value:
        raise RuntimeError("回测结果缺少 OpenD 行情缓存路径。")

    cache_path = Path(cache_value).resolve()
    allowed_root = (project_root / "data" / "opend").resolve()
    if allowed_root not in cache_path.parents or not cache_path.is_file():
        raise RuntimeError("OpenD 行情缓存不存在或超出项目数据目录。")
    return cache_path, str(summary.get("symbol", ""))


@lru_cache(maxsize=6)
def _index_opend_price_series(
    cache_value: str, modified_at: int, symbol: str
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Index matching CSV rows by byte offset without retaining parsed OHLCV rows."""
    del modified_at
    cache_path = Path(cache_value)
    offsets: list[int] = []
    with cache_path.open("rb") as handle:
        header_line = handle.readline().decode("utf-8")
        header = tuple(next(csv.reader([header_line])))
        try:
            code_index = header.index("code")
        except ValueError:
            code_index = -1
        symbol_prefix = f"{symbol},".encode() if symbol and code_index == 0 else b""
        while True:
            offset = handle.tell()
            line = handle.readline()
            if not line:
                break
            if symbol_prefix:
                if not line.startswith(symbol_prefix):
                    continue
            elif symbol and code_index >= 0:
                try:
                    values = next(csv.reader([line.decode("utf-8")]))
                except (csv.Error, UnicodeDecodeError):
                    continue
                if code_index >= len(values) or values[code_index] != symbol:
                    continue
            offsets.append(offset)
    return header, tuple(offsets)


def _opend_price_index(
    project_root: Path, summary: dict[str, Any]
) -> tuple[Path, tuple[str, ...], tuple[int, ...]]:
    path, symbol = _resolve_opend_price_source(project_root, summary)
    header, offsets = _index_opend_price_series(
        str(path), path.stat().st_mtime_ns, symbol
    )
    return path, header, offsets


def opend_price_count(project_root: Path, summary: dict[str, Any]) -> int:
    return len(_opend_price_index(project_root, summary)[2])


def load_opend_price_window(
    project_root: Path,
    summary: dict[str, Any],
    offset: int,
    limit: int,
) -> list[dict[str, float | str]]:
    path, header, offsets = _opend_price_index(project_root, summary)
    return _read_opend_price_offsets(path, header, offsets[offset : offset + limit])


def load_opend_price_overview(
    project_root: Path, summary: dict[str, Any], max_points: int
) -> list[dict[str, float | str]]:
    path, header, offsets = _opend_price_index(project_root, summary)
    if len(offsets) <= max_points:
        selected = offsets
    else:
        step = (len(offsets) - 1) / (max_points - 1)
        selected = tuple(offsets[round(index * step)] for index in range(max_points))
    return _read_opend_price_offsets(path, header, selected)


def _read_opend_price_offsets(
    path: Path, header: tuple[str, ...], offsets: tuple[int, ...]
) -> list[dict[str, float | str]]:
    points: list[dict[str, float | str]] = []
    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            try:
                line = handle.readline().decode("utf-8")
                row = dict(zip(header, next(csv.reader([line])), strict=False))
                points.append(
                    {
                        "date": str(row["time_key"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    }
                )
            except (csv.Error, KeyError, TypeError, UnicodeDecodeError, ValueError):
                continue
    return points


def read_downsampled_equity_curve(
    path: Path, max_points: int
) -> tuple[list[dict[str, Any]], int]:
    """Stream the curve while preserving endpoints, equity highs, and drawdown lows."""
    total = _csv_row_count(path)
    if total <= max_points:
        return read_csv(path), total
    bucket_count = max(1, max_points // 4)
    bucket_size = math.ceil(total / bucket_count)
    selected: list[tuple[int, dict[str, Any]]] = []
    bucket_first: tuple[int, dict[str, Any]] | None = None
    bucket_last: tuple[int, dict[str, Any]] | None = None
    bucket_drawdown: tuple[int, dict[str, Any]] | None = None
    bucket_equity: tuple[int, dict[str, Any]] | None = None
    bucket_length = 0

    def flush() -> None:
        nonlocal bucket_first, bucket_last, bucket_drawdown, bucket_equity, bucket_length
        if bucket_first is None:
            return
        selected.extend(
            item
            for item in (bucket_first, bucket_last, bucket_drawdown, bucket_equity)
            if item is not None
        )
        bucket_first = bucket_last = bucket_drawdown = bucket_equity = None
        bucket_length = 0

    with path.open("r", encoding="utf-8", newline="") as handle:
        header = handle.readline().rstrip("\r\n").split(",")
        date_index = header.index("date")
        equity_index = header.index("equity")
        benchmark_index = header.index("benchmark")
        drawdown_index = header.index("drawdown")
        required_index = max(date_index, equity_index, benchmark_index, drawdown_index)
        for index, line in enumerate(handle):
            values = line.rstrip("\r\n").split(",")
            if len(values) <= required_index:
                continue
            try:
                row = {
                    "date": values[date_index],
                    "equity": float(values[equity_index]),
                    "benchmark": float(values[benchmark_index]),
                    "drawdown": float(values[drawdown_index]),
                }
            except ValueError:
                continue
            item = (index, row)
            bucket_first = bucket_first or item
            bucket_last = item
            if bucket_drawdown is None or row["drawdown"] < bucket_drawdown[1]["drawdown"]:
                bucket_drawdown = item
            if bucket_equity is None or row["equity"] > bucket_equity[1]["equity"]:
                bucket_equity = item
            bucket_length += 1
            if bucket_length >= bucket_size:
                flush()
    flush()
    unique = {index: row for index, row in selected}
    return [unique[index] for index in sorted(unique)], total


@lru_cache(maxsize=16)
def _csv_row_count_cached(path_value: str, modified_at: int) -> int:
    del modified_at
    with Path(path_value).open("rb") as handle:
        line_count = sum(
            chunk.count(b"\n")
            for chunk in iter(lambda: handle.read(1024 * 1024), b"")
        )
    return max(0, line_count - 1)


def _csv_row_count(path: Path) -> int:
    resolved = path.resolve()
    return _csv_row_count_cached(str(resolved), resolved.stat().st_mtime_ns)


def _coerce(value: str | None) -> Any:
    if value is None or value == "":
        return value
    try:
        return float(value)
    except ValueError:
        return value
