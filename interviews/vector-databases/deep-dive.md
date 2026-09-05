# Vector Databases — Deep Dive

> Depth tiers: 🟢 fundamentals · 🟡 senior · 🔴 staff/architect.
> Read after [`answers.md`](answers.md). This file is the "why", not the "what".
> Numbers marked *approximate* are order-of-magnitude planning figures to verify against your own hardware.

---

## 1. Why "approximate" is the whole subject (🟢→🔴)

🟢 Exact nearest-neighbour search is trivially correct and hopelessly slow: compare the query against every
vector. For 10M × 1536-d that is ~1.5 × 10¹⁰ dimension-operations **per query**, growing linearly with the
corpus. Every vector index exists to avoid that scan.

🟡 The consequence is under-appreciated: **you have accepted a wrong-answer rate.** Not a crash, not a
timeout — a quietly incomplete result set. An ANN index that returns garbage looks identical, from the
outside, to one that returns perfection: K results, correct-looking scores, normal latency. This is the
single most important operational fact in the topic.

🔴 So the mature framing is not "which database is fastest" but **"what is our recall, at what latency, at our
corpus size, under our real filters — and who is measuring it?"** Vendor benchmarks answer almost none of
that, because they typically report unfiltered queries on uniform public datasets. Real corpora are skewed,
multi-tenant, and filtered.

**The curse of dimensionality, briefly (🟡):** in high dimensions, distances concentrate — the ratio between
the nearest and farthest neighbour tends toward 1. This is why ANN works at all (many "good enough"
neighbours exist) and simultaneously why recall is fragile (the true nearest is barely distinguishable from
the 50th). It also explains why re-ranking with a cross-encoder helps so much: it re-introduces information
the geometry threw away.

---

## 2. HNSW in depth (🟢→🔴)

🟢 A layered proximity graph. Top layers are sparse and give long-range hops; the bottom layer holds every
node with short links. Search enters at the top, greedily walks toward the query, descends when no neighbour
is closer, and finishes with a wide local search at layer 0.

🟡 The three knobs are not equal, and the asymmetry is what matters operationally:

| Knob | Phase | Change cost | What it buys |
|---|---|---|---|
| `m` | build | **rebuild** | Graph density; higher recall ceiling; more memory |
| `ef_construction` | build | **rebuild** | Graph quality; slower build |
| `ef_search` | query | **free** | Recall, paid for in latency, per query |

Because `ef_search` is per-query, it can be varied by *caller*: a background summarization job can afford
`ef_search=400`; an interactive autocomplete cannot. Most teams never exploit this and set one global value.

🔴 Two production behaviours worth knowing:

- **Recall degrades as N grows at fixed `ef_search`.** An index tuned at 1M vectors is not tuned at 50M. This
  is the mechanism behind "recall decayed and we changed nothing" (Q46) — the corpus changed, which *is* a
  change.
- **Long-lived graphs drift from freshly-built ones.** Incremental insertion plus tombstoned deletes produces
  a measurably worse graph than a bulk rebuild of the same data. Treat periodic rebuild as maintenance, like
  `VACUUM`, not as an incident response.

**Quantified failure mode (🔴):** *approximately*, teams commonly find recall@10 dropping from ~0.95 to the
0.7–0.8 range when a corpus grows ~10× with `ef_search` held constant. Treat the shape of that curve as real
and the exact figures as yours to measure — the point is the direction and that nothing alerts on it.

---

## 3. Filtering: the genuinely hard part (🟡→🔴)

🟡 Everyone learns HNSW; far fewer can reason about **filtered** ANN, which is what production actually runs.
The difficulty is structural, not an implementation gap: a graph walk reaches good nodes *through* their
neighbours, so removing nodes removes the paths. Filtering and graph traversal are in tension by design.

| Strategy | What breaks | Signature symptom |
|---|---|---|
| Post-filter | Candidates discarded after retrieval | **Fewer than K results**, non-deterministically |
| Pre-filter | Reachability severed; may fall back to scan | Plausible but **wrong** neighbours; or a latency cliff |
| Filtered traversal | Neither, but unbounded work | Long tail latency; needs a cap |

🔴 The selectivity insight is the senior move, and it inverts twice:

- **Very selective (≪1%)**: stop using ANN. 0.1% of 10M is 10K vectors — brute-force that subset for **100%
  recall** in single-digit milliseconds. The index is the wrong tool at this end.
- **Mid-band (~1–20%)**: genuinely hard. This is where engine differences actually matter, and where
  pgvector 0.8.0's *iterative index scans* and Couchbase's Composite index are aimed.
- **Weakly selective (>50%)**: post-filter is fine; few candidates get discarded.

🔴 **Multi-tenancy is the same problem wearing a hat.** "Filter by `tenant_id`" is a filtered-ANN query on
every request. The senior answer is usually to stop filtering and start **partitioning**: an index per tenant
converts a hard recall problem into an easy routing problem. It trades a correctness risk for an operational
one (many indexes, per-index overhead, long-tail tenants), which is a trade most teams should take.

Couchbase states the pre-filter trade-off in its own documentation for the Composite index — *"scalar values
filter data before vector search, potentially missing relevant results"* — which is a useful thing to be able
to quote: the vendor is telling you where recall goes.

---

## 4. The operating model, and the dual-write tax (🟡→🔴)

🟡 The question "pgvector or Pinecone?" is usually asked as a performance question and is almost always
actually a **data-topology** question. If your vectors live apart from your source of truth, you have taken
on a distributed-systems obligation:

```text
every write must land in two systems
  → partial failure is inevitable at scale
  → a row without its vector is invisible to search, permanently, with no error
  → therefore you need an outbox, or CDC, or a reconciler — pick one, and staff it
```

🔴 Real-world shapes:

| Shape | Who it fits | The tax |
|---|---|---|
| Vectors **in** the OLTP database (pgvector) | Teams already on Postgres, ≲ low tens of millions of vectors | Vector work contends with transactions for RAM and CPU |
| Vectors **in** the document platform (Couchbase) | Vectors describe documents already stored there; hybrid retrieval needed | Fewer third-party integrations than specialists |
| Vectors in a **separate service** | Vector search *is* the product; scale dominates | Dual-write, perimeter/residency, vendor pricing |

🔴 **Couchbase 8.0's three index types** are worth internalizing because they make the trade-offs explicit
rather than hiding them behind one index:

| Index | Optimized for | Filtering | Vendor-stated scale |
|---|---|---|---|
| Hyperscale | Pure vector; mostly on disk → low memory | none | billions |
| Composite | Vector + selective scalar pre-filter | scalar | tens of millions → billions |
| Search (FTS) | Hybrid vector + full-text + geo, single pass | FTS + geo | ~100M docs |

The architectural lesson generalizes beyond Couchbase: **the index follows the query shape.** One application
with three query shapes may legitimately maintain three indexes over one corpus. Candidates who insist on one
index for one project have not yet met filtered retrieval.

> Source: [Couchbase Docs — Choose the Right Vector Index](https://docs.couchbase.com/cloud/vector-index/use-vector-indexes.html).
> These are vendor-stated capabilities, not independent benchmarks.

---

## 5. Memory, quantization, and the arithmetic that decides your machine (🟡)

🟡 Do this arithmetic in the interview; it is more convincing than any opinion:

```text
10M vectors × 1536 dims × 4 B (float32) = 61.44 GB   ← raw vectors dominate
HNSW graph, m=16 ≈ 83 B/vector          =  0.83 GB   ← graph is a rounding error
                                          --------
                                          ~62 GB     → will not fit a 64 GB box
                                                        that also runs Postgres
```

| Precision | Bytes/vector | 10M total | Factor | Needs rescoring? |
|---|---|---|---|---|
| float32 | 6,144 | ~61.4 GB | 1× | no |
| int8 (scalar) | 1,536 | ~15.4 GB | 4× | recommended |
| binary | 192 | ~1.9 GB | 32× | **required** |

🔴 The subtlety people miss: quantization accelerates the **scan**, but you must still keep full-precision
vectors somewhere (disk is fine) to **rescore** the candidate set — otherwise you have permanently traded
ordering accuracy for memory. Couchbase's Hyperscale index leans on exactly this shape: keep the bulk on disk
in an optimized format, keep memory small, and it reports *"higher accuracy at lower quantizations"* as the
resulting benefit.

Also note the dimension lever: 1536-d → 768-d halves memory *and* scan cost, and many modern embedding models
support dimensionality reduction (e.g. Matryoshka-style truncation) at modest quality cost. Reducing `dims`
is often a bigger, cheaper win than switching databases — **verify the quality impact for your model and
corpus before adopting it.**

---

## 6. Hybrid retrieval and reranking (🟡→🔴)

🟡 Pure vector search fails predictably on **low-semantic, high-precision tokens**: error codes, SKUs,
version strings, rare proper nouns. Embeddings encode meaning, and these tokens have little learned meaning,
so they smear into a neighbourhood. BM25 has the mirror-image weakness (no synonym understanding). Combining
them is not a nicety for any corpus containing identifiers.

🟡 **RRF** merges by rank because scores are incomparable across retrievers:

```python
score(doc) = Σ_retrievers 1 / (k + rank_in_that_retriever)   # k ≈ 60, common default
```

It needs no normalization and no tuning, which is why it is the right default. A weighted score blend can
beat it *after* tuning, but requires re-tuning whenever either retriever changes — an ongoing cost most teams
under-budget.

🔴 The **bi-encoder / cross-encoder** distinction is the thing to be crisp about:

| | Bi-encoder (the index) | Cross-encoder (the reranker) |
|---|---|---|
| Encoding | Query and doc **separately** | Query and doc **together** |
| Precomputable | Yes — that's why an index exists | No |
| Cost | O(1) lookup after ANN | O(candidates) model calls |
| Accuracy | Good | Substantially better |

Hence: retrieve wide and cheap (recall), rerank narrow and accurate (precision). And the ceiling rule —
**a reranker cannot exceed the recall of the candidate set it is handed.** When a reranker "doesn't help",
measure recall@N *before* reranking; the problem is almost always upstream.

---

## 7. Lifecycle: the embedding model will change (🔴)

🔴 This is the migration that separates people who have run a RAG system from people who have built one.
A new embedding model produces a **different vector space**; old and new vectors are not comparable, so there
is no in-place upgrade. The shape is a versioned dual-index migration:

```text
v1 serving → create v2 → dual-write → backfill (re-embed everything)
           → shadow-read + compare recall → canary → cut over → soak → drop v1
```

Costs to state out loud, because they are what make it a project rather than a task:

| Cost | Why it bites |
|---|---|
| Re-embedding the entire corpus | One large, spiky bill; 50M docs is 50M model calls |
| **Double storage** for the whole migration | Two full indexes resident simultaneously |
| Rebuild time | Hours to days at scale; needs checkpointing and idempotency |
| Quality risk | v2 is not automatically better on *your* corpus — hence shadow-read |

🔴 Two defensive practices that cost nothing up front: **store the embedding model id and dimensions
alongside every vector**, and rehearse the migration on a subset before the vendor's deprecation clock forces
your hand. Without the recorded model version you cannot even reproduce your own index (see backup, §8).

---

## 8. Operating it for a year (🟡→🔴)

🟡 **Backup.** An ANN index is *derived data*. Either back up vectors + metadata and rebuild the index
(cheap storage, slow RTO), or snapshot the built index too (fast RTO, more storage). Either way the
non-negotiables are the **source documents** and the **embedding model version** — without the latter you
cannot faithfully regenerate vectors.

🟡 **Deletes.** HNSW nodes are load-bearing for traversal, so engines tombstone rather than truly remove.
Tombstones accumulate; recall drifts down over months. Compaction/rebuild is scheduled maintenance.

🔴 **Monitoring that would actually catch a quality regression:**

| Signal | Catches | Why it's usually missing |
|---|---|---|
| **recall@K vs brute-force baseline** | The silent killer | Requires building a ground-truth fixture |
| Result-count distribution | Post-filter starvation | Everyone graphs latency, nobody graphs count |
| Indexed count vs source count | Dual-write loss | Needs cross-system reconciliation |
| Tombstone ratio / index age | Compaction overdue | Not exposed by default in most engines |
| Embedding model id per request | Model skew across paths | Nobody logs it until after the first incident |

🔴 The ground-truth fixture is cheaper than people fear (**AB1**): sample ~1,000 representative queries,
brute-force them offline against the real corpus, store the true top-K, and diff nightly. It is 1,000
queries, not 1M, and it never touches the serving path.

---

## 9. Staff-level: knowing when the premise is wrong (🔴)

🔴 The highest-signal answer is often "not this tool":

| Problem | Why embeddings are wrong | Right tool |
|---|---|---|
| Exact lookup (ID, SKU, error code) | Precision is the requirement | Inverted index / B-tree |
| Aggregation ("revenue by region") | Not a similarity question | SQL |
| Corpus < ~10K docs | ANN complexity buys nothing | Brute force — exact, 100% recall, trivial |
| "What changed in the last minute" | Recency ≠ similarity; index lag | Timestamp index |

🔴 **Privacy is a real architectural constraint, not a checkbox.** Treat "embeddings are anonymized" as
false: published inversion research shows meaningful text can be partially reconstructed from embeddings.
Consequences: vectors inherit the residency and access classification of their source text; tenant filtering
belongs at the store, not the application; and sending vectors to a third-party service is sending the data.

*I am not certain of the current state of the art on embedding-inversion attacks — verify against recent
literature before quoting specifics. The safe operating assumption stands regardless.*

🔴 **GDPR deletion** stratifies by layer, and only one layer is genuinely hard:

| Layer | Deletable? |
|---|---|
| Source document | Yes |
| Vector + metadata | Yes, but tombstoned until compaction |
| Backups | Policy-dependent |
| **Fine-tuned model weights** | **Effectively not** — retraining is the only remedy |

The design rule that follows: **keep personal data in the retrievable layer, out of the parametric layer.**
This is a good argument for RAG over fine-tuning that has nothing to do with quality.

🔴 **Making the store swappable** works for the call and fails for the semantics. A `Retriever` interface
hides the SDK, but filter behaviour (pre vs post), recall knobs (`ef_search` has no portable equivalent),
consistency (read-after-write immediate vs eventual) and single-pass hybrid support all leak. Plan for
"swappable **with re-evaluation**", not "pluggable" — and keep the recall fixture (§8) precisely so that
re-evaluation is a measurement rather than an argument.

---

## 10. Closing cheat sheet

**The five things to say that signal seniority**
1. "What's our **recall**, and how do we measure it?" — the question that separates levels.
2. "How **selective** is the filter?" — before choosing pre- vs post-filter.
3. "Where's the **source of truth**?" — before choosing a vector store.
4. "What happens when the **embedding model** changes?" — the migration nobody plans.
5. "At this corpus size, would **brute force** just work?" — the un-clever answer that is often right.

**The arithmetic to have ready**
- `N × dims × bytes` → 10M × 1536 × 4 B ≈ **61.4 GB**; int8 **4×** smaller; binary **32×**.
- Exact search ≈ `N × dims` ops/query → **~1.5 × 10¹⁰** for 10M × 1536, linear in N.
- 0.1% filter on 10M = **10K vectors** → brute force, 100% recall.

**The failure modes, by signature**
| Symptom | Cause |
|---|---|
| Fewer than K results, intermittent | Post-filter starvation |
| Plausible but wrong neighbours | Pre-filter severed the graph, or model skew |
| Recall fell, nothing deployed | Corpus grew, or tombstones accumulated |
| Doc indexed but never retrieved | Dual-write loss → bisect with brute force |
| Reranker added, no improvement | Recall ceiling upstream of the reranker |
| Great in staging, poor in prod | Recall is a function of N and distribution |

**The one-sentence summary**
> Vector search buys latency by selling recall, and every real decision — index type, quantization, filtering
> strategy, where the vectors live — is a different way of choosing how much recall to sell and whether anyone
> is measuring the bill.
