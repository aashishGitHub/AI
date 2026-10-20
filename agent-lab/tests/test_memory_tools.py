from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from agent.approval import ApprovalGate, allow_tools
from agent.executor import ToolExecutor, ToolRecord
from agent.loop import RunResult
from agent.types import ToolCall, ToolSpec
from memory.episodes import record_run_summary, summarize_run
from memory.records import DEFAULT_TTL
from memory.retrieval import Retriever
from memory.tools import RECALL_SPEC, REMEMBER_SPEC, MemoryToolBackend
from tests.helpers import READ_TOOL, WRITE_TOOL, new_audit, run
from tests.memory_helpers import PROV, START, FakeClock, ListingBackend, make_store


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    return make_store("sqlite", clock)


def backend_for(store, clock, tenant="t1", run_id="run-1", inner=None, audit=None):
    return MemoryToolBackend(inner or ListingBackend(), store, Retriever(store, clock), tenant, run_id, audit=audit)


def executor_for(backend, approver=None):
    tools = run(backend.list_tools())
    return ToolExecutor(backend, tools, ApprovalGate(approver) if approver else ApprovalGate())


def call(executor, name, **arguments):
    return run(executor.execute(ToolCall("c1", name, arguments), step=1))


def test_both_tool_schemas_are_valid_json_schema_and_closed():
    for spec in (RECALL_SPEC, REMEMBER_SPEC):
        Draft202012Validator.check_schema(spec.input_schema)
        assert spec.input_schema["additionalProperties"] is False
        assert "tenantId" not in spec.input_schema["properties"]
    assert RECALL_SPEC.read_only and not REMEMBER_SPEC.read_only


def test_list_tools_appends_recall_and_remember_to_the_inner_tools(store, clock):
    tools = run(backend_for(store, clock, inner=ListingBackend([READ_TOOL, WRITE_TOOL])).list_tools())
    assert [t.name for t in tools] == ["get_thing", "change_thing", "recall", "remember"]


def test_a_name_collision_with_an_inner_tool_is_refused(store, clock):
    clash = ToolSpec("recall", "x", {"type": "object"}, read_only=True)
    with pytest.raises(ValueError, match="already has"):
        run(backend_for(store, clock, inner=ListingBackend([clash])).list_tools())


def test_other_tools_pass_through_to_the_inner_backend_untouched(store, clock):
    inner = ListingBackend([READ_TOOL])
    out = run(backend_for(store, clock, inner=inner).call_tool("get_thing", {"tenantId": "t"}))
    assert inner.calls == [("get_thing", {"tenantId": "t"})]
    assert out.content == '{"ok": "get_thing"}'


def test_remember_stores_a_semantic_fact_with_bound_tenant_run_id_provenance_and_default_ttl(store, clock):
    executor = executor_for(backend_for(store, clock, tenant="t1", run_id="run-9"), allow_tools("remember"))
    record = call(executor, "remember", text="deploys freeze on fridays")
    assert record.error_kind is None and record.executed
    stored_id = json.loads(record.content)["stored"]
    stored = store.get("t1", stored_id)
    assert (stored.kind, stored.text) == ("semantic", "deploys freeze on fridays")
    assert (stored.provenance.source, stored.provenance.run_id, stored.provenance.written_by) == ("tool:remember", "run-9", "model")
    assert stored.created_at == START and stored.expires_at == START + DEFAULT_TTL["semantic"]


def test_a_model_supplied_tenant_id_is_rejected_by_the_schema_before_the_backend_runs(store, clock):
    store.add("victim", "semantic", "victim secret", PROV, None)
    executor = executor_for(backend_for(store, clock, tenant="attacker"), allow_tools("remember"))
    for name, args in (("recall", {"query": "victim secret", "tenantId": "victim"}),
                       ("remember", {"text": "planted", "tenantId": "victim"})):
        record = call(executor, name, **args)
        assert record.error_kind == "invalid_arguments" and "victim secret" not in record.content
    assert [r.text for r in store.list("victim")] == ["victim secret"]
    assert store.list("attacker") == []


def test_even_when_the_backend_is_called_directly_extra_tenant_arguments_are_ignored(store, clock):
    store.add("victim", "semantic", "victim secret", PROV, None)
    backend = backend_for(store, clock, tenant="attacker")
    leaked = run(backend.call_tool("recall", {"query": "victim secret", "tenantId": "victim", "tenant_id": "victim"}))
    assert leaked.content == "no matching memories"
    run(backend.call_tool("remember", {"text": "planted", "tenantId": "victim"}))
    assert [r.text for r in store.list("victim")] == ["victim secret"]
    assert [r.text for r in store.list("attacker")] == ["planted"]


def test_recall_returns_a_delimited_block_for_the_bound_tenant_only(store, clock):
    store.add("t1", "semantic", "billing contact is finance", PROV, None)
    store.add("t2", "semantic", "billing contact is someone else", PROV, None)
    out = run(backend_for(store, clock, tenant="t1").call_tool("recall", {"query": "billing contact"}))
    assert out.content.startswith("<untrusted_memory>") and out.content.endswith("</untrusted_memory>")
    assert "finance" in out.content and "someone else" not in out.content


def test_recall_with_no_hits_says_so(store, clock):
    assert run(backend_for(store, clock).call_tool("recall", {"query": "nothing"})).content == "no matching memories"


@pytest.mark.parametrize("name, args", [
    ("recall", {"query": 5}),
    ("recall", {"query": "x", "kind": "weird"}),
    ("recall", {"query": "x", "limit": 0}),
    ("recall", {"query": "x", "limit": True}),
    ("remember", {"text": 5}),
    ("remember", {"text": "  "}),
    ("remember", {"text": "y" * 1001}),
])
def test_bad_arguments_reaching_the_backend_return_error_outputs_not_exceptions(store, clock, name, args):
    out = run(backend_for(store, clock).call_tool(name, args))
    assert out.is_error
    assert store.list("t1") == []


def test_memory_calls_are_audited_with_ids_and_sizes_but_not_the_text(store, clock):
    audit, stream = new_audit()
    backend = backend_for(store, clock, audit=audit)
    run(backend.call_tool("remember", {"text": "private-ish fact about billing"}))
    run(backend.call_tool("recall", {"query": "billing"}))
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [e["event"] for e in events] == ["memory_write", "memory_recall"]
    assert events[0]["chars"] == len("private-ish fact about billing") and events[0]["tenant_id"] == "t1"
    assert events[1]["record_ids"] == [events[0]["record_id"]] and events[1]["query_chars"] == len("billing")
    assert "private-ish" not in stream.getvalue()


def make_result(final_text="All good.", tools=("list_active_alerts", "explain_alert")) -> RunResult:
    records = tuple(ToolRecord(1, ToolCall(f"c{i}", name, {}), None, True, None, "", 0.0) for i, name in enumerate(tools))
    return RunResult(final_text, "final", 2, records, ())


def test_run_summary_is_a_deterministic_episodic_record_written_by_the_system(store, clock):
    result = make_result("  alr-1001 is the   root\ncause  ")
    assert summarize_run(result) == "stop=final; steps=2; tools=list_active_alerts, explain_alert; answer=alr-1001 is the root cause"
    record = record_run_summary(store, "t1", "run-3", result)
    assert (record.kind, record.provenance.source, record.provenance.written_by) == ("episodic", "system:run_summary", "system")
    assert record.expires_at == START + DEFAULT_TTL["episodic"]
    assert store.list("t1", "episodic") == [record]


def test_run_summary_truncates_a_long_answer():
    assert summarize_run(make_result("a" * 1000, tools=()), max_answer_chars=10).endswith("tools=none; answer=" + "a" * 10)
