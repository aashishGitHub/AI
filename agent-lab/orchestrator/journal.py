from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agent.mcp_backend import ToolBackend
from agent.types import ToolCall, ToolOutput, ToolSpec
from orchestrator.crash import TOOL_EXECUTED, TOOL_JOURNALED, CrashHook
from orchestrator.store import WorkflowStore


class JournalingBackend:
    """Replays a stored result instead of calling the tool again. `fatal` tells the engine to fail the step."""

    def __init__(self, inner: ToolBackend, store: WorkflowStore, run_id: str, step_id: str,
                 tools: Mapping[str, ToolSpec], crash: CrashHook) -> None:
        self._inner = inner
        self._store = store
        self._run_id = run_id
        self._step_id = step_id
        self._tools = tools
        self._crash = crash
        self._next_index = 0
        self.fatal: str | None = None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput:
        index = self._next_index
        self._next_index += 1
        arguments_json = json.dumps(arguments, sort_keys=True)
        read_only = name in self._tools and self._tools[name].read_only
        entry = self._store.journal_get(self._run_id, self._step_id, index)
        if entry is not None and (entry.tool, entry.arguments) == (name, arguments_json):
            if entry.status == "done":
                self._store.append_event(self._run_id, "tool_replayed", step=self._step_id, index=index, tool=name)
                return ToolOutput(entry.content or "", entry.is_error)
            if not entry.read_only:
                self.fatal = f"{name} (call {index}) may already have run before a crash; not repeating a write"
                return ToolOutput(f"error: {name} outcome unknown; not repeated", True)
        elif entry is not None and not entry.read_only:
            self.fatal = f"replay diverged at write call {index}: journal has {entry.tool}, the model asked for {name}"
            return ToolOutput(f"error: {name} not run; replay diverged from the journal", True)
        self._store.journal_start(self._run_id, self._step_id, index, name, arguments_json, read_only)
        output = await self._inner.call_tool(name, arguments)
        self._crash(TOOL_EXECUTED, self._step_id)
        self._store.journal_finish(self._run_id, self._step_id, index, output.content, output.is_error)
        self._store.append_event(self._run_id, "tool_journaled", step=self._step_id, index=index, tool=name)
        self._crash(TOOL_JOURNALED, self._step_id)
        return output


class StoreApprover:
    """Approves only the exact call a human granted; otherwise denies and remembers what to ask about."""

    def __init__(self, store: WorkflowStore, run_id: str, step_id: str) -> None:
        self._store = store
        self._run_id = run_id
        self._step_id = step_id
        self.requested: str | None = None

    def __call__(self, call: ToolCall, tool: ToolSpec) -> bool:
        wanted = json.dumps({"tool": call.name, "arguments": call.arguments}, sort_keys=True)
        step = self._store.get_step(self._run_id, self._step_id)
        if step is not None and step.approval == "granted" and step.pending_call == wanted:
            return True
        if self.requested is None:
            self.requested = wanted
        return False
