import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fde.types import Json

type Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Add:
    path: Path
    after: Json
    op: Literal["add"] = "add"


@dataclass(frozen=True)
class Remove:
    path: Path
    before: Json
    op: Literal["remove"] = "remove"


@dataclass(frozen=True)
class Replace:
    path: Path
    before: Json
    after: Json
    op: Literal["replace"] = "replace"


type Change = Add | Remove | Replace


def _kind(value: Json) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def diff(before: Json, after: Json) -> list[Change]:
    out: list[Change] = []
    _walk(before, after, (), out)
    return out


def _walk(before: Json, after: Json, path: Path, out: list[Change]) -> None:
    kinds = (_kind(before), _kind(after))
    if kinds == ("array", "array"):
        common = min(len(before), len(after))
        for i in range(common):
            _walk(before[i], after[i], (*path, i), out)
        for i in range(common, len(after)):
            out.append(Add((*path, i), after[i]))
        for i in range(len(before) - 1, common - 1, -1):
            out.append(Remove((*path, i), before[i]))
    elif kinds == ("object", "object"):
        for key, value in before.items():
            if key in after:
                _walk(value, after[key], (*path, key), out)
            else:
                out.append(Remove((*path, key), value))
        for key, value in after.items():
            if key not in before:
                out.append(Add((*path, key), value))
    elif kinds[0] != kinds[1] or before != after:
        out.append(Replace(path, before, after))


def apply_patch(doc: Json, changes: Sequence[Change]) -> Json:
    # A one-slot holder lets a change at the root path take the same code path as any other.
    holder: list[Json] = [copy.deepcopy(doc)]
    for change in changes:
        *route, key = (0, *change.path)
        try:
            parent = holder
            for segment in route:
                parent = parent[segment]
            value = None if isinstance(change, Remove) else copy.deepcopy(change.after)
            _write(parent, key, change, value)
        except (KeyError, IndexError, TypeError) as err:
            raise ValueError(f"no container at {change.path}") from err
    return holder[0]


def _write(parent: Json, key: str | int, change: Change, value: Json) -> None:
    if isinstance(parent, list):
        match change:
            case Add():
                parent.insert(key, value)
            case Remove():
                del parent[key]
            case Replace():
                parent[key] = value
    else:
        match change:
            case Remove():
                del parent[key]
            case Add() | Replace():
                parent[key] = value
