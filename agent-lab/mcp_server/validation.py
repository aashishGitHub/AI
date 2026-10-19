from __future__ import annotations

import re
import unicodedata

TEXT_CHARS = 200
TRUNCATED_MARKER = "[truncated]"

_TENANT = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ALERT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[0-9]{1,6}$")
_INVISIBLE = {"Cc", "Cf", "Cs", "Co", "Cn"}
_SPACE_LIKE = {"Zs", "Zl", "Zp"}


class InvalidToolInput(Exception):
    pass


def _invalid(argument: str, rule: str) -> InvalidToolInput:
    return InvalidToolInput(f"invalid argument '{argument}': expected {rule}")


def tenant(raw: object) -> str:
    if isinstance(raw, str) and _TENANT.match(raw):
        return raw
    raise _invalid(
        "tenantId",
        "1-32 characters: lowercase letters, digits and hyphens, not starting or ending with a hyphen",
    )


def optional_title(raw: object) -> str | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str) and _NAME.match(raw):
        return raw
    raise _invalid("titleId", "1-64 characters: letters, digits, '.', '_' and '-'")


def alert_id(raw: object) -> str:
    if isinstance(raw, str) and _ALERT_ID.match(raw):
        return raw
    raise _invalid("alertId", "1-128 characters: letters, digits, '.', '_', ':' and '-'")


def issue_key(raw: object) -> str:
    if isinstance(raw, str) and _ISSUE_KEY.match(raw):
        return raw
    raise _invalid("issueKey", "an issue key such as 'OPS-123' (project letters, a hyphen, digits)")


def untrusted_text(raw: str | None, max_chars: int = TEXT_CHARS) -> dict[str, object]:
    """Made safe to carry, not safe to obey: same rules as the Java UntrustedText."""
    if raw is None:
        return {"text": "", "truncated": False}
    clean: list[str] = []
    pending_space = False
    truncated = False
    length = 0
    for ch in raw:
        category = unicodedata.category(ch)
        if ch in "\t\n\r" or category in _SPACE_LIKE:
            pending_space = length > 0
            continue
        if category in _INVISIBLE:
            continue
        needed = 1 + (1 if pending_space else 0)
        if length + needed > max_chars:
            truncated = True
            break
        if pending_space:
            clean.append(" ")
            length += 1
            pending_space = False
        clean.append(ch)
        length += 1
    text = "".join(clean)
    return {"text": text + TRUNCATED_MARKER if truncated else text, "truncated": truncated}
