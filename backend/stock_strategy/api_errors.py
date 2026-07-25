from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiProblem(HTTPException):
    """An HTTP error with a stable code and optional machine-readable details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details


def error_payload(
    *,
    code: str,
    message: str,
    detail: Any | None = None,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "detail": message if detail is None else detail,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def install_api_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def handle_api_problem(
        _request: Request,
        error: ApiProblem,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=jsonable_encoder(
                error_payload(
                    code=error.code,
                    message=error.message,
                    details=error.details,
                )
            ),
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        details = error.errors()
        message = "；".join(str(item.get("msg", "Invalid request")) for item in details)
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                error_payload(
                    code="request_validation_error",
                    message=message,
                    detail=details,
                    details=details,
                )
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        _request: Request,
        error: HTTPException,
    ) -> JSONResponse:
        message = _message_from_detail(error.detail)
        return JSONResponse(
            status_code=error.status_code,
            content=jsonable_encoder(
                error_payload(
                    code=_default_error_code(error.status_code),
                    message=message,
                    detail=error.detail,
                )
            ),
            headers=error.headers,
        )


def _message_from_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return "；".join(
            str(item.get("msg", item)) if isinstance(item, dict) else str(item)
            for item in detail
        )
    return str(detail)


def _default_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "authentication_required",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "unprocessable_request",
        503: "service_unavailable",
    }.get(status_code, "http_error")
