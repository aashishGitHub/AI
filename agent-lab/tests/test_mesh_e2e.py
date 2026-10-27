from __future__ import annotations

import asyncio

from mesh.delegate import QueueTransport
from mesh.queue import MessageQueue, process_one
from mesh.service import AgentService
from tests.helpers import final_turn, run, tool_turn
from tests.mesh_helpers import NOW, SECRET, http_to, rig


def tool_result(log: list[dict]) -> str:
    return next(line for line in log if line["event"] == "tool_call")["result"]


def test_triage_delegates_to_the_investigator_over_http_and_both_audit_logs_share_the_correlation_id() -> None:
    async def scenario() -> None:
        async with rig(http_to) as mesh:
            task = await mesh.triage_task("corr-42")
        assert task["state"] == "completed"
        assert task["result"]["final_text"] == "Root cause is alr-1001."
        assert task["result"]["tools_called"] == ["ask_investigator"]
        assert {line["run_id"] for line in mesh.inv_log()} == {"corr-42"}
        assert {line["run_id"] for line in mesh.tri_log()} == {"corr-42"}
        received = next(line for line in mesh.inv_log() if line["event"] == "task_received")
        assert received["sender"] == "triage" and received["hop_count"] == 1
        assert "alr-1001" in tool_result(mesh.tri_log())

    run(scenario())


def test_the_same_delegation_works_over_the_queue_transport() -> None:
    queue = MessageQueue()

    def via_queue(investigator: AgentService) -> QueueTransport:
        return QueueTransport(queue, investigator.store, SECRET, "triage", poll_interval_s=0.0, clock=lambda: NOW)

    async def worker(investigator: AgentService) -> None:
        while not await process_one(queue, investigator.handle):
            await asyncio.sleep(0)

    async def scenario() -> None:
        async with rig(via_queue) as mesh:
            pump = asyncio.create_task(worker(mesh.investigator))
            task = await mesh.triage_task("corr-7")
            await pump
        assert task["state"] == "completed"
        assert "alr-1001" in tool_result(mesh.tri_log())
        assert {line["run_id"] for line in mesh.inv_log()} == {"corr-7"}

    run(scenario())


def test_a_hop_count_past_the_receivers_limit_is_refused_and_the_caller_sees_a_tool_error() -> None:
    script = [tool_turn("ask_investigator", prompt="List alerts for streamflix."), final_turn("could not ask")]

    async def scenario() -> None:
        async with rig(http_to, investigator_max_hops=1, triage_script=script) as mesh:
            task = await mesh.triage_task("corr-9", hop_count=1)
        assert task["state"] == "completed"
        record = next(line for line in mesh.tri_log() if line["event"] == "tool_call")
        assert record["error_kind"] == "tool_error"
        assert "422" in record["result"]
        assert not any(line["event"] == "task_received" for line in mesh.inv_log())

    run(scenario())
