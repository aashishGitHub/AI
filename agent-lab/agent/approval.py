from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent.types import ToolCall, ToolSpec

Approver = Callable[[ToolCall, ToolSpec], bool]


@dataclass(frozen=True)
class Decision:
    approved: bool
    reason: str


def deny_all(call: ToolCall, tool: ToolSpec) -> bool:
    return False


def allow_tools(*names: str) -> Approver:
    allowed = frozenset(names)
    return lambda call, tool: call.name in allowed


def ask_on_terminal(input_fn: Callable[[str], str] = input) -> Approver:
    def approve(call: ToolCall, tool: ToolSpec) -> bool:
        answer = input_fn(f"Approve {call.name}({call.arguments})? [y/N] ")
        return answer.strip().lower() in {"y", "yes"}

    return approve


class ApprovalGate:
    """Trusts read_only because this client owns the server; for a third-party server use an allowlist."""

    def __init__(self, approver: Approver = deny_all) -> None:
        self._approver = approver

    def decide(self, call: ToolCall, tool: ToolSpec) -> Decision:
        if tool.read_only:
            return Decision(True, "read-only tool")
        try:
            approved = self._approver(call, tool)
        except Exception:
            return Decision(False, "approver failed; denied")
        return Decision(approved, "approved by approver" if approved else "denied by approver")
