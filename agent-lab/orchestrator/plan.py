from __future__ import annotations

import json
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from orchestrator.errors import PlanError

MAX_SUBTASKS = 5

PLAN_SCHEMA = {
    "type": "object",
    "required": ["subtasks"],
    "additionalProperties": False,
    "properties": {
        "subtasks": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_SUBTASKS,
            "items": {
                "type": "object",
                "required": ["id", "task"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9-]{1,20}$"},
                    "task": {"type": "string", "minLength": 1, "maxLength": 500},
                },
            },
        }
    },
}

_VALIDATOR = Draft202012Validator(PLAN_SCHEMA)


@dataclass(frozen=True)
class Subtask:
    id: str
    task: str


def parse_plan(text: str) -> tuple[Subtask, ...]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"plan is not valid JSON: {exc.msg}") from exc
    errors = sorted(_VALIDATOR.iter_errors(data), key=lambda e: e.json_path)
    if errors:
        raise PlanError(f"plan rejected: {errors[0].json_path}: {errors[0].message}")
    subtasks = tuple(Subtask(item["id"], item["task"]) for item in data["subtasks"])
    ids = [s.id for s in subtasks]
    if len(set(ids)) != len(ids):
        raise PlanError("plan rejected: duplicate subtask ids")
    return subtasks
