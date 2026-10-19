from __future__ import annotations

import json

import pytest

from evals.cli import CASES_DIR, main
from evals.case import load_cases
from evals.runner import run_deterministic
from evals.metrics import summarize
from tests.helpers import run


def test_deterministic_golden_suite_passes_end_to_end_over_a_real_stdio_server():
    scores = run(run_deterministic(load_cases(CASES_DIR)))
    failing = {s.case_id: s.failures for s in scores if not s.success}
    assert failing == {}
    summary = summarize(scores)
    assert summary.runs >= 10
    assert (summary.task_success, summary.tool_selection_accuracy, summary.safety_failures) == (1.0, 1.0, 0)


def test_cli_exits_zero_when_every_case_passes_and_writes_a_json_report(tmp_path, capsys):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "q.yaml").write_text((CASES_DIR / "13_quiet_tenant.yaml").read_text())
    report = tmp_path / "report.json"
    assert main(["--cases", str(cases), "--report", str(report), "deterministic"]) == 0
    data = json.loads(report.read_text())
    assert data["mode"] == "deterministic" and data["summary"]["task_success"] == 1.0
    assert data["cases"][0]["id"] == "quiet_tenant"
    assert "quiet_tenant" in capsys.readouterr().out


def test_cli_exits_one_and_prints_the_reason_when_a_case_fails(tmp_path, capsys):
    cases = tmp_path / "cases"
    cases.mkdir()
    broken = (CASES_DIR / "13_quiet_tenant.yaml").read_text().replace("args: {tenantId: northwind}", "args: {tenantId: streamflix}")
    (cases / "q.yaml").write_text(broken)
    assert main(["--cases", str(cases), "deterministic"]) == 1
    assert "arg 'tenantId' expected exact 'streamflix' but got 'northwind'" in capsys.readouterr().out


def test_audit_dir_gets_one_jsonl_file_per_case(tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "q.yaml").write_text((CASES_DIR / "13_quiet_tenant.yaml").read_text())
    audit_dir = tmp_path / "audit"
    main(["--cases", str(cases), "--audit-dir", str(audit_dir), "deterministic"])
    lines = [json.loads(line) for line in (audit_dir / "quiet_tenant.jsonl").read_text().splitlines()]
    assert [e["event"] for e in lines] == ["run_start", "model_turn", "tool_call", "model_turn", "run_end"]


def test_only_runs_the_named_cases(tmp_path):
    report = tmp_path / "report.json"
    assert main(["--only", "quiet_tenant", "--only", "no_tool_needed", "--report", str(report), "deterministic"]) == 0
    assert sorted(c["id"] for c in json.loads(report.read_text())["cases"]) == ["no_tool_needed", "quiet_tenant"]


def test_only_with_an_unknown_case_id_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--only", "no_such_case", "deterministic"])
    assert exit_info.value.code == 2
    assert "unknown case id(s) ['no_such_case']" in capsys.readouterr().err
