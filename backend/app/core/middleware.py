"""Request-ID middleware (pure ASGI, so it also covers responses to unhandled errors)."""

import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
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
