from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class UnknownAgent(KeyError):
    pass


@dataclass(frozen=True)
class AgentCard:
    name: str
    version: str
    description: str
    endpoint: str
    skills: tuple[str, ...]
    auth: str = "hmac-envelope"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> AgentCard:
        return AgentCard(
            name=raw["name"], version=raw["version"], description=raw["description"],
            endpoint=raw["endpoint"], skills=tuple(raw["skills"]), auth=raw.get("auth", "hmac-envelope"),
        )


class Registry:
    def __init__(self, cards: tuple[AgentCard, ...] = ()) -> None:
        self._cards: dict[str, AgentCard] = {}
        for card in cards:
            self.register(card)

    def register(self, card: AgentCard) -> None:
        self._cards[card.name] = card

    def get(self, name: str) -> AgentCard:
        try:
            return self._cards[name]
        except KeyError:
            raise UnknownAgent(name) from None

    def find_by_skill(self, skill: str) -> list[AgentCard]:
        return sorted((c for c in self._cards.values() if skill in c.skills), key=lambda c: c.name)
