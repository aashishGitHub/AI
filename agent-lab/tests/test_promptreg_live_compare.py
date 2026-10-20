from __future__ import annotations

import evals.runner
from agent.llm import ScriptedLLM, turns_from_dicts
from evals.case import load_cases
from evals.cli import CASES_DIR
from evals.runner import in_process_server, run_live
from promptreg.live_compare import render, system_prompt_injected
from tests.helpers import run


def test_the_injected_prompt_is_what_the_model_sees_and_the_patch_is_undone_afterwards():
    cases = [c for c in load_cases(CASES_DIR) if c.id == "ambiguous_tenant_asks"]
    original = evals.runner.run_session
    llms: list[ScriptedLLM] = []

    def make_llm() -> ScriptedLLM:
        llms.append(ScriptedLLM(turns_from_dicts([{"content": "Which tenant do you mean?"}])))
        return llms[-1]

    with system_prompt_injected("CANDIDATE PROMPT"):
        run(run_live(cases, make_llm, 2, in_process_server))

    assert [llm.requests[0][0][0].content for llm in llms] == ["CANDIDATE PROMPT", "CANDIDATE PROMPT"]
    assert evals.runner.run_session is original
    run(run_live(cases, make_llm, 1, in_process_server))
    assert llms[-1].requests[0][0][0].content != "CANDIDATE PROMPT"


def test_the_table_shows_counts_and_wilson_intervals_side_by_side():
    reports = {
        1: {"cases": [{"id": "a", "runs": 5, "successes": 0}]},
        2: {"cases": [{"id": "a", "runs": 5, "successes": 5}]},
    }
    row = render(reports).splitlines()[1]
    assert "0/5 [0.00, 0.43]" in row
    assert "5/5 [0.57, 1.00]" in row
