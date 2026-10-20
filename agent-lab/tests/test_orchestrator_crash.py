from __future__ import annotations

import pytest

from orchestrator.crash import AFTER_STEP_COMMIT, BEFORE_STEP, STEP_STARTED, TOOL_EXECUTED, TOOL_JOURNALED
from tests.orchestrator_helpers import Outcome, drive

CRASH_MATRIX = [
    pytest.param(BEFORE_STEP, "plan", id="before-first-step"),
    pytest.param(BEFORE_STEP, "respond", id="before-write-step"),
    pytest.param(STEP_STARTED, "respond", id="write-step-running-at-crash"),
    pytest.param(TOOL_JOURNALED, "respond", id="after-write-journaled-before-commit"),
    pytest.param(AFTER_STEP_COMMIT, "respond", id="after-write-step-commit"),
    pytest.param(AFTER_STEP_COMMIT, "work-alerts", id="mid-fan-out-after-first-worker"),
    pytest.param(BEFORE_STEP, "work-metrics", id="mid-fan-out-before-second-worker"),
    pytest.param(TOOL_JOURNALED, "work-metrics", id="mid-fan-out-read-journaled-before-commit"),
    pytest.param(TOOL_EXECUTED, "work-metrics", id="mid-fan-out-read-executed-not-journaled"),
]


@pytest.fixture
def reference(tmp_path_factory) -> Outcome:
    return drive(tmp_path_factory.mktemp("reference"))


def test_the_uninterrupted_run_pauses_for_approval_then_writes_exactly_once(reference):
    assert reference.summary.status == "succeeded"
    assert (reference.crashes, reference.world.count("acknowledge_alert")) == (0, 1)
    assert "step_waiting_approval" in reference.event_types and "approval_granted" in reference.event_types
    assert '"execution": 1' in reference.summary.output


@pytest.mark.parametrize(("point", "step_id"), CRASH_MATRIX)
def test_a_crash_at_every_boundary_gives_the_same_answer_and_one_real_write(tmp_path, reference, point, step_id):
    outcome = drive(tmp_path, point, step_id)
    assert outcome.crashes == 1
    assert outcome.summary.status == "succeeded"
    assert outcome.summary.output == reference.summary.output
    assert outcome.world.count("acknowledge_alert") == 1
    assert all(status == "succeeded" for status, _ in outcome.steps.values())


def test_a_step_running_at_the_crash_is_re_run_with_attempt_plus_one(tmp_path):
    outcome = drive(tmp_path, TOOL_JOURNALED, "respond")
    assert outcome.steps["respond"] == ("succeeded", 2)
    assert "tool_replayed" in outcome.event_types


def test_a_write_journaled_before_the_crash_is_replayed_not_executed_again(tmp_path):
    outcome = drive(tmp_path, TOOL_JOURNALED, "respond")
    assert outcome.world.count("acknowledge_alert") == 1
    assert outcome.event_types.count("tool_journaled") == 3
    assert outcome.event_types.count("tool_replayed") == 1


def test_completed_steps_are_not_re_run_after_a_crash(tmp_path):
    outcome = drive(tmp_path, AFTER_STEP_COMMIT, "work-alerts")
    created = outcome.llm_created
    assert created.count(("plan", 1)) == 1
    assert created.count(("work-alerts", 1)) == 1
    assert [s for s in created if s[0] == "work-metrics"] == [("work-metrics", 1)]
    assert outcome.steps["plan"] == ("succeeded", 1) and outcome.steps["work-alerts"] == ("succeeded", 1)


def test_a_crash_between_a_write_and_its_journal_entry_is_never_repeated_and_fails_the_run_cleanly(tmp_path):
    outcome = drive(tmp_path, TOOL_EXECUTED, "respond")
    assert outcome.world.count("acknowledge_alert") == 1
    assert outcome.summary.status == "failed"
    assert "may already have run before a crash" in outcome.summary.error
    assert outcome.steps["respond"][0] == "failed"
