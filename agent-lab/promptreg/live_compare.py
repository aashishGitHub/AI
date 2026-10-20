from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import evals.runner
from agent.llm import LLM
from agent.ollama import OllamaLLM
from evals.case import Case, load_cases
from evals.cli import CASES_DIR, pulled_models
from evals.report import to_json
from evals.runner import run_live
from promptreg.cli import PROMPTS_DIR
from promptreg.registry import PromptRegistry
from promptreg.stats import wilson_interval
from promptreg.store import PromptStore


@contextmanager
def system_prompt_injected(text: str) -> Iterator[None]:
    # evals.runner.run_case has no system_prompt parameter and the eval package is not edited,
    # so the session call it makes is wrapped for the duration of the comparison.
    original = evals.runner.run_session

    async def with_prompt(*args: Any, **kwargs: Any):
        return await original(*args, system_prompt=text, **kwargs)

    with patch.object(evals.runner, "run_session", with_prompt):
        yield


def measure(cases: Sequence[Case], make_llm: Callable[[], LLM], runs: int, prompt_text: str) -> list:
    with system_prompt_injected(prompt_text):
        return asyncio.run(run_live(cases, make_llm, runs))


def render(reports: dict[int, dict[str, Any]]) -> str:
    versions = sorted(reports)
    lines = [f"{'case':34} " + "  ".join(f"{'v' + str(v) + ' pass [95% Wilson]':30}" for v in versions)]
    case_ids = [c["id"] for c in reports[versions[0]]["cases"]]
    for case_id in case_ids:
        cells = []
        for v in versions:
            case = next(c for c in reports[v]["cases"] if c["id"] == case_id)
            low, high = wilson_interval(case["successes"], case["runs"])
            cells.append(f"{case['successes']}/{case['runs']} [{low:.2f}, {high:.2f}]".ljust(30))
        lines.append(f"{case_id:34} " + "  ".join(cells))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m promptreg.live_compare")
    parser.add_argument("name")
    parser.add_argument("versions", nargs="+", type=int)
    parser.add_argument("--only", action="append", required=True, metavar="CASE_ID")
    parser.add_argument("-n", type=int, default=5)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    models = pulled_models(args.ollama_url)
    if models is None or (args.model not in models and f"{args.model}:latest" not in models):
        print(f"SKIPPED: model {args.model!r} not available at {args.ollama_url}")
        return 0
    cases = [c for c in load_cases(CASES_DIR) if c.id in args.only]
    unknown = sorted(set(args.only) - {c.id for c in cases})
    if unknown:
        parser.error(f"unknown case id(s) {unknown}")

    store = PromptStore(PROMPTS_DIR)
    registry = PromptRegistry(store)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    reports: dict[int, dict[str, Any]] = {}
    for version in args.versions:
        ref = registry.resolve(args.name, "live-compare", version=version)
        scores = measure(cases, lambda: OllamaLLM(args.model, args.ollama_url), args.n, ref.text)
        meta = {"mode": "live", "model": args.model, "n": args.n,
                "prompt": {"name": ref.name, "version": ref.version, "sha256": ref.sha256}}
        reports[version] = to_json(scores, meta)
        path = args.out_dir / f"{args.name}-v{version}-n{args.n}.json"
        path.write_text(json.dumps(reports[version], indent=2))
        print(f"wrote {path}", flush=True)
    print(render(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
