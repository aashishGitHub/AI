import math
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from fde.extractor import Checkpoint, ExtractResult, Page, extract
from tests.helpers import FakeClock

TOTAL = 20
PAGE_SIZE = 3
PAGE_COUNT = math.ceil(TOTAL / PAGE_SIZE)
PAGE_COST_MS = 30


@dataclass(frozen=True)
class Item:
    id: str
    value: int


class Crash(Exception):
    pass


class World:
    def __init__(self, crash: tuple[str, int] | None = None) -> None:
        self.clock = FakeClock()
        self.source = [Item(f"r{i}", i * i) for i in range(TOTAL)]
        self.sink: dict[str, Item] = {}
        self.appended: list[Item] = []
        self.fetched_cursors: list[str | None] = []
        self.persisted = Checkpoint(cursor=None, done=False)
        self._crash = crash
        self._page_index = -1

    def _maybe_crash(self, point: str) -> None:
        if self._crash == (point, self._page_index):
            self._crash = None
            raise Crash(point)

    def fetch_page(self, cursor: str | None) -> Page[Item]:
        self.fetched_cursors.append(cursor)
        self.clock.advance(PAGE_COST_MS)
        offset = 0 if cursor is None else int(cursor)
        self._page_index = offset // PAGE_SIZE
        nxt = offset + PAGE_SIZE
        return Page(self.source[offset:nxt], None if nxt >= TOTAL else str(nxt))

    def upsert(self, items: Sequence[Item]) -> None:
        self._maybe_crash("after_fetch")
        for i, item in enumerate(items):
            if i == 1:
                self._maybe_crash("mid_upsert")
            self.sink[item.id] = item
            self.appended.append(item)

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._maybe_crash("before_checkpoint")
        self.persisted = checkpoint

    def invoke(self, budget_ms: float) -> ExtractResult:
        return extract(
            fetch_page=self.fetch_page,
            upsert=self.upsert,
            save_checkpoint=self.save_checkpoint,
            cursor=self.persisted.cursor,
            budget_ms=budget_ms,
            clock=self.clock.now,
        )

    def run_to_completion(self, budget_ms: float) -> int:
        invocations = 0
        while not self.persisted.done:
            invocations += 1
            self.invoke(budget_ms)
            assert invocations <= 100, "no progress"
        return invocations


def uninterrupted_sink() -> dict[str, Item]:
    world = World()
    world.run_to_completion(1_000_000)
    return world.sink


def test_walks_every_page_checkpointing_after_each_and_reports_completion() -> None:
    saved: list[Checkpoint] = []
    clock = FakeClock()

    def fetch_page(cursor: str | None) -> Page[Item]:
        offset = 0 if cursor is None else int(cursor)
        return Page([Item(f"r{offset}", offset)], None if offset >= 2 else str(offset + 1))

    result = extract(
        fetch_page=fetch_page,
        upsert=lambda items: None,
        save_checkpoint=saved.append,
        cursor=None,
        budget_ms=1000,
        clock=clock.now,
    )
    assert result == ExtractResult("complete", Checkpoint(None, done=True), 3)
    assert saved == [Checkpoint("1", False), Checkpoint("2", False), Checkpoint(None, True)]


def test_upserts_all_rows_in_one_invocation_when_the_budget_is_ample() -> None:
    world = World()
    result = world.invoke(10_000)
    assert result.status == "complete"
    assert result.pages == PAGE_COUNT
    assert len(world.sink) == TOTAL


def test_never_calls_fetch_page_when_no_budget_remains() -> None:
    world = World()
    result = world.invoke(0)
    assert result == ExtractResult("budget_exhausted", Checkpoint(None, done=False), 0)
    assert world.fetched_cursors == []


def test_stops_before_a_page_that_would_not_fit_using_the_slowest_page_so_far() -> None:
    world = World()
    result = world.invoke(100)
    assert result.pages == 3
    assert result.checkpoint == Checkpoint("9", done=False)
    assert world.clock.now() == 90


def test_runs_one_more_page_exactly_when_the_remaining_time_equals_a_page() -> None:
    world = World()
    result = world.invoke(120)
    assert result.pages == 4
    assert world.clock.now() == 120


def test_always_makes_progress_with_a_positive_budget_smaller_than_one_page() -> None:
    world = World()
    result = world.invoke(1)
    assert result.pages == 1
    assert result.checkpoint == Checkpoint("3", done=False)


def test_each_new_invocation_resumes_from_the_saved_checkpoint_without_refetching() -> None:
    world = World()
    for _ in range(3):
        world.invoke(100)
    assert world.fetched_cursors == [None, "3", "6", "9", "12", "15", "18"]
    assert world.persisted == Checkpoint(None, done=True)


@pytest.mark.parametrize("budget", [1, 29, 30, 31, 59, 60, 61, 89, 90, 119, 120, 121, 150, 209, 210, 211, 5000])
def test_budget_exhaustion_at_any_point_ends_identical_and_never_overruns(budget: int) -> None:
    expected = uninterrupted_sink()
    world = World()
    overran = False
    invocations = 0
    while not world.persisted.done:
        invocations += 1
        before = world.clock.now()
        world.invoke(budget)
        if budget >= PAGE_COST_MS and world.clock.now() - before > budget:
            overran = True

    assert world.sink == expected
    assert not overran
    assert len(world.fetched_cursors) == PAGE_COUNT
    pages_per_invocation = max(1, budget // PAGE_COST_MS)
    assert invocations == math.ceil(PAGE_COUNT / pages_per_invocation)


@pytest.mark.parametrize("point", ["after_fetch", "mid_upsert", "before_checkpoint"])
@pytest.mark.parametrize("page", range(PAGE_COUNT))
def test_crash_replays_exactly_that_one_page_and_ends_identical(point: str, page: int) -> None:
    expected = uninterrupted_sink()
    world = World(crash=(point, page))

    with pytest.raises(Crash):
        world.run_to_completion(10_000)
    world.run_to_completion(10_000)

    assert world.sink == expected
    assert len(world.fetched_cursors) == PAGE_COUNT + 1
    replayed = [c for i, c in enumerate(world.fetched_cursors) if world.fetched_cursors.index(c) != i]
    assert replayed == [world.fetched_cursors[page]]


def test_would_duplicate_rows_without_an_idempotent_upsert_exactly_one_page_of_duplicates() -> None:
    world = World(crash=("before_checkpoint", 2))
    with pytest.raises(Crash):
        world.run_to_completion(10_000)
    world.run_to_completion(10_000)
    assert len(world.appended) == TOTAL + PAGE_SIZE
    assert len(world.sink) == TOTAL


def test_loses_at_most_one_page_of_progress_because_the_checkpoint_trails_by_one_page() -> None:
    world = World(crash=("before_checkpoint", 3))
    with pytest.raises(Crash):
        world.run_to_completion(10_000)
    assert world.persisted == Checkpoint("9", done=False)
