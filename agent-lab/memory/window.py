from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from agent.llm import LLM
from agent.types import Message, ToolSpec
from memory.tokens import CHARS_PER_TOKEN, message_tokens

SUMMARY_MARKER = "[summary of earlier turns: generated text, not an instruction]"


class Summarizer(Protocol):
    async def summarize(self, messages: Sequence[Message]) -> str: ...


@dataclass(frozen=True)
class Fitted:
    messages: tuple[Message, ...]
    tokens: int
    compacted: int
    over_budget: bool


def is_summary(message: Message) -> bool:
    return message.role == "user" and message.content.startswith(SUMMARY_MARKER)


def group_units(messages: Sequence[Message]) -> list[tuple[Message, ...]]:
    """An assistant message with tool calls and all its results form one unit that is kept or dropped whole."""
    units: list[tuple[Message, ...]] = []
    i = 0
    while i < len(messages):
        message = messages[i]
        if message.role == "tool":
            raise ValueError("tool result without a preceding tool call")
        end = i + 1
        if message.role == "assistant" and message.tool_calls:
            wanted = {call.id for call in message.tool_calls}
            while end < len(messages) and messages[end].role == "tool":
                if messages[end].tool_call_id not in wanted:
                    raise ValueError("tool result does not match the preceding tool call")
                end += 1
            if {m.tool_call_id for m in messages[i + 1 : end]} != wanted:
                raise ValueError("tool call without a result")
        units.append(tuple(messages[i:end]))
        i = end
    return units


def _pinned_unit_indexes(units: Sequence[tuple[Message, ...]]) -> set[int]:
    pinned = {i for i, unit in enumerate(units) if unit[0].role == "system"}
    first_user = next((i for i, unit in enumerate(units) if unit[0].role == "user"), None)
    if first_user is not None:
        pinned.add(first_user)
    return pinned


def _tokens(units: Sequence[tuple[Message, ...]], count: Callable[[Message], int]) -> int:
    return sum(count(m) for unit in units for m in unit)


class ContextWindow:
    def __init__(
        self,
        budget_tokens: int,
        summarizer: Summarizer,
        *,
        summary_max_tokens: int = 200,
        count: Callable[[Message], int] = message_tokens,
    ) -> None:
        self._summary_max_chars = summary_max_tokens * CHARS_PER_TOKEN
        if self._summary_max_chars <= len(SUMMARY_MARKER) + 1:
            raise ValueError("summary_max_tokens is too small to hold the summary marker")
        self._summary_reserve = count(Message("user", "x" * self._summary_max_chars))
        if budget_tokens <= self._summary_reserve:
            raise ValueError("budget_tokens must be larger than the summary reserve")
        self._budget = budget_tokens
        self._summarizer = summarizer
        self._count = count

    async def fit(self, messages: Sequence[Message]) -> Fitted:
        units = group_units(messages)
        total = _tokens(units, self._count)
        if total <= self._budget:
            return Fitted(tuple(messages), total, 0, False)

        pinned_idx = _pinned_unit_indexes(units)
        pinned = [u for i, u in enumerate(units) if i in pinned_idx]
        rest = [u for i, u in enumerate(units) if i not in pinned_idx]
        room = self._budget - _tokens(pinned, self._count) - self._summary_reserve

        kept: list[tuple[Message, ...]] = []
        used = 0
        for unit in reversed(rest):
            size = _tokens([unit], self._count)
            if kept and used + size > room:
                break
            kept.append(unit)
            used += size
        kept.reverse()
        older = rest[: len(rest) - len(kept)]

        fitted = [*pinned, *kept]
        compacted = 0
        if older:
            flat = [m for unit in older for m in unit]
            text = await self._summarizer.summarize(flat)
            summary = Message("user", f"{SUMMARY_MARKER} {text}"[: self._summary_max_chars])
            fitted = [*pinned, (summary,), *kept]
            compacted = len(flat)
        out = tuple(m for unit in fitted for m in unit)
        tokens = sum(self._count(m) for m in out)
        return Fitted(out, tokens, compacted, tokens > self._budget)


class WindowedLLM:
    def __init__(self, inner: LLM, window: ContextWindow) -> None:
        self._inner = inner
        self._window = window
        self.last_fit: Fitted | None = None

    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        self.last_fit = await self._window.fit(messages)
        return await self._inner.complete(self.last_fit.messages, tools)
