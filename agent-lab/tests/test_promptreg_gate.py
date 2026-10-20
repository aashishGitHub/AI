from __future__ import annotations

import pytest

from promptreg.errors import InvalidReport
from promptreg.gate import Gate, evaluate
from tests.promptreg_helpers import eval_report

BASELINE = {"asks": (0, 10), "chain": (10, 10), "lookup": (5, 10)}


def verdicts(decision):
    return {c.case_id: c.verdict for c in decision.cases}


def test_a_clear_improvement_is_approved_and_every_case_is_labelled():
    candidate = eval_report({"asks": (10, 10), "chain": (10, 10), "lookup": (7, 10)})
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert decision.approved
    assert decision.reasons == ()
    assert verdicts(decision) == {"asks": "higher", "chain": "equal", "lookup": "higher"}


def test_a_credible_regression_is_refused_with_the_case_and_the_arithmetic():
    candidate = eval_report({"asks": (0, 10), "chain": (5, 10), "lookup": (5, 10)})
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert not decision.approved
    assert len(decision.reasons) == 1
    assert decision.reasons[0].startswith("chain: regressed, candidate 5/10 has Wilson upper bound 0.763")
    assert verdicts(decision)["chain"] == "regressed"


def test_a_small_dip_inside_the_wilson_margin_is_tolerated_and_labelled():
    candidate = eval_report({"asks": (0, 10), "chain": (9, 10), "lookup": (5, 10)})
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert decision.approved
    assert verdicts(decision)["chain"] == "lower_tolerated"


def test_a_tie_is_approved_and_is_not_called_an_improvement():
    decision = evaluate(eval_report(BASELINE), eval_report(BASELINE), Gate())
    assert decision.approved
    assert set(verdicts(decision).values()) == {"equal"}


def test_any_safety_failure_refuses_even_when_every_case_improved():
    candidate = eval_report({"asks": (10, 10), "chain": (10, 10), "lookup": (10, 10)}, safety_failures=1)
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert decision.reasons == ("candidate has 1 safety failure(s); zero are allowed",)


def test_too_few_runs_refuses_and_names_which_side_is_short():
    baseline = eval_report({"asks": (5, 10)})
    candidate = eval_report({"asks": (5, 5)})
    decision = evaluate(candidate, baseline, Gate(min_runs=10))
    assert decision.reasons == ("asks: candidate has 5 run(s), minimum is 10",)
    short_baseline = eval_report({"asks": (5, 5)})
    long_candidate = eval_report({"asks": (10, 10)})
    assert evaluate(long_candidate, short_baseline, Gate(min_runs=10)).reasons == (
        "asks: baseline has 5 run(s), minimum is 10",
    )


def test_the_same_report_passes_when_the_minimum_is_lowered():
    report = eval_report({"asks": (5, 5)})
    assert evaluate(report, report, Gate(min_runs=5)).approved


def test_a_case_missing_from_the_candidate_is_a_refusal():
    candidate = eval_report({"asks": (10, 10), "chain": (10, 10)})
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert decision.reasons == ("candidate report is missing baseline case(s): ['lookup']",)


def test_a_renamed_case_is_both_missing_and_extra():
    candidate = eval_report({"asks": (10, 10), "chain": (10, 10), "lookup_renamed": (10, 10)})
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert decision.reasons == (
        "candidate report is missing baseline case(s): ['lookup']",
        "candidate report has case(s) the baseline never ran: ['lookup_renamed']",
    )


def test_a_different_model_is_a_refusal_because_the_numbers_are_not_comparable():
    candidate = eval_report(BASELINE, model="llama3.2:1b")
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert decision.reasons == ("model differs: candidate 'llama3.2:1b', baseline 'qwen2.5:3b'",)


def test_every_reason_is_reported_not_just_the_first():
    candidate = eval_report({"chain": (0, 5)}, safety_failures=2, model="other")
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert len(decision.reasons) == 5
    assert decision.reasons[0].startswith("candidate has 2 safety failure")


def test_a_wider_margin_accepts_what_a_narrow_one_refuses():
    candidate = eval_report({"asks": (0, 10), "chain": (5, 10), "lookup": (5, 10)})
    assert not evaluate(candidate, eval_report(BASELINE), Gate(margin=0.05)).approved
    assert evaluate(candidate, eval_report(BASELINE), Gate(margin=0.25)).approved


def test_the_report_pass_rate_field_is_ignored_in_favour_of_the_counts():
    candidate = eval_report(BASELINE)
    candidate["cases"][1]["pass_rate"] = 0.0
    assert evaluate(candidate, eval_report(BASELINE), Gate()).approved


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("cases"),
        lambda r: r["summary"].pop("safety_failures"),
        lambda r: r["cases"][0].update(successes=11),
        lambda r: r["cases"][0].update(runs=0),
        lambda r: r["cases"].append(dict(r["cases"][0])),
    ],
)
def test_a_malformed_candidate_report_raises_instead_of_passing(mutate):
    candidate = eval_report(BASELINE)
    mutate(candidate)
    with pytest.raises(InvalidReport):
        evaluate(candidate, eval_report(BASELINE), Gate())
