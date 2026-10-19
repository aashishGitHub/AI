from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb

from evals.scoring import CaseScore


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator 1 - C(n-c, k) / C(n, k) from Chen et al. 2021 (Codex paper)."""
    if not 1 <= k <= n or not 0 <= c <= n:
        raise ValueError(f"need 1 <= k <= n and 0 <= c <= n, got n={n} c={c} k={k}")
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


@dataclass(frozen=True)
class CaseSummary:
    case_id: str
    runs: int
    successes: int

    @property
    def pass_rate(self) -> float:
        return self.successes / self.runs

    def pass_at(self, k: int) -> float:
        return pass_at_k(self.runs, self.successes, k)


@dataclass(frozen=True)
class Summary:
    runs: int
    task_success: float
    tool_selection_accuracy: float
    arg_accuracy: float | None
    step_efficiency: float
    safety_failures: int
    cases: tuple[CaseSummary, ...]


def summarize(scores: Sequence[CaseScore]) -> Summary:
    by_case: dict[str, list[CaseScore]] = defaultdict(list)
    for score in scores:
        by_case[score.case_id].append(score)
    return Summary(
        runs=len(scores),
        task_success=sum(s.success for s in scores) / len(scores),
        tool_selection_accuracy=sum(bool(s.selection.ok) for s in scores) / len(scores),
        arg_accuracy=_mean([float(s.args.ok) for s in scores if s.args.ok is not None]),
        step_efficiency=sum(s.efficiency for s in scores) / len(scores),
        safety_failures=sum(s.safety.ok is False for s in scores),
        cases=tuple(CaseSummary(cid, len(group), sum(s.success for s in group)) for cid, group in by_case.items()),
    )
