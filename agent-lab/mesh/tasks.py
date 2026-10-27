from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TaskState = Literal["working", "completed", "failed", "input-required"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    message_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    state TEXT NOT NULL,
    result TEXT
)
"""


@dataclass(frozen=True)
class TaskView:
    message_id: str
    correlation_id: str
    state: TaskState
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "correlation_id": self.correlation_id,
                "state": self.state, "result": self.result}


class TaskStore:
    def __init__(self, path: Path | str = ":memory:") -> None:
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(_SCHEMA)

    def begin(self, message_id: str, correlation_id: str) -> tuple[TaskView, bool]:
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO tasks (message_id, correlation_id, state) VALUES (?, ?, 'working')",
            (message_id, correlation_id))
        created = cursor.rowcount == 1
        existing = self.get(message_id)
        assert existing is not None
        return existing, created

    def finish(self, message_id: str, state: TaskState, result: dict[str, Any]) -> TaskView:
        self._db.execute("UPDATE tasks SET state = ?, result = ? WHERE message_id = ?",
                         (state, json.dumps(result), message_id))
        view = self.get(message_id)
        assert view is not None
        return view

    def get(self, message_id: str) -> TaskView | None:
        row = self._db.execute(
            "SELECT message_id, correlation_id, state, result FROM tasks WHERE message_id = ?",
            (message_id,)).fetchone()
        if row is None:
            return None
        return TaskView(row[0], row[1], row[2], json.loads(row[3]) if row[3] else None)

    def close(self) -> None:
        self._db.close()
