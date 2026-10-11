"""Simple in-memory sliding-window rate limiter.

Good enough for a single server instance. Limits reset when the server restarts.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Record a hit for `key`, or raise 429 if the limit is exceeded."""
        now = time.monotonic()
        hits = self.hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(429, "Too many requests. Please wait a moment and try again.")
        hits.append(now)
        if len(self.hits) > 10_000:  # drop idle keys so memory stays bounded
            for k in [k for k, v in self.hits.items() if not v]:
                del self.hits[k]


def client_ip(request: Request) -> str:
    # Behind a hosting proxy (e.g. Render), the client IP is in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
