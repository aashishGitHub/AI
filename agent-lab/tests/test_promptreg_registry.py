from __future__ import annotations

import pytest

from promptreg.errors import InvalidReport, StateError, TamperError
from promptreg.gate import Gate
from promptreg.store import sha256_hex
from tests.promptreg_helpers import eval_report, new_registry, write_report

BASELINE = {"asks": (0, 10), "chain": (10, 10)}
BETTER = {"asks": (8, 10), "chain": (10, 10)}
WORSE = {"asks": (0, 10), "chain": (3, 10)}


def setup(tmp_path, texts=("one", "two")):
    registry, store = new_registry(tmp_path / "prompts")
    for text in texts:
        registry.add_version("system", text, "x", "c")
    return registry, store


def reports(tmp_path, candidate, baseline=BASELINE, **candidate_kwargs):
    return (
        write_report(tmp_path / "candidate.json", eval_report(candidate, **candidate_kwargs)),
        write_report(tmp_path / "baseline.json", eval_report(baseline)),
    )


def version_files(tmp_path):
    return {p.name: p.read_bytes() for p in (tmp_path / "prompts" / "system").glob("v*.md")}


def test_an_approved_promotion_moves_only_the_production_alias(tmp_path):
    registry, store = setup(tmp_path)
    files_before = version_files(tmp_path)
    versions_before = store.load_index("system").versions
    candidate, baseline = reports(tmp_path, BETTER)
    decision = registry.promote("system", 2, candidate, baseline, Gate())
    assert decision.approved
    index = store.load_index("system")
    assert index.production == 2
    assert version_files(tmp_path) == files_before
    assert index.versions == versions_before


def test_a_promotion_is_recorded_with_the_hash_of_both_reports_and_the_gate_used(tmp_path):
    registry, store = setup(tmp_path)
    candidate, baseline = reports(tmp_path, BETTER)
    registry.promote("system", 2, candidate, baseline, Gate(min_runs=10, margin=0.05, z=1.96))
    event = store.read_history("system")[-1]
    assert event["event"] == "promote"
    assert (event["from"], event["to"]) == (1, 2)
    assert event["candidate_report_sha256"] == sha256_hex(candidate.read_text())
    assert event["baseline_report_sha256"] == sha256_hex(baseline.read_text())
    assert event["gate"] == {"min_runs": 10, "margin": 0.05, "z": 1.96}


def test_a_refused_promotion_leaves_production_alone_and_records_why(tmp_path):
    registry, store = setup(tmp_path)
    candidate, baseline = reports(tmp_path, WORSE)
    decision = registry.promote("system", 2, candidate, baseline, Gate())
    assert not decision.approved
    assert store.load_index("system").production == 1
    event = store.read_history("system")[-1]
    assert event["event"] == "promote_refused"
    assert event["reasons"] == list(decision.reasons)


def test_a_dry_run_returns_the_decision_and_changes_and_records_nothing(tmp_path):
    registry, store = setup(tmp_path)
    history_before = store.read_history("system")
    candidate, baseline = reports(tmp_path, BETTER)
    assert registry.promote("system", 2, candidate, baseline, Gate(), dry_run=True).approved
    assert store.load_index("system").production == 1
    assert store.read_history("system") == history_before


def test_promoting_the_version_that_is_already_production_is_refused(tmp_path):
    registry, _ = setup(tmp_path)
    candidate, baseline = reports(tmp_path, BETTER)
    decision = registry.promote("system", 1, candidate, baseline, Gate())
    assert "system v1 is already production" in decision.reasons


def test_promoting_a_tampered_version_raises_before_any_alias_moves(tmp_path):
    registry, store = setup(tmp_path)
    (tmp_path / "prompts" / "system" / "v2.md").write_text("edited")
    candidate, baseline = reports(tmp_path, BETTER)
    with pytest.raises(TamperError):
        registry.promote("system", 2, candidate, baseline, Gate())
    assert store.load_index("system").production == 1


def test_an_unreadable_report_raises(tmp_path):
    registry, _ = setup(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    _, baseline = reports(tmp_path, BETTER)
    with pytest.raises(InvalidReport):
        registry.promote("system", 2, bad, baseline, Gate())


def test_reports_without_a_prompt_stamp_are_accepted_with_a_warning_for_each(tmp_path):
    registry, _ = setup(tmp_path)
    candidate, baseline = reports(tmp_path, BETTER)
    decision = registry.promote("system", 2, candidate, baseline, Gate(), dry_run=True)
    assert len(decision.warnings) == 2
    assert all("carries no prompt stamp" in w for w in decision.warnings)


def test_a_candidate_report_stamped_for_another_version_is_refused(tmp_path):
    registry, store = setup(tmp_path)
    one = store.load_index("system").versions[1].sha256
    candidate = write_report(
        tmp_path / "c.json", eval_report(BETTER, prompt={"name": "system", "version": 1, "sha256": one})
    )
    baseline = write_report(tmp_path / "b.json", eval_report(BASELINE, prompt={"name": "system", "version": 1, "sha256": one}))
    decision = registry.promote("system", 2, candidate, baseline, Gate(), dry_run=True)
    assert decision.warnings == ()
    assert len(decision.reasons) == 1
    assert decision.reasons[0].startswith("candidate report is stamped")


def test_correctly_stamped_reports_pass_with_no_warning(tmp_path):
    registry, store = setup(tmp_path)
    versions = store.load_index("system").versions
    stamp = lambda v: {"name": "system", "version": v, "sha256": versions[v].sha256}  # noqa: E731
    candidate = write_report(tmp_path / "c.json", eval_report(BETTER, prompt=stamp(2)))
    baseline = write_report(tmp_path / "b.json", eval_report(BASELINE, prompt=stamp(1)))
    decision = registry.promote("system", 2, candidate, baseline, Gate(), dry_run=True)
    assert decision.approved and decision.warnings == ()


def test_rollback_restores_the_previous_production_and_records_it(tmp_path):
    registry, store = setup(tmp_path)
    candidate, baseline = reports(tmp_path, BETTER)
    registry.promote("system", 2, candidate, baseline, Gate())
    files_before = version_files(tmp_path)
    assert registry.rollback("system") == 1
    assert store.load_index("system").production == 1
    assert version_files(tmp_path) == files_before
    event = store.read_history("system")[-1]
    assert (event["event"], event["from"], event["to"]) == ("rollback", 2, 1)


def test_rollback_walks_back_one_step_at_a_time_and_stops_at_the_first_version(tmp_path):
    registry, store = setup(tmp_path, texts=("one", "two", "three"))
    candidate, baseline = reports(tmp_path, BETTER)
    registry.promote("system", 2, candidate, baseline, Gate())
    registry.promote("system", 3, candidate, baseline, Gate())
    assert registry.rollback("system") == 2
    assert registry.rollback("system") == 1
    with pytest.raises(StateError, match="no earlier production"):
        registry.rollback("system")
    assert store.load_index("system").production == 1


def test_a_promotion_after_a_rollback_rolls_back_to_the_version_it_replaced(tmp_path):
    registry, _ = setup(tmp_path, texts=("one", "two", "three"))
    candidate, baseline = reports(tmp_path, BETTER)
    registry.promote("system", 2, candidate, baseline, Gate())
    registry.rollback("system")
    registry.promote("system", 3, candidate, baseline, Gate())
    assert registry.rollback("system") == 1


def test_rollback_refuses_when_the_index_disagrees_with_the_history(tmp_path):
    registry, store = setup(tmp_path)
    index = store.load_index("system")
    index.production = 2
    store.save_index("system", index)
    with pytest.raises(StateError, match="history says"):
        registry.rollback("system")


def test_rollback_refuses_to_restore_a_tampered_version(tmp_path):
    registry, store = setup(tmp_path)
    candidate, baseline = reports(tmp_path, BETTER)
    registry.promote("system", 2, candidate, baseline, Gate())
    (tmp_path / "prompts" / "system" / "v1.md").write_text("edited")
    with pytest.raises(TamperError):
        registry.rollback("system")
    assert store.load_index("system").production == 2


def test_pin_canary_and_clear_events_are_appended_to_history(tmp_path):
    registry, store = setup(tmp_path)
    registry.pin("system", 2)
    registry.unpin("system")
    registry.set_canary("system", 2, 10)
    registry.clear_canary("system")
    assert [e["event"] for e in store.read_history("system")] == [
        "bootstrap", "pin", "unpin", "canary_set", "canary_clear",
    ]


def test_pinning_an_unknown_version_is_refused(tmp_path):
    registry, store = setup(tmp_path)
    with pytest.raises(Exception, match="no version 9"):
        registry.pin("system", 9)
    assert store.load_index("system").pin is None
