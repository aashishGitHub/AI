import json
from typing import Literal

from fde.types import Json

type EchoDecision = Literal["apply", "drop-as-echo", "conflict"]


def fingerprint(value: Json) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class EchoGuard:
    def __init__(self) -> None:
        self._last_pushed: dict[str, str] = {}

    def record_push(self, entity_id: str, fp: str) -> None:
        self._last_pushed[entity_id] = fp

    def last_pushed(self, entity_id: str) -> str | None:
        return self._last_pushed.get(entity_id)

    def decide(self, entity_id: str, incoming: str, local: str | None) -> EchoDecision:
        pushed = self._last_pushed.get(entity_id)
        if incoming == pushed or incoming == local:
            return "drop-as-echo"
        return "apply" if local == pushed else "conflict"
