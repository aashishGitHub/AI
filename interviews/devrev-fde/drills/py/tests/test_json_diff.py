import copy
import json
import random
from collections.abc import Callable

import pytest

from fde.json_diff import Add, Change, Remove, Replace, apply_patch, diff
from fde.types import Json


def canonical(value: Json) -> str:
    return json.dumps(value, sort_keys=True)


def test_returns_nothing_for_equal_documents() -> None:
    assert diff({"a": [1, {"b": None}]}, {"a": [1, {"b": None}]}) == []


def test_reports_add_remove_and_replace_at_nested_paths() -> None:
    before = {"user": {"name": "Ada", "age": 36}, "tags": ["x"]}
    after = {"user": {"name": "Ada L", "email": "a@x.io"}, "tags": ["x"]}
    assert diff(before, after) == [
        Replace(("user", "name"), "Ada", "Ada L"),
        Remove(("user", "age"), 36),
        Add(("user", "email"), "a@x.io"),
    ]


def test_ops_carry_their_discriminator() -> None:
    assert [c.op for c in diff({"a": 1, "b": 2}, {"a": 9, "c": 3})] == ["replace", "remove", "add"]


def test_treats_a_type_change_as_a_replace_of_the_whole_subtree() -> None:
    assert diff({"a": [1]}, {"a": {"0": 1}}) == [Replace(("a",), [1], {"0": 1})]
    assert diff({"a": None}, {"a": {}}) == [Replace(("a",), None, {})]


def test_replaces_at_the_root_path_when_documents_are_different_scalars() -> None:
    assert diff(1, 2) == [Replace((), 1, 2)]


def test_distinguishes_null_false_zero_and_empty_string() -> None:
    assert len(diff({"v": None}, {"v": False})) == 1
    assert len(diff({"v": 0}, {"v": ""})) == 1
    assert len(diff({"v": False}, {"v": 0})) == 1


def test_python_footgun_true_equals_one_but_is_not_the_same_json_value() -> None:
    assert diff({"v": 1}, {"v": True}) == [Replace(("v",), 1, True)]
    assert diff({"v": True}, {"v": 1}) == [Replace(("v",), True, 1)]


def test_diffs_arrays_by_index_inserting_at_the_front_rewrites_every_element() -> None:
    assert diff(["b", "c"], ["a", "b", "c"]) == [
        Replace((0,), "b", "a"),
        Replace((1,), "c", "b"),
        Add((2,), "c"),
    ]


def test_emits_array_removals_from_the_tail_so_sequential_application_stays_valid() -> None:
    assert diff([1, 2, 3, 4], [1]) == [Remove((3,), 4), Remove((2,), 3), Remove((1,), 2)]


def test_apply_does_not_mutate_its_input() -> None:
    doc = {"a": [1, 2], "b": {"c": 1}}
    snapshot = copy.deepcopy(doc)
    apply_patch(doc, diff(doc, {"a": [9], "b": {}}))
    assert doc == snapshot


def test_apply_does_not_alias_the_target_document() -> None:
    target = {"list": [{"id": 1}]}
    patched = apply_patch({}, diff({}, target))
    patched["list"][0]["id"] = 99
    assert target["list"][0]["id"] == 1


def test_apply_handles_a_root_level_replace() -> None:
    assert apply_patch([1], diff([1], {"a": 1})) == {"a": 1}


def test_apply_raises_on_a_path_that_does_not_exist() -> None:
    with pytest.raises(ValueError):
        apply_patch({}, [Add(("a", "b"), 1)])


def generate(rand: random.Random, depth: int) -> Json:
    kind = rand.choice(["scalar"] if depth <= 0 else ["scalar", "scalar", "array", "object"])
    if kind == "array":
        return [generate(rand, depth - 1) for _ in range(rand.randrange(4))]
    if kind == "object":
        return {rand.choice("abcd"): generate(rand, depth - 1) for _ in range(rand.randrange(4))}
    return rand.choice([None, True, False, 0, 1, 2, "x", "y", ""])


def mutate(rand: random.Random, value: Json) -> Json:
    if rand.random() < 0.3:
        return generate(rand, 2)
    if isinstance(value, list):
        copied = [mutate(rand, v) for v in value]
        if rand.random() < 0.4:
            copied.append(generate(rand, 1))
        if copied and rand.random() < 0.3:
            copied.pop(rand.randrange(len(copied)))
        return copied
    if isinstance(value, dict):
        kept = {k: mutate(rand, v) for k, v in value.items() if rand.random() > 0.2}
        if rand.random() < 0.4:
            kept["e"] = generate(rand, 1)
        return kept
    return value


def test_property_apply_of_diff_equals_target_over_2000_seeded_pairs() -> None:
    rand = random.Random(20260101)
    non_trivial = 0
    for _ in range(2000):
        a = generate(rand, 3)
        b = mutate(rand, a) if rand.random() < 0.7 else generate(rand, 3)
        snapshot = canonical(a)

        changes = diff(a, b)
        assert canonical(apply_patch(a, changes)) == canonical(b)
        assert canonical(a) == snapshot
        assert diff(a, a) == []
        if len(changes) > 1:
            non_trivial += 1
    assert non_trivial > 200
