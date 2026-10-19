from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any

# titleId is left out on purpose: it is an optional filter the model may fairly normalise from free text.
IDENTIFIER_ARGS = frozenset({"tenantId", "alertId", "issueKey"})


def ungrounded_args(
    arguments: Mapping[str, Any], identifier_args: Collection[str], evidence: Sequence[str]
) -> list[str]:
    return sorted(
        name
        for name in identifier_args
        if isinstance(arguments.get(name), str) and not _appears_in(arguments[name], evidence)
    )


def _appears_in(value: str, evidence: Sequence[str]) -> bool:
    if not value.strip():
        return False
    token = re.compile(rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", re.IGNORECASE)
    return any(token.search(text) for text in evidence)
