from __future__ import annotations

from agent.approval import ApprovalGate, allow_tools, ask_on_terminal, deny_all
from tests.helpers import READ_TOOL, WRITE_TOOL, call


def test_read_only_tools_pass_without_asking_the_approver():
    def never(_call, _tool):
        raise AssertionError("approver must not be consulted for read-only tools")

    decision = ApprovalGate(never).decide(call("get_thing", tenantId="t"), READ_TOOL)
    assert decision.approved is True


def test_write_tools_are_denied_by_default():
    decision = ApprovalGate().decide(call("change_thing", tenantId="t", alertId="a"), WRITE_TOOL)
    assert decision.approved is False
    assert decision.reason == "denied by approver"
    assert ApprovalGate(deny_all).decide(call("change_thing"), WRITE_TOOL).approved is False


def test_allow_tools_approves_only_the_named_tools():
    gate = ApprovalGate(allow_tools("change_thing"))
    assert gate.decide(call("change_thing"), WRITE_TOOL).approved is True
    assert gate.decide(call("other_write"), WRITE_TOOL).approved is False


def test_an_approver_that_raises_means_denied():
    def broken(_call, _tool):
        raise RuntimeError("prompt crashed")

    decision = ApprovalGate(broken).decide(call("change_thing"), WRITE_TOOL)
    assert decision.approved is False
    assert "failed" in decision.reason


def test_unknown_read_only_status_defaults_to_write():
    from agent.types import ToolSpec

    assert ToolSpec("x", "d", {"type": "object"}).read_only is False


def test_terminal_approver_accepts_only_an_explicit_yes():
    answers = iter(["y", "YES", "n", "", "maybe"])
    approver = ask_on_terminal(lambda _prompt: next(answers))
    results = [approver(call("change_thing"), WRITE_TOOL) for _ in range(5)]
    assert results == [True, True, False, False, False]


def test_terminal_prompt_shows_the_tool_and_arguments():
    prompts: list[str] = []
    ask_on_terminal(lambda p: prompts.append(p) or "n")(call("change_thing", alertId="alr-1"), WRITE_TOOL)
    assert "change_thing" in prompts[0] and "alr-1" in prompts[0]
