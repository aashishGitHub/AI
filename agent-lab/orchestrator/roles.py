from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agent.types import ToolSpec

PromptProvider = Callable[[str], str]


@dataclass(frozen=True)
class AgentRole:
    name: str
    allowed_tools: frozenset[str] = frozenset()
    max_steps: int = 4
    handoff_to: frozenset[str] = frozenset()
    system_prompt: str = ""

    def visible_tools(self, tools: Sequence[ToolSpec]) -> list[ToolSpec]:
        return [t for t in tools if t.name in self.allowed_tools]


def check_roles(roles: Sequence[AgentRole], tools: Sequence[ToolSpec]) -> None:
    known = {t.name for t in tools}
    names = {r.name for r in roles}
    for role in roles:
        if role.allowed_tools - known:
            raise ValueError(f"role {role.name} allows unknown tools {sorted(role.allowed_tools - known)}")
        if role.handoff_to - names:
            raise ValueError(f"role {role.name} hands off to unknown roles {sorted(role.handoff_to - names)}")
