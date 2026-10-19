from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
import yaml

from agent.cli import build_parser, main
from agent.llm import ScriptExhausted, load_script, turns_from_dicts
from evals.cli import CASES_DIR
from tests.helpers import run

ACK_CASE = CASES_DIR / "07_ack_approved.yaml"


def run_cli(tmp_path: Path, *extra: str, script: Path = ACK_CASE):
    audit = tmp_path / "audit.jsonl"
    state = tmp_path / "state.json"
    code = main(["Acknowledge alert alr-1001 for tenant streamflix.", "--script", str(script),
                 "--audit", str(audit), "--state-file", str(state), *extra])
    events = [json.loads(line) for line in audit.read_text().splitlines()]
    return code, events, state


def test_write_tool_is_denied_by_default_and_the_server_state_is_never_created(tmp_path, capsys):
    code, events, state = run_cli(tmp_path)
    out = capsys.readouterr().out
    assert code == 0
    assert "approval=DENIED result=denied" in out
    assert not state.exists()
    assert [e["approval"]["approved"] for e in events if e["event"] == "tool_call"] == [False]


def test_approve_flag_lets_the_named_write_tool_through(tmp_path, capsys):
    code, events, state = run_cli(tmp_path, "--approve", "acknowledge_alert")
    assert code == 0
    assert "approval=approved result=ok" in capsys.readouterr().out
    assert list(json.loads(state.read_text())["acknowledged"]) == ["alr-1001"]
    assert [e["event"] for e in events][0] == "run_start" and events[-1]["event"] == "run_end"


def test_ask_flag_prompts_on_the_terminal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    code, _, state = run_cli(tmp_path, "--ask")
    assert code == 0
    assert list(json.loads(state.read_text())["acknowledged"]) == ["alr-1001"]


def test_exit_code_is_nonzero_when_the_run_does_not_reach_a_final_answer(tmp_path, capsys):
    script = tmp_path / "short.yaml"
    script.write_text(yaml.safe_dump([{"tool_calls": [{"name": "list_active_alerts", "arguments": {"tenantId": "streamflix"}}]}]))
    code, events, _ = run_cli(tmp_path, script=script)
    assert code == 1
    assert "stop_reason=llm_error" in capsys.readouterr().out
    assert events[-1]["stop_reason"] == "llm_error"


def test_must_choose_exactly_one_llm_source():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["prompt"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["prompt", "--model", "m", "--script", "s.yaml"])


def test_load_script_accepts_a_bare_list_or_a_case_file(tmp_path):
    bare = tmp_path / "bare.yaml"
    bare.write_text(yaml.safe_dump([{"content": "hi"}]))
    for path in (bare, ACK_CASE):
        llm = load_script(path)
        assert run(llm.complete([], [])).role == "assistant"


def test_scripted_llm_raises_when_asked_for_more_turns_than_it_has():
    from agent.llm import ScriptedLLM

    llm = ScriptedLLM(turns_from_dicts([{"content": "only"}]))
    run(llm.complete([], []))
    with pytest.raises(ScriptExhausted):
        run(llm.complete([], []))


def test_tool_call_ids_in_a_script_are_unique_per_turn_and_position():
    turns = turns_from_dicts([{"tool_calls": [{"name": "a"}, {"name": "b"}]}, {"tool_calls": [{"name": "c"}]}])
    ids = [c.id for t in turns for c in t.tool_calls]
    assert ids == ["call-1-1", "call-1-2", "call-2-1"]
