"""One error shape for the whole API: {"error": {code, message, details[]}, "request_id": ...}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import get_request_id

logger = logging.getLogger("app.errors")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    """Raise this from services; it becomes the standard error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body = {
        "error": {"code": code, "message": message, "details": details or []},
        "request_id": get_request_id(request.scope),
    }
    return JSONResponse(status_code=status_code, content=body)


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    return error_response(request, exc.status_code, code, str(exc.detail))


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in err["loc"] if part not in ("body", "query")),
            "issue": err["type"],
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return error_response(request, 422, "VALIDATION_ERROR", "The request is not valid.", details)


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the real cause with the request ID; never leak internals to the client.
    logger.error(
        "Unhandled error (request_id=%s)",
        get_request_id(request.scope),
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
