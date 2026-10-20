from __future__ import annotations

import asyncio
import json

import pytest

from agent.types import ToolCall
from orchestrator.control import RunControl
from orchestrator.guards import Limits
from orchestrator.journal import StoreApprover
from orchestrator.roles import AgentRole
from orchestrator.store import WorkflowStore
from orchestrator.triage import INPUT
from tests.helpers import run
from tests.orchestrator_helpers import (
    RUN_ID, TOOLS, CallThenEcho, FakeClock, FixedRng, Failing, World, make_orchestrator, new_audit, reactive_llm,
)


@pytest.fixture
def world() -> World:
    return World()


def start(tmp_path, world, **kwargs):
    orchestrator, store = make_orchestrator(tmp_path / "o.db", world, **kwargs)
    return orchestrator, store, run(orchestrator.run("triage", INPUT, RUN_ID))


def test_the_triage_run_pauses_at_the_write_and_no_write_has_happened(tmp_path, world):
    _, store, summary = start(tmp_path, world)
    assert summary.status == "waiting_approval"
    assert world.count("acknowledge_alert") == 0
    assert {s.step_id: s.status for s in store.steps(RUN_ID)}["respond"] == "waiting_approval"
    assert [e.type for e in store.events(RUN_ID)][-2:] == ["step_waiting_approval", "run_waiting_approval"]


def test_resume_without_an_approval_stays_paused(tmp_path, world):
    orchestrator, store, _ = start(tmp_path, world)
    assert run(orchestrator.resume(RUN_ID)).status == "waiting_approval"
    assert world.count("acknowledge_alert") == 0


def test_approve_then_resume_runs_the_write_once_and_finishes(tmp_path, world):
    orchestrator, store, _ = start(tmp_path, world)
    RunControl(store).approve(RUN_ID, "respond")
    summary = run(orchestrator.resume(RUN_ID))
    assert summary.status == "succeeded" and world.count("acknowledge_alert") == 1
    assert summary.output.startswith("Root cause: alr-1001 on streamflix.")
    assert '"execution": 1' in summary.output
    assert store.get_step(RUN_ID, "respond").attempt == 1


def test_deny_fails_the_run_cleanly_and_the_write_never_happens(tmp_path, world):
    orchestrator, store, _ = start(tmp_path, world)
    RunControl(store).deny(RUN_ID, "respond")
    summary = run(orchestrator.resume(RUN_ID))
    assert (summary.status, summary.error) == ("failed", "approval denied for step respond")
    assert world.count("acknowledge_alert") == 0
    assert "approval_denied" in [e.type for e in store.events(RUN_ID)]


def test_an_approval_is_bound_to_the_exact_call_that_was_approved(tmp_path, world):
    created = []

    def factory(role, step_id, attempt):
        if step_id != "respond":
            return reactive_llm(role, step_id, attempt)
        created.append(step_id)
        note = "first" if len(created) == 1 else "changed after approval"
        return CallThenEcho("acknowledge_alert", {"tenantId": "streamflix", "alertId": "alr-1001", "note": note})

    orchestrator, store, _ = start(tmp_path, world, llm_factory=factory)
    RunControl(store).approve(RUN_ID, "respond")
    summary = run(orchestrator.resume(RUN_ID))
    assert summary.status == "waiting_approval"
    assert world.count("acknowledge_alert") == 0
    assert store.get_step(RUN_ID, "respond").approval is None
    assert [e.type for e in store.events(RUN_ID)].count("step_waiting_approval") == 2


def test_the_approver_denies_by_default_and_approves_only_the_granted_call(tmp_path):
    store = WorkflowStore(tmp_path / "o.db")
    store.create_run("r", "wf", "in")
    store.set_run_status("r", "running")
    store.ensure_step("r", "s", "responder")
    store.begin_attempt("r", "s")
    granted = ToolCall("1", "acknowledge_alert", {"alertId": "a"})
    other = ToolCall("2", "acknowledge_alert", {"alertId": "b"})
    spec = next(t for t in TOOLS if t.name == "acknowledge_alert")
    assert StoreApprover(store, "r", "s")(granted, spec) is False
    store.pause_for_approval("r", "s", json.dumps({"tool": "acknowledge_alert", "arguments": {"alertId": "a"}}, sort_keys=True))
    store.approve_step("r", "s")
    assert StoreApprover(store, "r", "s")(granted, spec) is True
    assert StoreApprover(store, "r", "s")(other, spec) is False


def test_a_role_cannot_call_a_tool_outside_its_allowlist(tmp_path, world):
    audit = new_audit()

    def factory(role, step_id, attempt):
        if step_id == "work-alerts":
            return CallThenEcho("acknowledge_alert", {"tenantId": "streamflix", "alertId": "alr-1001"})
        return reactive_llm(role, step_id, attempt)

    start(tmp_path, world, llm_factory=factory, audit=audit)
    events = [json.loads(line) for line in audit.getvalue().splitlines()]
    refused = [e for e in events if e["event"] == "tool_call" and e["run_id"].startswith(f"{RUN_ID}/work-alerts")]
    assert [(e["tool"], e["error_kind"], e["executed"]) for e in refused] == [("acknowledge_alert", "unknown_tool", False)]
    assert world.count("acknowledge_alert") == 0


def test_the_model_is_only_shown_its_roles_tools(tmp_path, world):
    seen = {}

    def factory(role, step_id, attempt):
        llm = reactive_llm(role, step_id, attempt)
        original = llm.complete

        async def spy(messages, tools):
            seen[step_id] = sorted(t.name for t in tools)
            return await original(messages, tools)

        llm.complete = spy
        return llm

    start(tmp_path, world, llm_factory=factory)
    assert seen["plan"] == [] and seen["aggregate"] == []
    assert seen["work-alerts"] == ["explain_alert", "get_live_metrics", "list_active_alerts"]
    assert seen["respond"] == ["acknowledge_alert", "explain_alert"]


def test_every_step_is_audited_with_the_run_step_and_attempt(tmp_path, world):
    audit = new_audit()
    start(tmp_path, world, audit=audit)
    run_ids = {json.loads(line)["run_id"] for line in audit.getvalue().splitlines()}
    assert {"r1/plan#1", "r1/work-alerts#1", "r1/aggregate#1", "r1/respond#1"} <= run_ids


def test_an_llm_error_is_retried_with_exponential_backoff_and_then_succeeds(tmp_path, world):
    sleeps = []

    async def sleeper(seconds):
        sleeps.append(seconds)

    def factory(role, step_id, attempt):
        return Failing() if step_id == "plan" and attempt <= 2 else reactive_llm(role, step_id, attempt)

    _, store, summary = start(tmp_path, world, llm_factory=factory, sleeper=sleeper, rng=FixedRng(1.0),
                              limits=Limits(backoff_base_s=0.5, backoff_cap_s=8.0))
    assert summary.status == "waiting_approval"
    assert sleeps == [0.5, 1.0]
    assert store.get_step(RUN_ID, "plan").attempt == 3
    retries = [e.payload["reason"] for e in store.events(RUN_ID) if e.type == "step_retry_scheduled"]
    assert retries == ["llm error: boom", "llm error: boom"]


def test_a_step_that_keeps_failing_fails_the_run_with_the_reason(tmp_path, world):
    sleeps = []

    async def sleeper(seconds):
        sleeps.append(seconds)

    _, store, summary = start(tmp_path, world, llm_factory=lambda r, s, a: Failing(), sleeper=sleeper,
                              limits=Limits(max_attempts=3))
    assert summary.status == "failed"
    assert summary.error == "step plan gave up after 3 attempts: llm error: boom"
    assert len(sleeps) == 2 and store.get_step(RUN_ID, "plan").status == "failed"


def test_a_malformed_plan_fails_the_run_without_a_retry(tmp_path, world):
    sleeps = []

    async def sleeper(seconds):
        sleeps.append(seconds)

    def factory(role, step_id, attempt):
        if step_id == "plan":
            from agent.llm import ScriptedLLM, turns_from_dicts
            return ScriptedLLM(turns_from_dicts([{"content": '{"subtasks": []}'}]))
        return reactive_llm(role, step_id, attempt)

    _, store, summary = start(tmp_path, world, llm_factory=factory, sleeper=sleeper)
    assert summary.status == "failed" and summary.error.startswith("plan rejected")
    assert sleeps == [] and store.get_step(RUN_ID, "plan").attempt == 1
    assert [s.step_id for s in store.steps(RUN_ID)] == ["plan"]


def test_a_step_that_exceeds_its_timeout_is_retried_then_fails(tmp_path, world):
    class Hangs:
        async def complete(self, messages, tools):
            await asyncio.Event().wait()

    _, store, summary = start(tmp_path, world, llm_factory=lambda r, s, a: Hangs(),
                              limits=Limits(step_timeout_s=0.02, max_attempts=2))
    assert summary.status == "failed"
    assert summary.error == "step plan gave up after 2 attempts: step timed out after 0.02 s"


def test_the_wall_clock_budget_is_checked_against_the_injected_clock(tmp_path, world):
    clock = FakeClock()

    def factory(role, step_id, attempt):
        if step_id == "work-alerts":
            clock.advance(301)
        return reactive_llm(role, step_id, attempt)

    _, store, summary = start(tmp_path, world, llm_factory=factory, clock=clock, limits=Limits(wall_budget_s=300))
    assert summary.status == "failed" and summary.error == "wall-clock budget of 300 s exceeded"
    assert store.get_step(RUN_ID, "work-metrics").attempt == 0


def test_the_global_step_limit_stops_the_run(tmp_path, world):
    _, store, summary = start(tmp_path, world, limits=Limits(global_max_steps=2))
    assert summary.status == "failed" and summary.error == "global step limit of 2 reached"
    assert store.attempts_started(RUN_ID) == 2


def test_a_handoff_cycle_fails_the_run_before_the_second_handoff_runs(tmp_path, world):
    roles = (AgentRole("a", handoff_to=frozenset({"b"})), AgentRole("b", handoff_to=frozenset({"a"})))

    async def ping_pong(ctx):
        await ctx.step("s1", "a", "go")
        await ctx.handoff("s2", "b", "go")
        return await ctx.handoff("s3", "a", "go")

    def factory(role, step_id, attempt):
        return CallThenEcho("get_live_metrics", {"tenantId": "t"})

    orchestrator, store = make_orchestrator(tmp_path / "o.db", world, roles=roles, llm_factory=factory,
                                            workflows={"loop": ping_pong})
    summary = run(orchestrator.run("loop", "go", RUN_ID))
    assert summary.status == "failed" and "handoff cycle: a -> b -> a" in summary.error
    assert store.get_step(RUN_ID, "s3") is None
    assert [e.type for e in store.events(RUN_ID)].count("handoff") == 1


def test_cancel_while_waiting_for_approval_stops_everything(tmp_path, world):
    orchestrator, store, _ = start(tmp_path, world)
    control = RunControl(store)
    control.cancel(RUN_ID)
    assert run(orchestrator.resume(RUN_ID)).status == "cancelled"
    assert store.get_step(RUN_ID, "respond").status == "cancelled" and world.count("acknowledge_alert") == 0


def test_cancel_noticed_at_a_step_boundary_stops_before_the_next_tool_runs(tmp_path, world):
    holder = {}

    def cancel_after_first_worker(point, step_id):
        if (point, step_id) == ("after_step_commit", "work-alerts"):
            RunControl(holder["store"]).cancel(RUN_ID)

    orchestrator, store = make_orchestrator(tmp_path / "o.db", world, crash=cancel_after_first_worker)
    holder["store"] = store
    summary = run(orchestrator.run("triage", INPUT, RUN_ID))
    assert summary.status == "cancelled"
    assert (world.count("list_active_alerts"), world.count("get_live_metrics")) == (1, 0)


def test_cancel_during_a_step_discards_that_steps_result(tmp_path, world):
    holder = {}

    def factory(role, step_id, attempt):
        if step_id == "work-alerts":
            RunControl(holder["store"]).cancel(RUN_ID)
        return reactive_llm(role, step_id, attempt)

    orchestrator, store = make_orchestrator(tmp_path / "o.db", world, llm_factory=factory)
    holder["store"] = store
    summary = run(orchestrator.run("triage", INPUT, RUN_ID))
    assert summary.status == "cancelled" and store.get_step(RUN_ID, "work-alerts").status == "cancelled"


def test_a_crash_looping_step_is_stopped_by_max_attempts(tmp_path, world):
    orchestrator, store = make_orchestrator(tmp_path / "o.db", world, limits=Limits(max_attempts=2))
    store.create_run(RUN_ID, "triage", INPUT)
    store.set_run_status(RUN_ID, "running")
    store.ensure_step(RUN_ID, "plan", "planner")
    store.begin_attempt(RUN_ID, "plan")
    store.begin_attempt(RUN_ID, "plan")
    summary = run(orchestrator.resume(RUN_ID))
    assert summary.status == "failed" and "used all 2 attempts" in summary.error


def test_a_prompt_provider_overrides_the_role_prompt(tmp_path, world):
    seen = {}

    def factory(role, step_id, attempt):
        llm = reactive_llm(role, step_id, attempt)
        original = llm.complete

        async def spy(messages, tools):
            seen[step_id] = messages[0].content
            return await original(messages, tools)

        llm.complete = spy
        return llm

    orchestrator, _ = make_orchestrator(tmp_path / "o.db", world, llm_factory=factory)
    orchestrator.prompt_provider = lambda name: f"registry prompt for {name}"
    run(orchestrator.run("triage", INPUT, RUN_ID))
    assert seen["plan"] == "registry prompt for planner" and seen["respond"] == "registry prompt for responder"


def test_describe_prints_the_timeline_with_status_and_attempts(tmp_path, world):
    _, store, _ = start(tmp_path, world)
    text = RunControl(store).describe(RUN_ID)
    assert "run r1  workflow=triage  status=waiting_approval" in text
    assert "respond            responder      waiting_approval  attempt=1" in text
    assert "run_waiting_approval" in text and "handoff" in text
