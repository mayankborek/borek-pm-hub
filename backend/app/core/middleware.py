"""Pure ASGI middleware: request ID, request body size limit, security headers.

Pure ASGI (not BaseHTTPMiddleware), so they also cover responses to unhandled errors.
"""

import uuid
from collections.abc import Callable
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

# Read by the JSON log formatter so every log line carries the request ID.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id(scope: Scope) -> str:
    return str(scope.get("state", {}).get("request_id", ""))


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode()
        # Accept a caller-supplied ID only if it is short and printable; otherwise make one.
        request_id = incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else None
        request_id = request_id or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_ctx.reset(token)


# --- request body size --------------------------------------------------------------------------

JSON_BODY_LIMIT = 1024 * 1024  # 1 MB: far above any JSON this API accepts
MULTIPART_OVERHEAD = 1024 * 1024  # form boundaries and headers around the file


def _too_large() -> HTTPException:
    return HTTPException(413, "The request body is too large.")


class BodySizeLimitMiddleware:
    """Refuse oversized request bodies before the app reads them.

    FastAPI parses the body before it checks the sign-in, so without this an anonymous caller
    could stream a huge upload into memory or temp files. A declared Content-Length over the
    limit is refused at once; a body without one (chunked) is counted while it is read.
    `upload_limit` returns the allowed file size in bytes (read per request, so tests and
    settings changes apply).
    """

    def __init__(self, app: ASGIApp, upload_limit: Callable[[], int]) -> None:
        self.app = app
        self.upload_limit = upload_limit

    def _limit_for(self, scope: Scope) -> int:
        content_type = dict(scope["headers"]).get(b"content-type", b"")
        if content_type.lower().startswith(b"multipart/form-data"):
            return self.upload_limit() + MULTIPART_OVERHEAD
        return JSON_BODY_LIMIT

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > limit
            except ValueError:
                too_large = True
            if too_large:
                from app.core.errors import too_large_response  # avoid an import cycle

                await too_large_response(scope)(scope, receive, send)
                return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised while the route reads the body; becomes the standard 413 response.
                    raise _too_large()
            return message

        await self.app(scope, counting_receive, send)


# --- security headers ---------------------------------------------------------------------------

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# The API only returns JSON and file downloads: nothing may run or be framed.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
# Swagger UI (local/test/staging only) loads its scripts and styles from a CDN.
_DOCS_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = str(scope.get("path", "")).startswith(_DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", _API_CSP)
                    # Task data is private: never keep it in browser or proxy caches.
                    headers.setdefault("Cache-Control", "no-store")
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", "max-age=31536000")
            await send(message)

        await self.app(scope, receive, send_with_headers)
