from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from agent.approval import Approver, allow_tools, ask_on_terminal, deny_all
from agent.audit import AuditLog
from agent.llm import LLM, load_script
from agent.loop import RunResult
from agent.mcp_backend import PROJECT_ROOT, stdio_server_params
from agent.ollama import OllamaLLM
from agent.session import run_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agent", description="Run one prompt through the agent")
    parser.add_argument("prompt")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--model", help="Ollama model name (must already be pulled)")
    source.add_argument("--script", type=Path, help="replay a scripted trajectory (YAML list, or a case file)")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--approve", action="append", default=[], metavar="TOOL",
                        help="pre-approve a write tool for this run (repeatable); default is deny")
    parser.add_argument("--ask", action="store_true", help="ask on the terminal before each write tool")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--audit", type=Path, help="JSONL audit file (default: runs/audit-<timestamp>.jsonl)")
    parser.add_argument("--state-file", type=Path, help="where the server records acknowledgements and links")
    return parser


def _approver(approve: Sequence[str], ask: bool) -> Approver:
    if ask:
        return ask_on_terminal()
    return allow_tools(*approve) if approve else deny_all


def _llm(model: str | None, script: Path | None, ollama_url: str) -> LLM:
    return load_script(script) if script else OllamaLLM(model or "", base_url=ollama_url)


def _audit_path(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROJECT_ROOT / "runs" / f"audit-{stamp}.jsonl"


def _report(result: RunResult, audit_path: Path) -> None:
    for record in result.tool_records:
        verdict = "-" if record.decision is None else ("approved" if record.decision.approved else "DENIED")
        status = record.error_kind or "ok"
        print(f"  step {record.step}: {record.call.name}({record.call.arguments}) approval={verdict} result={status}")
    print(f"stop_reason={result.stop_reason} steps={result.steps} tool_calls={len(result.tool_records)}")
    if result.error:
        print(f"error: {result.error}")
    print(f"audit log: {audit_path}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit_path = _audit_path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("w") as stream:
        audit = AuditLog(stream, run_id=uuid.uuid4().hex[:12])
        result = asyncio.run(
            run_session(
                args.prompt,
                _llm(args.model, args.script, args.ollama_url),
                stdio_server_params(args.state_file),
                audit,
                _approver(args.approve, args.ask),
                args.max_steps,
            )
        )
    print(result.final_text or "(no final answer)")
    _report(result, audit_path)
    return 0 if result.stop_reason == "final" else 1


if __name__ == "__main__":
    sys.exit(main())
