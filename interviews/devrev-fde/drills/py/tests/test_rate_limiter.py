import pytest

from fde.rate_limiter import Allowed, Denied, TokenBucket
from tests.helpers import FakeClock


def setup(capacity: int = 5, refill_every_ms: int = 1000) -> tuple[FakeClock, TokenBucket]:
    clock = FakeClock(10_000)
    return clock, TokenBucket(capacity=capacity, refill_every_ms=refill_every_ms, now=clock.now)


def drain(bucket: TokenBucket, n: int = 5) -> None:
    for _ in range(n):
        bucket.try_take()


def test_allows_a_full_burst_then_denies_with_time_to_next_token() -> None:
    _, bucket = setup()
    for _ in range(5):
        assert bucket.try_take() == Allowed()
    assert bucket.try_take() == Denied(1000)


def test_denies_one_millisecond_before_refill_and_allows_at_the_exact_boundary() -> None:
    clock, bucket = setup()
    drain(bucket)

    clock.advance(999)
    assert bucket.try_take() == Denied(1)
    clock.advance(1)
    assert bucket.try_take() == Allowed()
    assert bucket.try_take() == Denied(1000)


def test_keeps_partial_credit_across_a_denial() -> None:
    clock, bucket = setup()
    drain(bucket)

    clock.advance(600)
    assert bucket.try_take() == Denied(400)
    clock.advance(400)
    assert bucket.try_take() == Allowed()


def test_never_refills_beyond_capacity_after_a_long_idle_period() -> None:
    clock, bucket = setup()
    clock.advance(1_000_000)
    for _ in range(5):
        assert bucket.try_take() == Allowed()
    assert bucket.try_take() == Denied(1000)


def test_charges_multi_token_costs_and_reports_the_shortfall() -> None:
    clock, bucket = setup()
    assert bucket.try_take(3) == Allowed()
    assert bucket.try_take(3) == Denied(1000)
    clock.advance(1000)
    assert bucket.try_take(3) == Allowed()


def test_rejects_a_cost_that_can_never_be_satisfied() -> None:
    _, bucket = setup()
    with pytest.raises(ValueError):
        bucket.try_take(6)


def test_ignores_a_clock_that_moves_backwards() -> None:
    clock, bucket = setup()
    drain(bucket)
    clock.advance(-5000)
    assert bucket.try_take() == Denied(1000)
    clock.advance(5000 + 1000)
    assert bucket.try_take() == Allowed()


def test_does_not_drift_with_non_divisible_refill_rates() -> None:
    clock, bucket = setup(capacity=1, refill_every_ms=333)
    assert bucket.try_take() == Allowed()
    clock.advance(332)
    assert bucket.try_take() == Denied(1)
    clock.advance(1)
    assert bucket.try_take() == Allowed()
