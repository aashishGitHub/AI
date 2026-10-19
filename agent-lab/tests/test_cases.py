from __future__ import annotations

import pytest
import yaml

from evals.case import case_from_dict, load_cases
from evals.cli import CASES_DIR
from evals.expectations import AllowedSet, ExactSequence
from evals.matchers import CaseError

MINIMAL = {
    "id": "c",
    "prompt": "p",
    "expect": {"tools": {"sequence": []}},
}


def with_expect(**expect):
    return {**MINIMAL, "expect": {"tools": {"sequence": []}, **expect}}


def test_there_are_at_least_ten_golden_cases_with_unique_ids_and_scripts():
    cases = load_cases(CASES_DIR)
    assert len(cases) >= 10
    assert len({c.id for c in cases}) == len(cases)
    assert all(c.script for c in cases)


def test_golden_set_covers_the_required_scenarios(golden):
    assert isinstance(golden["no_tool_needed"].tools, ExactSequence) and not golden["no_tool_needed"].tools.calls
    assert not golden["ambiguous_tenant_asks"].tools.calls
    assert [c.tool for c in golden["chain_list_then_explain"].tools.calls] == ["list_active_alerts", "explain_alert"]
    assert isinstance(golden["explain_suppressed_root_cause"].tools, AllowedSet)
    assert golden["ack_approved"].approve == ("acknowledge_alert",)
    assert golden["ack_approved"].state.acknowledged == {"alr-1001"}
    assert golden["ack_denied_by_default"].approve == () and golden["ack_denied_by_default"].denied
    assert golden["injection_resisted"].forbidden_tools == ("acknowledge_alert", "link_issue")
    assert golden["injection_obeyed_gate_blocks"].live is False
    assert golden["injection_obeyed_gate_blocks"].denied == ("acknowledge_alert",)


def test_a_typo_in_a_key_is_an_error_not_a_silently_ignored_expectation():
    with pytest.raises(CaseError, match=r"unknown key\(s\) \['forbidden_tool'\]"):
        case_from_dict(with_expect(forbidden_tool=["acknowledge_alert"]))
    with pytest.raises(CaseError, match="unknown key"):
        case_from_dict({**MINIMAL, "max_step": 3})
    with pytest.raises(CaseError, match=r"final_text.*unknown key"):
        case_from_dict(with_expect(final_text={"contain": ["x"]}))


def test_required_keys_are_enforced():
    with pytest.raises(CaseError, match="missing required key 'prompt'"):
        case_from_dict({"id": "c", "expect": {"tools": {"sequence": []}}})
    with pytest.raises(CaseError, match="missing required key 'tools'"):
        case_from_dict({**MINIMAL, "expect": {}})


def test_exactly_one_of_sequence_or_allowed():
    with pytest.raises(CaseError, match="exactly one of 'sequence' or 'allowed'"):
        case_from_dict({**MINIMAL, "expect": {"tools": {"sequence": [], "allowed": []}}})
    with pytest.raises(CaseError, match="exactly one of 'sequence' or 'allowed'"):
        case_from_dict({**MINIMAL, "expect": {"tools": {}}})


def test_bad_matcher_in_a_case_is_rejected_at_load_time():
    raw = {**MINIMAL, "expect": {"tools": {"sequence": [{"tool": "t", "args": {"a": {"regexx": "x"}}}]}}}
    with pytest.raises(CaseError, match="exactly one key"):
        case_from_dict(raw)


def test_duplicate_ids_are_rejected(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(yaml.safe_dump(MINIMAL))
    with pytest.raises(CaseError, match=r"duplicate case id\(s\): \['c'\]"):
        load_cases(tmp_path)


def test_optimal_calls_defaults_to_the_number_of_required_tools():
    case = case_from_dict({**MINIMAL, "expect": {"tools": {"allowed": ["a", "b"], "required": ["a"]}}})
    assert case.tools.optimal_calls == 1
