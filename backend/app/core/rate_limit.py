"""In-process sliding-window rate limiter for login, register, chat and upload.

Deliberately dependency-free so the app runs without Redis. The `RateLimiter`
interface is the seam to swap in a Redis//`slowapi` backend for multi-worker
deployments -- see `RedisRateLimiter` notes in the README.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request, status

from app.core.config import settings


def parse_rule(rule: str) -> tuple[int, int]:
    """Parse a "limit/window_seconds" rule, e.g. "10/60"."""
    try:
        limit_str, window_str = rule.split("/", 1)
        return int(limit_str), int(window_str)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid rate limit rule: {rule!r}. Expected 'limit/seconds'.") from exc


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window counter."""

    def __init__(self) -> None:
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] + window_seconds - now) + 1)
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


limiter = SlidingWindowRateLimiter()


def client_identifier(request: Request) -> str:
    """The client's address, as resolved by the ASGI server.

    X-Forwarded-For is deliberately not read here: any caller can send that
    header, and trusting it would let a client dodge rate limits by varying it.
    Behind a reverse proxy, run uvicorn with --proxy-headers so request.client
    already holds the real address (the Docker setup does this, and its nginx
    overwrites the header rather than appending to a client-supplied one).
    """
    return request.client.host if request.client else "unknown"


class RateLimit:
    """FastAPI dependency enforcing one named rule."""

    def __init__(self, rule: str, scope: str):
        self.limit, self.window = parse_rule(rule)
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        key = f"{self.scope}:{client_identifier(request)}"
        allowed, retry_after = limiter.check(key, self.limit, self.window)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many requests. Limit is {self.limit} per {self.window} seconds. "
                    f"Try again in {retry_after} seconds."
                ),
                headers={"Retry-After": str(retry_after)},
            )


login_rate_limit = RateLimit(settings.RATE_LIMIT_LOGIN, "login")
register_rate_limit = RateLimit(settings.RATE_LIMIT_REGISTER, "register")
chat_rate_limit = RateLimit(settings.RATE_LIMIT_CHAT, "chat")
upload_rate_limit = RateLimit(settings.RATE_LIMIT_UPLOAD, "upload")
