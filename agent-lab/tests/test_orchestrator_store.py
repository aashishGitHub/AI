from __future__ import annotations

import sqlite3

import pytest

from orchestrator.store import InvalidTransition, WorkflowStore
from tests.orchestrator_helpers import FakeClock


@pytest.fixture
def store(tmp_path):
    s = WorkflowStore(tmp_path / "o.db", FakeClock())
    s.create_run("r1", "wf", "input")
    yield s
    s.close()


def types(store: WorkflowStore) -> list[str]:
    return [e.type for e in store.events("r1")]


def test_database_is_in_wal_mode_and_a_new_run_is_pending_with_an_event(store):
    assert store._db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert store.get_run("r1").status == "pending"
    assert types(store) == ["run_created"]


def test_every_transition_appends_exactly_one_event(store):
    store.set_run_status("r1", "running")
    store.ensure_step("r1", "s1", "planner")
    store.begin_attempt("r1", "s1")
    store.succeed_step("r1", "s1", "out")
    store.set_run_status("r1", "succeeded", output="done")
    assert types(store) == ["run_created", "run_running", "step_created", "step_running", "step_succeeded",
                            "run_succeeded"]


def test_ensure_step_is_idempotent_and_does_not_duplicate_the_event(store):
    store.ensure_step("r1", "s1", "planner")
    store.ensure_step("r1", "s1", "planner")
    assert types(store).count("step_created") == 1


def test_an_illegal_transition_is_refused_and_leaves_no_trace(store):
    store.set_run_status("r1", "running")
    store.set_run_status("r1", "succeeded", output="x")
    before = types(store)
    with pytest.raises(InvalidTransition):
        store.set_run_status("r1", "running")
    assert store.get_run("r1").status == "succeeded" and types(store) == before


def test_a_pending_step_cannot_jump_to_succeeded(store):
    store.ensure_step("r1", "s1", "planner")
    with pytest.raises(InvalidTransition):
        store.succeed_step("r1", "s1", "out")


def test_begin_attempt_counts_attempts_and_a_running_step_restarts_with_attempt_plus_one(store):
    store.ensure_step("r1", "s1", "planner")
    assert store.begin_attempt("r1", "s1").attempt == 1
    assert store.begin_attempt("r1", "s1").attempt == 2
    assert store.attempts_started("r1") == 2


def test_retry_goes_back_to_pending_and_keeps_the_error_in_the_event(store):
    store.ensure_step("r1", "s1", "planner")
    store.begin_attempt("r1", "s1")
    store.schedule_retry("r1", "s1", "llm error: boom", 0.5)
    event = store.events("r1")[-1]
    assert (store.get_step("r1", "s1").status, event.type, event.payload["reason"]) == (
        "pending", "step_retry_scheduled", "llm error: boom")


def test_events_are_append_only(store):
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        store._db.execute("UPDATE events SET type = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        store._db.execute("DELETE FROM events")


def test_a_failed_transaction_rolls_back_the_state_change_and_its_event(store):
    store.set_run_status("r1", "running")
    store.ensure_step("r1", "s1", "planner")
    store.begin_attempt("r1", "s1")
    store._db.execute("CREATE TRIGGER boom BEFORE INSERT ON events WHEN NEW.type = 'step_succeeded'"
                      " BEGIN SELECT RAISE(ABORT, 'disk full'); END;")
    with pytest.raises(sqlite3.DatabaseError, match="disk full"):
        store.succeed_step("r1", "s1", "out")
    assert store.get_step("r1", "s1").status == "running"


def test_state_survives_reopening_the_database(tmp_path):
    path = tmp_path / "o.db"
    first = WorkflowStore(path)
    first.create_run("r1", "wf", "input")
    first.ensure_step("r1", "s1", "planner")
    first.close()
    second = WorkflowStore(path)
    assert second.get_run("r1").workflow == "wf" and second.get_step("r1", "s1").role == "planner"
    second.close()


def test_journal_is_keyed_by_run_step_and_call_index(store):
    store.journal_start("r1", "s1", 0, "acknowledge_alert", '{"a": 1}', False)
    assert store.journal_get("r1", "s1", 0).status == "started"
    store.journal_finish("r1", "s1", 0, "ok", False)
    entry = store.journal_get("r1", "s1", 0)
    assert (entry.status, entry.content, entry.is_error, entry.read_only) == ("done", "ok", False, False)
    assert store.journal_get("r1", "s1", 1) is None and store.journal_get("r1", "s2", 0) is None


def test_cancel_moves_the_run_and_every_open_step_in_one_transaction(store):
    store.set_run_status("r1", "running")
    for step in ("a", "b"):
        store.ensure_step("r1", step, "planner")
    store.begin_attempt("r1", "a")
    store.succeed_step("r1", "a", "out")
    store.cancel_run("r1")
    assert store.get_run("r1").status == "cancelled"
    assert {s.step_id: s.status for s in store.steps("r1")} == {"a": "succeeded", "b": "cancelled"}


def test_approve_requires_a_step_that_is_waiting(store):
    store.ensure_step("r1", "s1", "responder")
    with pytest.raises(InvalidTransition):
        store.approve_step("r1", "s1")
