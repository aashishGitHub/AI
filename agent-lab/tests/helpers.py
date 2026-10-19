from __future__ import annotations

import asyncio
import io
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from agent.audit import AuditLog
from agent.llm import ScriptedLLM, turns_from_dicts
from agent.types import ToolCall, ToolOutput, ToolSpec

T = TypeVar("T")


def run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


def scripted(*turns: dict[str, Any]) -> ScriptedLLM:
    return ScriptedLLM(turns_from_dicts(turns))


def tool_turn(name: str, **arguments: Any) -> dict[str, Any]:
    return {"tool_calls": [{"name": name, "arguments": arguments}]}


def final_turn(text: str) -> dict[str, Any]:
    return {"content": text}


def new_audit() -> tuple[AuditLog, io.StringIO]:
    stream = io.StringIO()
    return AuditLog(stream, run_id="test"), stream


READ_TOOL = ToolSpec(
    "get_thing",
    "reads a thing",
    {
        "type": "object",
        "properties": {"tenantId": {"type": "string"}},
        "required": ["tenantId"],
    },
    read_only=True,
)
WRITE_TOOL = ToolSpec(
    "change_thing",
    "changes a thing",
    {
        "type": "object",
        "properties": {"tenantId": {"type": "string"}, "alertId": {"type": "string"}},
        "required": ["tenantId", "alertId"],
    },
    read_only=False,
)


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=arguments)


class FakeBackend:
    def __init__(self, handler: Callable[[str, dict[str, Any]], Awaitable[ToolOutput]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._handler = handler

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput:
        self.calls.append((name, arguments))
        if self._handler:
            return await self._handler(name, arguments)
        return ToolOutput(content=f'{{"ok": "{name}"}}')
