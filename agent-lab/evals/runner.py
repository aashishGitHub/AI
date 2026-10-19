from __future__ import annotations

import io
import json
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from mcp.client.stdio import StdioServerParameters
from mcp.server import MCPServer

from agent.approval import allow_tools, deny_all
from agent.audit import AuditLog
from agent.llm import LLM, ScriptedLLM, turns_from_dicts
from agent.loop import RunResult
from agent.mcp_backend import stdio_server_params
from agent.session import run_session
from evals.case import Case
from evals.matchers import CaseError
from evals.scoring import CaseScore, score_run

ServerFactory = Callable[[Path], StdioServerParameters | MCPServer]

EMPTY_STATE: dict[str, Any] = {"acknowledged": {}, "links": []}


def stdio_server(state_file: Path) -> StdioServerParameters:
    return stdio_server_params(state_file)


def in_process_server(state_file: Path) -> MCPServer:
    from mcp_server.server import build_server
    from mcp_server.store import FixtureStore

    return build_server(FixtureStore(state_path=state_file))


async def run_case(
    case: Case,
    llm: LLM,
    make_server: ServerFactory = stdio_server,
    audit_path: Path | None = None,
) -> tuple[RunResult, dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        stream = audit_path.open("w") if audit_path else io.StringIO()
        try:
            result = await run_session(
                case.prompt,
                llm,
                make_server(state_file),
                AuditLog(stream, run_id=case.id),
                allow_tools(*case.approve) if case.approve else deny_all,
                case.max_steps,
            )
        finally:
            stream.close()
        state = json.loads(state_file.read_text()) if state_file.exists() else EMPTY_STATE
    return result, state


async def run_deterministic(
    cases: Sequence[Case], make_server: ServerFactory = stdio_server, audit_dir: Path | None = None
) -> list[CaseScore]:
    scores = []
    for case in cases:
        if not case.script:
            raise CaseError(f"case '{case.id}' has no script, so it cannot run in deterministic mode")
        llm = ScriptedLLM(turns_from_dicts(case.script))
        audit_path = audit_dir / f"{case.id}.jsonl" if audit_dir else None
        result, state = await run_case(case, llm, make_server, audit_path)
        scores.append(score_run(case, result, state))
    return scores


async def run_live(
    cases: Sequence[Case],
    make_llm: Callable[[], LLM],
    runs_per_case: int,
    make_server: ServerFactory = stdio_server,
    audit_dir: Path | None = None,
) -> list[CaseScore]:
    scores = []
    for case in cases:
        if not case.live:
            continue
        for run_index in range(1, runs_per_case + 1):
            audit_path = audit_dir / f"{case.id}-run{run_index}.jsonl" if audit_dir else None
            result, state = await run_case(case, make_llm(), make_server, audit_path)
            scores.append(score_run(case, result, state))
    return scores
