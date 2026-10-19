from __future__ import annotations

import asyncio
import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for

from agent.approval import ApprovalGate, Decision
from agent.grounding import ungrounded_args
from agent.mcp_backend import ToolBackend
from agent.types import ToolCall, ToolSpec

TRUNCATED_MARKER = "[truncated]"


@dataclass(frozen=True)
class ToolRecord:
    step: int
    call: ToolCall
    decision: Decision | None
    executed: bool
    error_kind: str | None
    content: str
    latency_ms: float
    detail: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error_kind is not None


class ToolExecutor:
    """execute() never raises: every failure becomes an error record the model can read."""

    def __init__(
        self,
        backend: ToolBackend,
        tools: Sequence[ToolSpec],
        gate: ApprovalGate,
        default_timeout_s: float = 10.0,
        timeouts_s: Mapping[str, float] | None = None,
        max_result_chars: int = 8000,
        grounded_args: Collection[str] = (),
    ) -> None:
        self._backend = backend
        self._tools = {t.name: t for t in tools}
        self._gate = gate
        self._default_timeout_s = default_timeout_s
        self._timeouts_s = dict(timeouts_s or {})
        self._max_result_chars = max_result_chars
        self._grounded_args = frozenset(grounded_args)

    async def execute(self, call: ToolCall, step: int, evidence: Sequence[str] = ()) -> ToolRecord:
        started = time.perf_counter()
        try:
            return await self._execute(call, step, started, evidence)
        except Exception as exc:
            return self._record(call, step, started, f"error: {call.name} could not be run; see the audit log",
                                kind="internal_error", detail=f"{type(exc).__name__}: {exc}")

    async def _execute(self, call: ToolCall, step: int, started: float, evidence: Sequence[str]) -> ToolRecord:
        tool = self._tools.get(call.name)
        if tool is None:
            known = ", ".join(sorted(self._tools))
            return self._record(call, step, started,
                                f"error: unknown tool '{call.name}'. Available tools: {known}", kind="unknown_tool")

        problems = self._schema_problems(tool, call)
        if problems:
            return self._record(call, step, started,
                                f"error: invalid arguments for {call.name}: {problems}", kind="invalid_arguments")

        ungrounded = ungrounded_args(call.arguments, self._grounded_args, evidence)
        if ungrounded:
            return self._record(
                call, step, started,
                f"error: {', '.join(ungrounded)} did not come from the user or an earlier tool result, so"
                f" {call.name} was not called. Do not guess identifiers: ask the user for the missing value.",
                kind="ungrounded_argument")

        decision = self._gate.decide(call, tool)
        if not decision.approved:
            return self._record(
                call, step, started,
                f"error: {call.name} was not approved ({decision.reason}). Do not retry it;"
                " tell the user the action needs human approval.",
                kind="denied", decision=decision)

        timeout_s = self._timeouts_s.get(call.name, self._default_timeout_s)
        try:
            output = await asyncio.wait_for(self._backend.call_tool(call.name, call.arguments), timeout_s)
        except TimeoutError:
            return self._record(call, step, started, f"error: {call.name} timed out after {timeout_s:g} s",
                                kind="timeout", decision=decision, executed=True)
        except Exception as exc:
            return self._record(call, step, started, f"error: {call.name} failed ({type(exc).__name__}); see the audit log",
                                kind="backend_error", decision=decision, executed=True, detail=str(exc))
        if output.is_error:
            return self._record(call, step, started, f"error: {output.content}",
                                kind="tool_error", decision=decision, executed=True)
        return self._record(call, step, started, output.content, kind=None, decision=decision, executed=True)

    def _record(self, call: ToolCall, step: int, started: float, content: str, *, kind: str | None,
                decision: Decision | None = None, executed: bool = False, detail: str | None = None) -> ToolRecord:
        if len(content) > self._max_result_chars:
            content = content[: self._max_result_chars] + TRUNCATED_MARKER
        return ToolRecord(step, call, decision, executed, kind, content, (time.perf_counter() - started) * 1000, detail)

    @staticmethod
    def _schema_problems(tool: ToolSpec, call: ToolCall) -> str:
        validator = validator_for(tool.input_schema, default=Draft202012Validator)(tool.input_schema)
        errors = sorted(validator.iter_errors(call.arguments), key=lambda e: e.json_path)
        return "; ".join(f"{e.json_path}: {e.message}" for e in errors)
