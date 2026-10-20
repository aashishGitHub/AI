from __future__ import annotations

import pytest

from promptreg.stats import wilson_interval


def test_known_values_at_z_1_96():
    low, high = wilson_interval(8, 10)
    assert (round(low, 4), round(high, 4)) == (0.4902, 0.9433)


def test_bounds_solve_the_score_test_equation():
    successes, runs, z = 7, 12, 1.96
    p = successes / runs
    for bound in wilson_interval(successes, runs, z):
        assert (p - bound) ** 2 == pytest.approx(z * z * bound * (1 - bound) / runs)


def test_all_successes_still_leaves_room_below_one():
    low, high = wilson_interval(5, 5)
    assert high == 1.0
    assert low == pytest.approx(0.5655, abs=1e-4)


def test_zero_successes_has_a_positive_upper_bound():
    low, high = wilson_interval(0, 5)
    assert low == 0.0
    assert high == pytest.approx(0.4345, abs=1e-4)


def test_more_runs_narrow_the_interval():
    small = wilson_interval(5, 10)
    large = wilson_interval(50, 100)
    assert (large[1] - large[0]) < (small[1] - small[0])


@pytest.mark.parametrize("successes,runs", [(1, 0), (-1, 5), (6, 5)])
def test_impossible_counts_raise(successes, runs):
    with pytest.raises(ValueError):
        wilson_interval(successes, runs)
