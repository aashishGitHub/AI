from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from memory.records import Kind, MemoryRecord
from memory.store import Clock, MemoryStore

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class ScoredRecord:
    record: MemoryRecord
    score: float
    keyword: float
    recency: float
    vector: float


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def bm25_scores(query_terms: Sequence[str], docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25, idf = ln(1 + (N - n + 0.5) / (n + 0.5)), computed over the candidate set only."""
    if not docs:
        return []
    avg_len = sum(len(d) for d in docs) / len(docs) or 1.0
    counts = [Counter(d) for d in docs]
    scores = [0.0] * len(docs)
    for term in set(query_terms):
        n = sum(1 for c in counts if term in c)
        if n == 0:
            continue
        idf = math.log(1 + (len(docs) - n + 0.5) / (n + 0.5))
        for i, c in enumerate(counts):
            tf = c[term]
            if tf:
                scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(docs[i]) / avg_len))
    return scores


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return 0.0
    return max(0.0, sum(x * y for x, y in zip(a, b)) / norm)


class Retriever:
    """score = relevance * ((1 - recency_weight) + recency_weight * 0.5 ** (age / half_life)); relevance 0 never returns.

    relevance = bm25 / max bm25 over the candidates; with an embedder:
    (1 - vector_weight) * that + vector_weight * cosine(query, record).
    """

    def __init__(
        self,
        store: MemoryStore,
        clock: Clock,
        *,
        half_life: timedelta = timedelta(days=7),
        recency_weight: float = 0.3,
        embedder: Embedder | None = None,
        vector_weight: float = 0.5,
    ) -> None:
        if half_life <= timedelta(0) or not 0 <= recency_weight <= 1 or not 0 <= vector_weight <= 1:
            raise ValueError("half_life must be positive and the weights must be in [0, 1]")
        self._store = store
        self._clock = clock
        self._half_life_s = half_life.total_seconds()
        self._recency_weight = recency_weight
        self._embedder = embedder
        self._vector_weight = vector_weight

    def search(self, tenant_id: str, query: str, *, kinds: Sequence[Kind] | None = None, limit: int = 5) -> list[ScoredRecord]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        candidates = [r for r in self._store.list(tenant_id) if kinds is None or r.kind in kinds]
        terms = tokenize(query)
        if not candidates or not terms:
            return []
        keyword = self._keyword_scores(terms, candidates)
        vector = self._vector_scores(query, candidates)
        now = self._clock()
        scored = []
        for record, kw, vec in zip(candidates, keyword, vector):
            relevance = kw if self._embedder is None else (1 - self._vector_weight) * kw + self._vector_weight * vec
            if relevance <= 0:
                continue
            age_s = max(0.0, (now - record.created_at).total_seconds())
            recency = 0.5 ** (age_s / self._half_life_s)
            score = relevance * ((1 - self._recency_weight) + self._recency_weight * recency)
            scored.append(ScoredRecord(record, score, kw, recency, vec))
        scored.sort(key=lambda s: (-s.score, -s.record.created_at.timestamp(), s.record.id))
        return scored[:limit]

    @staticmethod
    def _keyword_scores(terms: Sequence[str], candidates: Sequence[MemoryRecord]) -> list[float]:
        raw = bm25_scores(terms, [tokenize(r.text) for r in candidates])
        top = max(raw)
        return [s / top if top > 0 else 0.0 for s in raw]

    def _vector_scores(self, query: str, candidates: Sequence[MemoryRecord]) -> list[float]:
        if self._embedder is None:
            return [0.0] * len(candidates)
        query_vec, *doc_vecs = self._embedder.embed([query, *(r.text for r in candidates)])
        return [cosine(query_vec, v) for v in doc_vecs]
