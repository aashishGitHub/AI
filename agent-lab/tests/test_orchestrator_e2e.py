from __future__ import annotations

import json

from orchestrator.cli import EXIT_CRASHED, main
from orchestrator.control import RunControl
from orchestrator.store import WorkflowStore
from orchestrator.triage import INPUT, triage_orchestrator
from tests.helpers import run

EXPECTED_OUTPUT = (
    "Root cause: alr-1001 on streamflix, error rate above 5% in us-east-1.\n"
    "Acknowledged alr-1001 on streamflix."
)


def test_triage_end_to_end_over_the_in_process_mcp_server(tmp_path):
    db, state = tmp_path / "o.db", tmp_path / "state.json"

    async def scenario():
        async with triage_orchestrator(db, state) as orchestrator:
            paused = await orchestrator.run("triage", INPUT, "e2e")
            assert paused.status == "waiting_approval" and not state.exists()
            RunControl(orchestrator.store).approve("e2e", "respond")
            return await orchestrator.resume("e2e")

    summary = run(scenario())
    assert (summary.status, summary.output) == ("succeeded", EXPECTED_OUTPUT)
    assert list(json.loads(state.read_text())["acknowledged"]) == ["alr-1001"]
    store = WorkflowStore(db)
    steps = {s.step_id: (s.role, s.status, s.attempt) for s in store.steps("e2e")}
    assert steps == {
        "plan": ("planner", "succeeded", 1),
        "work-alerts": ("investigator", "succeeded", 1),
        "work-metrics": ("investigator", "succeeded", 1),
        "aggregate": ("aggregator", "succeeded", 1),
        "respond": ("responder", "succeeded", 1),
    }
    store.close()


def test_cli_run_approve_resume_status(tmp_path, capsys):
    db = str(tmp_path / "o.db")
    assert main(["--db", db, "run", "--run-id", "c1"]) == 3
    assert main(["--db", db, "approve", "c1", "respond"]) == 0
    assert main(["--db", db, "resume", "c1"]) == 0
    out = capsys.readouterr().out
    assert "run c1: waiting_approval" in out and "run c1: succeeded" in out and EXPECTED_OUTPUT in out
    assert main(["--db", db, "status", "c1"]) == 0
    assert "status=succeeded" in capsys.readouterr().out


def test_cli_simulated_crash_then_resume_finishes_the_run(tmp_path, capsys):
    db = str(tmp_path / "o.db")
    assert main(["--db", db, "run", "--run-id", "c2"]) == 3
    assert main(["--db", db, "approve", "c2", "respond"]) == 0
    assert main(["--db", db, "resume", "c2", "--crash-at", "tool_journaled:respond"]) == EXIT_CRASHED
    assert main(["--db", db, "resume", "c2"]) == 0
    assert main(["--db", db, "status", "c2"]) == 0
    out = capsys.readouterr().out
    assert "simulated crash at tool_journaled@respond" in out
    assert "tool_replayed" in out and "run_succeeded" in out


def test_cli_deny_fails_the_run(tmp_path, capsys):
    db = str(tmp_path / "o.db")
    assert main(["--db", db, "run", "--run-id", "c3"]) == 3
    assert main(["--db", db, "deny", "c3", "respond"]) == 0
    assert main(["--db", db, "resume", "c3"]) == 1
    assert "approval denied for step respond" in capsys.readouterr().out
