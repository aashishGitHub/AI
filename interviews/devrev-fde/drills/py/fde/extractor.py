from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from fde.types import Clock


@dataclass(frozen=True)
class Page[T]:
    items: Sequence[T]
    next_cursor: str | None


@dataclass(frozen=True)
class Checkpoint:
    cursor: str | None
    done: bool


@dataclass(frozen=True)
class ExtractResult:
    status: Literal["complete", "budget_exhausted"]
    checkpoint: Checkpoint
    pages: int


def extract[T](
    *,
    fetch_page: Callable[[str | None], Page[T]],
    upsert: Callable[[Sequence[T]], None],
    save_checkpoint: Callable[[Checkpoint], None],
    cursor: str | None,
    budget_ms: float,
    clock: Clock,
) -> ExtractResult:
    started_at = clock()
    pages = 0
    slowest_page_ms = 0.0

    while True:
        remaining_ms = budget_ms - (clock() - started_at)
        if remaining_ms <= 0 or remaining_ms < slowest_page_ms:
            return ExtractResult("budget_exhausted", Checkpoint(cursor, done=False), pages)

        page_started_at = clock()
        page = fetch_page(cursor)
        upsert(page.items)
        checkpoint = Checkpoint(page.next_cursor, done=page.next_cursor is None)
        save_checkpoint(checkpoint)

        pages += 1
        if checkpoint.done:
            return ExtractResult("complete", checkpoint, pages)
        cursor = page.next_cursor
        slowest_page_ms = max(slowest_page_ms, clock() - page_started_at)
