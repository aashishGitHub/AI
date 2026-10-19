from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import yaml

from agent.types import LLMError, Message, ToolCall, ToolSpec


class LLM(Protocol):
    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message: ...


class ScriptExhausted(LLMError):
    pass


class ScriptedLLM:
    def __init__(self, turns: Sequence[Message]) -> None:
        self._turns = list(turns)
        self._next = 0
        self.requests: list[tuple[tuple[Message, ...], tuple[ToolSpec, ...]]] = []

    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        self.requests.append((tuple(messages), tuple(tools)))
        if self._next >= len(self._turns):
            raise ScriptExhausted(f"script has {len(self._turns)} turn(s) but the loop asked for turn {self._next + 1}")
        turn = self._turns[self._next]
        self._next += 1
        return turn


def turns_from_dicts(raw_turns: Sequence[Mapping[str, Any]]) -> list[Message]:
    turns: list[Message] = []
    for index, raw in enumerate(raw_turns, start=1):
        calls = tuple(
            ToolCall(id=f"call-{index}-{n}", name=call["name"], arguments=dict(call.get("arguments", {})))
            for n, call in enumerate(raw.get("tool_calls", []), start=1)
        )
        turns.append(Message(role="assistant", content=raw.get("content", ""), tool_calls=calls))
    return turns


def load_script(path: Path) -> ScriptedLLM:
    data = yaml.safe_load(path.read_text())
    raw_turns = data["script"] if isinstance(data, dict) else data
    return ScriptedLLM(turns_from_dicts(raw_turns))
