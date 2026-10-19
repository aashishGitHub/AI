import math
from collections import deque

from fde.types import Clock


class FixedWindowCounter:
    def __init__(self, limit: int, window_ms: int, now: Clock) -> None:
        self._limit = limit
        self._window_ms = window_ms
        self._now = now
        self._window: int | None = None
        self._count = 0

    def allow(self) -> bool:
        window = math.floor(self._now() / self._window_ms)
        if window != self._window:
            self._window = window
            self._count = 0
        if self._count >= self._limit:
            return False
        self._count += 1
        return True


class SlidingWindowLog:
    def __init__(self, limit: int, window_ms: int, now: Clock) -> None:
        self._limit = limit
        self._window_ms = window_ms
        self._now = now
        self._log: deque[float] = deque()

    def allow(self) -> bool:
        t = self._now()
        while self._log and self._log[0] <= t - self._window_ms:
            self._log.popleft()
        if len(self._log) >= self._limit:
            return False
        self._log.append(t)
        return True
