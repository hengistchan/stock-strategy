from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .api_errors import ApiProblem
from .api_models import BacktestJob, error_responses
from .evidence_bundle import EvidenceBundleError, MAX_BUNDLE_BYTES
from .job_store import JobStore


def create_evidence_router(store: JobStore) -> APIRouter:
    router = APIRouter(prefix="/api/evidence", tags=["evidence"])

    @router.get(
        "/{job_id}.zip",
        responses=error_responses(404, 409),
    )
    async def export_evidence(job_id: str) -> FileResponse:
        try:
            path = store.evidence_bundle_path(job_id)
            return FileResponse(
                path,
                media_type="application/zip",
                filename=path.name,
            )
        except KeyError as error:
            raise ApiProblem(
                status_code=404,
                code="backtest_not_found",
                message="找不到这次回测。",
            ) from error
        except (RuntimeError, EvidenceBundleError, OSError) as error:
            raise ApiProblem(
                status_code=409,
                code="evidence_export_unavailable",
                message=str(error),
            ) from error

    @router.post(
        "/import",
        status_code=201,
        response_model=BacktestJob,
        responses=error_responses(413, 422),
    )
    async def import_evidence(request: Request) -> dict[str, object]:
        declared_size = request.headers.get("content-length")
        try:
            too_large = bool(
                declared_size and int(declared_size) > MAX_BUNDLE_BYTES
            )
        except ValueError:
            too_large = False
        if too_large:
            raise ApiProblem(
                status_code=413,
                code="evidence_bundle_too_large",
                message="证据包不能超过 512 MiB。",
            )
        content = await request.body()
        try:
            return store.import_evidence_bundle(content)
        except EvidenceBundleError as error:
            raise ApiProblem(
                status_code=422,
                code="invalid_evidence_bundle",
                message=str(error),
            ) from error

    return router
