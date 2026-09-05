# Vector Databases — Interview Diagrams

> **Start with Diagram 1.** It is the central split; every other diagram is a zoom into one of its two axes.
> **Reference:** answers in [`answers.md`](answers.md) · plain mental model in [`simple-diagram.md`](simple-diagram.md)
> **Cross-links:** [`../rag-hybrid-search/`](../rag-hybrid-search/) (retrieval paths) · [`../llm-eval-and-observability/`](../llm-eval-and-observability/) (measuring recall)

---

## Diagram 1 — The central split: index vs operating model

> **When to use:** Q5, Q18, Q20, Q41 — and as the opening frame for *any* "which vector DB?" question.

```mermaid
flowchart TB
    ASK(["'Which vector database<br/>should we use?'"])
    SPLIT{"Two INDEPENDENT<br/>decisions"}

    subgraph AXIS1["Axis 1 — Index: how much recall do you sell?"]
        direction TB
        I1["HNSW<br/>graph · best recall/latency"]
        I2["IVF<br/>clusters · cheap build"]
        I3["Quantization<br/>PQ · scalar · binary"]
        IKNOB["Knob: ef_search / probes<br/>recall ⇄ latency, live"]
    end

    subgraph AXIS2["Axis 2 — Operating model: where do vectors live?"]
        direction TB
        O1["In your RDBMS<br/>pgvector"]
        O2["Managed service<br/>Pinecone"]
        O3["In your data platform<br/>Couchbase 8.0"]
        OCON["Decided by: joins ·<br/>consistency · ops · perimeter"]
    end

    ASK --> SPLIT
    SPLIT -->|"tune LAST"| AXIS1
    SPLIT -->|"decide FIRST"| AXIS2

    style ASK fill:#e0e7ff,stroke:#4338ca
    style SPLIT fill:#fef9c3,stroke:#ca8a04
    style I1 fill:#dcfce7,stroke:#16a34a
    style I2 fill:#dcfce7,stroke:#16a34a
    style I3 fill:#dcfce7,stroke:#16a34a
    style IKNOB fill:#fef9c3,stroke:#ca8a04
    style O1 fill:#dbeafe,stroke:#1d4ed8
    style O2 fill:#dbeafe,stroke:#1d4ed8
    style O3 fill:#dbeafe,stroke:#1d4ed8
    style OCON fill:#e0e7ff,stroke:#4338ca
```

**What the interviewer is checking:**
- Do you separate the two axes, or collapse them into brand preference ("Pinecone is better")?
- Do you drive the operating model from **data and consistency** needs rather than benchmarks?
- Can you name the live recall knob (`ef_search`) versus the build-time commitments (`m`)?
- Do you treat index tuning as the *last* step, not the first?

---

## Diagram 2 — HNSW: why the graph walk is fast

> **When to use:** Q7, Q8 — "explain HNSW", and any "why is it logarithmic" follow-up.

```mermaid
flowchart TB
    Q(["Query vector"])
    L2A["L2 · sparse<br/>long-range hops"]
    L1A["L1 · medium density"]
    L0A["L0 · every node<br/>short links"]
    RES["Nearest neighbours<br/>ef_search candidates kept"]

    Q -->|"1 enter at top layer"| L2A
    L2A -->|"2 greedy hop toward query"| L2A
    L2A -->|"3 descend when no closer neighbour"| L1A
    L1A -->|"4 refine"| L1A
    L1A -->|"5 descend"| L0A
    L0A -->|"6 exhaustive local search<br/>within ef_search budget"| RES

    style Q fill:#fed7aa,stroke:#ea580c
    style L2A fill:#dbeafe,stroke:#1d4ed8
    style L1A fill:#dbeafe,stroke:#1d4ed8
    style L0A fill:#dbeafe,stroke:#1d4ed8
    style RES fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Can you explain *why* layers exist (coarse-to-fine, like a skip list) rather than reciting "it's a graph"?
- Do you connect `ef_search` to the **width of the candidate list at L0** — the actual recall/latency dial?
- Do you know the search is **greedy and therefore fallible** — that's the source of imperfect recall?
- Can you say why HNSW needs no training step (contrast with Diagram 3)?

---

## Diagram 3 — IVF: clusters, probes, and the boundary problem

> **When to use:** Q9, Q10 — "explain IVF", "when would you pick IVF over HNSW?"

```mermaid
flowchart LR
    QV(["Query vector"])
    CENT["Compare to `lists` centroids"]
    C1[("Cell 1")]
    C2[("Cell 2 · probed")]
    C3[("Cell 3 · probed")]
    C4[("Cell 4 · NOT probed")]
    MISS["True neighbour just across<br/>the boundary — MISSED"]
    OUT["Candidates from probed cells"]

    QV --> CENT
    CENT -->|"nearest `probes` cells only"| C2
    CENT -->|"nearest `probes` cells only"| C3
    CENT -.->|"skipped"| C1
    CENT -.->|"skipped"| C4
    C4 -.-> MISS
    C2 --> OUT
    C3 --> OUT

    style QV fill:#fed7aa,stroke:#ea580c
    style CENT fill:#fef9c3,stroke:#ca8a04
    style C2 fill:#dcfce7,stroke:#16a34a
    style C3 fill:#dcfce7,stroke:#16a34a
    style C4 fill:#fee2e2,stroke:#dc2626
    style MISS fill:#fee2e2,stroke:#dc2626
    style OUT fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Do you name the boundary problem — a near neighbour in an unprobed cell is simply invisible?
- Do you know IVF **requires representative data before building** (k-means training) and HNSW does not?
- Can you say when IVF still wins: build time and memory, not query quality?
- Do you mention centroid **drift** as the corpus changes, requiring retraining?

---

## Diagram 4 — Pre-filter vs post-filter: where recall dies

> **When to use:** Q13, Q14, Q15, Q17 — the highest-signal diagram in this folder.

```mermaid
flowchart TB
    QQ(["Query + filter<br/>tenant = 42"])
    CHOICE{"Filter strategy"}

    POST["POST-filter<br/>ANN first, then discard"]
    POSTR["Asked for K=10<br/>9 discarded → 1 RESULT"]

    PRE["PRE-filter<br/>restrict set, then search"]
    PRER["Graph path severed<br/>true match unreachable"]

    ITER["Filtered / iterative traversal<br/>filter DURING the walk"]
    ITERR["K results, high recall<br/>unbounded worst case"]

    QQ --> CHOICE
    CHOICE -->|"simple, default"| POST --> POSTR
    CHOICE -->|"selective filters"| PRE --> PRER
    CHOICE -->|"best, engine-specific"| ITER --> ITERR

    style QQ fill:#fed7aa,stroke:#ea580c
    style CHOICE fill:#fef9c3,stroke:#ca8a04
    style POSTR fill:#fee2e2,stroke:#dc2626
    style PRER fill:#fee2e2,stroke:#dc2626
    style ITERR fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Do you know **both** failure modes — short-K (starvation) *and* wrong-K (severed graph)?
- Do you make **selectivity** the deciding variable rather than picking a favourite?
- Do you spot that at very high selectivity the right answer is **brute force**, not ANN at all?
- Do you reach for **partitioning by the filter key** (index per tenant) to dissolve the problem?

---

## Diagram 5 — Quantization and the rescore repair

> **When to use:** Q11, Q31 — "how do you fit this in memory?"

```mermaid
flowchart LR
    FULL[("Full-precision vectors<br/>1536-d float32 · 6144 B")]
    QUANT["Quantize<br/>int8 4× · binary 32×"]
    SMALL[("Compressed index<br/>fits in RAM")]
    SCAN["Fast approximate scan<br/>over compressed vectors"]
    CAND["Over-fetched candidates<br/>N ≫ K"]
    RESC["RESCORE with<br/>full-precision vectors"]
    OUT["Top-K, correct order"]

    FULL --> QUANT --> SMALL --> SCAN --> CAND --> RESC --> OUT
    FULL -.->|"kept on disk for rescoring"| RESC

    style FULL fill:#dbeafe,stroke:#1d4ed8
    style QUANT fill:#fef9c3,stroke:#ca8a04
    style SMALL fill:#dbeafe,stroke:#1d4ed8
    style SCAN fill:#fef9c3,stroke:#ca8a04
    style RESC fill:#e0e7ff,stroke:#4338ca
    style OUT fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Do you pair quantization with **rescoring**, or propose it as a free lunch?
- Can you do the arithmetic (10M × 1536 × 4 B ≈ 61.4 GB → int8 ≈ 15.4 GB)?
- Do you realise full-precision vectors must still be **retained somewhere** to rescore against?
- Do you frame quantization as a *scan* accelerator rather than a storage decision?

---

## Diagram 6 — The dual-write problem

> **When to use:** Q19, Q22, Q23 — whenever a *separate* vector service is proposed.

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant PG as Postgres (source of truth)
    participant VDB as Vector service
    participant User

    App->>PG: INSERT document
    PG-->>App: committed ✅
    App->>VDB: upsert embedding
    VDB--xApp: timeout ❌
    Note over App,VDB: Row exists. Vector does not.<br/>No error surfaces to anyone.

    User->>App: search for that document
    App->>VDB: ANN query
    VDB-->>App: 0 matching results
    App-->>User: "I don't have information about that"
    Note over User: Document is invisible forever<br/>unless a reconciler exists
```

**What the interviewer is checking:**
- Do you identify this **unprompted** when proposing a separate vector store?
- Can you name real mitigations: transactional outbox, CDC, reconciliation sweep?
- Do you note that co-locating vectors with the source of truth **removes** the failure class?
- Do you see that the user-visible symptom is a *plausible* answer, not an error?

---

## Diagram 7 — Hybrid search and Reciprocal Rank Fusion

> **When to use:** Q24, Q25, Q26 — "why isn't vector search enough?"

```mermaid
flowchart TB
    UQ(["Query: 'ERR_CONN_4021 on login'"])
    VEC["Vector search<br/>semantic · paraphrase-tolerant"]
    BM["BM25 / FTS<br/>exact tokens · error codes"]
    RRF["RRF merge<br/>score = Σ 1/(k + rank), k≈60"]
    RR["Cross-encoder rerank<br/>query+doc scored together"]
    TOPK["Top-K to the LLM"]

    UQ --> VEC
    UQ --> BM
    VEC -->|"ranked list A"| RRF
    BM -->|"ranked list B"| RRF
    RRF -->|"N ≫ K candidates"| RR
    RR --> TOPK

    style UQ fill:#fed7aa,stroke:#ea580c
    style VEC fill:#dbeafe,stroke:#1d4ed8
    style BM fill:#dbeafe,stroke:#1d4ed8
    style RRF fill:#fef9c3,stroke:#ca8a04
    style RR fill:#e0e7ff,stroke:#4338ca
    style TOPK fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Can you say *why* RRF uses **rank not score** (BM25 and cosine scores aren't comparable)?
- Do you distinguish bi-encoder (precomputed, cheap) from cross-encoder (joint, accurate, not precomputable)?
- Do you over-fetch N ≫ K so the reranker has room to work?
- Do you know Couchbase's Search index does hybrid **in a single pass**, avoiding the two-query merge?

---

## Diagram 8 — Full RAG retrieval path: every place recall dies

> **When to use:** Q35, Q37, Q40 — the end-to-end walkthrough.

```mermaid
flowchart TB
    DOCS(["Source documents"])
    CHUNK["Chunk<br/>❌ answer split across chunks"]
    EMBW["Embed (write)<br/>❌ model version skew"]
    IDXB[("Index<br/>❌ stale / partial reindex")]

    UQ(["User question"])
    EMBR["Embed (read)<br/>❌ different model"]
    FILT["Filter<br/>❌ severed graph / starved K"]
    ANN["ANN search<br/>❌ ef_search too low for N"]
    OVER["Over-fetch N<br/>❌ N too small caps rerank"]
    RANK["Rerank<br/>❌ miscalibrated"]
    TOPK["Top-K<br/>❌ lost in the middle"]
    LLM["LLM answer"]

    DOCS --> CHUNK --> EMBW --> IDXB
    UQ --> EMBR --> FILT --> ANN --> OVER --> RANK --> TOPK --> LLM
    IDXB -.->|"serves"| ANN

    style CHUNK fill:#fee2e2,stroke:#dc2626
    style EMBW fill:#fee2e2,stroke:#dc2626
    style EMBR fill:#fee2e2,stroke:#dc2626
    style FILT fill:#fee2e2,stroke:#dc2626
    style ANN fill:#fee2e2,stroke:#dc2626
    style OVER fill:#fee2e2,stroke:#dc2626
    style RANK fill:#fee2e2,stroke:#dc2626
    style TOPK fill:#fee2e2,stroke:#dc2626
    style LLM fill:#dcfce7,stroke:#16a34a
    style IDXB fill:#dbeafe,stroke:#1d4ed8
```

**What the interviewer is checking:**
- Do you see recall as a **product** of every stage — the weakest stage sets the ceiling?
- Do you check chunking *before* tuning index parameters?
- Can you name a diagnostic per stage rather than just listing stages?
- Do you separate **retrieval** failure from **generation** failure (Q39)?

---

## Diagram 9 — Zero-downtime embedding-model migration

> **When to use:** Q29, QB2 — "the embedding model is deprecated, now what?"

```mermaid
stateDiagram-v2
    [*] --> V1Only: v1 index serving
    V1Only --> DualWrite: create v2 index alongside
    DualWrite --> Backfill: re-embed corpus into v2, batched
    Backfill --> ShadowRead: v2 complete, not served
    ShadowRead --> Compare: run live queries against both
    Compare --> Rollback: v2 recall worse
    Rollback --> Backfill
    Compare --> Canary: v2 recall acceptable
    Canary --> V2Only: ramp to 100 percent
    V2Only --> [*]: drop v1 after soak

    note right of DualWrite
        Every new doc written to BOTH
        indexes for the whole migration
    end note
    note right of ShadowRead
        Two full indexes stored at once
        Budget for double storage
    end note
```

**What the interviewer is checking:**
- Do you know an in-place upgrade is **impossible** — different model means a different vector space?
- Do you include a **shadow-read/compare** phase rather than cutting over blind?
- Do you budget the real costs: re-embedding the whole corpus plus double storage?
- Do you keep v1 warm for rollback?

---

## Diagram 10 — HNSW node lifecycle: why deletes need compaction

> **When to use:** Q30, Q34, Q46 — "how do deletes work?" and slow recall decay.

```mermaid
stateDiagram-v2
    [*] --> Inserted: add vector, link to neighbours
    Inserted --> Live: reachable, returned in results
    Live --> Tombstoned: delete requested
    Tombstoned --> Live: re-inserted with same id
    Tombstoned --> Compacted: rebuild or compaction runs
    Compacted --> [*]: truly removed

    note right of Tombstoned
        Still traversed as a stepping stone
        Filtered from results but not the graph
        Accumulation degrades recall over months
    end note
```

**What the interviewer is checking:**
- Do you know deletion is harder than insertion because nodes are **load-bearing** for traversal?
- Can you explain the tombstone compromise and its cost over time?
- Do you schedule **compaction/rebuild** as routine operations, not an emergency?
- Do you connect tombstone accumulation to the "recall decayed with no deploys" scenario (Q46)?

---

## Diagram 11 — Choosing the operating model

> **When to use:** Q18, Q20, Q21, Q41 — the decision, made from requirements not brands.

```mermaid
flowchart TB
    START(["Where should vectors live?"])
    JOIN{"Need JOINs / transactions<br/>with relational data?"}
    SIZE{"Fits comfortably in RAM<br/>alongside OLTP?"}
    DOCS{"Vectors describe JSON docs<br/>you already store?"}
    HYB{"Need hybrid<br/>vector + FTS + geo?"}

    PGV[("pgvector<br/>no sync problem")]
    CBH[("Couchbase Hyperscale<br/>billions, pure vector")]
    CBS[("Couchbase Search index<br/>hybrid, single pass")]
    MAN[("Managed service<br/>accept dual-write cost")]

    START --> JOIN
    JOIN -->|"yes"| SIZE
    JOIN -->|"no"| DOCS
    SIZE -->|"yes"| PGV
    SIZE -->|"no"| MAN
    DOCS -->|"yes"| HYB
    DOCS -->|"no"| MAN
    HYB -->|"yes"| CBS
    HYB -->|"no"| CBH

    style START fill:#e0e7ff,stroke:#4338ca
    style JOIN fill:#fef9c3,stroke:#ca8a04
    style SIZE fill:#fef9c3,stroke:#ca8a04
    style DOCS fill:#fef9c3,stroke:#ca8a04
    style HYB fill:#fef9c3,stroke:#ca8a04
    style PGV fill:#dbeafe,stroke:#1d4ed8
    style CBH fill:#dbeafe,stroke:#1d4ed8
    style CBS fill:#dbeafe,stroke:#1d4ed8
    style MAN fill:#fed7aa,stroke:#ea580c
```

**What the interviewer is checking:**
- Is your first question about **data relationships**, not throughput?
- Do you treat the managed service as carrying a **dual-write tax** rather than being free?
- Do you know Couchbase's index choice is **per query shape**, so one app may need more than one?
- Can you name the pressures that push you *off* pgvector (RAM contention, build vs OLTP)?

---

## Diagram 12 — Debugging "the assistant doesn't know about an indexed doc"

> **When to use:** Q40, Q6 — the most common real-world incident.

```mermaid
flowchart TB
    SYM(["Doc is indexed but never retrieved"])
    S1{"Vector present<br/>by doc id?"}
    S2{"Found by EXACT<br/>brute-force search?"}
    S3{"Found with filters<br/>removed?"}
    S4{"Answer actually inside<br/>one chunk?"}
    S5{"Ranked below K?"}

    F1["Dual-write loss<br/>→ reconcile (Diagram 6)"]
    F2["Index/tuning problem<br/>→ raise ef_search, rebuild"]
    F3["Filter problem<br/>→ Diagram 4"]
    F4["Chunking problem<br/>→ re-chunk with overlap"]
    F5["Ranking problem<br/>→ rerank, raise K"]
    F6["Model skew<br/>→ compare write vs read model id"]

    SYM --> S1
    S1 -->|"no"| F1
    S1 -->|"yes"| S2
    S2 -->|"no"| F6
    S2 -->|"yes"| S3
    S3 -->|"only without filters"| F3
    S3 -->|"still missing"| F2
    S3 -->|"found"| S4
    S4 -->|"no"| F4
    S4 -->|"yes"| S5
    S5 -->|"yes"| F5

    style SYM fill:#fee2e2,stroke:#dc2626
    style S1 fill:#fef9c3,stroke:#ca8a04
    style S2 fill:#fef9c3,stroke:#ca8a04
    style S3 fill:#fef9c3,stroke:#ca8a04
    style S4 fill:#fef9c3,stroke:#ca8a04
    style S5 fill:#fef9c3,stroke:#ca8a04
    style F1 fill:#dcfce7,stroke:#16a34a
    style F2 fill:#dcfce7,stroke:#16a34a
    style F3 fill:#dcfce7,stroke:#16a34a
    style F4 fill:#dcfce7,stroke:#16a34a
    style F5 fill:#dcfce7,stroke:#16a34a
    style F6 fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Do you **bisect** (exact vs ANN) instead of guessing? That one test halves the problem space.
- Do you check the cheapest thing first (is the vector even there)?
- Do you reach for a **brute-force comparison** as a debugging primitive?
- Can you name the fix for each branch, not just the diagnosis?

---

## Quick Interview Reference

### Scale numbers

| Quantity | Math | Result |
|---|---|---|
| Raw vectors, 10M × 1536-d | `10e6 × 1536 × 4 B` | **~61.4 GB** |
| Same, int8 quantized | `10e6 × 1536 × 1 B` | **~15.4 GB** (4×) |
| Same, binary | `10e6 × 192 B` | **~1.9 GB** (32×) |
| HNSW graph, m=16 | `~83 B × 10e6` | **~0.83 GB** |
| Exact search cost | `N × dims` | **~1.5 × 10¹⁰** ops/query |
| 0.1% selective filter of 10M | — | **10K vectors** → brute force |
| pgvector comfort zone | *approximate* | millions → low tens of millions |
| Couchbase Search (FTS) index | vendor-stated | **~100M docs** |

### Domain quick-ref

| Term | One line |
|---|---|
| **HNSW** | Layered proximity graph; best recall/latency; no training step |
| **IVF** | k-means cells; probe the nearest `probes`; needs training data first |
| **`ef_search`** | Query-time recall dial — **no rebuild required** |
| **`m` / `ef_construction`** | Build-time commitments — rebuild to change |
| **PQ / SQ / binary** | Quantization; pair with **rescoring** |
| **Pre-filter** | Filter then search; can sever the graph |
| **Post-filter** | Search then filter; can starve K |
| **RRF** | Merge ranked lists by rank, `1/(k+rank)`, k≈60 |
| **Cross-encoder** | Joint query+doc scoring; accurate; not precomputable |
| **recall@K** | Fraction of true top-K returned — the metric nobody measures |

### Canonical trade-offs
- **HNSW vs IVF** — recall/latency + no training vs cheap build + low memory.
- **Pre- vs post-filter** — wrong-K vs short-K; *selectivity decides*.
- **Quantization vs precision** — 4–32× memory vs ordering error; rescore repairs it.
- **In-RDBMS vs managed** — joins and no sync problem vs elastic scale and no index ops.
- **Bigger K vs reranking** — more context and distractors vs fewer, better chunks.
- **Shared index + filter vs index-per-tenant** — fewer indexes vs correct recall and isolation.

### Common mistakes
- Quoting speed without stating **recall**.
- Treating filtering as a detail — it is the hardest part.
- Proposing a separate vector store without naming the **dual-write** problem.
- Suggesting an in-place embedding-model upgrade.
- Never saying how recall would be **measured**.
- Using ANN at 10K documents where brute force is exact and simpler.
- Forgetting hybrid search for corpora full of identifiers and error codes.
