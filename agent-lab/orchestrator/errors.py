from __future__ import annotations


class WorkflowError(Exception):
    """Raised inside a workflow to fail the run; str(exc) becomes the stored reason."""


class PlanError(WorkflowError):
    pass


class HandoffRefused(WorkflowError):
    pass


class BudgetExceeded(WorkflowError):
    pass


class StepFailed(WorkflowError):
    pass


class RunPaused(Exception):
    """Control flow, not a failure: the run is waiting for a human."""


class RunStopped(Exception):
    """Control flow: the run was cancelled, possibly by another process."""
