from __future__ import annotations

import pytest

from agent.approval import ApprovalGate
from agent.executor import ToolExecutor
from agent.llm import ScriptedLLM
from agent.loop import run_agent
from agent.types import Message
from memory.tokens import estimate_tokens, message_tokens
from memory.window import SUMMARY_MARKER, ContextWindow, WindowedLLM, group_units, is_summary
from tests.helpers import READ_TOOL, FakeBackend, final_turn, new_audit, run, scripted, tool_turn
from tests.memory_helpers import ScriptedSummarizer, assistant, tool_result, user

SYSTEM = Message("system", "S" * 40)
TASK = user("T" * 40)


def conversation(pairs: int, size: int = 200) -> list[Message]:
    messages = [SYSTEM, TASK]
    for n in range(pairs):
        messages += [assistant("", f"c{n}"), tool_result(f"c{n}", f"r{n}-" + "x" * size)]
    return messages


def window(budget: int, summarizer: ScriptedSummarizer | None = None, **kwargs) -> ContextWindow:
    return ContextWindow(budget, summarizer or ScriptedSummarizer(), summary_max_tokens=32, **kwargs)


def is_paired(messages) -> bool:
    call_at = {c.id: i for i, m in enumerate(messages) if m.role == "assistant" for c in m.tool_calls}
    result_at = {m.tool_call_id: i for i, m in enumerate(messages) if m.role == "tool"}
    return set(call_at) == set(result_at) and all(call_at[cid] < result_at[cid] for cid in call_at)


def test_token_estimate_is_chars_over_four_rounded_up():
    assert [estimate_tokens(t) for t in ("", "a", "abcd", "abcde")] == [0, 1, 1, 2]
    assert message_tokens(Message("user", "abcd")) == 4 + 1


def test_under_budget_is_returned_unchanged_without_calling_the_summarizer():
    summarizer = ScriptedSummarizer()
    messages = conversation(1)
    fitted = run(window(10_000, summarizer).fit(messages))
    assert fitted.messages == tuple(messages)
    assert (fitted.compacted, fitted.over_budget, summarizer.calls) == (0, False, [])


def test_over_budget_compacts_older_turns_into_one_marked_summary_and_stays_under_budget():
    summarizer = ScriptedSummarizer("the model listed alerts")
    messages = conversation(6)
    fitted = run(window(300, summarizer).fit(messages))
    out = fitted.messages
    assert out[0] == SYSTEM and out[1] == TASK
    assert is_summary(out[2]) and out[2].content == f"{SUMMARY_MARKER} the model listed alerts"
    assert out[-2:] == tuple(messages[-2:])
    assert fitted.tokens <= 300 and not fitted.over_budget
    assert fitted.compacted == len(messages) - len(out) + 1


def test_the_summarizer_receives_exactly_the_messages_that_were_dropped():
    summarizer = ScriptedSummarizer()
    messages = conversation(6)
    fitted = run(window(300, summarizer).fit(messages))
    dropped = tuple(messages[2 : 2 + fitted.compacted])
    assert summarizer.calls == [dropped]


@pytest.mark.parametrize("budget", range(60, 400, 7))
def test_a_tool_call_is_never_separated_from_its_result_at_any_budget(budget):
    fitted = run(window(budget).fit(conversation(8)))
    assert is_paired(fitted.messages)
    assert fitted.messages[0] == SYSTEM and fitted.messages[1] == TASK


def test_parallel_tool_calls_are_kept_or_dropped_as_one_unit():
    messages = [SYSTEM, TASK, assistant("", "a", "b"), tool_result("a", "x" * 80), tool_result("b", "y" * 80),
                assistant("", "c"), tool_result("c", "z" * 80)]
    for budget in range(60, 200, 5):
        assert is_paired(run(window(budget).fit(messages)).messages)


def test_system_and_first_user_task_are_pinned_even_when_everything_else_is_compacted():
    fitted = run(window(120).fit(conversation(10)))
    assert fitted.messages[:2] == (SYSTEM, TASK)
    assert fitted.compacted > 0


def test_the_newest_unit_is_always_kept_and_over_budget_is_reported():
    big = [SYSTEM, TASK, assistant("", "c0"), tool_result("c0", "x" * 2000)]
    fitted = run(window(120).fit(big))
    assert fitted.messages[-2:] == tuple(big[-2:])
    assert fitted.over_budget


def test_a_second_compaction_summarizes_the_previous_summary_instead_of_losing_it():
    summarizer = ScriptedSummarizer("first", "second")
    win = window(300, summarizer)
    first = run(win.fit(conversation(6)))
    grown = [*first.messages, assistant("", "n1"), tool_result("n1", "n" * 200), assistant("", "n2"), tool_result("n2", "m" * 200)]
    second = run(win.fit(grown))
    assert any(is_summary(m) and "first" in m.content for m in summarizer.calls[1])
    assert sum(is_summary(m) for m in second.messages) == 1


def test_fitting_an_already_fitted_window_changes_nothing():
    win = window(300)
    once = run(win.fit(conversation(6)))
    assert run(win.fit(once.messages)).messages == once.messages


def test_summary_is_truncated_to_its_cap_so_a_chatty_summarizer_cannot_blow_the_budget():
    fitted = run(window(300, ScriptedSummarizer("w" * 5000)).fit(conversation(6)))
    summary = next(m for m in fitted.messages if is_summary(m))
    assert len(summary.content) == 32 * 4
    assert fitted.tokens <= 300


def test_malformed_history_raises_instead_of_being_silently_repaired():
    with pytest.raises(ValueError, match="without a preceding"):
        group_units([SYSTEM, TASK, tool_result("c0", "x")])
    with pytest.raises(ValueError, match="without a result"):
        group_units([SYSTEM, TASK, assistant("", "c0", "c1"), tool_result("c0", "x")])
    with pytest.raises(ValueError, match="does not match"):
        group_units([SYSTEM, TASK, assistant("", "c0"), tool_result("zzz", "x")])


def test_a_failing_summarizer_propagates_and_the_input_is_untouched():
    class Broken:
        async def summarize(self, messages):
            raise RuntimeError("summarizer down")

    messages = conversation(6)
    snapshot = tuple(messages)
    with pytest.raises(RuntimeError, match="summarizer down"):
        run(ContextWindow(300, Broken(), summary_max_tokens=32).fit(messages))
    assert tuple(messages) == snapshot


def test_constructor_rejects_a_budget_that_cannot_hold_the_summary():
    with pytest.raises(ValueError):
        ContextWindow(10, ScriptedSummarizer(), summary_max_tokens=32)
    with pytest.raises(ValueError):
        ContextWindow(1000, ScriptedSummarizer(), summary_max_tokens=2)


def test_windowed_llm_shows_the_model_a_fitted_view_while_the_loop_keeps_the_full_history():
    inner = scripted(*[tool_turn("get_thing", tenantId="t") for _ in range(7)], final_turn("done"))
    windowed = WindowedLLM(inner, window(260))
    executor = ToolExecutor(FakeBackend(), [READ_TOOL], ApprovalGate())
    audit, _ = new_audit()
    result = run(run_agent("hi " * 10, windowed, executor, [READ_TOOL], audit, max_steps=10))
    assert result.stop_reason == "final"
    assert len(result.messages) == 2 + 7 * 2 + 1
    last_request, _ = inner.requests[-1]
    assert len(last_request) < len(result.messages) - 1
    assert any(is_summary(m) for m in last_request)
    assert all(is_paired(request) for request, _ in inner.requests)
    assert isinstance(inner, ScriptedLLM) and windowed.last_fit is not None
