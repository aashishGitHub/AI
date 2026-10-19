from collections.abc import Callable, Iterable


def merge_latest[T](
    records: Iterable[T],
    key: Callable[[T], str],
    version: Callable[[T], int],
) -> list[T]:
    winners: dict[str, T] = {}
    for record in records:
        k = key(record)
        if k not in winners or version(record) >= version(winners[k]):
            winners[k] = record
    return list(winners.values())
