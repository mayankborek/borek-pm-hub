"""One error shape for the whole API: {"error": {code, message, details[]}, "request_id": ...}."""

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
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
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
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


_LOCATION_PREFIXES = ("body", "query", "path", "header", "cookie")


# Rules that span several fields are raised by model validators and have no field in `loc`.
# Their messages start with the field they are about ("due_date must not be before ...").
_LEADING_FIELD = re.compile(r"^([a-z]+(?:_[a-z]+)*) (?:must|and|can) ")


def _field_name(loc: tuple[Any, ...], message: str) -> str:
    parts = [str(part) for part in loc]
    if parts and parts[0] in _LOCATION_PREFIXES:
        parts = parts[1:]
    if not parts and (found := _LEADING_FIELD.match(message)):
        return found.group(1)
    return ".".join(parts)


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        message = str(err["msg"]).removeprefix("Value error, ")
        details.append(
            {"field": _field_name(err["loc"], message), "issue": err["type"], "message": message}
        )
    return error_response(request, 422, "VALIDATION_ERROR", "The request is not valid.", details)


async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """A constraint the services did not catch: report a conflict, never a 500."""
    logger.warning("Integrity error (request_id=%s): %s", get_request_id(request.scope), exc.orig)
    return error_response(
        request, 409, "CONFLICT", "The request conflicts with existing data or its rules."
    )


async def _data_error_handler(request: Request, exc: DataError) -> JSONResponse:
    """A value the database cannot store (too long, out of range, bad characters)."""
    logger.warning("Data error (request_id=%s): %s", get_request_id(request.scope), exc.orig)
    return error_response(request, 422, "VALIDATION_ERROR", "The request is not valid.")


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
    app.add_exception_handler(IntegrityError, _integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DataError, _data_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
