from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from orchestrator.errors import HandoffRefused


@dataclass(frozen=True)
class Limits:
    global_max_steps: int = 20
    max_handoffs: int = 2
    max_attempts: int = 3
    step_timeout_s: float = 30.0
    tool_timeout_s: float = 10.0
    wall_budget_s: float = 300.0
    backoff_base_s: float = 0.5
    backoff_cap_s: float = 8.0


class Uniform(Protocol):
    def uniform(self, a: float, b: float) -> float: ...


def full_jitter_delay(attempt: int, base_s: float, cap_s: float, rng: Uniform) -> float:
    return rng.uniform(0.0, min(cap_s, base_s * 2 ** (attempt - 1)))


class HandoffGuard:
    def __init__(self, max_handoffs: int) -> None:
        self._max = max_handoffs
        self._chain: list[str] = []

    @property
    def current(self) -> str:
        return self._chain[-1]

    def begin(self, role: str) -> None:
        self._chain = [role]

    def hand_off(self, to_role: str, allowed_targets: frozenset[str]) -> None:
        if to_role not in allowed_targets:
            raise HandoffRefused(f"{self.current} may not hand off to {to_role}")
        if to_role in self._chain:
            raise HandoffRefused(f"handoff cycle: {' -> '.join([*self._chain, to_role])}")
        if len(self._chain) - 1 >= self._max:
            raise HandoffRefused(f"max handoffs ({self._max}) reached at {' -> '.join(self._chain)}")
        self._chain.append(to_role)
