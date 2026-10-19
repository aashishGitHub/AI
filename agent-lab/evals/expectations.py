from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent.types import ToolCall
from evals.matchers import mismatch


@dataclass(frozen=True)
class ToolCheck:
    selection: tuple[str, ...]
    args: tuple[str, ...]
    args_checked: bool
    optimal_calls: int


class ToolExpectation(Protocol):
    def check(self, calls: Sequence[ToolCall]) -> ToolCheck: ...


def _arg_failures(position: str, tool: str, matchers: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    failures = []
    for key, matcher in matchers.items():
        reason = mismatch(matcher, key in arguments, arguments.get(key))
        if reason:
            failures.append(f"{position}{tool}: arg '{key}' {reason}")
    return failures


@dataclass(frozen=True)
class ExpectedCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExactSequence:
    calls: tuple[ExpectedCall, ...]

    def check(self, calls: Sequence[ToolCall]) -> ToolCheck:
        selection: list[str] = []
        args: list[str] = []
        expected_names = [c.tool for c in self.calls]
        actual_names = [c.name for c in calls]
        for index, (want, got) in enumerate(zip(self.calls, calls), start=1):
            if want.tool != got.name:
                selection.append(f"call {index}: expected '{want.tool}' but model called '{got.name}'")
                break
            args += _arg_failures(f"call {index} ", want.tool, want.args, got.arguments)
        else:
            if len(actual_names) > len(expected_names):
                selection.append(
                    f"unexpected extra call(s) {actual_names[len(expected_names):]} after {actual_names[:len(expected_names)]}"
                    f" (expected {len(expected_names)} call(s))"
                )
            elif len(actual_names) < len(expected_names):
                selection.append(f"missing call(s) {expected_names[len(actual_names):]} after {actual_names}")
        return ToolCheck(tuple(selection), tuple(args), any(c.args for c in self.calls), len(self.calls))


@dataclass(frozen=True)
class AllowedSet:
    allowed: frozenset[str]
    required: tuple[str, ...] = ()
    order: tuple[tuple[str, str], ...] = ()
    args: dict[str, dict[str, Any]] = field(default_factory=dict)
    optimal_calls: int = 0

    def check(self, calls: Sequence[ToolCall]) -> ToolCheck:
        names = [c.name for c in calls]
        selection = [f"tool '{n}' is not in the allowed set {sorted(self.allowed)}" for n in dict.fromkeys(names)
                     if n not in self.allowed]
        selection += [f"required tool '{t}' was never called" for t in self.required if t not in names]
        for first, second in self.order:
            if first in names and second in names and names.index(first) > names.index(second):
                selection.append(f"'{second}' was called before '{first}'")
        args: list[str] = []
        for index, call in enumerate(calls, start=1):
            args += _arg_failures(f"call {index} ", call.name, self.args.get(call.name, {}), call.arguments)
        return ToolCheck(tuple(selection), tuple(args), bool(self.args), self.optimal_calls)
