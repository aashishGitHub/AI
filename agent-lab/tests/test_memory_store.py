from __future__ import annotations

from datetime import timedelta

import pytest

from memory.records import MAX_TEXT_CHARS, DEFAULT_TTL, MemoryRecord, Provenance
from memory.sqlite_store import SqliteMemoryStore
from memory.store import ids_to_evict
from tests.memory_helpers import PROV, START, STORE_KINDS, FakeClock, make_store, seq_ids

DAY = timedelta(days=1)


@pytest.fixture(params=STORE_KINDS)
def kind_of_store(request):
    return request.param


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(kind_of_store, clock):
    return make_store(kind_of_store, clock)


def test_add_then_get_and_list_round_trip_with_provenance_and_injected_clock_and_id(store, clock):
    prov = Provenance(source="tool:remember", run_id="run-7", written_by="model")
    record = store.add("t1", "semantic", "the sky is blue", prov, DAY)
    assert record == MemoryRecord("m1", "t1", "semantic", "the sky is blue", prov, START, START + DAY)
    assert store.get("t1", "m1") == record
    assert store.list("t1") == [record]


def test_list_is_newest_first_and_can_filter_by_kind(store, clock):
    store.add("t1", "semantic", "old fact", PROV, None)
    clock.advance(DAY)
    store.add("t1", "episodic", "new run", PROV, None)
    assert [r.text for r in store.list("t1")] == ["new run", "old fact"]
    assert [r.text for r in store.list("t1", "semantic")] == ["old fact"]


@pytest.mark.parametrize("other", ["t2", "T1", "t1 ", "t1' OR '1'='1", "%"])
def test_a_record_written_for_one_tenant_is_invisible_to_every_other_tenant(store, other):
    record = store.add("t1", "semantic", "secret roadmap", PROV, None)
    assert store.get(other, record.id) is None
    assert store.list(other) == []
    assert store.list(other, "semantic") == []
    assert store.forget(other, record.id) is False
    assert store.forget_all(other) == 0
    assert store.get("t1", record.id) == record


@pytest.mark.parametrize("bad", ["", "   "])
def test_every_api_call_requires_a_tenant_id(store, bad):
    calls = [
        lambda: store.add(bad, "semantic", "x", PROV, None),
        lambda: store.get(bad, "m1"),
        lambda: store.list(bad),
        lambda: store.forget(bad, "m1"),
        lambda: store.forget_all(bad),
    ]
    for call in calls:
        with pytest.raises(ValueError, match="tenant_id"):
            call()


def test_expired_records_are_invisible_to_get_and_list_from_the_exact_expiry_instant(store, clock):
    record = store.add("t1", "semantic", "short lived", PROV, DAY)
    clock.advance(DAY - timedelta(microseconds=1))
    assert store.get("t1", record.id) == record
    clock.advance(timedelta(microseconds=1))
    assert store.get("t1", record.id) is None
    assert store.list("t1") == []


def test_a_record_without_ttl_never_expires(store, clock):
    record = store.add("t1", "semantic", "forever", PROV, None)
    clock.advance(timedelta(days=3650))
    assert store.get("t1", record.id) == record


def test_default_ttls_are_set_per_kind():
    assert DEFAULT_TTL["semantic"] > DEFAULT_TTL["episodic"] > timedelta(0)


def test_cap_evicts_episodic_before_semantic_then_oldest_first(kind_of_store, clock):
    store = make_store(kind_of_store, clock, max_records=3)
    store.add("t1", "semantic", "fact-old", PROV, None)
    clock.advance(DAY)
    store.add("t1", "episodic", "run-1", PROV, None)
    clock.advance(DAY)
    store.add("t1", "episodic", "run-2", PROV, None)
    clock.advance(DAY)
    store.add("t1", "semantic", "fact-new", PROV, None)
    assert sorted(r.text for r in store.list("t1")) == ["fact-new", "fact-old", "run-2"]
    clock.advance(DAY)
    store.add("t1", "semantic", "fact-newest", PROV, None)
    assert sorted(r.text for r in store.list("t1")) == ["fact-new", "fact-newest", "fact-old"]
    clock.advance(DAY)
    store.add("t1", "semantic", "fact-last", PROV, None)
    assert sorted(r.text for r in store.list("t1")) == ["fact-last", "fact-new", "fact-newest"]


def test_the_cap_is_per_tenant_so_a_noisy_tenant_cannot_evict_a_quiet_one(kind_of_store, clock):
    store = make_store(kind_of_store, clock, max_records=2)
    store.add("quiet", "semantic", "quiet fact", PROV, None)
    for n in range(5):
        clock.advance(DAY)
        store.add("noisy", "semantic", f"noise {n}", PROV, None)
    assert [r.text for r in store.list("quiet")] == ["quiet fact"]
    assert len(store.list("noisy")) == 2


def test_expired_records_are_purged_before_a_live_record_is_evicted(kind_of_store, clock):
    store = make_store(kind_of_store, clock, max_records=2)
    store.add("t1", "semantic", "live", PROV, None)
    store.add("t1", "semantic", "doomed", PROV, DAY)
    clock.advance(2 * DAY)
    store.add("t1", "semantic", "new", PROV, None)
    assert sorted(r.text for r in store.list("t1")) == ["live", "new"]


def test_ids_to_evict_rule_is_pure_and_explicit():
    def rec(i, kind, day):
        return MemoryRecord(i, "t", kind, "x", PROV, START + day * DAY, None)

    live = [rec("a", "semantic", 0), rec("b", "episodic", 5), rec("c", "episodic", 1)]
    assert ids_to_evict(live, max_records=4) == []
    assert ids_to_evict(live, max_records=3) == ["c"]
    assert ids_to_evict(live, max_records=2) == ["c", "b"]
    assert ids_to_evict(live, max_records=1) == ["c", "b", "a"]


@pytest.mark.parametrize("text, kind", [("", "semantic"), ("   ", "semantic"), ("x" * (MAX_TEXT_CHARS + 1), "semantic"), ("ok", "weird")])
def test_invalid_writes_are_rejected_and_store_nothing(store, text, kind):
    with pytest.raises(ValueError):
        store.add("t1", kind, text, PROV, None)
    assert store.list("t1") == []


def test_forget_removes_one_record_and_reports_whether_it_existed(store):
    keep = store.add("t1", "semantic", "keep", PROV, None)
    gone = store.add("t1", "semantic", "gone", PROV, None)
    assert store.forget("t1", gone.id) is True
    assert store.forget("t1", gone.id) is False
    assert store.list("t1") == [keep]


def test_forget_all_erases_every_kind_including_expired_rows_for_that_tenant_only(store, clock):
    store.add("t1", "semantic", "a", PROV, None)
    store.add("t1", "episodic", "b", PROV, DAY)
    store.add("t2", "semantic", "other tenant", PROV, None)
    clock.advance(2 * DAY)
    assert store.forget_all("t1") == 2
    assert store.list("t1") == []
    assert [r.text for r in store.list("t2")] == ["other tenant"]


def test_sqlite_data_survives_reopening_the_file_and_the_schema_rejects_unknown_kinds(tmp_path, clock):
    path = str(tmp_path / "memory.db")
    first = SqliteMemoryStore(path, clock, seq_ids())
    record = first.add("t1", "semantic", "persisted", PROV, None)
    first.close()
    second = SqliteMemoryStore(path, clock, seq_ids())
    assert second.get("t1", record.id) == record
    with pytest.raises(Exception, match="CHECK"):
        second._conn.execute(
            "INSERT INTO memory VALUES ('x', 't1', 'weird', 't', 's', 'r', 'w', 0, NULL)"
        )
    second.close()


def test_sqlite_rejects_naive_timestamps(tmp_path):
    from datetime import datetime

    store = SqliteMemoryStore(":memory:", clock=lambda: datetime(2026, 1, 1), new_id=seq_ids())
    with pytest.raises(ValueError, match="timezone-aware"):
        store.add("t1", "semantic", "x", PROV, None)
