from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent.types import Message, ToolCall, ToolOutput, ToolSpec
from orchestrator.control import RunControl
from orchestrator.engine import RunContext, RunSummary
from orchestrator.guards import Limits
from orchestrator.roles import AgentRole
from orchestrator.store import TERMINAL, WAITING_APPROVAL
from tests.helpers import run
from tests.orchestrator_helpers import RUN_ID, World, make_orchestrator

ACK = {"tenantId": "streamflix", "alertId": "alr-1001"}
RESPONDER = AgentRole("responder", frozenset({"acknowledge_alert", "get_live_metrics"}), max_steps=6,
                      system_prompt="You acknowledge the root-cause alert when asked.")
LIMITS = Limits(tool_timeout_s=0.01, step_timeout_s=5.0, max_attempts=2)


class HangingBackend:
    """The first call to `hang_tool` never answers, so the executor times out; the world still saw the call."""

    def __init__(self, world: World, hang_tool: str | None = None) -> None:
        self._world = world
        self._hang_tool = hang_tool

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput:
        n = self._world.executions[name] = self._world.count(name) + 1
        if name == self._hang_tool and n == 1:
            await asyncio.sleep(3600)
        return ToolOutput(json.dumps({"tool": name, "arguments": arguments, "execution": n}, sort_keys=True))


class RetryOnTimeout:
    """Calls the write, and after a timeout asks for the identical write again inside the same step."""

    def __init__(self, tool: str, arguments: dict[str, Any]) -> None:
        self._call = ToolCall("c1", tool, arguments)
        self.tool_results: list[str] = []

    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        last = messages[-1]
        if last.role != "tool":
            return Message("assistant", "", (self._call,))
        self.tool_results.append(last.content)
        if "timed out" in last.content:
            return Message("assistant", "", (ToolCall("c2", self._call.name, dict(self._call.arguments)),))
        return Message("assistant", f"done: {last.content}")


class ReadAfterTimeout:
    """After the write times out, checks the metrics instead of retrying the write."""

    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        last = messages[-1]
        if last.role != "tool":
            return Message("assistant", "", (ToolCall("c1", "acknowledge_alert", dict(ACK)),))
        if "timed out" in last.content:
            return Message("assistant", "", (ToolCall("c2", "get_live_metrics", {"tenantId": "streamflix"}),))
        return Message("assistant", "could not confirm the acknowledgement; metrics checked")


async def respond(ctx: RunContext) -> str:
    return await ctx.step("respond", "responder", ctx.input)


def drive(tmp_path: Path, llm: Any, world: World, hang_tool: str | None) -> RunSummary:
    """Boot a fresh orchestrator per 'process', approving whatever the step asks for, until the run is terminal."""
    db = tmp_path / "o.db"
    for boot in range(6):
        orchestrator, store = make_orchestrator(
            db, world, llm_factory=lambda role, step, attempt: llm, limits=LIMITS,
            roles=(RESPONDER,), workflows={"ack": respond}, backend=HangingBackend(world, hang_tool))
        try:
            if boot == 0:
                summary = run(orchestrator.run("ack", "Acknowledge alr-1001 for streamflix.", RUN_ID))
            else:
                if store.get_run(RUN_ID).status == WAITING_APPROVAL:
                    RunControl(store).approve(RUN_ID, "respond")
                summary = run(orchestrator.resume(RUN_ID))
        finally:
            store.close()
        if summary.status in TERMINAL:
            return summary
    raise AssertionError("run did not reach a terminal state")


def test_a_write_that_timed_out_is_not_sent_again_when_the_model_retries_it(tmp_path: Path) -> None:
    world = World()
    llm = RetryOnTimeout("acknowledge_alert", ACK)
    summary = drive(tmp_path, llm, world, hang_tool="acknowledge_alert")
    assert any("timed out" in result for result in llm.tool_results), "the first write should have timed out"
    assert world.count("acknowledge_alert") == 1, (
        "a write whose outcome is unknown after a timeout must not be sent a second time,"
        f" but the backend saw it {world.count('acknowledge_alert')} times")
    assert summary.status == "failed"
    assert "outcome is unknown" in (summary.error or "")


def test_a_read_after_a_timed_out_write_still_runs(tmp_path: Path) -> None:
    world = World()
    summary = drive(tmp_path, ReadAfterTimeout(), world, hang_tool="acknowledge_alert")
    assert summary.status == "succeeded"
    assert (world.count("acknowledge_alert"), world.count("get_live_metrics")) == (1, 1)
