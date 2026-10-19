#!/usr/bin/env python3
"""Tier-1 eval gate: prove the eval harness grades the prompt the server actually ships.

Why this exists
---------------
On 2026-09-07 the eval suite's negative ("must decline") case failed while the *server*
answered the same question correctly with the same model. Cause: two different prompts.
`evals/prompts/answer.txt` said "use ONLY the context" but gave the model no permitted
alternative, so a model that could not comply invented syntax instead. The server's
`groundedSystemPrompt` supplies an exact refusal string, so the same model declined.

A prohibition without a permitted alternative is not a constraint, it is a trap — and an
eval that grades a prompt nobody ships cannot tell you whether production still works.

This check derives the rules from the SERVER prompt (the source of truth) and asserts the
eval prompt carries each one. Add a rule to the server and forget the eval, and CI fails.
No model, no network, no Docker — so it runs on every PR in milliseconds.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER_PROMPT = REPO / "fe-hands-on" / "server" / "stream.go"
EVAL_PROMPT = REPO / "evals" / "prompts" / "answer.txt"

# Rules that legitimately do NOT apply to the eval harness, with the reason.
# Keep this list SHORT and justified — every entry is a hole in the parity guarantee.
EXEMPT = {
    "cite the sources you used by their [n] number": (
        "eval golden contexts are a single unnumbered document, so there is no [n] to cite; "
        "citation fidelity needs its own test with numbered chunks"
    ),
}


def rules_from_server() -> list[str]:
    """Extract the bullet rules out of the Go `groundedSystemPrompt` raw string literal."""
    src = SERVER_PROMPT.read_text()
    m = re.search(r"groundedSystemPrompt\s*=\s*`(.+?)`", src, re.S)
    if not m:
        sys.exit(f"FAIL: could not find groundedSystemPrompt in {SERVER_PROMPT}")
    block = m.group(1)
    return [
        line.strip()[2:].strip()
        for line in block.splitlines()
        if line.strip().startswith("- ")
    ]


def norm(s: str) -> str:
    """Compare on lowercase, collapsed whitespace — wording drifts, meaning shouldn't."""
    return re.sub(r"\s+", " ", s.lower()).strip()


def rule_key(rule: str) -> str:
    """Normalised rule with trailing sentence punctuation removed.

    The eval prompt legitimately extends a rule ("...actionable steps, including exact
    syntax where relevant"), so matching must not require the server's full stop. Note
    this only strips a TRAILING '.' — the period inside the quoted refusal string is
    kept, because that string has to match exactly on both sides.
    """
    return norm(rule).rstrip(" .")


def main() -> int:
    server_rules = rules_from_server()
    if not server_rules:
        sys.exit("FAIL: no rules parsed from groundedSystemPrompt — parser is stale")

    eval_text = norm(EVAL_PROMPT.read_text())

    missing, exempted = [], []
    for rule in server_rules:
        key = rule_key(rule)
        if key in EXEMPT:
            exempted.append((rule, EXEMPT[key]))
        elif key not in eval_text:
            missing.append(rule)

    print(f"server rules found : {len(server_rules)}")
    print(f"exempted           : {len(exempted)}")
    for rule, why in exempted:
        print(f"  ~ {rule}\n      exempt: {why}")

    if missing:
        print(f"\nPROMPT PARITY FAILED — {len(missing)} server rule(s) absent from")
        print(f"{EVAL_PROMPT.relative_to(REPO)}:\n")
        for rule in missing:
            print(f"  x {rule}")
        print(
            "\nThe eval is grading a weaker prompt than the server ships, so its results\n"
            "say nothing about production behaviour. Copy the rule across, or add a\n"
            "justified entry to EXEMPT in this file.\n"
        )
        return 1

    print("\nPROMPT PARITY OK — every non-exempt server rule is present in the eval prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
