from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PENDING, RUNNING, SUCCEEDED, FAILED = "pending", "running", "succeeded", "failed"
WAITING_APPROVAL, CANCELLED = "waiting_approval", "cancelled"
TERMINAL = frozenset({SUCCEEDED, FAILED, CANCELLED})

STEP_MOVES = {
    PENDING: {RUNNING, CANCELLED},
    RUNNING: {RUNNING, SUCCEEDED, FAILED, PENDING, WAITING_APPROVAL, CANCELLED},
    WAITING_APPROVAL: {RUNNING, FAILED, CANCELLED},
    SUCCEEDED: set(),
    FAILED: set(),
    CANCELLED: set(),
}
RUN_MOVES = {
    PENDING: {RUNNING, CANCELLED},
    RUNNING: {RUNNING, SUCCEEDED, FAILED, WAITING_APPROVAL, CANCELLED},
    WAITING_APPROVAL: {RUNNING, FAILED, CANCELLED},
    SUCCEEDED: set(),
    FAILED: set(),
    CANCELLED: set(),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, workflow TEXT NOT NULL, status TEXT NOT NULL, input TEXT NOT NULL,
    output TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL REFERENCES runs(run_id), step_id TEXT NOT NULL, role TEXT NOT NULL,
    status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0, output TEXT, error TEXT,
    approval TEXT, pending_call TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, step_id)
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, ts TEXT NOT NULL,
    type TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    run_id TEXT NOT NULL, step_id TEXT NOT NULL, call_index INTEGER NOT NULL,
    tool TEXT NOT NULL, arguments TEXT NOT NULL, read_only INTEGER NOT NULL,
    status TEXT NOT NULL, content TEXT, is_error INTEGER,
    PRIMARY KEY (run_id, step_id, call_index)
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
"""


class InvalidTransition(Exception):
    pass


@dataclass(frozen=True)
class RunRow:
    run_id: str
    workflow: str
    status: str
    input: str
    output: str | None
    error: str | None


@dataclass(frozen=True)
class StepRow:
    run_id: str
    step_id: str
    role: str
    status: str
    attempt: int
    output: str | None
    error: str | None
    approval: str | None
    pending_call: str | None


@dataclass(frozen=True)
class EventRow:
    seq: int
    ts: str
    type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class JournalEntry:
    tool: str
    arguments: str
    read_only: bool
    status: str
    content: str | None
    is_error: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStore:
    def __init__(self, path: str | Path, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self._db
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._db.execute("COMMIT")

    def _now(self) -> str:
        return self._clock().isoformat()

    def _event(self, db: sqlite3.Connection, run_id: str, type_: str, payload: dict[str, Any]) -> None:
        db.execute("INSERT INTO events (run_id, ts, type, payload) VALUES (?, ?, ?, ?)",
                   (run_id, self._now(), type_, json.dumps(payload, sort_keys=True)))

    def append_event(self, run_id: str, type_: str, **payload: Any) -> None:
        with self._tx() as db:
            self._event(db, run_id, type_, payload)

    def create_run(self, run_id: str, workflow: str, input_: str) -> RunRow:
        now = self._now()
        with self._tx() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                       (run_id, workflow, PENDING, input_, now, now))
            self._event(db, run_id, "run_created", {"workflow": workflow})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRow:
        row = self._db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run {run_id}")
        return RunRow(row["run_id"], row["workflow"], row["status"], row["input"], row["output"], row["error"])

    def _move_run(self, db: sqlite3.Connection, run_id: str, new: str, event: str | None, output: str | None,
                  error: str | None, **payload: Any) -> None:
        row = db.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run {run_id}")
        if new not in RUN_MOVES[row["status"]]:
            raise InvalidTransition(f"run {run_id}: {row['status']} -> {new}")
        db.execute("UPDATE runs SET status = ?, output = COALESCE(?, output), error = COALESCE(?, error),"
                   " updated_at = ? WHERE run_id = ?", (new, output, error, self._now(), run_id))
        self._event(db, run_id, event or f"run_{new}", {"prev": row["status"], **payload})

    def set_run_status(self, run_id: str, new: str, *, event: str | None = None, output: str | None = None,
                       error: str | None = None) -> None:
        with self._tx() as db:
            self._move_run(db, run_id, new, event, output, error, **({"reason": error} if error else {}))

    def ensure_step(self, run_id: str, step_id: str, role: str) -> StepRow:
        now = self._now()
        with self._tx() as db:
            created = db.execute("INSERT OR IGNORE INTO steps (run_id, step_id, role, status, created_at, updated_at)"
                                 " VALUES (?, ?, ?, ?, ?, ?)", (run_id, step_id, role, PENDING, now, now)).rowcount
            if created:
                self._event(db, run_id, "step_created", {"step": step_id, "role": role})
        return self.get_step(run_id, step_id)

    def get_step(self, run_id: str, step_id: str) -> StepRow | None:
        row = self._db.execute("SELECT * FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id)).fetchone()
        return _step(row) if row else None

    def steps(self, run_id: str) -> list[StepRow]:
        rows = self._db.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY created_at, rowid", (run_id,))
        return [_step(r) for r in rows]

    def attempts_started(self, run_id: str) -> int:
        return self._db.execute("SELECT COALESCE(SUM(attempt), 0) FROM steps WHERE run_id = ?", (run_id,)).fetchone()[0]

    def _move_step(self, db: sqlite3.Connection, run_id: str, step_id: str, new: str, event: str | None, *,
                   output: str | None = None, error: str | None = None, pending_call: str | None = None,
                   bump_attempt: bool = False, **payload: Any) -> int:
        row = db.execute("SELECT status, attempt FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id)).fetchone()
        if row is None:
            raise KeyError(f"unknown step {run_id}/{step_id}")
        if new not in STEP_MOVES[row["status"]]:
            raise InvalidTransition(f"step {run_id}/{step_id}: {row['status']} -> {new}")
        attempt = row["attempt"] + (1 if bump_attempt else 0)
        db.execute("UPDATE steps SET status = ?, attempt = ?, output = COALESCE(?, output), error = ?,"
                   " pending_call = COALESCE(?, pending_call), updated_at = ? WHERE run_id = ? AND step_id = ?",
                   (new, attempt, output, error, pending_call, self._now(), run_id, step_id))
        self._event(db, run_id, event or f"step_{new}", {"step": step_id, "prev": row["status"], "attempt": attempt, **payload})
        return attempt

    def begin_attempt(self, run_id: str, step_id: str) -> StepRow:
        with self._tx() as db:
            before = db.execute("SELECT status FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id)).fetchone()
            resumed_after_approval = before is not None and before["status"] == WAITING_APPROVAL
            self._move_step(db, run_id, step_id, RUNNING, None, bump_attempt=not resumed_after_approval)
        return self.get_step(run_id, step_id)  # type: ignore[return-value]

    def succeed_step(self, run_id: str, step_id: str, output: str) -> None:
        with self._tx() as db:
            self._move_step(db, run_id, step_id, SUCCEEDED, None, output=output)

    def fail_step(self, run_id: str, step_id: str, error: str) -> None:
        with self._tx() as db:
            self._move_step(db, run_id, step_id, FAILED, None, error=error, reason=error)

    def schedule_retry(self, run_id: str, step_id: str, error: str, delay_s: float) -> None:
        with self._tx() as db:
            self._move_step(db, run_id, step_id, PENDING, "step_retry_scheduled", error=error, reason=error,
                            delay_s=delay_s)

    def pause_for_approval(self, run_id: str, step_id: str, pending_call: str) -> None:
        with self._tx() as db:
            self._move_step(db, run_id, step_id, WAITING_APPROVAL, None, pending_call=pending_call,
                            call=json.loads(pending_call))
            db.execute("UPDATE steps SET approval = NULL WHERE run_id = ? AND step_id = ?", (run_id, step_id))
            self._move_run(db, run_id, WAITING_APPROVAL, None, None, None, step=step_id)

    def approve_step(self, run_id: str, step_id: str) -> None:
        with self._tx() as db:
            step = self._waiting_step(db, run_id, step_id)
            db.execute("UPDATE steps SET approval = 'granted' WHERE run_id = ? AND step_id = ?", (run_id, step_id))
            self._event(db, run_id, "approval_granted", {"step": step_id, "call": json.loads(step["pending_call"])})

    def deny_step(self, run_id: str, step_id: str) -> None:
        with self._tx() as db:
            step = self._waiting_step(db, run_id, step_id)
            reason = f"approval denied for step {step_id}"
            db.execute("UPDATE steps SET approval = 'denied' WHERE run_id = ? AND step_id = ?", (run_id, step_id))
            self._event(db, run_id, "approval_denied", {"step": step_id, "call": json.loads(step["pending_call"])})
            self._move_step(db, run_id, step_id, FAILED, None, error=reason, reason=reason)
            self._move_run(db, run_id, FAILED, None, None, reason, reason=reason)

    def _waiting_step(self, db: sqlite3.Connection, run_id: str, step_id: str) -> sqlite3.Row:
        step = db.execute("SELECT * FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id)).fetchone()
        if step is None or step["status"] != WAITING_APPROVAL:
            raise InvalidTransition(f"step {run_id}/{step_id} is not waiting for approval")
        return step

    def cancel_run(self, run_id: str) -> None:
        with self._tx() as db:
            self._move_run(db, run_id, CANCELLED, None, None, None)
            open_steps = db.execute("SELECT step_id FROM steps WHERE run_id = ? AND status NOT IN (?, ?, ?)",
                                    (run_id, *sorted(TERMINAL))).fetchall()
            for row in open_steps:
                self._move_step(db, run_id, row["step_id"], CANCELLED, None)

    def events(self, run_id: str) -> list[EventRow]:
        rows = self._db.execute("SELECT seq, ts, type, payload FROM events WHERE run_id = ? ORDER BY seq", (run_id,))
        return [EventRow(r["seq"], r["ts"], r["type"], json.loads(r["payload"])) for r in rows]

    def journal_get(self, run_id: str, step_id: str, call_index: int) -> JournalEntry | None:
        row = self._db.execute("SELECT * FROM journal WHERE run_id = ? AND step_id = ? AND call_index = ?",
                               (run_id, step_id, call_index)).fetchone()
        if row is None:
            return None
        return JournalEntry(row["tool"], row["arguments"], bool(row["read_only"]), row["status"], row["content"],
                            bool(row["is_error"]))

    def journal_start(self, run_id: str, step_id: str, call_index: int, tool: str, arguments: str,
                      read_only: bool) -> None:
        with self._tx() as db:
            db.execute("INSERT OR REPLACE INTO journal VALUES (?, ?, ?, ?, ?, ?, 'started', NULL, NULL)",
                       (run_id, step_id, call_index, tool, arguments, int(read_only)))

    def journal_finish(self, run_id: str, step_id: str, call_index: int, content: str, is_error: bool) -> None:
        with self._tx() as db:
            db.execute("UPDATE journal SET status = 'done', content = ?, is_error = ? WHERE run_id = ? AND step_id = ?"
                       " AND call_index = ?", (content, int(is_error), run_id, step_id, call_index))


def _step(row: sqlite3.Row) -> StepRow:
    return StepRow(row["run_id"], row["step_id"], row["role"], row["status"], row["attempt"], row["output"],
                   row["error"], row["approval"], row["pending_call"])
