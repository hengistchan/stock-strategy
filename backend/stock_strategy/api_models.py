from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .web_models import BacktestRequest


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    detail: Any
    error: ErrorBody


def error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    return {
        status_code: {
            "model": ErrorResponse,
            "description": "Structured API error",
        }
        for status_code in status_codes
    }


class OpenDHealth(BaseModel):
    connected: bool
    host: str
    port: int


class HealthResponse(BaseModel):
    status: str
    opend: OpenDHealth


class DiagnosticCheckResponse(BaseModel):
    id: str
    status: Literal["pass", "fail", "blocked"]
    detail: str
    hint: str | None


class DiagnosticsResponse(BaseModel):
    ready: bool
    host: str
    port: int
    checks: list[DiagnosticCheckResponse]


class StrategyMetadata(ApiModel):
    path: str
    name: str
    group: str
    readonly: bool
    revision: str
    size: int
    updated_at: str
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    compatibility: dict[str, Any] = Field(default_factory=dict)


class StrategyDocument(StrategyMetadata):
    content: str


class ConfigResponse(BaseModel):
    strategies: list[StrategyMetadata]
    kline_types: list[str]
    adjustment_types: list[str]
    session_types: list[str]


class SymbolMatch(BaseModel):
    code: str
    name: str
    market: str


class SymbolSearchResponse(BaseModel):
    query: str
    symbols: list[SymbolMatch]


class SymbolResolveResponse(BaseModel):
    symbols: list[SymbolMatch]


class BacktestJob(ApiModel):
    id: str
    status: Literal[
        "queued",
        "running",
        "cancelling",
        "succeeded",
        "failed",
        "cancelled",
    ]
    created_at: str
    started_at: str | None
    finished_at: str | None
    request: BacktestRequest
    strategy_path: str
    strategy_revision: str | None = None
    strategy_snapshot_path: str | None = None
    market_data_path: str | None = None
    execution_profile: str | None = None
    retry_of: str | None = None
    run_dir: str | None
    stdout: str
    stderr: str
    error: str | None


class JobsResponse(BaseModel):
    jobs: list[BacktestJob]


class PricePoint(ApiModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class PriceWindowResponse(BaseModel):
    offset: int
    total: int
    points: list[PricePoint]


class BacktestResultResponse(ApiModel):
    job: BacktestJob
    summary: dict[str, Any]
    price_series: list[PricePoint]
    price_series_offset: int
    price_series_count: int
    price_overview: list[PricePoint]
    trades: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]
    equity_curve_count: int
    report_url: str


class StrategiesResponse(BaseModel):
    strategies: list[StrategyMetadata]


class ExperimentRun(ApiModel):
    index: int
    parameters: dict[str, Any]
    job_id: str | None
    status: str
    metrics: dict[str, Any] | None
    score: float | None
    rank: int | None
    error: str | None


class ExperimentResponse(ApiModel):
    id: str
    name: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    objective: str
    base_request: BacktestRequest
    parameter_grid: dict[str, list[Any]]
    strategy_path: str
    strategy_revision: str | None = None
    strategy_snapshot_path: str | None = None
    progress: dict[str, int]
    runs: list[ExperimentRun]


class ExperimentsResponse(BaseModel):
    experiments: list[ExperimentResponse]


class CacheEntry(ApiModel):
    id: str
    symbol: str
    start: str
    end: str
    ktype: str
    autype: str
    session: str
    path: str
    bytes: int
    rows: int
    first_time: str | None
    last_time: str | None
    updated_at: str
    content_sha256: str | None = None


class CacheResponse(BaseModel):
    entries: list[CacheEntry]
    total_bytes: int


class CacheDeleteResponse(BaseModel):
    deleted: str
