from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Protocol

from memory.records import KINDS, MAX_TEXT_CHARS, Kind, MemoryRecord, Provenance

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]
DEFAULT_MAX_RECORDS = 200


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return uuid.uuid4().hex


class MemoryStore(Protocol):
    """Every method takes tenant_id and can only see that tenant's records. Expired records are invisible."""

    def add(self, tenant_id: str, kind: Kind, text: str, provenance: Provenance, ttl: timedelta | None) -> MemoryRecord: ...

    def get(self, tenant_id: str, record_id: str) -> MemoryRecord | None: ...

    def list(self, tenant_id: str, kind: Kind | None = None) -> list[MemoryRecord]: ...

    def forget(self, tenant_id: str, record_id: str) -> bool: ...

    def forget_all(self, tenant_id: str) -> int: ...


def require_tenant(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    return tenant_id


def validate_new(tenant_id: str, kind: str, text: str) -> None:
    require_tenant(tenant_id)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not text.strip():
        raise ValueError("memory text is empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"memory text is longer than {MAX_TEXT_CHARS} characters")


def ids_to_evict(live: Sequence[MemoryRecord], max_records: int) -> list[str]:
    """Make room for one new record: drop episodic before semantic, then oldest first, then lowest id."""
    excess = len(live) + 1 - max_records
    if excess <= 0:
        return []
    ranked = sorted(live, key=lambda r: (r.kind != "episodic", r.created_at, r.id))
    return [r.id for r in ranked[:excess]]


def newest_first(records: Sequence[MemoryRecord]) -> list[MemoryRecord]:
    return sorted(records, key=lambda r: (-r.created_at.timestamp(), r.id))


class InMemoryStore:
    def __init__(self, clock: Clock = utc_now, new_id: IdFactory = new_uuid, max_records: int = DEFAULT_MAX_RECORDS) -> None:
        if max_records < 1:
            raise ValueError("max_records must be at least 1")
        self._clock = clock
        self._new_id = new_id
        self._max_records = max_records
        self._records: dict[str, MemoryRecord] = {}

    def add(self, tenant_id: str, kind: Kind, text: str, provenance: Provenance, ttl: timedelta | None) -> MemoryRecord:
        validate_new(tenant_id, kind, text)
        now = self._clock()
        self._purge_expired(tenant_id, now)
        for record_id in ids_to_evict(self._tenant(tenant_id), self._max_records):
            del self._records[record_id]
        record = MemoryRecord(self._new_id(), tenant_id, kind, text, provenance, now, None if ttl is None else now + ttl)
        self._records[record.id] = record
        return record

    def get(self, tenant_id: str, record_id: str) -> MemoryRecord | None:
        require_tenant(tenant_id)
        record = self._records.get(record_id)
        if record is None or record.tenant_id != tenant_id or record.is_expired(self._clock()):
            return None
        return record

    def list(self, tenant_id: str, kind: Kind | None = None) -> list[MemoryRecord]:
        require_tenant(tenant_id)
        now = self._clock()
        live = [r for r in self._tenant(tenant_id) if not r.is_expired(now) and kind in (None, r.kind)]
        return newest_first(live)

    def forget(self, tenant_id: str, record_id: str) -> bool:
        require_tenant(tenant_id)
        record = self._records.get(record_id)
        if record is None or record.tenant_id != tenant_id:
            return False
        del self._records[record_id]
        return True

    def forget_all(self, tenant_id: str) -> int:
        require_tenant(tenant_id)
        doomed = [r.id for r in self._tenant(tenant_id)]
        for record_id in doomed:
            del self._records[record_id]
        return len(doomed)

    def _tenant(self, tenant_id: str) -> list[MemoryRecord]:
        return [r for r in self._records.values() if r.tenant_id == tenant_id]

    def _purge_expired(self, tenant_id: str, now: datetime) -> None:
        for record in self._tenant(tenant_id):
            if record.is_expired(now):
                del self._records[record.id]
