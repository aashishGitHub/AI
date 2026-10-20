from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Sequence
from pathlib import Path

from promptreg.errors import PromptRegError
from promptreg.gate import Decision, Gate
from promptreg.registry import PromptRegistry
from promptreg.stats import Z_95
from promptreg.store import PromptStore

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m promptreg")
    parser.add_argument("--root", type=Path, default=PROMPTS_DIR, help="prompt store directory")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="every prompt with its aliases")

    show = commands.add_parser("show", help="metadata and text of one version (default: production)")
    show.add_argument("name")
    show.add_argument("version", nargs="?", type=int)

    diff = commands.add_parser("diff", help="unified diff between two versions")
    diff.add_argument("name")
    diff.add_argument("old", type=int)
    diff.add_argument("new", type=int)

    resolve = commands.add_parser("resolve", help="which version this run_key gets")
    resolve.add_argument("name")
    resolve.add_argument("run_key")
    resolve.add_argument("--version", type=int, help="explicit version, wins over everything")
    resolve.add_argument("--shadow", action="store_true", help="show the primary and the shadow candidate")

    add = commands.add_parser("add", help="add an immutable version from a file")
    add.add_argument("name")
    add.add_argument("--file", type=Path, required=True)
    add.add_argument("--author", required=True)
    add.add_argument("--changelog", required=True)

    promote = commands.add_parser("promote", help="move production to a version if the eval gate allows it")
    promote.add_argument("name")
    promote.add_argument("version", type=int)
    promote.add_argument("--candidate", type=Path, required=True, help="eval report JSON of the candidate")
    promote.add_argument("--baseline", type=Path, required=True, help="eval report JSON of current production")
    promote.add_argument("--min-runs", type=int, default=Gate.min_runs)
    promote.add_argument("--margin", type=float, default=Gate.margin)
    promote.add_argument("--z", type=float, default=Z_95)
    promote.add_argument("--dry-run", action="store_true", help="print the decision, change and record nothing")

    rollback = commands.add_parser("rollback", help="restore the previous production version")
    rollback.add_argument("name")

    pin = commands.add_parser("pin", help="force one version for every run until --clear")
    pin.add_argument("name")
    pin.add_argument("version", nargs="?", type=int)
    pin.add_argument("--clear", action="store_true")

    canary = commands.add_parser("canary", help="send a percentage of run keys to a candidate version")
    canary.add_argument("name")
    canary.add_argument("version", nargs="?", type=int)
    canary.add_argument("percent", nargs="?", type=int)
    canary.add_argument("--clear", action="store_true")
    return parser


def _format_decision(decision: Decision) -> str:
    lines = ["APPROVED" if decision.approved else "REFUSED"]
    lines += [f"  reason: {reason}" for reason in decision.reasons]
    lines += [f"  warning: {warning}" for warning in decision.warnings]
    for case in decision.cases:
        lines.append(
            f"  {case.case_id:34} candidate {case.candidate_successes}/{case.candidate_runs}"
            f" [{case.candidate_interval[0]:.2f}, {case.candidate_interval[1]:.2f}]"
            f"  baseline {case.baseline_successes}/{case.baseline_runs}"
            f" [{case.baseline_interval[0]:.2f}, {case.baseline_interval[1]:.2f}]  {case.verdict}"
        )
    return "\n".join(lines)


def _list(store: PromptStore) -> None:
    for name in store.names():
        index = store.load_index(name)
        canary = f"v{index.canary}@{index.canary_percent}%" if index.canary else "-"
        pin = f"v{index.pin}" if index.pin else "-"
        print(f"{name}: versions={sorted(index.versions)} production=v{index.production} canary={canary} pin={pin}")


def _show(store: PromptStore, args: argparse.Namespace) -> None:
    index = store.load_index(args.name)
    version = args.version or index.production
    if version is None:
        raise PromptRegError(f"{args.name} has no production version; pass a version")
    text, _ = store.read_version(args.name, version)
    meta = index.versions[version]
    print(f"{args.name} v{version} sha256={meta.sha256}\ncreated_at={meta.created_at} author={meta.author}")
    print(f"changelog={meta.changelog}\n---\n{text}")


def _sentences(text: str) -> list[str]:
    return [line + "\n" for line in text.replace(". ", ".\n").splitlines()]


def _diff(store: PromptStore, args: argparse.Namespace) -> None:
    old, _ = store.read_version(args.name, args.old)
    new, _ = store.read_version(args.name, args.new)
    sys.stdout.writelines(difflib.unified_diff(_sentences(old), _sentences(new), f"v{args.old}", f"v{args.new}"))


def _resolve(registry: PromptRegistry, args: argparse.Namespace) -> None:
    if args.shadow:
        pair = registry.resolve_shadow(args.name, args.run_key)
        refs = [("primary", pair.primary)] + ([("shadow", pair.shadow)] if pair.shadow else [])
    else:
        refs = [("resolved", registry.resolve(args.name, args.run_key, args.version))]
    for label, ref in refs:
        print(f"{label}: {ref.name} v{ref.version} sha256={ref.sha256} reason={ref.reason}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = PromptStore(args.root)
    registry = PromptRegistry(store)
    try:
        if args.command == "list":
            _list(store)
        elif args.command == "show":
            _show(store, args)
        elif args.command == "diff":
            _diff(store, args)
        elif args.command == "resolve":
            _resolve(registry, args)
        elif args.command == "add":
            number = registry.add_version(args.name, args.file.read_text(), args.author, args.changelog)
            print(f"added {args.name} v{number}")
        elif args.command == "promote":
            gate = Gate(args.min_runs, args.margin, args.z)
            decision = registry.promote(args.name, args.version, args.candidate, args.baseline, gate, args.dry_run)
            print(_format_decision(decision))
            return 0 if decision.approved else 1
        elif args.command == "rollback":
            print(f"{args.name} production is now v{registry.rollback(args.name)}")
        elif args.command == "pin":
            if args.clear:
                registry.unpin(args.name)
            elif args.version is None:
                parser.error("pin needs a version or --clear")
            else:
                registry.pin(args.name, args.version)
        elif args.command == "canary":
            if args.clear:
                registry.clear_canary(args.name)
            elif args.version is None or args.percent is None:
                parser.error("canary needs a version and a percent, or --clear")
            else:
                registry.set_canary(args.name, args.version, args.percent)
    except PromptRegError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
