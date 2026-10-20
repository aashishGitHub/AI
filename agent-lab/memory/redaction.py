from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import timedelta

from memory.records import Kind, MemoryRecord, Provenance
from memory.store import MemoryStore

# Heuristic: misses names, addresses, secrets and obfuscated digits; also flags some dates and times.
DEFAULT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("digits", re.compile(r"(?<![\w])\d{9,}(?![\w])")),
    ("phone", re.compile(r"(?<![\w])(?=(?:\D*\d){10,})\+?\(?\d[\d ().-]{8,}\d(?![\w])")),
)


class Redactor:
    def __init__(self, rules: Sequence[tuple[str, re.Pattern[str]]] = DEFAULT_RULES) -> None:
        self._rules = tuple(rules)

    def __call__(self, text: str) -> str:
        for label, pattern in self._rules:
            text = pattern.sub(f"[REDACTED:{label}]", text)
        return text


class RedactingStore:
    """Redacts text before it reaches the inner store, so no write path can skip it."""

    def __init__(self, inner: MemoryStore, redact: Redactor | None = None) -> None:
        self._inner = inner
        self._redact = redact or Redactor()

    def add(self, tenant_id: str, kind: Kind, text: str, provenance: Provenance, ttl: timedelta | None) -> MemoryRecord:
        return self._inner.add(tenant_id, kind, self._redact(text), provenance, ttl)

    def get(self, tenant_id: str, record_id: str) -> MemoryRecord | None:
        return self._inner.get(tenant_id, record_id)

    def list(self, tenant_id: str, kind: Kind | None = None) -> list[MemoryRecord]:
        return self._inner.list(tenant_id, kind)

    def forget(self, tenant_id: str, record_id: str) -> bool:
        return self._inner.forget(tenant_id, record_id)

    def forget_all(self, tenant_id: str) -> int:
        return self._inner.forget_all(tenant_id)
