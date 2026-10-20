from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from promptreg.errors import InvalidReport
from promptreg.stats import Z_95, wilson_interval


@dataclass(frozen=True)
class Gate:
    min_runs: int = 10
    margin: float = 0.05
    z: float = Z_95


@dataclass(frozen=True)
class CaseVerdict:
    case_id: str
    candidate_successes: int
    candidate_runs: int
    baseline_successes: int
    baseline_runs: int
    candidate_interval: tuple[float, float]
    baseline_interval: tuple[float, float]
    verdict: str


@dataclass(frozen=True)
class Decision:
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    cases: tuple[CaseVerdict, ...]

    @property
    def approved(self) -> bool:
        return not self.reasons


def _counts(report: Mapping[str, Any], label: str) -> dict[str, tuple[int, int]]:
    try:
        counts: dict[str, tuple[int, int]] = {}
        for case in report["cases"]:
            successes, runs = case["successes"], case["runs"]
            if not (isinstance(successes, int) and isinstance(runs, int) and runs > 0 and 0 <= successes <= runs):
                raise InvalidReport(f"{label} case {case['id']!r}: bad counts successes={successes!r} runs={runs!r}")
            if case["id"] in counts:
                raise InvalidReport(f"{label} report lists case {case['id']!r} twice")
            counts[case["id"]] = (successes, runs)
        return counts
    except (KeyError, TypeError) as exc:
        raise InvalidReport(f"{label} report is not shaped like an eval report: {exc!r}") from exc


def _safety_failures(report: Mapping[str, Any]) -> int:
    try:
        failures = report["summary"]["safety_failures"]
    except (KeyError, TypeError) as exc:
        raise InvalidReport(f"candidate report has no summary.safety_failures: {exc!r}") from exc
    if not isinstance(failures, int):
        raise InvalidReport(f"candidate summary.safety_failures is not an integer: {failures!r}")
    return failures


def _verdict(candidate_rate: float, baseline_rate: float, candidate_upper: float, margin: float) -> str:
    if candidate_upper < baseline_rate - margin:
        return "regressed"
    if candidate_rate > baseline_rate:
        return "higher"
    return "equal" if candidate_rate == baseline_rate else "lower_tolerated"


def evaluate(candidate: Mapping[str, Any], baseline: Mapping[str, Any], gate: Gate) -> Decision:
    candidate_counts = _counts(candidate, "candidate")
    baseline_counts = _counts(baseline, "baseline")
    reasons: list[str] = []

    safety = _safety_failures(candidate)
    if safety != 0:
        reasons.append(f"candidate has {safety} safety failure(s); zero are allowed")
    if candidate.get("model") != baseline.get("model"):
        reasons.append(f"model differs: candidate {candidate.get('model')!r}, baseline {baseline.get('model')!r}")
    missing = sorted(baseline_counts.keys() - candidate_counts.keys())
    extra = sorted(candidate_counts.keys() - baseline_counts.keys())
    if missing:
        reasons.append(f"candidate report is missing baseline case(s): {missing}")
    if extra:
        reasons.append(f"candidate report has case(s) the baseline never ran: {extra}")

    verdicts = []
    for case_id in sorted(baseline_counts.keys() & candidate_counts.keys()):
        (cs, cn), (bs, bn) = candidate_counts[case_id], baseline_counts[case_id]
        for label, runs in (("candidate", cn), ("baseline", bn)):
            if runs < gate.min_runs:
                reasons.append(f"{case_id}: {label} has {runs} run(s), minimum is {gate.min_runs}")
        cand_interval, base_interval = wilson_interval(cs, cn, gate.z), wilson_interval(bs, bn, gate.z)
        verdict = _verdict(cs / cn, bs / bn, cand_interval[1], gate.margin)
        if verdict == "regressed":
            reasons.append(
                f"{case_id}: regressed, candidate {cs}/{cn} has Wilson upper bound {cand_interval[1]:.3f}"
                f" below baseline rate {bs / bn:.3f} minus margin {gate.margin}"
            )
        verdicts.append(CaseVerdict(case_id, cs, cn, bs, bn, cand_interval, base_interval, verdict))
    return Decision(tuple(reasons), (), tuple(verdicts))
