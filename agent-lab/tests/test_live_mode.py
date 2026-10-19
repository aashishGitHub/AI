from __future__ import annotations

import json

from agent.ollama import OllamaLLM
from evals.case import load_cases
from evals.cli import CASES_DIR, main, pulled_models
from evals.metrics import summarize
from evals.runner import in_process_server, run_live
from tests.fake_ollama import FakeOllama, serve, text_response, tool_response
from tests.helpers import run


def lookup_case():
    return [c for c in load_cases(CASES_DIR) if c.id == "lookup_live_metrics"]


def test_live_runner_reports_a_per_case_pass_rate_over_n_runs_against_a_fake_ollama():
    good = [tool_response("get_live_metrics", tenantId="streamflix"), text_response("streamflix error rate 7.1%")]
    wrong_tool = [tool_response("list_active_alerts", tenantId="streamflix"), text_response("streamflix error rate")]
    fake = FakeOllama(good + wrong_tool + good + good)
    with serve(fake) as url:
        scores = run(run_live(lookup_case(), lambda: OllamaLLM("fake", url), 4, in_process_server))
    summary = summarize(scores)
    case = summary.cases[0]
    assert (case.runs, case.successes, case.pass_rate) == (4, 3, 0.75)
    assert case.pass_at(1) == 0.75
    assert case.pass_at(2) == 1.0
    assert [s.selection.ok for s in scores] == [True, False, True, True]
    assert len(fake.requests) == 8


def test_live_runner_skips_cases_marked_deterministic_only():
    cases = [c for c in load_cases(CASES_DIR) if c.id == "injection_obeyed_gate_blocks"]
    assert run(run_live(cases, lambda: OllamaLLM("fake", "http://127.0.0.1:1"), 3, in_process_server)) == []


def test_live_cli_skips_cleanly_when_ollama_is_not_running(capsys):
    assert main(["live", "--model", "any", "--ollama-url", "http://127.0.0.1:1"]) == 0
    assert "SKIPPED: no Ollama reachable" in capsys.readouterr().out


def test_live_cli_skips_cleanly_when_the_model_is_not_pulled(capsys):
    fake = FakeOllama([])

    import http.server

    class Tags(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"models": [{"name": "other:1b", "model": "other:1b"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    from tests.fake_ollama import QuickServer
    import threading

    server = QuickServer(("127.0.0.1", 0), Tags)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert pulled_models(url) == ["other:1b"]
        assert main(["live", "--model", "wanted:3b", "--ollama-url", url]) == 0
        assert "SKIPPED: model 'wanted:3b' is not pulled" in capsys.readouterr().out
    finally:
        server.shutdown()
        server.server_close()
    assert fake.requests == []
