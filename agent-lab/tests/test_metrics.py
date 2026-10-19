from __future__ import annotations

import pytest

from evals.metrics import pass_at_k, summarize
from evals.scoring import CaseScore, Check

OK = Check(True)
BAD = Check(False, ("reason",))


def score(case_id="c", *, selection=OK, args=Check(None), safety=OK, outcome=OK, budget=OK, efficiency=1.0):
    return CaseScore(case_id, selection, args, safety, outcome, budget, efficiency, steps=1, tool_calls=1)


def test_pass_at_1_is_the_plain_pass_rate():
    assert pass_at_k(5, 2, 1) == pytest.approx(0.4)
    assert pass_at_k(5, 0, 1) == 0.0
    assert pass_at_k(5, 5, 1) == 1.0


def test_pass_at_k_is_one_when_fewer_than_k_runs_failed():
    assert pass_at_k(5, 3, 3) == 1.0


def test_pass_at_k_hand_computed_value():
    assert pass_at_k(10, 5, 2) == pytest.approx(1 - 10 / 45)


@pytest.mark.parametrize("n, c, k", [(5, 1, 0), (5, 1, 6), (5, 6, 1), (5, -1, 1)])
def test_pass_at_k_rejects_out_of_range_arguments(n, c, k):
    with pytest.raises(ValueError):
        pass_at_k(n, c, k)


def test_summary_aggregates_each_metric_over_all_runs():
    scores = [
        score("a"),
        score("a", selection=BAD),
        score("b", args=Check(True), efficiency=0.5),
        score("b", args=Check(False, ("x",)), safety=BAD),
    ]
    summary = summarize(scores)
    assert summary.runs == 4
    assert summary.task_success == 0.5
    assert summary.tool_selection_accuracy == 0.75
    assert summary.arg_accuracy == 0.5
    assert summary.step_efficiency == pytest.approx(0.875)
    assert summary.safety_failures == 1
    by_case = {c.case_id: c for c in summary.cases}
    assert (by_case["a"].runs, by_case["a"].successes, by_case["a"].pass_rate) == (2, 1, 0.5)
    assert by_case["b"].successes == 1


def test_arg_accuracy_is_none_when_no_run_checked_arguments():
    assert summarize([score(), score()]).arg_accuracy is None


def test_a_check_that_was_not_applicable_does_not_fail_the_case():
    assert score(args=Check(None)).success is True
    assert score(args=BAD).success is False
