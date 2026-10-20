from __future__ import annotations

from hashlib import sha256


def bucket(name: str, run_key: str) -> int:
    digest = sha256(f"{name}:{run_key}".encode()).hexdigest()
    return int(digest[:8], 16) % 100
