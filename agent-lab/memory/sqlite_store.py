from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from memory.records import MemoryRecord, Kind, Provenance
from memory.store import (
    DEFAULT_MAX_RECORDS,
    Clock,
    IdFactory,
    ids_to_evict,
    new_uuid,
    newest_first,
    require_tenant,
    utc_now,
    validate_new,
)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id         TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('semantic', 'episodic')),
    text       TEXT NOT NULL,
    source     TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    written_by TEXT NOT NULL,
    created_us INTEGER NOT NULL,
    expires_us INTEGER
);
CREATE INDEX IF NOT EXISTS memory_tenant_kind ON memory (tenant_id, kind, created_us);
"""

COLUMNS = "id, tenant_id, kind, text, source, run_id, written_by, created_us, expires_us"


def to_us(moment: datetime) -> int:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return (moment - EPOCH) // timedelta(microseconds=1)


def from_us(value: int) -> datetime:
    return EPOCH + timedelta(microseconds=value)


def _record(row: tuple) -> MemoryRecord:
    record_id, tenant_id, kind, text, source, run_id, written_by, created_us, expires_us = row
    return MemoryRecord(
        record_id, tenant_id, kind, text, Provenance(source, run_id, written_by),
        from_us(created_us), None if expires_us is None else from_us(expires_us),
    )


class SqliteMemoryStore:
    """One connection, one process. Every statement filters on tenant_id."""

    def __init__(self, path: str = ":memory:", clock: Clock = utc_now, new_id: IdFactory = new_uuid,
                 max_records: int = DEFAULT_MAX_RECORDS) -> None:
        if max_records < 1:
            raise ValueError("max_records must be at least 1")
        self._conn = sqlite3.connect(path)
        self._conn.executescript(SCHEMA)
        self._clock = clock
        self._new_id = new_id
        self._max_records = max_records

    def close(self) -> None:
        self._conn.close()

    def add(self, tenant_id: str, kind: Kind, text: str, provenance: Provenance, ttl: timedelta | None) -> MemoryRecord:
        validate_new(tenant_id, kind, text)
        now = self._clock()
        now_us = to_us(now)
        with self._conn:
            self._conn.execute(
                "DELETE FROM memory WHERE tenant_id = ? AND expires_us IS NOT NULL AND expires_us <= ?",
                (tenant_id, now_us),
            )
            live = self._select("WHERE tenant_id = ?", (tenant_id,))
            for record_id in ids_to_evict(live, self._max_records):
                self._conn.execute("DELETE FROM memory WHERE tenant_id = ? AND id = ?", (tenant_id, record_id))
            record = MemoryRecord(self._new_id(), tenant_id, kind, text, provenance, now, None if ttl is None else now + ttl)
            self._conn.execute(
                f"INSERT INTO memory ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.id, tenant_id, kind, text, provenance.source, provenance.run_id, provenance.written_by,
                 to_us(now), None if record.expires_at is None else to_us(record.expires_at)),
            )
        return record

    def get(self, tenant_id: str, record_id: str) -> MemoryRecord | None:
        require_tenant(tenant_id)
        rows = self._select(
            "WHERE tenant_id = ? AND id = ? AND (expires_us IS NULL OR expires_us > ?)",
            (tenant_id, record_id, to_us(self._clock())),
        )
        return rows[0] if rows else None

    def list(self, tenant_id: str, kind: Kind | None = None) -> list[MemoryRecord]:
        require_tenant(tenant_id)
        where = "WHERE tenant_id = ? AND (expires_us IS NULL OR expires_us > ?)"
        params: tuple = (tenant_id, to_us(self._clock()))
        if kind is not None:
            where += " AND kind = ?"
            params += (kind,)
        return newest_first(self._select(where, params))

    def forget(self, tenant_id: str, record_id: str) -> bool:
        require_tenant(tenant_id)
        with self._conn:
            cursor = self._conn.execute("DELETE FROM memory WHERE tenant_id = ? AND id = ?", (tenant_id, record_id))
        return cursor.rowcount == 1

    def forget_all(self, tenant_id: str) -> int:
        require_tenant(tenant_id)
        with self._conn:
            return self._conn.execute("DELETE FROM memory WHERE tenant_id = ?", (tenant_id,)).rowcount

    def _select(self, where: str, params: tuple) -> list[MemoryRecord]:
        return [_record(row) for row in self._conn.execute(f"SELECT {COLUMNS} FROM memory {where}", params)]
