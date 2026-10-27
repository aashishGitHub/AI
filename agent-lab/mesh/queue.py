from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from mesh.envelope import Envelope

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'ready',
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0
)
"""

Handler = Callable[[Envelope], Awaitable[object]]


@dataclass(frozen=True)
class Leased:
    envelope: Envelope
    attempts: int


class MessageQueue:
    """At-least-once: a leased message not acked before lease_until becomes visible again."""

    def __init__(self, path: Path | str = ":memory:", lease_s: float = 30.0, max_attempts: int = 3,
                 clock: Callable[[], float] = time.time) -> None:
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(_SCHEMA)
        self._lease_s = lease_s
        self._max_attempts = max_attempts
        self._clock = clock

    def enqueue(self, env: Envelope) -> bool:
        cursor = self._db.execute("INSERT OR IGNORE INTO messages (message_id, body) VALUES (?, ?)",
                                  (env.message_id, json.dumps(env.to_dict())))
        return cursor.rowcount == 1

    def lease(self) -> Leased | None:
        now = self._clock()
        while True:
            row = self._db.execute(
                "SELECT message_id, body, attempts FROM messages"
                " WHERE state = 'ready' AND lease_until <= ? ORDER BY seq LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            message_id, body, attempts = row
            if attempts >= self._max_attempts:
                self._db.execute("UPDATE messages SET state = 'dead' WHERE message_id = ?", (message_id,))
                continue
            self._db.execute("UPDATE messages SET attempts = attempts + 1, lease_until = ? WHERE message_id = ?",
                             (now + self._lease_s, message_id))
            return Leased(Envelope.from_dict(json.loads(body)), attempts + 1)

    def ack(self, message_id: str) -> None:
        self._db.execute("UPDATE messages SET state = 'done' WHERE message_id = ?", (message_id,))

    def nack(self, message_id: str) -> None:
        self._db.execute("UPDATE messages SET lease_until = 0 WHERE message_id = ?", (message_id,))

    def dead_letters(self) -> list[str]:
        rows = self._db.execute("SELECT message_id FROM messages WHERE state = 'dead' ORDER BY seq").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        self._db.close()


async def process_one(queue: MessageQueue, handler: Handler) -> bool:
    leased = queue.lease()
    if leased is None:
        return False
    try:
        await handler(leased.envelope)
    except Exception:
        queue.nack(leased.envelope.message_id)
        return True
    queue.ack(leased.envelope.message_id)
    return True
