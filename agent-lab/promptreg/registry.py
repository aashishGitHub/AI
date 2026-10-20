from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from promptreg.bucketing import bucket
from promptreg.errors import InvalidReport, PromptRegError, StateError
from promptreg.gate import Decision, Gate, evaluate
from promptreg.models import PromptRef, ShadowPair
from promptreg.store import PromptStore

PRODUCTION_EVENTS = ("bootstrap", "promote", "rollback")


class PromptRegistry:
    def __init__(self, store: PromptStore) -> None:
        self._store = store

    def add_version(self, name: str, text: str, author: str, changelog: str, version: int | None = None) -> int:
        number = self._store.add_version(name, text, author, changelog, version)
        index = self._store.load_index(name)
        if index.production is None:
            index.production = number
            self._store.save_index(name, index)
            self._store.append_history(name, "bootstrap", to=number)
        return number

    def _ref(self, name: str, version: int, reason: str) -> PromptRef:
        text, digest = self._store.read_version(name, version)
        return PromptRef(name, version, digest, text, reason)

    def resolve(self, name: str, run_key: str, version: int | None = None) -> PromptRef:
        index = self._store.load_index(name)
        if version is not None:
            return self._ref(name, version, f"explicit version {version}")
        if index.pin is not None:
            return self._ref(name, index.pin, f"pinned to {index.pin}")
        if index.production is None:
            raise StateError(f"{name} has no production version")
        if index.canary is None or index.canary_percent == 0:
            return self._ref(name, index.production, "production: no canary configured")
        slot = bucket(name, run_key)
        if slot < index.canary_percent:
            return self._ref(name, index.canary, f"canary: bucket {slot} < {index.canary_percent}")
        return self._ref(name, index.production, f"production: bucket {slot} >= {index.canary_percent}")

    def resolve_shadow(self, name: str, run_key: str) -> ShadowPair:
        index = self._store.load_index(name)
        if index.pin is not None:
            primary = self._ref(name, index.pin, f"pinned to {index.pin}")
        elif index.production is not None:
            primary = self._ref(name, index.production, "production (primary run)")
        else:
            raise StateError(f"{name} has no production version")
        shadow = None
        if index.canary is not None and index.canary != primary.version:
            shadow = self._ref(name, index.canary, "shadow: canary candidate")
        return ShadowPair(primary, shadow)

    def set_canary(self, name: str, version: int, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise PromptRegError(f"canary percent must be 0..100, got {percent}")
        self._store.read_version(name, version)
        index = self._store.load_index(name)
        index.canary, index.canary_percent = version, percent
        self._store.save_index(name, index)
        self._store.append_history(name, "canary_set", version=version, percent=percent)

    def clear_canary(self, name: str) -> None:
        index = self._store.load_index(name)
        index.canary, index.canary_percent = None, 0
        self._store.save_index(name, index)
        self._store.append_history(name, "canary_clear")

    def pin(self, name: str, version: int) -> None:
        self._store.read_version(name, version)
        index = self._store.load_index(name)
        index.pin = version
        self._store.save_index(name, index)
        self._store.append_history(name, "pin", version=version)

    def unpin(self, name: str) -> None:
        index = self._store.load_index(name)
        index.pin = None
        self._store.save_index(name, index)
        self._store.append_history(name, "unpin")

    def promote(self, name: str, version: int, candidate_report: Path, baseline_report: Path,
                gate: Gate, dry_run: bool = False) -> Decision:
        ref = self._ref(name, version, "promotion candidate")
        index = self._store.load_index(name)
        candidate, baseline = _load(candidate_report), _load(baseline_report)
        decision = evaluate(candidate, baseline, gate)
        production_sha = index.versions[index.production].sha256 if index.production is not None else None
        extra_reasons, warnings = [], []
        if index.production == version:
            extra_reasons.append(f"{name} v{version} is already production")
        for label, report, expected in (
            ("candidate", candidate, (name, version, ref.sha256)),
            ("baseline", baseline, (name, index.production, production_sha)),
        ):
            stamp = report.get("prompt")
            target = f"{expected[0]} v{expected[1]}"
            if stamp is None:
                warnings.append(f"{label} report carries no prompt stamp: not proven to be a run of {target}")
            elif (stamp.get("name"), stamp.get("version"), stamp.get("sha256")) != expected:
                extra_reasons.append(f"{label} report is stamped {stamp}, expected {target} sha256 {expected[2]}")
        decision = replace(decision, reasons=decision.reasons + tuple(extra_reasons), warnings=tuple(warnings))
        if dry_run:
            return decision
        evidence = {
            "from": index.production,
            "to": version,
            "candidate_report_sha256": _file_sha256(candidate_report),
            "baseline_report_sha256": _file_sha256(baseline_report),
            "gate": {"min_runs": gate.min_runs, "margin": gate.margin, "z": gate.z},
        }
        if decision.approved:
            index.production = version
            self._store.save_index(name, index)
            self._store.append_history(name, "promote", **evidence)
        else:
            self._store.append_history(name, "promote_refused", reasons=list(decision.reasons), **evidence)
        return decision

    def rollback(self, name: str) -> int:
        index = self._store.load_index(name)
        stack: list[int] = []
        for event in self._store.read_history(name):
            if event["event"] == "rollback":
                stack = stack[:-1]
            elif event["event"] in PRODUCTION_EVENTS:
                stack.append(event["to"])
        if not stack or stack[-1] != index.production:
            history_says = stack[-1] if stack else None
            raise StateError(f"{name}: history says production is {history_says}, index says {index.production}")
        if len(stack) < 2:
            raise StateError(f"{name} has no earlier production version to roll back to")
        target = stack[-2]
        self._store.read_version(name, target)
        index.production = target
        self._store.save_index(name, index)
        self._store.append_history(name, "rollback", **{"from": stack[-1], "to": target})
        return target


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise InvalidReport(f"cannot read eval report {path}: {exc}") from exc


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
