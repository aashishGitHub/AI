from __future__ import annotations

from orchestrator.store import WorkflowStore


class RunControl:
    """Operations that only touch the store, so a CLI can use them without connecting any tools."""

    def __init__(self, store: WorkflowStore) -> None:
        self._store = store

    def approve(self, run_id: str, step_id: str) -> None:
        self._store.approve_step(run_id, step_id)

    def deny(self, run_id: str, step_id: str) -> None:
        self._store.deny_step(run_id, step_id)

    def cancel(self, run_id: str) -> None:
        self._store.cancel_run(run_id)

    def describe(self, run_id: str) -> str:
        run = self._store.get_run(run_id)
        lines = [f"run {run.run_id}  workflow={run.workflow}  status={run.status}", f"input: {run.input}"]
        if run.error:
            lines.append(f"error: {run.error}")
        lines.append("steps:")
        for step in self._store.steps(run_id):
            lines.append(f"  {step.step_id:<18} {step.role:<14} {step.status:<17} attempt={step.attempt}")
        lines.append("events:")
        for event in self._store.events(run_id):
            detail = " ".join(f"{k}={v}" for k, v in event.payload.items() if k != "prev")
            lines.append(f"  {event.seq:>3}  {event.ts}  {event.type:<24} {detail}")
        return "\n".join(lines)
