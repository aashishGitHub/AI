from __future__ import annotations

from agent.approval import allow_tools
from orchestrator.roles import AgentRole
from tests.helpers import READ_TOOL, WRITE_TOOL, FakeBackend, final_turn, run, tool_turn
from tests.mesh_helpers import NOW, build_service, mesh_client

READ_ONLY_ROLE = AgentRole("investigator", frozenset({"get_thing"}), max_steps=3)
RESPONDER_ROLE = AgentRole("responder", frozenset({"get_thing", "change_thing"}), max_steps=3)


def ask(built, prompt: str = "check acme alr-1"):
    client = mesh_client(built.app)
    return run(client.send("http://agent", client.make_envelope(built.service.card.name, prompt, "corr-1", NOW + 30)))


def test_a_tool_outside_the_roles_allowlist_is_never_called_even_if_the_model_asks() -> None:
    backend = FakeBackend()
    script = [tool_turn("change_thing", tenantId="acme", alertId="alr-1"), final_turn("done")]
    built = build_service("investigator", READ_ONLY_ROLE, [READ_TOOL, WRITE_TOOL], backend, script)
    task = ask(built)
    assert backend.calls == []
    assert task["result"]["tools_called"] == []
    assert '"error_kind": "unknown_tool"' in built.audit.getvalue()


def test_a_write_without_approval_is_denied_and_the_task_asks_for_input() -> None:
    backend = FakeBackend()
    script = [tool_turn("change_thing", tenantId="acme", alertId="alr-1"), final_turn("needs approval")]
    built = build_service("responder", RESPONDER_ROLE, [READ_TOOL, WRITE_TOOL], backend, script)
    task = ask(built)
    assert backend.calls == []
    assert task["state"] == "input-required"
    assert task["result"]["needs_approval"] == [{"tool": "change_thing", "arguments": {"tenantId": "acme", "alertId": "alr-1"}}]


def test_the_same_write_runs_when_the_agents_own_approver_allows_it() -> None:
    backend = FakeBackend()
    script = [tool_turn("change_thing", tenantId="acme", alertId="alr-1"), final_turn("changed")]
    built = build_service("responder", RESPONDER_ROLE, [READ_TOOL, WRITE_TOOL], backend, script,
                          approver=allow_tools("change_thing"))
    task = ask(built)
    assert [name for name, _ in backend.calls] == ["change_thing"]
    assert task["state"] == "completed"


def test_an_id_the_model_invented_is_not_sent_to_the_tool() -> None:
    backend = FakeBackend()
    script = [tool_turn("get_thing", tenantId="globex"), final_turn("guessed")]
    built = build_service("investigator", READ_ONLY_ROLE, [READ_TOOL], backend, script)
    ask(built, prompt="check acme")
    assert backend.calls == []
    assert "ungrounded_argument" in built.audit.getvalue()
