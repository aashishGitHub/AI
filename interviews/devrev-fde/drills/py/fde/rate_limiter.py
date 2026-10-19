import math
from dataclasses import dataclass

from fde.types import Clock


@dataclass(frozen=True)
class Allowed:
    pass


@dataclass(frozen=True)
class Denied:
    retry_after_ms: int


type Decision = Allowed | Denied


class TokenBucket:
    def __init__(self, capacity: int, refill_every_ms: int, now: Clock) -> None:
        self._capacity = capacity
        self._refill_every_ms = refill_every_ms
        self._now = now
        self._max_credit = capacity * refill_every_ms
        self._credit = self._max_credit
        self._last = now()

    def try_take(self, cost: int = 1) -> Decision:
        if cost > self._capacity:
            raise ValueError("cost exceeds capacity")

        t = self._now()
        elapsed = max(0, t - self._last)
        self._credit = min(self._max_credit, self._credit + elapsed)
        self._last = t

        price = cost * self._refill_every_ms
        if self._credit >= price:
            self._credit -= price
            return Allowed()
        return Denied(math.ceil(price - self._credit))
