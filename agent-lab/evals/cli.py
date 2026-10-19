from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from agent.ollama import OllamaLLM
from evals.case import load_cases
from evals.report import render_text, to_json
from evals.runner import run_deterministic, run_live

CASES_DIR = Path(__file__).resolve().parent / "cases"


def pulled_models(base_url: str) -> list[str] | None:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=5) as response:
            models = json.loads(response.read())["models"]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
    return list(dict.fromkeys(name for m in models for name in (m.get("name"), m.get("model")) if name))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals")
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--report", type=Path, help="write a JSON report here")
    parser.add_argument("--audit-dir", type=Path, help="write one JSONL audit file per run here")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("deterministic", help="ScriptedLLM, no network, gating: exit 1 on any failure")
    live = modes.add_parser("live", help="OllamaLLM, report-only: always exit 0")
    live.add_argument("--model", required=True)
    live.add_argument("-n", type=int, default=5, help="runs per case")
    live.add_argument("--ollama-url", default="http://localhost:11434")
    return parser


def _deterministic(args: argparse.Namespace) -> int:
    scores = asyncio.run(run_deterministic(load_cases(args.cases), audit_dir=args.audit_dir))
    print(render_text(scores))
    if args.report:
        args.report.write_text(json.dumps(to_json(scores, {"mode": "deterministic"}), indent=2))
    return 0 if all(s.success for s in scores) else 1


def _live(args: argparse.Namespace) -> int:
    models = pulled_models(args.ollama_url)
    if models is None:
        print(f"SKIPPED: no Ollama reachable at {args.ollama_url}")
        return 0
    if args.model not in models and f"{args.model}:latest" not in models:
        print(f"SKIPPED: model '{args.model}' is not pulled; Ollama has: {models or 'no models'}")
        return 0
    scores = asyncio.run(
        run_live(load_cases(args.cases), lambda: OllamaLLM(args.model, args.ollama_url), args.n,
                 audit_dir=args.audit_dir)
    )
    k = min(args.n, 3)
    print(f"model={args.model} n={args.n} (tiny sample, local, report-only)")
    print(render_text(scores, k))
    if args.report:
        meta = {"mode": "live", "model": args.model, "n": args.n}
        args.report.write_text(json.dumps(to_json(scores, meta, k), indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _deterministic(args) if args.mode == "deterministic" else _live(args)


if __name__ == "__main__":
    sys.exit(main())
