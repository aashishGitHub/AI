from __future__ import annotations

import io
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent.llm import LLM, ScriptedLLM, turns_from_dicts
from agent.types import LLMError, Message, ToolCall, ToolOutput, ToolSpec
from orchestrator.control import RunControl
from orchestrator.crash import SimulatedCrash
from orchestrator.engine import Orchestrator, RunSummary
from orchestrator.guards import Limits
from orchestrator.roles import AgentRole
from orchestrator.store import TERMINAL, WAITING_APPROVAL, WorkflowStore
from orchestrator.triage import INPUT, ROLES, SCRIPTS, triage
from tests.helpers import run

RUN_ID = "r1"


def _tool(name: str, read_only: bool, *required: str) -> ToolSpec:
    schema = {"type": "object", "properties": {k: {"type": "string"} for k in ("tenantId", "alertId", "note")},
              "required": list(required)}
    return ToolSpec(name, name, schema, read_only=read_only)


TOOLS = (
    _tool("get_live_metrics", True, "tenantId"),
    _tool("list_active_alerts", True, "tenantId"),
    _tool("explain_alert", True, "tenantId", "alertId"),
    _tool("acknowledge_alert", False, "tenantId", "alertId"),
)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FixedRng:
    def __init__(self, fraction: float = 1.0) -> None:
        self._fraction = fraction

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._fraction


@dataclass
class World:
    """The outside world: survives a simulated process death, so it can count real tool executions."""

    executions: dict[str, int] = field(default_factory=dict)

    def count(self, tool: str) -> int:
        return self.executions.get(tool, 0)


class WorldBackend:
    def __init__(self, world: World) -> None:
        self._world = world

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput:
        n = self._world.executions[name] = self._world.count(name) + 1
        body: dict[str, Any] = {"tool": name, "arguments": arguments}
        if name == "acknowledge_alert":
            body["execution"] = n
        return ToolOutput(json.dumps(body, sort_keys=True))


class CallThenEcho:
    def __init__(self, tool: str, arguments: dict[str, Any]) -> None:
        self._call = ToolCall("c1", tool, arguments)

    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        if messages[-1].role == "tool":
            return Message("assistant", f"saw {messages[-1].content}")
        return Message("assistant", "", (self._call,))


class EchoPrompt:
    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        return Message("assistant", f"Root cause: alr-1001 on streamflix. {messages[1].content}")


class Failing:
    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        raise LLMError("boom")


def reactive_llm(role: AgentRole, step_id: str, attempt: int) -> LLM:
    if step_id == "plan":
        return ScriptedLLM(turns_from_dicts(SCRIPTS["plan"]))
    if step_id == "work-alerts":
        return CallThenEcho("list_active_alerts", {"tenantId": "streamflix"})
    if step_id == "work-metrics":
        return CallThenEcho("get_live_metrics", {"tenantId": "streamflix"})
    if step_id == "aggregate":
        return EchoPrompt()
    return CallThenEcho("acknowledge_alert", {"tenantId": "streamflix", "alertId": "alr-1001"})


def make_orchestrator(db: Path, world: World, *, llm_factory=reactive_llm, limits: Limits = Limits(),
                      crash=None, clock: FakeClock | None = None, sleeper=None, rng=None, audit=None,
                      roles: Sequence[AgentRole] = ROLES, workflows=None) -> tuple[Orchestrator, WorkflowStore]:
    clock = clock or FakeClock()
    store = WorkflowStore(db, clock)

    async def no_sleep(seconds: float) -> None:
        return None

    kwargs: dict[str, Any] = {}
    if crash is not None:
        kwargs["crash"] = crash
    orchestrator = Orchestrator(
        store, WorldBackend(world), TOOLS, roles, workflows or {"triage": triage}, llm_factory, limits=limits,
        audit_stream=audit, clock=clock, sleeper=sleeper or no_sleep, rng=rng or FixedRng(),
        new_id=lambda: RUN_ID, **kwargs)
    return orchestrator, store


class OneShotCrash:
    def __init__(self, point: str | None = None, step_id: str | None = None) -> None:
        self._target = (point, step_id)
        self.fired = False

    def __call__(self, point: str, step_id: str) -> None:
        if not self.fired and (point, step_id) == self._target:
            self.fired = True
            raise SimulatedCrash(f"{point}@{step_id}")


@dataclass
class Outcome:
    summary: RunSummary
    world: World
    crashes: int
    steps: dict[str, tuple[str, int]]
    event_types: list[str]
    llm_created: list[tuple[str, int]]


def drive(tmp_path: Path, point: str | None = None, step_id: str | None = None, max_boots: int = 8) -> Outcome:
    """Boot a fresh orchestrator per 'process', approve when asked, until the run is terminal."""
    db, world, hook = tmp_path / "o.db", World(), OneShotCrash(point, step_id)
    llm_created: list[tuple[str, int]] = []

    def factory(role: AgentRole, step: str, attempt: int) -> LLM:
        llm_created.append((step, attempt))
        return reactive_llm(role, step, attempt)

    crashes, summary = 0, None
    for boot in range(max_boots):
        orchestrator, store = make_orchestrator(db, world, llm_factory=factory, crash=hook)
        try:
            if boot == 0:
                summary = run(orchestrator.run("triage", INPUT, RUN_ID))
            else:
                if store.get_run(RUN_ID).status == WAITING_APPROVAL:
                    RunControl(store).approve(RUN_ID, "respond")
                summary = run(orchestrator.resume(RUN_ID))
        except SimulatedCrash:
            crashes += 1
            summary = None
        steps = {s.step_id: (s.status, s.attempt) for s in store.steps(RUN_ID)}
        event_types = [e.type for e in store.events(RUN_ID)]
        store.close()
        if summary is not None and summary.status in TERMINAL:
            return Outcome(summary, world, crashes, steps, event_types, llm_created)
    raise AssertionError("run did not reach a terminal state")


def new_audit() -> io.StringIO:
    return io.StringIO()
