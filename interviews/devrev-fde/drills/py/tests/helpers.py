from collections.abc import Callable, Sequence


class FakeClock:
    def __init__(self, start: float = 0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, ms: float) -> None:
        self._now += ms


def scripted(values: Sequence[float]) -> Callable[[], float]:
    remaining = iter(values)

    def rng() -> float:
        try:
            return next(remaining)
        except StopIteration:
            raise AssertionError("scripted rng exhausted") from None

    return rng
