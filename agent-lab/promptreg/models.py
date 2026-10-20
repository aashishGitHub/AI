from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptRef:
    name: str
    version: int
    sha256: str
    text: str
    reason: str


@dataclass(frozen=True)
class ShadowPair:
    primary: PromptRef
    shadow: PromptRef | None
