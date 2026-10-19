from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from evals.metrics import Summary, summarize
from evals.scoring import CaseScore


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def render_text(scores: Sequence[CaseScore], k: int | None = None) -> str:
    summary = summarize(scores)
    lines = [f"{'case':34} {'runs':>4} {'pass':>5} {'rate':>5}  failures"]
    for case in summary.cases:
        reasons = sorted({f for s in scores if s.case_id == case.case_id for f in s.failures})
        lines.append(f"{case.case_id:34} {case.runs:>4} {case.successes:>5} {_pct(case.pass_rate):>5}  {'; '.join(reasons)}")
    lines += [
        "",
        f"runs={summary.runs}  task_success={_pct(summary.task_success)}"
        f"  tool_selection_accuracy={_pct(summary.tool_selection_accuracy)}"
        f"  arg_accuracy={_pct(summary.arg_accuracy)}  step_efficiency={_pct(summary.step_efficiency)}"
        f"  safety_failures={summary.safety_failures}",
    ]
    if k:
        lines.append(f"pass@{k} per case: " + ", ".join(f"{c.case_id}={c.pass_at(k):.2f}" for c in summary.cases))
    return "\n".join(lines)


def to_json(scores: Sequence[CaseScore], meta: dict[str, Any], k: int | None = None) -> dict[str, Any]:
    summary = summarize(scores)
    return {
        **meta,
        "summary": {key: value for key, value in asdict(summary).items() if key != "cases"},
        "cases": [
            {
                "id": c.case_id,
                "runs": c.runs,
                "successes": c.successes,
                "pass_rate": c.pass_rate,
                **({f"pass_at_{k}": c.pass_at(k)} if k else {}),
                "failures": sorted({f for s in scores if s.case_id == c.case_id for f in s.failures}),
            }
            for c in summary.cases
        ],
    }
