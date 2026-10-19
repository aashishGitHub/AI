from dataclasses import dataclass

from fde.merge_records import merge_latest


@dataclass(frozen=True)
class Rec:
    id: str
    version: int
    note: str = ""


def merge(records: list[Rec]) -> list[Rec]:
    return merge_latest(records, key=lambda r: r.id, version=lambda r: r.version)


def test_keeps_the_highest_version_per_key_regardless_of_arrival_order() -> None:
    out = merge([Rec("a", 2, "new"), Rec("a", 1, "old"), Rec("a", 3, "newest")])
    assert out == [Rec("a", 3, "newest")]


def test_is_stable_output_follows_first_appearance_of_each_key() -> None:
    out = merge([Rec("b", 1), Rec("a", 1), Rec("b", 2), Rec("c", 1), Rec("a", 5)])
    assert [(r.id, r.version) for r in out] == [("b", 2), ("a", 5), ("c", 1)]


def test_breaks_version_ties_in_favour_of_the_later_record() -> None:
    assert merge([Rec("a", 1, "first"), Rec("a", 1, "second")]) == [Rec("a", 1, "second")]


def test_does_not_let_a_stale_record_displace_a_newer_one_after_a_tie() -> None:
    assert merge([Rec("a", 2, "x"), Rec("a", 2, "y"), Rec("a", 1, "z")]) == [Rec("a", 2, "y")]


def test_handles_empty_input_and_returns_the_original_object_references() -> None:
    assert merge([]) == []
    only = Rec("a", 1)
    assert merge([only])[0] is only


def test_accepts_any_iterable_and_does_not_mutate_the_input() -> None:
    records = [Rec("a", 1), Rec("a", 2)]
    snapshot = list(records)
    assert merge_latest(iter(records), key=lambda r: r.id, version=lambda r: r.version) == [Rec("a", 2)]
    assert records == snapshot


def test_is_linear_one_key_call_per_record_and_at_most_two_version_calls() -> None:
    n = 5000
    records = [Rec(f"k{i % 100}", i) for i in range(n)]
    calls = {"key": 0, "version": 0}

    def key(r: Rec) -> str:
        calls["key"] += 1
        return r.id

    def version(r: Rec) -> int:
        calls["version"] += 1
        return r.version

    merge_latest(records, key=key, version=version)
    assert calls["key"] == n
    assert calls["version"] <= 2 * n
