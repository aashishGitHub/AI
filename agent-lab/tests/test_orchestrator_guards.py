from __future__ import annotations

import json

import pytest

from agent.types import ToolSpec
from orchestrator.errors import HandoffRefused, PlanError
from orchestrator.guards import HandoffGuard, full_jitter_delay
from orchestrator.plan import MAX_SUBTASKS, parse_plan
from orchestrator.roles import AgentRole, check_roles
from tests.orchestrator_helpers import TOOLS, FixedRng

GOOD = json.dumps({"subtasks": [{"id": "alerts", "task": "List alerts"}, {"id": "metrics", "task": "Read metrics"}]})


class Recorder:
    def __init__(self, fraction: float) -> None:
        self.fraction, self.ranges = fraction, []

    def uniform(self, a: float, b: float) -> float:
        self.ranges.append((a, b))
        return a + (b - a) * self.fraction


def test_backoff_range_doubles_per_attempt_and_is_capped_with_full_jitter():
    rng = Recorder(0.5)
    delays = [full_jitter_delay(n, 0.5, 4.0, rng) for n in (1, 2, 3, 4, 5)]
    assert rng.ranges == [(0.0, 0.5), (0.0, 1.0), (0.0, 2.0), (0.0, 4.0), (0.0, 4.0)]
    assert delays == [0.25, 0.5, 1.0, 2.0, 2.0]


def test_backoff_with_a_zero_draw_waits_zero():
    assert full_jitter_delay(3, 0.5, 8.0, FixedRng(0.0)) == 0.0


def test_a_valid_plan_parses_into_subtasks():
    plan = parse_plan(GOOD)
    assert [(s.id, s.task) for s in plan] == [("alerts", "List alerts"), ("metrics", "Read metrics")]


@pytest.mark.parametrize(("text", "fragment"), [
    ("not json", "not valid JSON"),
    ("[]", "plan rejected"),
    (json.dumps({"subtasks": []}), "plan rejected"),
    (json.dumps({"subtasks": [{"id": "A B", "task": "x"}]}), "plan rejected"),
    (json.dumps({"subtasks": [{"id": "a"}]}), "plan rejected"),
    (json.dumps({"subtasks": [{"id": "a", "task": "x", "role": "responder"}]}), "plan rejected"),
    (json.dumps({"subtasks": [{"id": "a", "task": "x"}], "extra": 1}), "plan rejected"),
    (json.dumps({"subtasks": [{"id": f"t{i}", "task": "x"} for i in range(MAX_SUBTASKS + 1)]}), "plan rejected"),
    (json.dumps({"subtasks": [{"id": "a", "task": "x"}, {"id": "a", "task": "y"}]}), "duplicate subtask ids"),
])
def test_a_malformed_plan_is_rejected(text, fragment):
    with pytest.raises(PlanError, match=fragment):
        parse_plan(text)


def test_handoff_a_to_b_to_a_is_refused_as_a_cycle():
    guard = HandoffGuard(max_handoffs=5)
    guard.begin("a")
    guard.hand_off("b", frozenset({"b"}))
    with pytest.raises(HandoffRefused, match="cycle: a -> b -> a"):
        guard.hand_off("a", frozenset({"a"}))


def test_max_handoffs_is_enforced():
    guard = HandoffGuard(max_handoffs=1)
    guard.begin("a")
    guard.hand_off("b", frozenset({"b"}))
    with pytest.raises(HandoffRefused, match="max handoffs"):
        guard.hand_off("c", frozenset({"c"}))


def test_a_role_may_only_hand_off_to_its_declared_targets():
    guard = HandoffGuard(max_handoffs=5)
    guard.begin("a")
    with pytest.raises(HandoffRefused, match="may not hand off to c"):
        guard.hand_off("c", frozenset({"b"}))


def test_a_plain_step_starts_a_new_chain():
    guard = HandoffGuard(max_handoffs=1)
    guard.begin("a")
    guard.hand_off("b", frozenset({"b"}))
    guard.begin("a")
    guard.hand_off("b", frozenset({"b"}))


def test_a_role_sees_only_its_allowlisted_tools():
    role = AgentRole("investigator", frozenset({"list_active_alerts"}))
    assert [t.name for t in role.visible_tools(TOOLS)] == ["list_active_alerts"]
    assert AgentRole("planner").visible_tools(TOOLS) == []


def test_a_role_that_allows_a_tool_the_server_does_not_have_is_rejected_at_startup():
    with pytest.raises(ValueError, match="unknown tools"):
        check_roles([AgentRole("r", frozenset({"delete_everything"}))], TOOLS)


def test_a_handoff_to_an_unknown_role_is_rejected_at_startup():
    with pytest.raises(ValueError, match="unknown roles"):
        check_roles([AgentRole("a", handoff_to=frozenset({"ghost"}))], [ToolSpec("t", "", {}, True)])
