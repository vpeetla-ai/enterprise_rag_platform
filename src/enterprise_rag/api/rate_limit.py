"""Simple in-process sliding-window rate limiter (Phase 4)."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Per-key request counts over a rolling window (single-process)."""

    def __init__(self, *, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = max(1, limit)
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - self.window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def rate_limit_per_minute() -> int:
    return int(os.getenv("RAG_RATE_LIMIT_PER_MIN", "60"))


_limiter: SlidingWindowRateLimiter | None = None


def get_limiter() -> SlidingWindowRateLimiter:
    global _limiter
    if _limiter is None or _limiter.limit != rate_limit_per_minute():
        _limiter = SlidingWindowRateLimiter(limit=rate_limit_per_minute())
    return _limiter
