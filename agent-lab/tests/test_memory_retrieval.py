from __future__ import annotations

import math
from datetime import timedelta

import pytest

from memory.retrieval import Retriever, bm25_scores, cosine, tokenize
from tests.memory_helpers import PROV, STORE_KINDS, FakeClock, FakeEmbedder, make_store

DAY = timedelta(days=1)


@pytest.fixture(params=STORE_KINDS)
def setup(request):
    clock = FakeClock()
    store = make_store(request.param, clock)
    return store, clock, Retriever(store, clock)


def texts(results):
    return [r.record.text for r in results]


def test_tokenize_lowercases_and_splits_on_non_alphanumerics():
    assert tokenize("Error-rate > 5% in EU_west-1!") == ["error", "rate", "5", "in", "eu", "west", "1"]


def test_bm25_single_document_single_term_matches_the_hand_computed_value():
    [score] = bm25_scores(["alert"], [["alert"]])
    assert score == pytest.approx(math.log(4 / 3))


def test_bm25_gives_rarer_terms_more_weight():
    docs = [["alert", "alert", "common"], ["common", "rare"], ["common"]]
    common_only, rare_only = bm25_scores(["common"], docs), bm25_scores(["rare"], docs)
    assert max(rare_only) > max(common_only)


def test_more_matching_terms_rank_first(setup):
    store, _, retriever = setup
    store.add("t1", "semantic", "billing contact is finance team", PROV, None)
    store.add("t1", "semantic", "escalation contact for billing incidents is the finance on-call", PROV, None)
    store.add("t1", "semantic", "unrelated weather note", PROV, None)
    results = retriever.search("t1", "billing finance escalation")
    assert texts(results) == [
        "escalation contact for billing incidents is the finance on-call",
        "billing contact is finance team",
    ]


def test_records_with_no_query_term_never_return_even_if_they_are_the_newest(setup):
    store, _, retriever = setup
    store.add("t1", "semantic", "alpha beta", PROV, None)
    assert retriever.search("t1", "gamma") == []


def test_recency_breaks_a_keyword_tie_in_favour_of_the_newer_record(setup):
    store, clock, retriever = setup
    store.add("t1", "semantic", "deploy freeze starts friday", PROV, None)
    clock.advance(10 * DAY)
    store.add("t1", "semantic", "deploy freeze starts friday", PROV, None)
    results = retriever.search("t1", "deploy freeze")
    assert [r.record.id for r in results] == ["m2", "m1"]
    assert results[0].score > results[1].score


def test_a_much_more_relevant_old_record_can_beat_a_weak_new_one(setup):
    store, clock, retriever = setup
    store.add("t1", "semantic", "payment gateway timeout runbook for payment gateway", PROV, None)
    clock.advance(30 * DAY)
    store.add("t1", "semantic", "gateway", PROV, None)
    results = retriever.search("t1", "payment gateway timeout")
    assert results[0].record.id == "m1"


def test_the_documented_formula_gives_0_85_for_a_perfect_match_one_half_life_old():
    clock = FakeClock()
    store = make_store("memory", clock)
    store.add("t1", "semantic", "alert", PROV, None)
    clock.advance(timedelta(days=7))
    [hit] = Retriever(store, clock, half_life=timedelta(days=7), recency_weight=0.3).search("t1", "alert")
    assert (hit.keyword, hit.recency) == (1.0, pytest.approx(0.5))
    assert hit.score == pytest.approx(1.0 * (0.7 + 0.3 * 0.5))


def test_identical_scores_are_ordered_by_record_id_so_results_are_deterministic(setup):
    store, _, retriever = setup
    for _ in range(3):
        store.add("t1", "semantic", "same words here", PROV, None)
    assert [r.record.id for r in retriever.search("t1", "same words")] == ["m1", "m2", "m3"]


@pytest.mark.parametrize("query", ["", "   ", "!!! ???"])
def test_empty_or_punctuation_only_query_returns_nothing(setup, query):
    store, _, retriever = setup
    store.add("t1", "semantic", "anything at all", PROV, None)
    assert retriever.search("t1", query) == []


def test_empty_store_returns_nothing(setup):
    assert setup[2].search("t1", "anything") == []


def test_expired_records_never_return(setup):
    store, clock, retriever = setup
    store.add("t1", "semantic", "short lived fact about billing", PROV, DAY)
    assert len(retriever.search("t1", "billing")) == 1
    clock.advance(DAY)
    assert retriever.search("t1", "billing") == []


def test_search_never_crosses_tenants_even_for_an_exact_keyword_match(setup):
    store, _, retriever = setup
    store.add("tenant-a", "semantic", "acquisition target is contoso", PROV, None)
    assert retriever.search("tenant-b", "acquisition target contoso") == []
    assert len(retriever.search("tenant-a", "acquisition contoso")) == 1


def test_kind_filter_and_limit(setup):
    store, _, retriever = setup
    store.add("t1", "semantic", "alert fact", PROV, None)
    store.add("t1", "episodic", "alert run summary", PROV, None)
    assert texts(retriever.search("t1", "alert", kinds=["episodic"])) == ["alert run summary"]
    assert len(retriever.search("t1", "alert", limit=1)) == 1
    with pytest.raises(ValueError):
        retriever.search("t1", "alert", limit=0)


def test_embedder_hook_adds_a_hit_that_keywords_alone_miss():
    clock = FakeClock()
    store = make_store("memory", clock)
    store.add("t1", "semantic", "the car would not start", PROV, None)
    store.add("t1", "semantic", "invoice was paid twice", PROV, None)
    assert Retriever(store, clock).search("t1", "automobile") == []

    embedder = FakeEmbedder()
    hybrid = Retriever(store, clock, embedder=embedder).search("t1", "automobile")
    assert texts(hybrid) == ["the car would not start"]
    assert hybrid[0].keyword == 0 and hybrid[0].vector == pytest.approx(1.0)
    assert embedder.batches == [["automobile", "the car would not start", "invoice was paid twice"]]


def test_embedder_is_not_called_for_an_empty_query_or_an_empty_tenant():
    clock = FakeClock()
    store = make_store("memory", clock)
    store.add("t1", "semantic", "car", PROV, None)
    embedder = FakeEmbedder()
    retriever = Retriever(store, clock, embedder=embedder)
    assert retriever.search("t1", "") == [] and retriever.search("other", "car") == []
    assert embedder.batches == []


def test_cosine_handles_zero_and_negative_similarity():
    assert cosine([0, 0], [1, 1]) == 0.0
    assert cosine([1, 0], [-1, 0]) == 0.0
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)


def test_constructor_rejects_bad_weights():
    clock = FakeClock()
    store = make_store("memory", clock)
    with pytest.raises(ValueError):
        Retriever(store, clock, recency_weight=1.5)
    with pytest.raises(ValueError):
        Retriever(store, clock, half_life=timedelta(0))
