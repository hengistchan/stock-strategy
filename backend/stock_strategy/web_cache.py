from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .api_errors import ApiProblem
from .job_store import JobStore


def create_cache_router(store: JobStore) -> APIRouter:
    router = APIRouter(prefix="/api/cache", tags=["market-data-cache"])

    @router.get("")
    async def list_cache() -> dict[str, Any]:
        entries = store.cache.list()
        return {
            "entries": entries,
            "total_bytes": sum(entry.get("bytes", 0) for entry in entries),
        }

    @router.delete("/{cache_id}")
    async def delete_cache(cache_id: str) -> dict[str, Any]:
        try:
            deleted = store.cache.delete(cache_id)
        except KeyError as error:
            raise ApiProblem(
                status_code=404,
                code="market_cache_not_found",
                message="找不到这份 OpenD 缓存。",
            ) from error
        if not deleted:
            raise ApiProblem(
                status_code=404,
                code="market_cache_not_found",
                message="找不到这份 OpenD 缓存。",
            )
        return {"deleted": cache_id}

    return router
