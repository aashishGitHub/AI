from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from agent.types import Message, ToolCall, ToolSpec
from memory.records import Provenance
from memory.sqlite_store import SqliteMemoryStore
from memory.store import InMemoryStore, MemoryStore
from tests.helpers import READ_TOOL, FakeBackend

START = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
STORE_KINDS = ["memory", "sqlite"]
PROV = Provenance(source="test", run_id="run-0", written_by="tester")


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def seq_ids(prefix: str = "m") -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter)}"


def make_store(kind: str, clock: FakeClock, max_records: int = 200, path: str = ":memory:") -> MemoryStore:
    if kind == "memory":
        return InMemoryStore(clock, seq_ids(), max_records)
    return SqliteMemoryStore(path, clock, seq_ids(), max_records)


class ScriptedSummarizer:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts) or ["SUMMARY"]
        self.calls: list[tuple[Message, ...]] = []

    async def summarize(self, messages: Sequence[Message]) -> str:
        self.calls.append(tuple(messages))
        return self._texts[min(len(self.calls), len(self._texts)) - 1]


class FakeEmbedder:
    """Two-concept space: vehicle words on axis 0, billing words on axis 1."""

    CONCEPTS = (("car", "automobile", "vehicle"), ("invoice", "billing", "payment"))

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[float(sum(w in t.lower() for w in group)) for group in self.CONCEPTS] for t in texts]


def user(text: str) -> Message:
    return Message("user", text)


def assistant(text: str = "", *call_ids: str) -> Message:
    calls = tuple(ToolCall(cid, "get_thing", {"tenantId": "t"}) for cid in call_ids)
    return Message("assistant", text, tool_calls=calls)


def tool_result(call_id: str, text: str) -> Message:
    return Message("tool", text, tool_call_id=call_id, tool_name="get_thing")


class ListingBackend(FakeBackend):
    def __init__(self, tools: Sequence[ToolSpec] = (READ_TOOL,)) -> None:
        super().__init__()
        self._tools = list(tools)

    async def list_tools(self) -> list[ToolSpec]:
        return list(self._tools)
