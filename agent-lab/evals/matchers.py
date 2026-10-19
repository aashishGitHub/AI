from __future__ import annotations

import re
from typing import Any

MATCHER_KEYS = ("exact", "regex", "subset", "absent")


class CaseError(Exception):
    pass


def validate_matcher(matcher: Any, where: str) -> None:
    if not isinstance(matcher, dict):
        return
    if len(matcher) != 1 or next(iter(matcher)) not in MATCHER_KEYS:
        raise CaseError(f"{where}: a dict matcher must have exactly one key from {MATCHER_KEYS}, got {sorted(matcher)}")
    if "regex" in matcher:
        try:
            re.compile(matcher["regex"])
        except (re.error, TypeError) as exc:
            raise CaseError(f"{where}: bad regex: {exc}") from exc


def describe(matcher: Any) -> str:
    if not isinstance(matcher, dict):
        return f"exact {matcher!r}"
    kind, value = next(iter(matcher.items()))
    return "absent" if kind == "absent" else f"{kind} {value!r}"


def mismatch(matcher: Any, present: bool, actual: Any) -> str | None:
    """None when the argument satisfies the matcher, else the reason it does not."""
    kind, expected = ("exact", matcher) if not isinstance(matcher, dict) else next(iter(matcher.items()))
    if kind == "absent":
        return None if not present else f"expected the argument to be absent but got {actual!r}"
    if not present:
        return f"expected {describe(matcher)} but the argument was missing"
    if kind == "exact":
        return None if actual == expected else f"expected {describe(matcher)} but got {actual!r}"
    if kind == "regex":
        ok = isinstance(actual, str) and re.search(expected, actual) is not None
        return None if ok else f"expected {describe(matcher)} but got {actual!r}"
    if isinstance(actual, dict) and isinstance(expected, dict):
        ok = all(k in actual and actual[k] == v for k, v in expected.items())
    elif isinstance(actual, list) and isinstance(expected, list):
        ok = all(item in actual for item in expected)
    else:
        ok = False
    return None if ok else f"expected {describe(matcher)} but got {actual!r}"
