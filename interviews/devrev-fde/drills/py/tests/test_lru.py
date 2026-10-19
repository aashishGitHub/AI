import random

import pytest

from fde.lru import LinkedLruCache, LruCache

IMPLEMENTATIONS = [LruCache, LinkedLruCache]


@pytest.fixture(params=IMPLEMENTATIONS, ids=["ordered-dict", "linked-list"])
def make(request: pytest.FixtureRequest):
    return request.param


def test_returns_none_for_a_miss_and_the_value_for_a_hit(make) -> None:
    cache = make(2)
    assert cache.get("a") is None
    cache.put("a", 1)
    assert cache.get("a") == 1


def test_evicts_the_least_recently_used_entry_when_over_capacity(make) -> None:
    cache = make(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") is None
    assert cache.keys() == ["b", "c"]
    assert cache.size == 2


def test_counts_a_get_as_a_use(make) -> None:
    cache = make(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1


def test_counts_an_overwrite_as_a_use_and_updates_the_value_without_growing(make) -> None:
    cache = make(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    assert cache.size == 2
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 10


def test_works_with_capacity_one(make) -> None:
    cache = make(1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    cache.put("b", 3)
    assert cache.keys() == ["b"]


def test_a_miss_does_not_disturb_the_order(make) -> None:
    cache = make(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("zzz")
    assert cache.keys() == ["a", "b"]


@pytest.mark.parametrize("capacity", [0, -1, 1.5])
def test_rejects_a_capacity_below_one(make, capacity) -> None:
    with pytest.raises(ValueError):
        make(capacity)


def test_stays_correct_over_a_long_mixed_workload_matching_a_naive_model(make) -> None:
    cache = make(5)
    model: list[tuple[str, int]] = []
    rand = random.Random(12345)
    for i in range(5000):
        key = str(rand.randrange(9))
        at = next((n for n, (k, _) in enumerate(model) if k == key), -1)
        if rand.random() < 0.5:
            cache.put(key, i)
            if at >= 0:
                model.pop(at)
            model.append((key, i))
            if len(model) > 5:
                model.pop(0)
        else:
            expected = model[at][1] if at >= 0 else None
            if at >= 0:
                model.append(model.pop(at))
            assert cache.get(key) == expected
        assert cache.keys() == [k for k, _ in model]
