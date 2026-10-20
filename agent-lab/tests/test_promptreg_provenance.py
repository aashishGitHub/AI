from __future__ import annotations

import io
import json

from agent.audit import AuditLog
from agent.session import run_session
from evals.runner import in_process_server
from promptreg.provenance import record_prompt_ref
from promptreg.store import sha256_hex
from tests.helpers import final_turn, run, scripted, tool_turn
from tests.promptreg_helpers import new_registry


def run_with_ref(tmp_path, ref, llm, prompt="Are there any active alerts right now?", run_id="run-a"):
    stream = io.StringIO()
    audit = AuditLog(stream, run_id=run_id)
    record_prompt_ref(audit, ref)
    result = run(run_session(prompt, llm, in_process_server(tmp_path / "state.json"), audit, system_prompt=ref.text))
    return result, [json.loads(line) for line in stream.getvalue().splitlines()]


def test_the_audit_log_names_the_exact_prompt_version_the_model_was_given(tmp_path):
    registry, store = new_registry(tmp_path / "prompts")
    registry.add_version("system", "You are version one.", "x", "c")
    ref = registry.resolve("system", "run-a")
    llm = scripted(final_turn("Which tenant do you mean?"))

    result, events = run_with_ref(tmp_path, ref, llm)

    assert result.stop_reason == "final"
    assert events[0]["event"] == "prompt_resolved"
    assert {k: events[0][k] for k in ("name", "version", "sha256", "reason")} == {
        "name": "system",
        "version": 1,
        "sha256": store.load_index("system").versions[1].sha256,
        "reason": "production: no canary configured",
    }
    assert events[1]["event"] == "run_start"
    system_message = llm.requests[0][0][0]
    assert (system_message.role, system_message.content) == ("system", "You are version one.")
    assert sha256_hex(system_message.content) == events[0]["sha256"]


def test_a_changed_prompt_text_gives_a_new_version_and_a_new_sha256_in_the_log(tmp_path):
    registry, _ = new_registry(tmp_path / "prompts")
    registry.add_version("system", "You are version one.", "x", "c")
    registry.add_version("system", "You are version one. Ask for the tenant.", "x", "c")
    first = registry.resolve("system", "run-a", version=1)
    second = registry.resolve("system", "run-a", version=2)

    _, first_events = run_with_ref(tmp_path, first, scripted(final_turn("ok")))
    _, second_events = run_with_ref(tmp_path, second, scripted(final_turn("ok")))

    assert (first_events[0]["version"], second_events[0]["version"]) == (1, 2)
    assert first_events[0]["sha256"] != second_events[0]["sha256"]
    assert second_events[0]["reason"] == "explicit version 2"


def test_a_canary_run_is_logged_with_the_bucket_that_chose_it(tmp_path):
    registry, _ = new_registry(tmp_path / "prompts")
    registry.add_version("system", "stable", "x", "c")
    registry.add_version("system", "candidate", "x", "c")
    registry.set_canary("system", 2, 100)
    ref = registry.resolve("system", "run-a")

    _, events = run_with_ref(tmp_path, ref, scripted(tool_turn("list_active_alerts", tenantId="streamflix"), final_turn("done")))

    assert events[0]["version"] == 2
    assert events[0]["reason"].startswith("canary: bucket ")
    assert [e["event"] for e in events].count("tool_call") == 1
