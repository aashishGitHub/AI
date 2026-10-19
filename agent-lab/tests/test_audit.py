from __future__ import annotations

import io
import json
from datetime import datetime, timezone

from agent.audit import AuditLog


def test_each_event_is_one_json_line_with_run_id_sequence_and_timestamp():
    stream = io.StringIO()
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    log = AuditLog(stream, run_id="r1", clock=lambda: fixed)
    log.record("run_start", prompt="hi")
    log.record("model_turn", step=1, tool_calls=[])
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [line["seq"] for line in lines] == [1, 2]
    assert {line["run_id"] for line in lines} == {"r1"}
    assert lines[0] == {
        "ts": "2026-01-02T03:04:05+00:00",
        "run_id": "r1",
        "seq": 1,
        "event": "run_start",
        "prompt": "hi",
    }


def test_values_that_are_not_json_serialisable_are_stringified_not_raised():
    stream = io.StringIO()
    AuditLog(stream, run_id="r").record("x", value={1, 2})
    assert json.loads(stream.getvalue())["value"]
