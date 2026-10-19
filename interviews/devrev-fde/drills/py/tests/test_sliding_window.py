from fde.sliding_window import FixedWindowCounter, SlidingWindowLog
from tests.helpers import FakeClock

LIMIT = 5
WINDOW_MS = 1000


def pair(start: float = 0) -> tuple[FakeClock, FixedWindowCounter, SlidingWindowLog]:
    clock = FakeClock(start)
    return (
        clock,
        FixedWindowCounter(LIMIT, WINDOW_MS, clock.now),
        SlidingWindowLog(LIMIT, WINDOW_MS, clock.now),
    )


def burst(limiter: FixedWindowCounter | SlidingWindowLog, n: int) -> int:
    return sum(limiter.allow() for _ in range(n))


def test_both_allow_up_to_the_limit_within_a_window_and_deny_the_rest() -> None:
    _, fixed, log = pair()
    assert burst(fixed, 8) == LIMIT
    assert burst(log, 8) == LIMIT


def test_fixed_window_lets_twice_the_limit_through_in_2ms_across_a_window_edge() -> None:
    clock, fixed, _ = pair(999)
    assert burst(fixed, LIMIT) == LIMIT
    clock.advance(1)
    assert burst(fixed, LIMIT) == LIMIT


def test_sliding_log_holds_the_line_across_the_same_edge() -> None:
    clock, _, log = pair(999)
    assert burst(log, LIMIT) == LIMIT
    clock.advance(1)
    assert burst(log, LIMIT) == 0


def test_sliding_log_admits_again_exactly_when_the_oldest_entries_leave_the_window() -> None:
    clock, _, log = pair(0)
    assert burst(log, LIMIT) == LIMIT
    clock.advance(WINDOW_MS - 1)
    assert not log.allow()
    clock.advance(1)
    assert burst(log, LIMIT) == LIMIT


def test_sliding_log_frees_slots_gradually_as_individual_entries_expire() -> None:
    clock, _, log = pair(0)
    for _ in range(LIMIT):
        log.allow()
        clock.advance(100)
    assert not log.allow()
    clock.advance(500)
    assert log.allow()
    assert not log.allow()


def test_denied_requests_are_not_logged_so_hammering_does_not_extend_the_lockout() -> None:
    clock, _, log = pair(0)
    burst(log, LIMIT)
    for _ in range(9):
        clock.advance(100)
        assert not log.allow()
    clock.advance(100)
    assert burst(log, LIMIT) == LIMIT


def test_fixed_window_resets_at_the_aligned_edge_not_window_ms_after_the_first_request() -> None:
    clock, fixed, _ = pair(700)
    assert burst(fixed, LIMIT) == LIMIT
    clock.advance(299)
    assert not fixed.allow()
    clock.advance(1)
    assert fixed.allow()
