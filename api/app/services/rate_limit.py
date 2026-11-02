"""Small in-process sliding-window rate limiter.

Used only for routes that have no user session (platform bootstrap). The MVP runs one API
replica (R15); the login lockout, which must work across replicas, lives in the database.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta

from ..core.clock import Clock
from ..core.errors import AppError


class SlidingWindowLimiter:
    def __init__(self, clock: Clock, limit: int, window_seconds: int) -> None:
        self._clock, self._limit, self._window = clock, limit, timedelta(seconds=window_seconds)
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record a hit; raise 429 RATE_LIMITED when ``key`` exceeded the limit in the window."""
        now = self._clock.now()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self._window:
                q.popleft()
            if len(q) >= self._limit:
                wait = max(1, math.ceil((q[0] + self._window - now).total_seconds()))
                raise AppError.too_many_requests("RATE_LIMITED", "Too many requests. Try again later.", wait)
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory: drop idle keys
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self._window]:
                    del self._hits[k]
