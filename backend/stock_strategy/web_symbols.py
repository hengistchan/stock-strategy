from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Query

from .api_errors import ApiProblem
from .api_models import (
    SymbolResolveResponse,
    SymbolSearchResponse,
    error_responses,
)
from .opend import OpenDRequestError, OpenDSymbolDirectory, OpenDUnavailableError
from .web_models import SYMBOL_PATTERN


def create_symbols_router(directory: OpenDSymbolDirectory) -> APIRouter:
    router = APIRouter(prefix="/api/symbols", tags=["symbols"])

    @router.get(
        "",
        response_model=SymbolSearchResponse,
        responses=error_responses(422, 503),
    )
    def search_symbols(
        q: str = Query(min_length=1, max_length=80),
        limit: int = Query(default=8, ge=1, le=20),
    ) -> dict[str, Any]:
        try:
            return {"query": q, "symbols": directory.search(q, limit)}
        except (OpenDUnavailableError, OpenDRequestError, OSError) as error:
            raise ApiProblem(
                status_code=503,
                code="opend_symbol_search_unavailable",
                message=f"OpenD 标的搜索暂不可用：{error}",
            ) from error

    @router.get(
        "/resolve",
        response_model=SymbolResolveResponse,
        responses=error_responses(422, 503),
    )
    def resolve_symbols(
        codes: Annotated[list[str], Query(min_length=1)],
    ) -> dict[str, Any]:
        normalized = list(
            dict.fromkeys(code.strip().upper() for code in codes if code.strip())
        )
        if not normalized:
            raise ApiProblem(
                status_code=422,
                code="symbol_codes_required",
                message="至少需要一个标的代码。",
            )
        if len(normalized) > 100:
            raise ApiProblem(
                status_code=422,
                code="too_many_symbol_codes",
                message="单次最多解析 100 个标的代码。",
            )
        invalid = [
            code for code in normalized if re.fullmatch(SYMBOL_PATTERN, code) is None
        ]
        if invalid:
            raise ApiProblem(
                status_code=422,
                code="invalid_symbol_codes",
                message=f"无效的 Futu 标的代码：{', '.join(invalid)}",
                details={"codes": invalid},
            )
        try:
            return {"symbols": directory.resolve(normalized)}
        except (OpenDUnavailableError, OpenDRequestError, OSError) as error:
            raise ApiProblem(
                status_code=503,
                code="opend_symbol_resolve_unavailable",
                message=f"OpenD 标的名称暂不可用：{error}",
            ) from error

    return router
