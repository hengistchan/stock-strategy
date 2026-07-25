from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .opend import OpenDRequestError, OpenDSymbolDirectory, OpenDUnavailableError
from .web_models import SYMBOL_PATTERN


def create_symbols_router(directory: OpenDSymbolDirectory) -> APIRouter:
    router = APIRouter(prefix="/api/symbols", tags=["symbols"])

    @router.get("")
    def search_symbols(
        q: str = Query(min_length=1, max_length=80),
        limit: int = Query(default=8, ge=1, le=20),
    ) -> dict[str, Any]:
        try:
            return {"query": q, "symbols": directory.search(q, limit)}
        except (OpenDUnavailableError, OpenDRequestError, OSError) as error:
            raise HTTPException(
                status_code=503,
                detail=f"OpenD 标的搜索暂不可用：{error}",
            ) from error

    @router.get("/resolve")
    def resolve_symbols(codes: list[str] = Query()) -> dict[str, Any]:
        normalized = list(
            dict.fromkeys(code.strip().upper() for code in codes if code.strip())
        )
        if not normalized:
            raise HTTPException(status_code=422, detail="至少需要一个标的代码。")
        if len(normalized) > 100:
            raise HTTPException(
                status_code=422,
                detail="单次最多解析 100 个标的代码。",
            )
        invalid = [
            code for code in normalized if re.fullmatch(SYMBOL_PATTERN, code) is None
        ]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"无效的 Futu 标的代码：{', '.join(invalid)}",
            )
        try:
            return {"symbols": directory.resolve(normalized)}
        except (OpenDUnavailableError, OpenDRequestError, OSError) as error:
            raise HTTPException(
                status_code=503,
                detail=f"OpenD 标的名称暂不可用：{error}",
            ) from error

    return router
