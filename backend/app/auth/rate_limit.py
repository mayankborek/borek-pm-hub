"""In-memory sliding-window limiter for sign-in attempts (per worker process, no extra service).

Each worker keeps its own counts, so with N workers a client gets up to N x the limit. Good
enough to stop password spraying and login floods; a proxy limit (Caddy, nginx, Azure) can be
added on top later.
"""

import ipaddress
import time
from collections import deque

from starlette.requests import Request

_MAX_KEYS = 10_000  # bounds the memory when many different clients call


def _is_internal(value: str) -> bool:
    """Loopback or private address: one of our own proxies (Docker network, host proxy)."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def client_ip(request: Request, trust_proxy_headers: bool) -> str:
    """The visitor's IP.

    Behind our proxies the direct peer is a proxy, so X-Forwarded-For is read from the right
    and the first address that is not one of our proxies wins. The left part of the header
    comes from the client and can be forged, so it is never used.
    """
    peer = request.client.host if request.client else "unknown"
    if not trust_proxy_headers or not _is_internal(peer):
        return peer
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
    for hop in reversed(forwarded):
        if hop and not _is_internal(hop):
            return hop
    return peer


class SlidingWindowLimiter:
    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int) -> int | None:
        """Record one attempt. None = allowed, else seconds until the next attempt is allowed."""
        if limit <= 0:
            return None
        now = time.monotonic()
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= _MAX_KEYS:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(hits[0] + self.window - now) + 1)
        hits.append(now)
        return None

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]
        if len(self._hits) >= _MAX_KEYS:  # still full: start over rather than grow without bound
            self._hits.clear()
