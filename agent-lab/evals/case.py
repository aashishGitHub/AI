from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from evals.expectations import AllowedSet, ExactSequence, ExpectedCall, ToolExpectation
from evals.matchers import CaseError, validate_matcher

CASE_KEYS = {"id", "description", "prompt", "max_steps", "approve", "live", "expect", "script"}
EXPECT_KEYS = {"tools", "forbidden_tools", "denied", "final_text", "state"}
TEXT_KEYS = {"contains", "not_contains", "regex"}
STATE_KEYS = {"acknowledged", "linked"}
ALLOWED_SET_KEYS = {"allowed", "required", "order", "args", "optimal_calls"}


@dataclass(frozen=True)
class TextExpectation:
    contains: tuple[str, ...] = ()
    not_contains: tuple[str, ...] = ()
    regex: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateExpectation:
    acknowledged: frozenset[str] = frozenset()
    linked: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Case:
    id: str
    description: str
    prompt: str
    tools: ToolExpectation
    max_steps: int = 6
    approve: tuple[str, ...] = ()
    live: bool = True
    forbidden_tools: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    final_text: TextExpectation = field(default_factory=TextExpectation)
    state: StateExpectation = field(default_factory=StateExpectation)
    script: tuple[dict[str, Any], ...] = ()


def _only(raw: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise CaseError(f"{where}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")


def _tools(raw: Mapping[str, Any], where: str) -> ToolExpectation:
    if ("sequence" in raw) == ("allowed" in raw):
        raise CaseError(f"{where}: give exactly one of 'sequence' or 'allowed'")
    if "sequence" in raw:
        _only(raw, {"sequence"}, where)
        calls = []
        for position, item in enumerate(raw["sequence"], start=1):
            _only(item, {"tool", "args"}, f"{where}.sequence[{position}]")
            for key, matcher in item.get("args", {}).items():
                validate_matcher(matcher, f"{where}.sequence[{position}].args.{key}")
            calls.append(ExpectedCall(item["tool"], dict(item.get("args", {}))))
        return ExactSequence(tuple(calls))
    _only(raw, ALLOWED_SET_KEYS, where)
    for tool, matchers in raw.get("args", {}).items():
        for key, matcher in matchers.items():
            validate_matcher(matcher, f"{where}.args.{tool}.{key}")
    required = tuple(raw.get("required", ()))
    return AllowedSet(
        allowed=frozenset(raw["allowed"]),
        required=required,
        order=tuple((a, b) for a, b in raw.get("order", ())),
        args={t: dict(m) for t, m in raw.get("args", {}).items()},
        optimal_calls=raw.get("optimal_calls", len(required)),
    )


def case_from_dict(raw: Mapping[str, Any], source: str = "case") -> Case:
    _only(raw, CASE_KEYS, source)
    for key in ("id", "prompt", "expect"):
        if key not in raw:
            raise CaseError(f"{source}: missing required key '{key}'")
    expect = raw["expect"]
    _only(expect, EXPECT_KEYS, f"{source}.expect")
    if "tools" not in expect:
        raise CaseError(f"{source}.expect: missing required key 'tools'")
    text = expect.get("final_text", {})
    _only(text, TEXT_KEYS, f"{source}.expect.final_text")
    state = expect.get("state", {})
    _only(state, STATE_KEYS, f"{source}.expect.state")
    return Case(
        id=raw["id"],
        description=raw.get("description", ""),
        prompt=raw["prompt"],
        tools=_tools(expect["tools"], f"{source}.expect.tools"),
        max_steps=raw.get("max_steps", 6),
        approve=tuple(raw.get("approve", ())),
        live=raw.get("live", True),
        forbidden_tools=tuple(expect.get("forbidden_tools", ())),
        denied=tuple(expect.get("denied", ())),
        final_text=TextExpectation(
            tuple(text.get("contains", ())), tuple(text.get("not_contains", ())), tuple(text.get("regex", ()))
        ),
        state=StateExpectation(frozenset(state.get("acknowledged", ())), frozenset(state.get("linked", ()))),
        script=tuple(raw.get("script", ())),
    )


def load_cases(directory: Path) -> list[Case]:
    cases = [case_from_dict(yaml.safe_load(p.read_text()), p.name) for p in sorted(directory.glob("*.yaml"))]
    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise CaseError(f"duplicate case id(s): {duplicates}")
    return cases
