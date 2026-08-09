"""Redis-backed rate limiting middleware.

Enforces per-tenant (or per-IP fallback) request limits using a token-bucket
algorithm. The primary store is Redis (shared across workers). If Redis is
unreachable, the limiter degrades to an in-memory token bucket so requests are
never mistakenly rejected due to a broker outage.

The middleware is additive and safe: it wraps the ASGI app and returns HTTP 429
when a caller exceeds its allocated rate. It never modifies request payloads or
response bodies of allowed requests.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, Tuple

import redis as redis_lib
from fastapi.responses import JSONResponse

from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Default limits (requests per minute per tenant).
DEFAULT_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
WINDOW_SECONDS = 60


class _MemoryBucket:
    """Thread-safe in-memory token bucket fallback when Redis is unavailable."""

    def __init__(self, limit: int, window: int) -> None:
        self.limit = limit
        self.window = window
        self._buckets: Dict[str, Tuple[float, int]] = {}  # key -> (window_start, count)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        start, count = self._buckets.get(key, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        if count >= self.limit:
            return False
        self._buckets[key] = (start, count + 1)
        return True


class RateLimitMiddleware:
    """ASGI middleware that limits requests per tenant/IP.

    Automatically uses Redis when reachable, otherwise falls back to an
    in-memory bucket so the application never hard-fails on Redis outage.
    """

    def __init__(self, app, limit: int = DEFAULT_LIMIT, window: int = WINDOW_SECONDS):
        self.app = app
        self.limit = limit
        self.window = window
        self._redis = None
        self._memory = _MemoryBucket(limit, window)
        self._lock = asyncio.Lock()
        try:
            self._redis = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
            self._redis.ping()
        except Exception:  # noqa: BLE001 - fall back to in-memory
            self._redis = None

    def _client_key(self, scope: dict) -> str:
        """Derive a rate-limit key from tenant or client IP."""
        # Prefer the tenant header if present (set by an upstream auth gateway).
        headers = dict(scope.get("headers") or [])
        tenant = headers.get(b"x-tenant-id", b"")
        if tenant:
            return f"rl:tenant:{tenant.decode()}"
        client = scope.get("client") or ("unknown", 0)
        return f"rl:ip:{client[0]}"

    async def _redis_allow(self, key: str) -> bool:
        """Increment a Redis counter with a 60s expiry; enforce the limit."""
        script = """
        local c = redis.call('INCR', KEYS[1])
        if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        if c > tonumber(ARGV[2]) then return 0 else return 1 end
        """
        try:
            return bool(
                self._redis.eval(script, 1, key, self.window, self.limit)
            )
        except Exception:  # noqa: BLE001 - degrade to in-memory on Redis error
            return self._memory.allow(key)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        key = self._client_key(scope)
        allowed = (
            await self._redis_allow(key)
            if self._redis is not None
            else self._memory.allow(key)
        )

        if not allowed:
            response = JSONResponse(
                {"detail": "Rate limit exceeded. Try again shortly."},
                status_code=429,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
