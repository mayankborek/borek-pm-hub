"""Security event log (logger "app.security"): sign-ins, lockouts, rate limits, sign-outs, refusals.

One line per event, `event=<name>` first, so the log can be searched and alerted on. Never logs
passwords or tokens. Unknown emails are logged as a short hash: attempts against the same
address can be linked without writing the address itself into the log.
"""

import hashlib
import logging
import uuid

from starlette.requests import Request

from app.auth.rate_limit import client_ip
from app.core.config import get_settings

logger = logging.getLogger("app.security")


def email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def _clean(value: object) -> str:
    # Values come partly from the client: keep each one a single short token.
    return "".join(c if c.isprintable() and not c.isspace() else "_" for c in str(value))[:120]


def security_event(
    event: str,
    request: Request,
    *,
    level: int = logging.WARNING,
    user_id: uuid.UUID | None = None,
    **fields: object,
) -> None:
    parts = [
        f"event={event}",
        f"ip={_clean(client_ip(request, get_settings().trust_proxy_headers))}",
    ]
    if user_id is not None:
        parts.append(f"user_id={user_id}")
    parts += [f"{name}={_clean(value)}" for name, value in fields.items()]
    parts.append(f"path={_clean(request.method)}:{_clean(request.url.path)}")
    logger.log(level, " ".join(parts))
