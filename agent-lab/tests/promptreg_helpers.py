from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from promptreg.registry import PromptRegistry
from promptreg.store import PromptStore


def stepping_clock(start: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)):
    state = {"now": start}

    def clock() -> datetime:
        current = state["now"]
        state["now"] = current + timedelta(seconds=1)
        return current

    return clock


def new_registry(root: Path) -> tuple[PromptRegistry, PromptStore]:
    store = PromptStore(root, clock=stepping_clock())
    return PromptRegistry(store), store


def eval_report(
    cases: dict[str, tuple[int, int]], safety_failures: int = 0, model: str | None = "qwen2.5:3b",
    prompt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "live",
        "summary": {"runs": sum(n for _, n in cases.values()), "safety_failures": safety_failures},
        "cases": [
            {"id": case_id, "runs": runs, "successes": successes, "pass_rate": successes / runs, "failures": []}
            for case_id, (successes, runs) in cases.items()
        ],
    }
    if model:
        report["model"] = model
    if prompt:
        report["prompt"] = prompt
    return report


def write_report(path: Path, report: dict[str, Any]) -> Path:
    path.write_text(json.dumps(report))
    return path
