from __future__ import annotations

import json

import pytest

from promptreg.cli import main
from tests.promptreg_helpers import eval_report, write_report


@pytest.fixture
def root(tmp_path, capsys):
    store = tmp_path / "prompts"
    for text in ("You are one.", "You are one. Ask first."):
        file = tmp_path / "text.md"
        file.write_text(text)
        assert main(["--root", str(store), "add", "system", "--file", str(file), "--author", "a", "--changelog", "c"]) == 0
    capsys.readouterr()
    return store


def run_cli(root, capsys, *args):
    code = main(["--root", str(root), *args])
    return code, capsys.readouterr().out


def test_list_show_and_diff(root, capsys):
    _, listing = run_cli(root, capsys, "list")
    assert "system: versions=[1, 2] production=v1 canary=- pin=-" in listing
    _, shown = run_cli(root, capsys, "show", "system")
    assert "system v1 sha256=" in shown and "You are one." in shown
    _, diff = run_cli(root, capsys, "diff", "system", "1", "2")
    assert "+Ask first." in diff


def test_resolve_pin_and_canary_flow(root, capsys):
    assert run_cli(root, capsys, "canary", "system", "2", "100")[0] == 0
    _, resolved = run_cli(root, capsys, "resolve", "system", "run-1")
    assert "system v2" in resolved and "reason=canary: bucket" in resolved
    _, shadow = run_cli(root, capsys, "resolve", "system", "run-1", "--shadow")
    assert "primary: system v1" in shadow and "shadow: system v2" in shadow
    run_cli(root, capsys, "pin", "system", "1")
    assert "system v1" in run_cli(root, capsys, "resolve", "system", "run-1")[1]
    run_cli(root, capsys, "pin", "system", "--clear")
    assert "system v2" in run_cli(root, capsys, "resolve", "system", "run-1")[1]


def test_promote_exit_codes_and_rollback(root, tmp_path, capsys):
    baseline = write_report(tmp_path / "b.json", eval_report({"a": (5, 10)}))
    bad = write_report(tmp_path / "bad.json", eval_report({"a": (5, 10)}, safety_failures=1))
    good = write_report(tmp_path / "good.json", eval_report({"a": (9, 10)}))
    args = ("promote", "system", "2", "--baseline", str(baseline))
    code, out = run_cli(root, capsys, *args, "--candidate", str(bad))
    assert (code, out.splitlines()[0]) == (1, "REFUSED")
    code, out = run_cli(root, capsys, *args, "--candidate", str(good), "--dry-run")
    assert (code, out.splitlines()[0]) == (0, "APPROVED")
    assert json.loads((root / "system" / "index.json").read_text())["aliases"]["production"] == 1
    assert run_cli(root, capsys, *args, "--candidate", str(good))[0] == 0
    assert "production is now v1" in run_cli(root, capsys, "rollback", "system")[1]


def test_errors_exit_2_with_a_message_on_stderr(root, capsys):
    code = main(["--root", str(root), "show", "system", "9"])
    assert code == 2
    assert "no version 9" in capsys.readouterr().err
