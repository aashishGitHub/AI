from __future__ import annotations

import json

from agent.approval import ApprovalGate, allow_tools
from agent.executor import ToolExecutor
from agent.llm import ScriptExhausted
from agent.loop import SYSTEM_PROMPT, run_agent
from agent.types import ToolOutput
from tests.helpers import READ_TOOL, WRITE_TOOL, FakeBackend, final_turn, new_audit, run, scripted, tool_turn

TOOLS = [READ_TOOL, WRITE_TOOL]


def drive(llm, backend=None, approver=None, max_steps=5, prompt="hi", grounded_args=()):
    audit, stream = new_audit()
    gate = ApprovalGate(approver) if approver else ApprovalGate()
    executor = ToolExecutor(backend or FakeBackend(), TOOLS, gate, grounded_args=grounded_args)
    result = run(run_agent(prompt, llm, executor, TOOLS, audit, max_steps))
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    return result, events


def test_answer_without_tools_finishes_in_one_step():
    result, _ = drive(scripted(final_turn("hello")))
    assert (result.stop_reason, result.steps, result.final_text) == ("final", 1, "hello")
    assert result.tool_records == ()


def test_starts_with_the_system_prompt_then_the_user_prompt():
    llm = scripted(final_turn("ok"))
    drive(llm)
    first_request_messages, tools = llm.requests[0]
    assert [m.role for m in first_request_messages] == ["system", "user"]
    assert first_request_messages[0].content == SYSTEM_PROMPT
    assert first_request_messages[1].content == "hi"
    assert [t.name for t in tools] == ["get_thing", "change_thing"]


def test_tool_result_is_fed_back_to_the_model_on_the_next_turn():
    llm = scripted(tool_turn("get_thing", tenantId="t"), final_turn("done"))
    result, _ = drive(llm)
    second_request_messages, _ = llm.requests[1]
    assert [m.role for m in second_request_messages] == ["system", "user", "assistant", "tool"]
    tool_message = second_request_messages[-1]
    assert tool_message.tool_name == "get_thing"
    assert tool_message.content == '{"ok": "get_thing"}'
    assert (result.stop_reason, result.steps) == ("final", 2)


def test_loop_stops_at_max_steps_when_the_model_never_answers():
    llm = scripted(*[tool_turn("get_thing", tenantId="t") for _ in range(10)])
    result, events = drive(llm, max_steps=3)
    assert (result.stop_reason, result.steps, result.final_text) == ("max_steps", 3, "")
    assert len(result.tool_records) == 3
    assert events[-1]["event"] == "run_end" and events[-1]["stop_reason"] == "max_steps"


def test_model_failure_ends_the_run_cleanly_and_is_audited():
    result, events = drive(scripted(tool_turn("get_thing", tenantId="t")))
    assert result.stop_reason == "llm_error"
    assert "script has 1 turn(s)" in (result.error or "")
    assert [e["event"] for e in events if e["event"] == "llm_error"] == ["llm_error"]


def test_script_exhausted_is_an_llm_error_subclass():
    from agent.types import LLMError

    assert issubclass(ScriptExhausted, LLMError)


def test_model_can_self_correct_after_an_invalid_arguments_error():
    llm = scripted(tool_turn("get_thing"), tool_turn("get_thing", tenantId="streamflix"), final_turn("fixed"))
    backend = FakeBackend()
    result, _ = drive(llm, backend)
    assert [r.error_kind for r in result.tool_records] == ["invalid_arguments", None]
    assert backend.calls == [("get_thing", {"tenantId": "streamflix"})]
    assert result.final_text == "fixed"


def test_several_tool_calls_in_one_turn_run_in_order_and_each_gets_a_result():
    turn = {"tool_calls": [{"name": "get_thing", "arguments": {"tenantId": "a"}},
                           {"name": "get_thing", "arguments": {"tenantId": "b"}}]}
    llm = scripted(turn, final_turn("both"))
    backend = FakeBackend()
    result, _ = drive(llm, backend)
    assert [c[1]["tenantId"] for c in backend.calls] == ["a", "b"]
    assert [m.role for m in llm.requests[1][0]][-2:] == ["tool", "tool"]
    assert [r.step for r in result.tool_records] == [1, 1]


def test_denied_write_is_reported_to_the_model_and_the_run_still_completes():
    llm = scripted(tool_turn("change_thing", tenantId="t", alertId="a"), final_turn("could not, needs approval"))
    backend = FakeBackend()
    result, _ = drive(llm, backend)
    assert backend.calls == []
    assert result.tool_records[0].error_kind == "denied"
    assert "not approved" in llm.requests[1][0][-1].content
    assert result.stop_reason == "final"


def test_audit_log_records_every_model_turn_tool_call_decision_and_latency():
    llm = scripted(tool_turn("get_thing", tenantId="t"), tool_turn("change_thing", tenantId="t", alertId="a"),
                   final_turn("done"))
    _, events = drive(llm, approver=allow_tools("change_thing"))
    assert [e["event"] for e in events] == [
        "run_start", "model_turn", "tool_call", "model_turn", "tool_call", "model_turn", "run_end"]
    read_call, write_call = [e for e in events if e["event"] == "tool_call"]
    assert read_call["approval"] == {"approved": True, "reason": "read-only tool"}
    assert write_call["approval"] == {"approved": True, "reason": "approved by approver"}
    assert write_call["arguments"] == {"tenantId": "t", "alertId": "a"}
    assert write_call["result"] == '{"ok": "change_thing"}'
    assert write_call["executed"] is True and write_call["latency_ms"] >= 0
    assert all(e["latency_ms"] >= 0 for e in events if e["event"] == "model_turn")
    assert [e["seq"] for e in events] == list(range(1, 8))
    assert events[-1]["final_text"] == "done" and events[-1]["tool_calls"] == 2


def test_audit_log_records_a_denial_with_executed_false():
    _, events = drive(scripted(tool_turn("change_thing", tenantId="t", alertId="a"), final_turn("no")))
    denied = next(e for e in events if e["event"] == "tool_call")
    assert denied["approval"] == {"approved": False, "reason": "denied by approver"}
    assert denied["executed"] is False and denied["error_kind"] == "denied"


def test_backend_error_text_goes_to_the_audit_log_only():
    async def boom(_n, _a):
        raise RuntimeError("secret-detail")

    llm = scripted(tool_turn("get_thing", tenantId="t"), final_turn("x"))
    result, events = drive(llm, FakeBackend(boom))
    tool_event = next(e for e in events if e["event"] == "tool_call")
    assert tool_event["detail"] == "secret-detail"
    assert "secret-detail" not in tool_event["result"]
    assert "secret-detail" not in llm.requests[1][0][-1].content
    assert result.tool_records[0].error_kind == "backend_error"


def test_tool_error_result_from_the_server_reaches_the_model_prefixed():
    async def tool_error(_n, _a):
        return ToolOutput("unknown tenant 'globex'", is_error=True)

    llm = scripted(tool_turn("get_thing", tenantId="globex"), final_turn("x"))
    drive(llm, FakeBackend(tool_error))
    assert llm.requests[1][0][-1].content == "error: unknown tenant 'globex'"


def returns(content: str, is_error: bool = False):
    async def handler(_name, _args):
        return ToolOutput(content, is_error=is_error)

    return FakeBackend(handler)


def test_an_invented_tenant_is_refused_and_the_model_is_told_to_ask():
    llm = scripted(tool_turn("get_thing", tenantId="streampulse"), final_turn("Which tenant do you mean?"))
    backend = FakeBackend()
    result, events = drive(llm, backend, prompt="Are there any active alerts right now?", grounded_args={"tenantId"})
    assert backend.calls == []
    assert result.tool_records[0].error_kind == "ungrounded_argument"
    assert "ask the user" in llm.requests[1][0][-1].content
    assert next(e for e in events if e["event"] == "tool_call")["executed"] is False


def test_an_id_from_an_earlier_tool_result_is_allowed():
    llm = scripted(tool_turn("get_thing", tenantId="t1"), tool_turn("change_thing", tenantId="t1", alertId="alr-7"),
                   final_turn("done"))
    backend = returns('{"firing": [{"alertId": "alr-7"}]}')
    result, _ = drive(llm, backend, allow_tools("change_thing"), prompt="Fix tenant t1", grounded_args={"tenantId", "alertId"})
    assert [r.error_kind for r in result.tool_records] == [None, None]
    assert backend.calls[1] == ("change_thing", {"tenantId": "t1", "alertId": "alr-7"})


def test_an_id_seen_only_in_an_error_result_is_not_grounded():
    llm = scripted(tool_turn("get_thing", tenantId="t1"), tool_turn("change_thing", tenantId="t1", alertId="alr-9"),
                   final_turn("x"))
    backend = returns("unknown alert 'alr-9'", is_error=True)
    result, _ = drive(llm, backend, allow_tools("change_thing"), prompt="tenant t1", grounded_args={"tenantId", "alertId"})
    assert [r.error_kind for r in result.tool_records] == ["tool_error", "ungrounded_argument"]
    assert len(backend.calls) == 1


def test_a_call_cannot_be_grounded_by_a_result_from_the_same_turn():
    same_turn = {"tool_calls": [{"name": "get_thing", "arguments": {"tenantId": "t1"}},
                                {"name": "change_thing", "arguments": {"tenantId": "t1", "alertId": "alr-7"}}]}
    backend = returns('{"alertId": "alr-7"}')
    result, _ = drive(scripted(same_turn, final_turn("x")), backend, allow_tools("change_thing"), prompt="tenant t1",
                      grounded_args={"tenantId", "alertId"})
    assert [r.error_kind for r in result.tool_records] == [None, "ungrounded_argument"]
