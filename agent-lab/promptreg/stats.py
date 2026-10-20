from __future__ import annotations

from math import sqrt

Z_95 = 1.96


def wilson_interval(successes: int, runs: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, p = successes / runs.

    centre = (p + z^2 / 2n) / (1 + z^2 / n)
    half   = z * sqrt(p(1-p)/n + z^2 / 4n^2) / (1 + z^2 / n)
    interval = centre -/+ half, clamped to [0, 1]. z = 1.96 is the two-sided 95% normal quantile.
    Assumes the runs are independent and identically distributed.
    """
    if runs <= 0 or not 0 <= successes <= runs:
        raise ValueError(f"need runs > 0 and 0 <= successes <= runs, got successes={successes} runs={runs}")
    p = successes / runs
    denominator = 1 + z * z / runs
    centre = (p + z * z / (2 * runs)) / denominator
    half = z * sqrt(p * (1 - p) / runs + z * z / (4 * runs * runs)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)
