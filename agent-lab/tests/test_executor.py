from __future__ import annotations

import asyncio
import time

from agent.approval import ApprovalGate, allow_tools
from agent.executor import TRUNCATED_MARKER, ToolExecutor
from agent.types import ToolOutput, ToolSpec
from tests.helpers import READ_TOOL, WRITE_TOOL, FakeBackend, call, run


def executor(backend: FakeBackend, gate: ApprovalGate | None = None, **kwargs) -> ToolExecutor:
    return ToolExecutor(backend, [READ_TOOL, WRITE_TOOL], gate or ApprovalGate(), **kwargs)


def test_valid_read_call_is_executed_and_returns_the_tool_text():
    backend = FakeBackend()
    record = run(executor(backend).execute(call("get_thing", tenantId="streamflix"), step=1))
    assert backend.calls == [("get_thing", {"tenantId": "streamflix"})]
    assert (record.executed, record.is_error, record.error_kind) == (True, False, None)
    assert record.content == '{"ok": "get_thing"}'
    assert record.decision is not None and record.decision.approved


def test_unknown_tool_is_an_error_result_that_lists_the_available_tools():
    backend = FakeBackend()
    record = run(executor(backend).execute(call("delete_everything"), step=1))
    assert record.error_kind == "unknown_tool"
    assert "get_thing" in record.content and "change_thing" in record.content
    assert backend.calls == [] and record.executed is False


def test_missing_required_argument_is_rejected_before_the_backend_and_before_approval():
    backend = FakeBackend()
    asked: list[str] = []
    gate = ApprovalGate(lambda c, t: asked.append(c.name) or True)
    record = run(executor(backend, gate).execute(call("change_thing", tenantId="t"), step=1))
    assert record.error_kind == "invalid_arguments"
    assert "'alertId' is a required property" in record.content
    assert backend.calls == [] and asked == []
    assert record.decision is None


def test_wrong_argument_type_is_rejected_with_the_path_and_reason():
    record = run(executor(FakeBackend()).execute(call("get_thing", tenantId=5), step=1))
    assert record.error_kind == "invalid_arguments"
    assert "$.tenantId: 5 is not of type 'string'" in record.content


def test_denied_write_never_reaches_the_backend():
    backend = FakeBackend()
    record = run(executor(backend).execute(call("change_thing", tenantId="t", alertId="a"), step=2))
    assert backend.calls == []
    assert (record.executed, record.error_kind) == (False, "denied")
    assert record.decision is not None and not record.decision.approved
    assert "needs human approval" in record.content


def test_approved_write_is_executed():
    backend = FakeBackend()
    gate = ApprovalGate(allow_tools("change_thing"))
    record = run(executor(backend, gate).execute(call("change_thing", tenantId="t", alertId="a"), step=1))
    assert backend.calls == [("change_thing", {"tenantId": "t", "alertId": "a"})]
    assert record.executed and not record.is_error


def test_slow_tool_times_out_and_the_run_continues():
    async def slow(_name, _args):
        await asyncio.sleep(5)
        return ToolOutput("late")

    started = time.perf_counter()
    record = run(executor(FakeBackend(slow), default_timeout_s=0.05).execute(call("get_thing", tenantId="t"), step=1))
    assert time.perf_counter() - started < 1
    assert record.error_kind == "timeout"
    assert "timed out after 0.05 s" in record.content
    assert record.executed is True


def test_per_tool_timeout_overrides_the_default():
    async def slow(_name, _args):
        await asyncio.sleep(0.2)
        return ToolOutput("done")

    fast_default = executor(FakeBackend(slow), default_timeout_s=0.01)
    assert run(fast_default.execute(call("get_thing", tenantId="t"), step=1)).error_kind == "timeout"
    overridden = executor(FakeBackend(slow), default_timeout_s=0.01, timeouts_s={"get_thing": 2})
    assert run(overridden.execute(call("get_thing", tenantId="t"), step=1)).error_kind is None


def test_backend_exception_is_hidden_from_the_model_but_kept_for_the_audit_log():
    async def boom(_name, _args):
        raise RuntimeError("password=hunter2")

    record = run(executor(FakeBackend(boom)).execute(call("get_thing", tenantId="t"), step=1))
    assert record.error_kind == "backend_error"
    assert "hunter2" not in record.content
    assert "RuntimeError" in record.content
    assert record.detail == "password=hunter2"


def test_tool_reported_error_is_passed_through_with_an_error_prefix():
    async def tool_error(_name, _args):
        return ToolOutput("invalid argument 'tenantId'", is_error=True)

    record = run(executor(FakeBackend(tool_error)).execute(call("get_thing", tenantId="t"), step=1))
    assert record.error_kind == "tool_error"
    assert record.content == "error: invalid argument 'tenantId'"


def test_oversized_result_is_truncated_with_a_marker():
    async def big(_name, _args):
        return ToolOutput("x" * 500)

    record = run(executor(FakeBackend(big), max_result_chars=100).execute(call("get_thing", tenantId="t"), step=1))
    assert record.content == "x" * 100 + TRUNCATED_MARKER


def test_execute_never_raises_even_when_the_tool_schema_itself_is_broken():
    broken = ToolSpec("broken", "bad schema", {"type": "object", "properties": {"a": {"type": 5}}}, read_only=True)
    record = run(ToolExecutor(FakeBackend(), [broken], ApprovalGate()).execute(call("broken", a="x"), step=1))
    assert record.error_kind == "internal_error"
    assert "see the audit log" in record.content
    assert record.detail
