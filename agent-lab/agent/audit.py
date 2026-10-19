from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TextIO


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog:
    def __init__(self, stream: TextIO, run_id: str, clock: Callable[[], datetime] = _utc_now) -> None:
        self._stream = stream
        self._run_id = run_id
        self._clock = clock
        self._seq = 0

    def record(self, event: str, **fields: Any) -> None:
        self._seq += 1
        line = {
            "ts": self._clock().isoformat(),
            "run_id": self._run_id,
            "seq": self._seq,
            "event": event,
            **fields,
        }
        self._stream.write(json.dumps(line, default=str) + "\n")
        self._stream.flush()
