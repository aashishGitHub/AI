from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from promptreg.errors import PromptRegError, TamperError, UnknownPrompt, VersionExists

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_hex(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VersionMeta:
    sha256: str
    created_at: str
    author: str
    changelog: str


@dataclass
class PromptIndex:
    versions: dict[int, VersionMeta] = field(default_factory=dict)
    production: int | None = None
    canary: int | None = None
    canary_percent: int = 0
    pin: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "versions": {str(v): asdict(meta) for v, meta in sorted(self.versions.items())},
            "aliases": {"production": self.production, "canary": self.canary},
            "canary_percent": self.canary_percent,
            "pin": self.pin,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> PromptIndex:
        return cls(
            versions={int(v): VersionMeta(**meta) for v, meta in raw["versions"].items()},
            production=raw["aliases"]["production"],
            canary=raw["aliases"]["canary"],
            canary_percent=raw["canary_percent"],
            pin=raw["pin"],
        )


class PromptStore:
    """prompts/<name>/v<N>.md plus index.json (hashes, aliases) and history.jsonl (append-only events)."""

    def __init__(self, root: Path, clock: Callable[[], datetime] = _utc_now) -> None:
        self._root = root
        self._clock = clock

    def _dir(self, name: str) -> Path:
        # The name becomes a path segment, so it must never contain '/' or '..'.
        if not NAME_PATTERN.match(name):
            raise PromptRegError(f"invalid prompt name {name!r}: use lowercase letters, digits, '_' or '-'")
        return self._root / name

    def names(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(p.name for p in self._root.iterdir() if (p / "index.json").is_file())

    def load_index(self, name: str) -> PromptIndex:
        path = self._dir(name) / "index.json"
        if not path.is_file():
            raise UnknownPrompt(f"no prompt named {name!r}")
        return PromptIndex.from_json(json.loads(path.read_text()))

    def save_index(self, name: str, index: PromptIndex) -> None:
        directory = self._dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "index.json.tmp"
        temporary.write_text(json.dumps(index.to_json(), indent=2) + "\n")
        os.replace(temporary, directory / "index.json")

    def add_version(self, name: str, text: str, author: str, changelog: str, version: int | None = None) -> int:
        directory = self._dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        index = self.load_index(name) if (directory / "index.json").is_file() else PromptIndex()
        number = version if version is not None else max(index.versions, default=0) + 1
        if number < 1:
            raise PromptRegError(f"version must be >= 1, got {number}")
        if number in index.versions:
            raise VersionExists(f"{name} v{number} already exists and is immutable")
        try:
            with (directory / f"v{number}.md").open("xb") as handle:
                handle.write(text.encode("utf-8"))
        except FileExistsError:
            raise VersionExists(f"{name} v{number}.md already exists on disk and is immutable") from None
        index.versions[number] = VersionMeta(sha256_hex(text), self._clock().isoformat(), author, changelog)
        self.save_index(name, index)
        return number

    def read_version(self, name: str, version: int) -> tuple[str, str]:
        meta = self.load_index(name).versions.get(version)
        if meta is None:
            raise UnknownPrompt(f"{name} has no version {version}")
        text = (self._dir(name) / f"v{version}.md").read_bytes().decode("utf-8")
        actual = sha256_hex(text)
        if actual != meta.sha256:
            raise TamperError(f"{name} v{version} was modified: recorded sha256 {meta.sha256}, file has {actual}")
        return text, meta.sha256

    def append_history(self, name: str, event: str, **fields: Any) -> None:
        line = {"ts": self._clock().isoformat(), "event": event, "name": name, **fields}
        with (self._dir(name) / "history.jsonl").open("a") as handle:
            handle.write(json.dumps(line, sort_keys=True) + "\n")

    def read_history(self, name: str) -> list[dict[str, Any]]:
        path = self._dir(name) / "history.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]
