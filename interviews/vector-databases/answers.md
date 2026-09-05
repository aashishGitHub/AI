# Vector Databases — Answers

> Keyed to [`questions.md`](questions.md). Each answer includes either code or a comparison table.
> Numbers marked *approximate* are order-of-magnitude planning figures to verify, not hard limits.

---

## Level 1 — Fundamentals

### A1. Embeddings and distance
An embedding maps content into a fixed-length vector such that *semantic* similarity becomes *geometric*
proximity. The model defines the space; distance is only meaningful **inside one model's space**.

| Concern | Why it matters |
|---|---|
| Same model | Vectors from two models are incomparable even at identical dimensionality — they are different spaces. |
| Same dimensionality | A dimension mismatch is a hard error. This is the *lucky* failure: it's loud. |
| Same metric | Cosine vs L2 vs dot rank differently unless vectors are normalized. |
| Same preprocessing | Different chunking/cleaning on write vs read shifts the query off the document manifold. |

**Key takeaway:** An embedding is only comparable to another embedding from the identical model, dimensions, and metric — the vector store cannot detect a mismatch for you.

### A2. Why approximate
Exact (brute-force) search compares the query against every vector: for 10M × 1536 dims that is ~1.5 × 10¹⁰
dimension-operations **per query**, and it grows **linearly** with the corpus.

| Approach | Complexity | 10M vectors, 1536-d |
|---|---|---|
| Exact / flat | O(N·d) | ~1.5 × 10¹⁰ ops/query — *approximately* seconds single-threaded |
| ANN (HNSW) | ~O(log N · d) with tuning | single-digit ms, at <100% recall |

You give up a guarantee: ANN may miss true neighbours. You buy several orders of magnitude of latency.

**Key takeaway:** ANN trades a *correctness guarantee* for latency, so the real design question is not "is it fast" but "how much recall did I sell, and did I measure it".

### A3. Recall@K
Of the true top-K nearest neighbours (by exact search), what fraction did the index return?

```
recall@10 = |ANN_top10 ∩ EXACT_top10| / 10
```

It is under-measured because **ANN failure is silent**: a badly tuned index still returns exactly K results,
in confident rank order, with normal latency. There is no error to alert on. You must construct a
brute-force baseline on a sample and diff against it.

**Key takeaway:** Latency regressions page you; recall regressions don't — which is exactly why recall needs a deliberate, scheduled measurement.

### A4. Distance metrics

| Metric | Use when | Note |
|---|---|---|
| **Cosine** | Text embeddings; magnitude is noise | Most common default for RAG |
| **Inner product (dot)** | Model trained for it; magnitude carries signal | On normalized vectors, ranks identically to cosine |
| **L2 (Euclidean)** | Image/spatial embeddings | On normalized vectors, monotonically related to cosine |

Pick the metric the model was **trained/documented** for. Picking wrong doesn't error — it silently degrades
ranking, which returns us to A3.

**Key takeaway:** The metric is a property of the embedding model, not a preference — and a wrong choice degrades quality silently rather than failing loudly.

### A5. Category or feature?
Both, and the honest answer names the axis:

| Position | Argument |
|---|---|
| It's a **feature** | ANN indexing is an index type. Postgres, Couchbase, Elastic, Mongo all added it. Data rarely wants to live alone. |
| It's a **category** | At billions of vectors, the workload (index build, quantization, memory tiering, recall tuning) dominates the system design, and specialization wins. |

**Key takeaway:** "Vector database" describes a workload, not a schema — say which side of the scale/specialization line you're on and why, rather than picking a tribe.

### A6. Silent retrieval degradation *(failure mode)*

| Cause | Tell-tale | How to confirm |
|---|---|---|
| Embedding model/version changed on one path | Query vectors off-manifold; scores compress toward the mean | Log model id + dims on **both** paths; compare |
| Index rebuilt with weaker params (lower `ef_search`, fewer `probes`) | Latency may *improve* — a smell, not a win | Diff index config; re-run recall baseline |
| Corpus changed (re-chunk, partial reindex, deletes) | Some docs unreachable | Count indexed vectors vs source rows |

**Key takeaway:** Every silent-quality incident starts with the same three questions — did the model change, did the index params change, did the corpus change — so log all three as first-class facts.

---

## Level 2 — Index internals

### A7. HNSW mechanically
A multi-layer proximity graph. Upper layers are sparse (long-range hops); the bottom layer contains every
node. Search enters at the top, greedily walks toward the query, then descends — coarse-to-fine, like a
skip list over a graph.

```text
L2:  A ─────────────── F              sparse: big jumps
L1:  A ─── C ─── D ─── F              medium
L0:  A─B─C─D─E─F─G─H─I─J              every node, short links
     ↑ enter top, greedy-descend to the query's neighbourhood
```

Search is roughly logarithmic because each layer cuts the remaining distance by a large factor, rather than
scanning candidates linearly.

**Key takeaway:** HNSW is a skip-list idea applied to a proximity graph — long hops first, short hops last — which is why search cost grows with log(N) rather than N.

### A8. HNSW knobs

| Knob | When | Effect | Cost of raising |
|---|---|---|---|
| `m` | **Build** | Links per node; graph density | Memory, build time. Rebuild to change. |
| `ef_construction` | **Build** | Candidate list while building | Build time. Better graph quality. Rebuild to change. |
| `ef_search` | **Query** | Candidate list at search time | Latency only — **no rebuild** |

That split is the operational point: `ef_search` is a **live** recall/latency dial you can turn per query or
per tenant; `m` and `ef_construction` are commitments you re-pay for.

**Key takeaway:** `ef_search` is the only recall knob you can turn without a rebuild, so it's the one to expose as configuration and the one to tune first.

### A9. IVF mechanically
Cluster the vectors (k-means) into `lists` cells with centroids. At query time, compare against centroids,
pick the nearest `probes` cells, and search only inside them.

```text
build:  k-means over sample → `lists` centroids → assign every vector to a cell
query:  compare to centroids → scan nearest `probes` cells only
        (a true neighbour sitting just across a cell boundary is missed)
```

Crucially, IVF needs **representative data present before building** in order to train centroids. HNSW has
no training step and can be built on an empty table, then filled.

**Key takeaway:** IVF needs data before it can be built and degrades as the distribution drifts from its trained centroids; HNSW has no training step, which is why it is the default for mutable corpora.

### A10. HNSW vs IVFFlat

| Dimension | HNSW | IVFFlat |
|---|---|---|
| Build time | Slower | Faster |
| Memory | Higher (graph links) | Lower |
| Recall @ fixed latency | Better | Worse |
| Needs training data first | No | **Yes** |
| Heavy updates | Degrades gracefully | Centroids drift → periodic retrain |
| Choose when | Default; quality matters | Build time/memory constrained, or huge corpus where index build cost dominates |

**Key takeaway:** HNSW is the right default and IVF is the considered exception — chosen for build cost or memory, not for query quality.

### A11. Quantization

| Type | Compression (1536-d float32 baseline) | Cost |
|---|---|---|
| None (float32) | 6,144 B/vector | — |
| **Scalar (int8)** | 1,536 B/vector (**4×**) | Small precision loss |
| **Product (PQ)** | Configurable, often 10–50× | Notable precision loss |
| **Binary** | 192 B/vector (**32×**) | Large loss; needs rescoring |

The repair is **rescoring**: retrieve an over-fetched candidate set using the compressed vectors, then
re-rank those candidates with full-precision vectors (or a cross-encoder). Compression accelerates the
*scan*; rescoring restores the *ordering*.

**Key takeaway:** Quantization is a search accelerator, not a storage decision — it is only safe when paired with a full-precision rescore of the candidate set.

### A12. Staging good, production bad *(failure mode)*
Same `ef_search`, different recall ⇒ the *data*, not the config, differs.

| Cause | Mechanism |
|---|---|
| Corpus size | Recall at fixed `ef_search` **falls as N grows**. Staging has 100K rows, prod 50M. |
| Distribution | Prod has clusters/duplicates/multilingual content staging lacks. |
| Index built incrementally vs bulk | Long-lived, heavily-updated graphs degrade vs a fresh bulk build. |
| Filtered queries | Prod applies tenant filters; staging doesn't (see Level 3). |

Confirm by measuring recall against a brute-force baseline **on production data**, not staging data.

**Key takeaway:** ANN recall is a function of corpus size and distribution, so a recall number measured on staging data is not evidence about production.

---

## Level 3 — Filtering

### A13. Pre-filter vs post-filter

| Strategy | Mechanism | Failure mode |
|---|---|---|
| **Post-filter** | ANN first, discard non-matching | Ask for 10, get 10 candidates, 9 fail the filter → **1 result**. Fewer than K, non-deterministically. |
| **Pre-filter** | Restrict to matching set, then search | The restricted set may be poorly connected in the graph, or you fall back to brute force. Couchbase states it plainly for its Composite index: filtering first can *"miss relevant results"*. |
| **Filtered/hybrid traversal** | Filter *during* graph walk | Best quality; engine-specific support (e.g. pgvector 0.8.0's *iterative index scans*) |

**Key takeaway:** Post-filtering silently returns fewer than K and pre-filtering silently returns the wrong K — filtered ANN is a correctness problem, not a performance detail.

### A14. Why `WHERE` doesn't compose with a graph walk
A B-tree scan can skip non-matching rows because ordering is total and independent of the predicate. An HNSW
walk **navigates by proximity**: it reaches good nodes only by hopping through their neighbours.

```text
Query wants: nearest to Q  WHERE tenant = 42
Graph path to the true match runs:  Q → n1(t=7) → n2(t=7) → n3(t=42) ✓
Delete the tenant-7 nodes from consideration and the path is severed —
the reachable frontier collapses and the true match is never visited.
```

**Key takeaway:** Filtering removes the stepping stones the graph walk needs, so aggressive pre-filtering can disconnect the very region containing the right answer.

### A15. Selectivity decides

| Filter selectivity | Best strategy | Why |
|---|---|---|
| **Very selective** (0.1% match) | Pre-filter, often **brute force** the matched subset | 0.1% of 10M = 10K vectors — exact search over 10K is trivial and gives **100% recall** |
| **Mid** (1–20%) | Filtered traversal / iterative scan | Neither extreme works; this is the genuinely hard band |
| **Not selective** (>50%) | Post-filter | ANN is efficient and few candidates get discarded |

**Key takeaway:** At high selectivity the correct move is to stop using the ANN index and brute-force the small matched set — exact and fast beats approximate and clever.

### A16. Multi-tenancy

| Approach | Isolation | Recall under filter | Scales to |
|---|---|---|---|
| Shared index + tenant filter | Weak (logical) | **Poor** — the Level 3 problem, every query | Many small tenants |
| Index per tenant | Strong | **Excellent** — no filter needed | Tens/hundreds of large tenants |
| Namespace / partition | Strong | Excellent within namespace | The usual managed-service answer |

Per-tenant indexes convert a *filtering* problem into a *routing* problem, which is much easier — at the cost
of per-index overhead and a noisy-neighbour/long-tail management burden.

**Key takeaway:** Partitioning by tenant turns the hard filtered-ANN problem into an easy routing problem, and is the default answer whenever tenants are few and large.

### A17. Intermittently fewer results *(failure mode)*
Classic **post-filtering**. The engine retrieves a fixed candidate pool, then discards non-matching ones; how
many survive depends on where that tenant's vectors happen to sit relative to the query.

| Fix | Trade-off |
|---|---|
| Over-fetch (request N ≫ K, then filter) | Higher latency; still no guarantee |
| Iterative/filtered scan (keep searching until K survive) | Unbounded worst case; needs a cap |
| Partition by the filter key (index per tenant) | Best correctness; more indexes to operate |

**Key takeaway:** "Sometimes returns fewer than K" is the signature of post-filtering, and over-fetching only reduces the probability rather than eliminating it.

---

## Level 4 — The operating model

### A18. The three operating models

| | **pgvector** (in your RDBMS) | **Pinecone** (managed service) | **Couchbase 8.0** (in your data platform) |
|---|---|---|---|
| Buys | Real `JOIN`s, ACID, one backup/ops story, no new system | No index ops, elastic scale, purpose-built | Vectors beside the JSON they describe; hybrid vector+FTS+geo **single pass** |
| Costs | Vector work competes with OLTP for the same box | **Dual-write/sync problem**; data leaves your perimeter; vendor pricing | Fewer third-party integrations than the specialists |
| Filtering | SQL `WHERE`, with the Level 3 caveats | Namespaces + metadata filters | Composite (scalar pre-filter) or Search (FTS) index |
| Best when | You already run Postgres and vectors are ≲ low tens of millions | Scale/ops dominate and vectors are the product | Documents are already there; hybrid retrieval matters |

**Key takeaway:** Choose the operating model from your consistency and join requirements, then tune the index — doing it in the other order is how teams end up maintaining a sync pipeline they never wanted.

### A19. The dual-write / sync problem
Two systems, one truth. Every write must land in both; anything that can fail partially, will.

```text
app ──write──▶ Postgres (source of truth)     ✅ committed
    └─write──▶ Pinecone (vectors)              ❌ timed out

result: row exists, vector missing  → document is invisible to search, forever,
        with no error anywhere and no reconciliation unless you built one.
```

Mitigations: transactional outbox + CDC, periodic reconciliation sweeps, or **avoid it entirely** by keeping
vectors in the same store as the source of truth (pgvector, Couchbase).

**Key takeaway:** A separate vector service converts a storage decision into a distributed-systems problem, so budget for an outbox and a reconciler or choose a single-store model.

### A20. When pgvector stops being right

| Pressure | Symptom |
|---|---|
| Index no longer fits comfortably in RAM | Cache thrash; p99 collapses |
| Index build competes with OLTP | Nightly rebuild starves production queries |
| Need independent scaling | Vectors need more RAM; transactions need more IOPS; one box must serve both |
| Very high write churn | Constant reindexing |

*Approximate* rule of thumb, to validate against your own hardware: pgvector is comfortable into the
**millions to low tens of millions** of vectors; beyond that the pressures above start compounding.

**Key takeaway:** Leave pgvector when the vector workload starts contending with the transactional workload for the same memory and CPU — the trigger is resource contention, not a vector count.

### A21. Couchbase 8.0's three indexes
Per [Couchbase docs](https://docs.couchbase.com/cloud/vector-index/use-vector-indexes.html):

| Index | Optimized for | Filtering | Stated scale |
|---|---|---|---|
| **Hyperscale** | Pure vector; mostly on disk, low memory | ❌ none | billions |
| **Composite** | Vector + scalar **pre-filter**, when filters are selective | ✅ scalar | tens of millions → billions |
| **Search (FTS)** | **Hybrid** vector + full-text + geospatial, single pass | ✅ FTS + geo | ~100M docs |

It is per-query-shape because the deciding factor is *what the query does* — pure similarity, similarity
under a selective scalar filter, or hybrid semantic+keyword — and one application usually has more than one
of those shapes.

**Key takeaway:** The index follows the query shape, so a single application may legitimately maintain more than one vector index over the same data.

### A22. Filter value lives in a different system

| Option | How | Trade-off |
|---|---|---|
| **Denormalize** the field into vector metadata | Copy `plan_tier` into Pinecone metadata | Fast; now you own a consistency problem for that field |
| **Two-phase**: query Postgres for allowed IDs, then filter ANN by ID set | `WHERE id IN (...)` | Breaks down as the ID set grows; ANN engines cap filter size |
| **Co-locate**: move vectors into Postgres | pgvector | Removes the problem entirely; see A20 for when this stops scaling |

**Key takeaway:** Cross-system filtering forces you to denormalize the filter key, bound the ID set, or co-locate — and the third option is the only one that removes the failure mode rather than managing it.

### A23. Vector service outage *(failure mode)*
Retrieval is down; the LLM is not. Decide deliberately what the product does.

| Degradation tier | Behaviour |
|---|---|
| **Best** | Fall back to keyword/BM25 search — worse ranking, still grounded |
| **Acceptable** | Serve a cache of recent/popular query→context results |
| **Honest** | Tell the user retrieval is unavailable and refuse to answer from parametric memory |
| **Worst** | Silently answer with no context — **confident, ungrounded hallucination** |

**Key takeaway:** The dangerous failure is not the outage but answering ungrounded, so the retrieval client must distinguish "no results" from "retrieval unavailable" and the prompt must be told which.

---

## Level 5 — Hybrid search & ranking

### A24. Why pure vector search is insufficient

| Query | Vector search | Keyword/BM25 |
|---|---|---|
| `ERR_CONN_4021` | Blurs to "connection errors" generally | Exact match ✅ |
| `SKU-99A-XL` | Near-meaningless embedding | Exact match ✅ |
| "how do I make login faster" | Understands paraphrase ✅ | Misses synonyms |

Embeddings encode *meaning*; rare tokens and identifiers carry little learned meaning, so they are smeared
into their neighbourhood. Keyword search has the opposite strengths — hence hybrid.

**Key takeaway:** Embeddings are weakest exactly where strings are most precise, so hybrid retrieval is the default for any corpus containing identifiers, codes, or product names.

### A25. Reciprocal Rank Fusion
Merge ranked lists using **rank**, not score — because scores from BM25 and cosine are not comparable.

```python
# k dampens the influence of top ranks; 60 is the widely used default (verify for your data)
def rrf(rank_lists, k=60):
    scores = {}
    for ranked in rank_lists:                 # e.g. [vector_hits, bm25_hits]
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

The alternative is a **weighted score blend** (`α·cosine + (1-α)·normalized_bm25`), which can outperform RRF
*if* tuned — but it requires score normalization that must be re-tuned whenever either retriever changes.

**Key takeaway:** RRF needs no score normalization and no tuning, which is why it is the right default and a weighted blend is the earned optimization.

### A26. Cross-encoder reranking
A **bi-encoder** (what the index uses) embeds query and document *separately* — necessary for precomputation.
A **cross-encoder** processes query and document *together*, so it can model interaction, and is far more
accurate — but cannot be precomputed, so it only runs on a candidate set.

```text
ANN (bi-encoder, precomputed):   10M docs ──▶ top 100      cheap, approximate
Cross-encoder rerank:               100 docs ──▶ top 5      expensive, accurate
                                                └─▶ LLM context
```

Over-fetching exists to give the reranker room: recall@100 is much higher than recall@5, so fetch wide with
the cheap retriever and let the accurate one choose.

**Key takeaway:** Over-fetch with the cheap retriever and re-rank with the accurate one — the index's job is recall, the reranker's job is precision.

### A27. Allocating a 300ms retrieval budget

| Stage | Budget | Notes |
|---|---|---|
| Query embedding | ~30–50ms | Network-bound if hosted; **cache repeated queries** |
| ANN search | ~10–30ms | `ef_search` dial lives here |
| Filtering | ~5–20ms | Blows up if post-filtering forces re-queries |
| Rerank (cross-encoder) | ~100–150ms | Dominant cost; scales with candidate count |
| Headroom | remainder | p99, not p50 |

Cut order under pressure: **shrink the rerank candidate set** first (100 → 30, sub-linear quality loss), then
lower `ef_search`, then drop the reranker entirely. Never cut the filter — that's a correctness boundary.

**Key takeaway:** Reranking dominates the retrieval budget, so tune its candidate count first, and never trade away filtering because that is correctness rather than quality.

### A28. Reranker slower and no better *(failure mode)*

| Cause | Explanation |
|---|---|
| **Recall ceiling** | The reranker can only reorder what ANN returned. If the right doc isn't in the top-100, reranking cannot conjure it. |
| Wrong metric offline | Improved NDCG over the candidate set ≠ improved end-answer quality |
| Latency crossed a perception threshold | Users feel added seconds; ranking gains are invisible |
| K unchanged | Better order, same 5 chunks to the LLM → identical answers |

Diagnose by measuring **recall@candidate-set** *before* reranking. If it's low, fix retrieval — the reranker
is treating a symptom.

**Key takeaway:** A reranker cannot exceed the recall of the candidate set it is given, so measure recall before the reranker before blaming or crediting it.

---

## Level 6 — Operations & lifecycle

### A29. Zero-downtime re-embedding of 50M vectors
New model ⇒ new vector space ⇒ **old and new vectors are incomparable**. You cannot migrate in place.

```text
1. Add a NEW index/collection alongside the old (dual storage, versioned:  v1 · v2)
2. Backfill: re-embed 50M docs into v2 in batches, idempotently, checkpointed
3. Keep BOTH written on every new doc during backfill (dual write)
4. Shadow-read: run live queries against v2, compare recall/quality offline — do not serve
5. Cut over behind a flag, per-tenant or percentage-based
6. Keep v1 warm for rollback until v2 is proven, then drop
```

Cost is the real constraint: 50M embedding calls plus the storage of two full indexes during migration.

**Key takeaway:** An embedding-model upgrade is a versioned dual-index migration with a shadow-read phase, never an in-place update — because the two vector spaces cannot be compared.

### A30. Deletes and updates in HNSW
Insertion just adds a node. Deletion is hard because the node may be **load-bearing** — other nodes reach
their neighbourhoods *through* it.

| Strategy | Mechanism | Cost |
|---|---|---|
| **Tombstone** (usual) | Mark deleted, keep in graph for traversal, filter from results | Index grows; recall drifts as tombstones accumulate |
| Repair links | Reconnect neighbours on delete | Expensive; complex |
| **Periodic rebuild/compaction** | Rebuild without tombstones | The real fix; needs a maintenance window or online rebuild |

An update is delete + insert, so a high-churn corpus accumulates tombstones fast.

**Key takeaway:** Deleting from a proximity graph would sever traversal paths, so engines tombstone instead — which makes periodic compaction a scheduled operational requirement, not an optimization.

### A31. Memory arithmetic
Raw vectors dominate; graph overhead is secondary.

```text
10,000,000 vectors × 1536 dims × 4 bytes (float32)
  = 10e6 × 6,144 B
  = 61,440,000,000 B ≈ 61.4 GB   (raw vectors)

HNSW graph, m = 16:  ~16 links × 4 B ≈ 64 B/vector at layer 0,
                     ~×1.3 for upper layers ≈ 83 B/vector
  = 10e6 × 83 B ≈ 0.83 GB        (graph — small by comparison)

TOTAL ≈ 62 GB   → does not fit a 64 GB box with an OS and Postgres on it
```

| Quantization | Bytes/vector | 10M total | Factor |
|---|---|---|---|
| float32 | 6,144 | ~61.4 GB | 1× |
| int8 (scalar) | 1,536 | ~15.4 GB | 4× |
| binary | 192 | ~1.9 GB | 32× |

**Key takeaway:** Memory is dominated by dims × bytes-per-component × N, so quantization — not a smaller graph — is the lever that changes which machine you need.

### A32. What to monitor

| Metric | Catches | Cadence |
|---|---|---|
| **recall@K vs brute-force baseline** | The silent one (A3) | Scheduled job on a sample |
| Query latency p50/p95/p99 | Index/resource pressure | Continuous |
| Result-count distribution | **Post-filter starvation** (A17) | Continuous |
| Indexed count vs source count | Sync drift / dual-write loss (A19) | Continuous |
| Index age / tombstone ratio | Compaction due (A30) | Daily |
| Embedding model id + dims per request | Model skew (A6) | Log every request |
| Score distribution drift | Corpus or model shift | Daily |

**Key takeaway:** Latency monitoring is table stakes and catches none of the quality failures — a scheduled recall check against a brute-force baseline is the only alarm that does.

### A33. Backup and restore
An ANN index is **derived data**. Two valid postures:

| Posture | Recovery time | Storage cost | When |
|---|---|---|---|
| Back up vectors + metadata, **rebuild** index | Slow — hours at scale | Low | Rebuild time fits your RTO |
| Snapshot the built index too | Fast | High | Large index; tight RTO |

Non-negotiable either way: back up the **source documents and the embedding model version**. Without the
model version you cannot faithfully regenerate the vectors (A29).

**Key takeaway:** The index is derived and can be rebuilt, but the vectors are only reproducible if you also recorded which embedding model made them — so version the model like a schema.

### A34. Nine-hour index build *(failure mode)*
Ordered by what to try first:

| Lever | Effort | Effect |
|---|---|---|
| 1. **Incremental / delta indexing** — only changed docs | Medium | Usually the real fix; nightly full rebuilds are often unnecessary |
| 2. **Parallelize the build** (pgvector added parallel HNSW builds) | Low | Multi-core scaling |
| 3. Lower `ef_construction` / `m` | Low | Faster build, **lower recall** — measure before accepting |
| 4. Shard the index | High | Parallel builds, more moving parts |

**Key takeaway:** Attack build time by rebuilding less (incremental) before rebuilding faster (parameters), because lowering build quality silently spends recall.

---

## Level 7 — Applying it to a RAG system

### A35. Full retrieval path, and where recall dies

```text
question → embed → [filter] → ANN → over-fetch N → rerank → top-K → LLM
```

| Stage | Recall lost when |
|---|---|
| Chunking (write path) | The answer is split across two chunks, so neither is individually relevant |
| Embedding | Query phrasing sits off the document manifold (question vs statement) |
| Filter | Pre-filter severs the graph / post-filter starves K (Level 3) |
| ANN | `ef_search` too low, or corpus grew (A12) |
| Over-fetch N | N too small — caps the reranker (A28) |
| Rerank | Miscalibrated model reorders wrongly |
| Top-K | K too small; or "lost in the middle" buries the right chunk |

**Key takeaway:** Retrieval recall is the product of every stage's recall, so the weakest stage sets the ceiling and tuning any other stage is wasted effort until you know which one it is.

### A36. Choosing K

| K | Failure |
|---|---|
| Too small | The answer simply isn't in context — unrecoverable, and the model will confabulate to fill the gap |
| Too large | Cost and latency rise; **the "lost in the middle" effect** — models attend less reliably to content in the middle of a long context — and irrelevant chunks actively distract |

Practical approach: start ~5, measure answer quality against a golden set as you vary K, and stop where the
curve flattens. Prefer *fewer, better* chunks (rerank) over *more* chunks.

> *Reference:* "Lost in the Middle: How Language Models Use Long Contexts", Liu et al. — **2023**, flagged as
> pre-2025 per the accuracy contract; re-verify how strongly it applies to current long-context models.

**Key takeaway:** Bigger K is not safer — beyond a modest number it adds distractors and buries the right chunk, so raise precision with reranking rather than raising K.

### A37. Chunking interacts with retrieval

| Chunking | Effect on retrieval |
|---|---|
| Too small | Each vector is precise but context-free; the answer spans several chunks |
| Too large | The embedding averages several topics into a blurred centroid that matches nothing sharply |
| No overlap | Answers straddling a boundary are lost |
| Structure-blind | Tables/code split mid-structure; the retrieved fragment is unusable |

A perfect index over bad chunks retrieves *exactly the wrong thing, reliably* — the index faithfully returns
the nearest vector, but the vector represents an incoherent span.

**Key takeaway:** The index can only retrieve the units you created, so chunking sets the ceiling on retrieval quality before any index parameter is touched.

### A38. Measuring retrieval offline
Build a golden set of `(question → known-relevant chunk ids)` and score **retrieval separately from generation**.

| Metric | Question it answers |
|---|---|
| **recall@K** | Was the right chunk retrieved at all? *(the ceiling on everything downstream)* |
| **MRR / NDCG@K** | Was it ranked near the top? |
| **Context precision** | What fraction of retrieved chunks were actually relevant? (distractor load) |

Seed questions from **real logs**, not invented ones. Cross-link:
[`../llm-eval-and-observability/`](../llm-eval-and-observability/).

**Key takeaway:** Score retrieval on its own golden set before scoring answers, because an end-to-end answer metric cannot tell you which half of the system is broken.

### A39. Retrieval failure vs generation failure

| Evidence | Verdict |
|---|---|
| Right chunk **not** in retrieved context | **Retrieval** failure → tune chunking/index/K |
| Right chunk **was** in context, answer still wrong | **Generation** failure → prompt, model, or context ordering |
| Right chunk present but ranked 18th of 20 | Ranking failure → rerank / lower K |

Instrument by logging the retrieved chunk ids **with every answer**. Without that trace the distinction is
unanswerable and teams tune prompts to fix retrieval bugs.

**Key takeaway:** Log retrieved chunk ids alongside every answer — without that one field, retrieval and generation failures are indistinguishable and debugging becomes guesswork.

### A40. "It doesn't know about a document that is indexed" *(failure mode)*
Debug in this order — cheapest and most likely first:

| # | Check | Command/method |
|---|---|---|
| 1 | Is the vector actually there? | Look up by doc id in the store — catches dual-write loss (A19) |
| 2 | Retrievable by **exact** search? | Brute-force it. If exact finds it but ANN doesn't → **index/tuning** problem |
| 3 | Filter excluding it? | Re-run with filters removed (A13) |
| 4 | Chunking destroyed it? | Read the stored chunk text — is the answer even in one chunk? (A37) |
| 5 | Ranked below K? | Raise K temporarily and look |
| 6 | Model skew? | Compare embedding model id on write vs read (A6) |

**Key takeaway:** Always separate "is it in the store" from "can ANN find it" with a brute-force lookup — that single test splits the problem space in half on the first try.

---

## Level 8 — Architect / Staff

### A41. Against, then for, a dedicated vector DB

| Against (stay on Postgres) | For (adopt a specialist) |
|---|---|
| No new system, no sync problem (A19) | Purpose-built: quantization, tiering, filtered ANN |
| `JOIN`s and transactions with your real data | Scales past what one Postgres box holds in RAM |
| One backup/HA/on-call story | Independent scaling from OLTP |
| Team already fluent | Ops burden outsourced |

**Evidence that settles it:** measured recall@K *and* p99 at your **projected** corpus size, on your **real**
filter patterns — not a vendor benchmark, and not your current 100K-row corpus.

**Key takeaway:** Settle the argument with recall and p99 measured on your own data at projected scale with real filters, because every published vector benchmark omits the filtering that dominates real workloads.

### A42. Making the store swappable

```go
// The seam: a repository interface over retrieval, not over the vendor SDK.
type Retriever interface {
    Search(ctx context.Context, q Query) ([]Chunk, error)
}
type Query struct {
    Embedding []float32
    K         int
    Filter    map[string]any  // the leaky part
}
```

| Leaks through the abstraction anyway | Why |
|---|---|
| **Filter semantics** | Pre- vs post-filter behaviour differs per engine and changes results |
| Recall tuning knobs | `ef_search` has no portable equivalent |
| Consistency model | Read-after-write is immediate in Postgres, eventual in some services |
| Hybrid search | Single-pass hybrid (Couchbase Search index) vs two queries + RRF |

**Key takeaway:** You can abstract the call but not the filtering semantics or the consistency model, so treat the store as swappable-with-re-evaluation rather than genuinely pluggable.

### A43. Cost model at 1M queries/month
Model the *structure*; fill in current vendor pricing yourself (I have not verified current prices, and they change).

| Cost line | Driver | Usually |
|---|---|---|
| **Embedding (query)** | 1M × query tokens | Small per unit; **cache repeated queries** |
| **Embedding (corpus)** | One-off + churn | Spiky — the re-embedding migration (A29) is the surprise |
| **Storage** | vectors × dims × bytes (A31) | Predictable |
| **Compute/RAM** | Index resident in memory | **Usually dominates** for self-hosted |
| **Reranking** | 1M × candidate count | Sneaky — scales with N, not K |

The surprise line is almost always **re-embedding**, because it is invisible until the model is deprecated
and then arrives as one large bill.

**Key takeaway:** Steady-state cost is dominated by resident memory, but the budget-breaking event is a re-embedding migration — so price the model upgrade before you pick the model.

### A44. When vector search is the wrong tool

| Problem | Why embeddings fail | Use instead |
|---|---|---|
| Exact lookup (ID, SKU, error code) | Precision is the requirement; embeddings blur | Inverted index / B-tree |
| Structured aggregation ("revenue by region last quarter") | Not a similarity question at all | SQL |
| Small corpus (< ~10K docs) | ANN complexity buys nothing | Brute force — exact, simple, 100% recall |
| Freshness-critical ("what changed in the last minute") | Index lag; recency isn't similarity | Timestamp index |

**Key takeaway:** Vector search answers "what is similar", so any question that is really "what is exactly this" or "what is the total" belongs to a different index.

### A45. GDPR deletion

| Layer | Deletion difficulty |
|---|---|
| Source document | Easy — delete the row |
| Vector + metadata | Easy-ish — delete by id, but see A30 (tombstones persist in the graph until compaction) |
| **Compacted/derived index artifacts** | Requires a rebuild to truly remove |
| Backups | Retention policy must cover them |
| **Fine-tuned model weights** | **Effectively irreversible** — retraining is the only true remedy |

Design consequence: **do not fine-tune on deletable personal data.** Keep personal data in the retrievable
layer (deletable) rather than the parametric layer (not deletable). Embeddings are also partially invertible,
so treat a vector as personal data, not as anonymized data.

**Key takeaway:** Keep personal data in the retrieval layer and out of model weights, because a vector can be deleted and compacted away but a fine-tuned weight cannot.

### A46. 15% recall decay with no changes *(failure mode)*
"No deploys" does not mean "nothing changed" — the **data** changed.

| Cause | Mechanism |
|---|---|
| **Corpus growth** | Recall at fixed `ef_search` falls as N rises (A12). The classic answer. |
| Tombstone accumulation | Six months of deletes/updates degrading the graph (A30) |
| Distribution drift | New content types/languages the index wasn't tuned for |
| Query drift | Users ask different things than they did six months ago |
| Silent model change | A hosted embedding endpoint updated behind a stable name |

**Key takeaway:** An ANN index degrades with corpus growth and churn even when nothing is deployed, so recall needs a scheduled measurement and index parameters need periodic re-tuning.

---

## Bonus — answers

### AB1. Establishing a ground-truth recall baseline
Sample, don't exhaust. Take ~1,000 representative queries; for each, run **exact brute-force** over the
corpus (offline, off-peak, no latency SLA) to get true top-K; store as a fixture; diff ANN against it nightly.
Cost is bounded because it is 1,000 queries, not 1M, and it is not on the serving path.

**Key takeaway:** A recall baseline only needs a sampled fixture computed offline, so the usual objection that brute force is too expensive doesn't apply.

### AB2. Embedding model deprecation
The plan is A29 (versioned dual-index migration) and the cost is re-embedding the entire corpus plus double
storage during cutover. Reduce exposure by recording the model version with every vector and rehearsing the
migration on a subset **before** you are forced into it.

**Key takeaway:** Treat the embedding model as a dependency with a deprecation clock, and rehearse the migration before the vendor sets the deadline for you.

### AB3. Vectors nobody retrieves
Log retrieved chunk ids (you already need this for A39), then aggregate over 90 days.

| Finding | Action |
|---|---|
| Never retrieved, still valid | Move to cheaper tier / exclude from the hot index |
| Never retrieved, stale | Delete — improves recall by removing distractors |
| Retrieved but never cited in an answer | Chunking or ranking problem, not a storage one |

**Key takeaway:** Retrieval logs turn the index into a measurable inventory, and pruning dead content improves quality as well as cost.

### AB4. Corpus ownership and freshness SLA
State it explicitly: who re-indexes, how fast a source change appears in results, and who is paged when the
pipeline stalls. Unowned pipelines fail silently — the index keeps serving *stale but plausible* results,
which is worse than an outage because nothing alerts.

**Key takeaway:** A stale index has no error state, so freshness needs a named owner, a stated SLA, and an alert on indexing lag.

### AB5. Do vectors leak source text?
Treat "embeddings are anonymized" as **false**. Published inversion research shows meaningful text can be
partially reconstructed from embeddings, so a vector store holding customer content is holding personal data.

| Consequence | Action |
|---|---|
| Residency/perimeter | Vectors inherit the source data's classification |
| Access control | Filter by tenant at the store, not in the app |
| Vendor choice | Sending vectors to a third party = sending the data |

> I am not certain of the current state of the art on inversion attacks — verify against recent literature
> before quoting specifics. The safe operating assumption remains that vectors are derived personal data.

**Key takeaway:** Embeddings are not anonymization, so a vector inherits the residency and access rules of the text it came from.

---

## ⚡ Quick Revision Cheatsheet

### Scale numbers (math shown — verify against your hardware)
- **Raw vectors:** `N × dims × bytes`. 10M × 1536 × 4 B = **~61.4 GB**.
- **HNSW graph (m=16):** ~83 B/vector → 10M ≈ **~0.83 GB** (small vs the vectors).
- **Quantization:** int8 = **4×** smaller (~15.4 GB); binary = **32×** smaller (~1.9 GB).
- **Exact search cost:** `N × dims` ops/query → 10M × 1536 = **~1.5 × 10¹⁰** per query, linear in N.
- **Selective filter:** 0.1% of 10M = **10K vectors** → brute force wins, 100% recall.
- **pgvector comfort zone:** *approximately* millions to low tens of millions of vectors.
- **Couchbase Search (FTS) index:** vendor-stated ceiling **~100M documents**; Hyperscale scales to billions.

### Key technology choices

| Component | Choice | Why |
|---|---|---|
| Index (default) | **HNSW** | Best recall at fixed latency; no training step |
| Index (build-cost constrained) | IVFFlat | Cheaper build/memory; needs training data |
| Memory reduction | Scalar quantization **+ rescore** | 4× smaller, precision repaired by rescoring |
| Vectors beside relational data | pgvector | No sync problem; real `JOIN`s |
| Vectors beside documents + hybrid | Couchbase Search index | Vector + FTS + geo in a single pass |
| Billions, pure vector | Couchbase Hyperscale / specialist | Disk-optimized, low memory |
| Merging hybrid results | **RRF** (k≈60) | No score normalization needed |
| Final ordering | Cross-encoder rerank over N≫K | Precision the index cannot provide |

### Canonical trade-offs to memorize
- **HNSW vs IVF:** better recall/latency + no training vs cheaper build + less memory.
- **Pre-filter vs post-filter:** wrong-K (severed graph) vs short-K (starvation). Selectivity decides.
- **Quantization vs precision:** 4–32× memory saving vs ordering error — always pair with rescoring.
- **Shared index + filter vs index-per-tenant:** operational simplicity vs correctness and isolation.
- **In-RDBMS vs managed service:** no sync problem + joins vs elastic scale + no index ops.
- **Bigger K vs reranking:** more context (distractors, lost-in-the-middle) vs fewer better chunks.
- **`ef_search` up:** recall bought with latency, live, no rebuild.

### Common interview mistakes to avoid
- Saying "vector search is fast" without saying **at what recall**. Speed is free if you'll accept wrong answers.
- Treating **filtering** as a detail — it is the hardest part and where recall dies silently.
- Forgetting the **dual-write/sync problem** when proposing a separate vector service.
- Proposing an in-place embedding-model upgrade. Different model = different space = **new index**.
- Never mentioning **recall measurement**. If you can't say how you'd measure it, you can't claim it.
- Reaching for a vector DB at 10K documents, where brute force is exact, simpler, and fast.
- Ignoring **hybrid search** for corpora full of error codes, SKUs and identifiers.
- Assuming embeddings are anonymized data.
