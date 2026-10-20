from __future__ import annotations

from collections.abc import Callable

BEFORE_STEP = "before_step"
STEP_STARTED = "step_started"
TOOL_EXECUTED = "tool_executed"
TOOL_JOURNALED = "tool_journaled"
AFTER_STEP_COMMIT = "after_step_commit"
CRASH_POINTS = (BEFORE_STEP, STEP_STARTED, TOOL_EXECUTED, TOOL_JOURNALED, AFTER_STEP_COMMIT)

CrashHook = Callable[[str, str], None]


class SimulatedCrash(BaseException):
    """BaseException on purpose: no `except Exception` in the engine may turn a dead process into a failed step."""


def no_crash(point: str, step_id: str) -> None:
    return None


def crash_at(point: str, step_id: str) -> CrashHook:
    def hook(current_point: str, current_step: str) -> None:
        if (current_point, current_step) == (point, step_id):
            raise SimulatedCrash(f"{point}@{step_id}")

    return hook
