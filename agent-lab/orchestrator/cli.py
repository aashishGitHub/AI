from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from agent.mcp_backend import PROJECT_ROOT
from orchestrator.control import RunControl
from orchestrator.crash import CRASH_POINTS, SimulatedCrash, crash_at, no_crash
from orchestrator.engine import RunSummary
from orchestrator.store import SUCCEEDED, WAITING_APPROVAL, WorkflowStore
from orchestrator.triage import INPUT, triage_orchestrator

EXIT_CODES = {SUCCEEDED: 0, WAITING_APPROVAL: 3}
EXIT_CRASHED = 70


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m orchestrator", description="Durable alert-triage workflow demo")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "runs" / "orchestrator.db")
    crash = argparse.ArgumentParser(add_help=False)
    crash.add_argument("--crash-at", metavar="POINT:STEP", help=f"simulate a process death; POINT is one of {CRASH_POINTS}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", parents=[crash], help="start a triage run")
    run.add_argument("--run-id")
    run.add_argument("--input", default=INPUT)
    resume = commands.add_parser("resume", parents=[crash], help="continue a run after a crash or an approval")
    resume.add_argument("run_id")
    commands.add_parser("status", help="print the timeline").add_argument("run_id")
    for name in ("approve", "deny"):
        sub = commands.add_parser(name, help=f"{name} the write a step is waiting on")
        sub.add_argument("run_id")
        sub.add_argument("step_id")
    commands.add_parser("cancel").add_argument("run_id")
    return parser


def _crash_hook(spec: str | None):
    if not spec:
        return no_crash
    point, _, step = spec.partition(":")
    if point not in CRASH_POINTS or not step:
        raise SystemExit(f"--crash-at must be POINT:STEP with POINT in {CRASH_POINTS}")
    return crash_at(point, step)


def _report(summary: RunSummary) -> int:
    print(f"run {summary.run_id}: {summary.status}")
    if summary.output:
        print(summary.output)
    if summary.error:
        print(f"error: {summary.error}")
    return EXIT_CODES.get(summary.status, 1)


async def _execute(args: argparse.Namespace) -> int:
    state_file = args.db.with_suffix(".state.json")
    audit_path = args.db.with_suffix(".audit.jsonl")
    crash = _crash_hook(args.crash_at)
    with audit_path.open("a") as audit:
        async with triage_orchestrator(args.db, state_file, audit, crash) as orchestrator:
            try:
                if args.command == "run":
                    return _report(await orchestrator.run("triage", args.input, args.run_id))
                return _report(await orchestrator.resume(args.run_id))
            except SimulatedCrash as crashed:
                print(f"simulated crash at {crashed}; run `resume` to finish")
                return EXIT_CRASHED


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.command in ("run", "resume"):
        return asyncio.run(_execute(args))
    store = WorkflowStore(args.db)
    try:
        control = RunControl(store)
        if args.command == "status":
            print(control.describe(args.run_id))
        elif args.command == "approve":
            control.approve(args.run_id, args.step_id)
            print(f"approved {args.step_id}; run `resume {args.run_id}` to continue")
        elif args.command == "deny":
            control.deny(args.run_id, args.step_id)
            print(f"denied {args.step_id}; run {args.run_id} is {store.get_run(args.run_id).status}")
        else:
            control.cancel(args.run_id)
            print(f"cancelled {args.run_id}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
