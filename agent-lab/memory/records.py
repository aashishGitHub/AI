from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Literal

Kind = Literal["semantic", "episodic"]
KINDS: tuple[Kind, ...] = ("semantic", "episodic")

MAX_TEXT_CHARS = 1000

# Arbitrary defaults, not measured: facts outlive run summaries.
DEFAULT_TTL = MappingProxyType({"semantic": timedelta(days=90), "episodic": timedelta(days=30)})


@dataclass(frozen=True)
class Provenance:
    source: str
    run_id: str
    written_by: str


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    tenant_id: str
    kind: Kind
    text: str
    provenance: Provenance
    created_at: datetime
    expires_at: datetime | None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at
