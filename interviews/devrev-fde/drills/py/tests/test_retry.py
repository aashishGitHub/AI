import dataclasses
import random
from datetime import UTC, datetime
from collections.abc import Callable, Sequence

import pytest

from fde.retry import HttpError, NetworkError, RetryOptions, parse_retry_after, retry
from tests.helpers import scripted

NOW = int(datetime(2015, 10, 21, 7, 28, tzinfo=UTC).timestamp()) * 1000


def harness(**overrides: object) -> tuple[list[int], RetryOptions]:
    sleeps: list[int] = []
    options = RetryOptions(
        method="GET",
        max_attempts=4,
        base_ms=100,
        cap_ms=1000,
        sleep=sleeps.append,
        rng=scripted([0.5] * 5),
        now_ms=lambda: NOW,
    )
    return sleeps, dataclasses.replace(options, **overrides)


def failing_then_ok(errors: Sequence[Exception], value: str = "ok") -> tuple[Callable[[int], str], list[int]]:
    calls: list[int] = []

    def op(attempt: int) -> str:
        calls.append(attempt)
        if attempt <= len(errors):
            raise errors[attempt - 1]
        return value

    return op, calls


def status(code: int, **headers: str) -> HttpError:
    return HttpError(code, {name.replace("_", "-"): value for name, value in headers.items()})


def test_returns_immediately_without_sleeping_when_first_attempt_succeeds() -> None:
    sleeps, options = harness()
    op, calls = failing_then_ok([])
    assert retry(op, options) == "ok"
    assert calls == [1]
    assert sleeps == []


def test_sleeps_rng_times_min_cap_base_pow2_full_jitter() -> None:
    sleeps, options = harness()
    op, _ = failing_then_ok([status(503), status(503), status(503)])
    retry(op, options)
    assert sleeps == [50, 100, 200]


def test_clamps_the_ceiling_at_cap_ms() -> None:
    sleeps, options = harness(max_attempts=6, cap_ms=300)
    op, _ = failing_then_ok([status(500)] * 5)
    retry(op, options)
    assert sleeps == [50, 100, 150, 150, 150]


def test_can_sleep_zero_and_stays_strictly_below_the_ceiling() -> None:
    sleeps, options = harness(rng=scripted([0, 0.999999]))
    op, _ = failing_then_ok([status(500), status(500)])
    retry(op, options)
    assert sleeps == [0, 199]


def test_is_fully_determined_by_a_seeded_rng() -> None:
    expected_draws = random.Random(42)
    expected = [int(expected_draws.random() * ceiling) for ceiling in (100, 200, 400)]

    sleeps, options = harness(rng=random.Random(42).random, cap_ms=10_000)
    op, _ = failing_then_ok([status(503)] * 3)
    retry(op, options)
    assert sleeps == expected


def test_retry_after_seconds_is_a_floor_over_the_jittered_delay() -> None:
    sleeps, options = harness()
    op, _ = failing_then_ok([status(429, Retry_After="2"), status(429, retry_after="0")])
    retry(op, options)
    assert sleeps == [2000, 100]


def test_jittered_delay_wins_when_larger_than_the_hint() -> None:
    sleeps, options = harness(rng=scripted([0.999]), base_ms=10_000, cap_ms=10_000)
    op, _ = failing_then_ok([status(503, retry_after="1")])
    retry(op, options)
    assert sleeps == [9990]


def test_honours_an_http_date_relative_to_the_injected_clock() -> None:
    sleeps, options = harness()
    op, _ = failing_then_ok([status(503, retry_after="Wed, 21 Oct 2015 07:28:05 GMT")])
    retry(op, options)
    assert sleeps == [5000]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Wed, 21 Oct 2015 07:27:00 GMT", 0),
        ("soon", None),
        ("foo 3", None),
        ("-5", None),
        ("1.5", None),
        ("9" * 400, None),
        ("Wed, 21 Xxx 2015 07:28:00 GMT", None),
        (None, None),
    ],
)
def test_parse_retry_after(value: str | None, expected: int | None) -> None:
    assert parse_retry_after(value, NOW) == expected


def test_gives_up_after_max_attempts_and_reraises_the_last_error() -> None:
    sleeps, options = harness(max_attempts=3)
    last = status(502)
    op, calls = failing_then_ok([status(503), status(503), last, status(503)])
    with pytest.raises(HttpError) as raised:
        retry(op, options)
    assert raised.value is last
    assert calls == [1, 2, 3]
    assert len(sleeps) == 2


@pytest.mark.parametrize("code", [400, 401, 404, 409, 422])
def test_does_not_retry_client_errors(code: int) -> None:
    sleeps, options = harness()
    op, calls = failing_then_ok([status(code)])
    with pytest.raises(HttpError):
        retry(op, options)
    assert calls == [1]
    assert sleeps == []


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504, 599])
def test_retries_throttling_and_server_errors(code: int) -> None:
    _, options = harness()
    op, calls = failing_then_ok([status(code)])
    retry(op, options)
    assert calls == [1, 2]


def test_retries_network_errors_but_not_programmer_errors() -> None:
    _, options = harness()
    net_op, net_calls = failing_then_ok([NetworkError("ECONNRESET")])
    retry(net_op, options)
    assert net_calls == [1, 2]

    bug_op, bug_calls = failing_then_ok([TypeError("x is None")])
    with pytest.raises(TypeError):
        retry(bug_op, options)
    assert bug_calls == [1]


def test_never_retries_post_without_an_idempotency_key() -> None:
    sleeps, options = harness(method="POST")
    op, calls = failing_then_ok([status(503)])
    with pytest.raises(HttpError):
        retry(op, options)
    assert calls == [1]
    assert sleeps == []


def test_never_retries_a_post_network_error_without_a_key() -> None:
    _, options = harness(method="post")
    op, calls = failing_then_ok([NetworkError("reset")])
    with pytest.raises(NetworkError):
        retry(op, options)
    assert calls == [1]


def test_retries_post_once_it_carries_an_idempotency_key() -> None:
    _, options = harness(method="POST", idempotency_key="req-123")
    op, calls = failing_then_ok([status(503)])
    retry(op, options)
    assert calls == [1, 2]


@pytest.mark.parametrize("method", ["PUT", "DELETE", "get"])
def test_retries_inherently_idempotent_methods(method: str) -> None:
    _, options = harness(method=method)
    op, calls = failing_then_ok([status(500)])
    retry(op, options)
    assert calls == [1, 2]
