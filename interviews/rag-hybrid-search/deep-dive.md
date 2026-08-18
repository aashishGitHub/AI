# RAG & Hybrid Search — Deep Dive

> Depth tiers: 🟢 fundamentals · 🟡 senior · 🔴 staff/architect.
> Pairs with [`answers.md`](answers.md). Ask AI facts from [`../../docs/Ask AI design document.md`](../../docs/Ask%20AI%20design%20document.md); tool/model specifics change fast — **verify current docs**.

---

## 1. Why the write/read split is the whole game (🟢→🔴)

🟢 A RAG system looks like one pipeline, but it's two. The **write path** turns a corpus into searchable vectors; the **read path** turns a question into a grounded answer. They're joined only by the store.

🟡 They have *opposite* constraints, and that's why separating them matters. The write path is throughput-bound and can be slow, batch, and parallel — nobody waits on it (Ask AI runs it weekly). The read path is latency-bound — a user watches tokens appear, so every millisecond and every one of the top-K counts. Conflating them leads to bad instincts, like optimizing indexing latency (irrelevant) or batching user queries (harmful).

🔴 The split is also your **debugging coordinate system**. A wrong answer is a write-path fault (bad chunk, stale embedding, missing doc), a read-path retrieval fault (right chunk not in top-K), or a generation fault (right chunk, wrong answer). Senior engineers reflexively localize a failure to one of these before touching anything — see the attribution diagram in [`../llm-eval-and-observability/diagrams.md`](../llm-eval-and-observability/diagrams.md).

---

## 2. The write path in depth (🟢→🔴)

🟢 Stages: fetch → clean → chunk → embed → store/version. Ask AI fetches HTML from S3, strips headers/footers/sidebars, chunks to ≤1,000 tokens, embeds each chunk with `text-embedding-3-small` (1,536-d), and stores in Couchbase.

🟡 **Cleaning is not cosmetic.** Nav bars, footers, and sidebars repeat on *every* page. If you embed them, thousands of chunks share that boilerplate text, so their vectors cluster around chrome instead of content, and full-text search matches the repeated words everywhere. Stripping them is a direct retrieval-quality lever.

🟡 **Chunking is the highest-leverage, cheapest knob.** Too big → one vector represents several ideas, so similarity is diluted and the right passage never scores high. Too small → an answer is split across chunks and no single chunk is sufficient. Structure-aware chunking (split on headings/sections, then cap size) fits documentation especially well because the author already segmented meaning. The ≤1,000-token cap keeps each vector focused *and* bounds prompt size when K chunks are concatenated.

🔴 **Freshness is a versioning problem, not a speed problem.** The dangerous operation is mutating the serving index in place: a half-finished re-embed leaves a "broken window" (some chunks new, some stale/missing). The correct pattern is build-beside → validate → atomic flip, keeping the old version as a backup — which is exactly why Ask AI's design lists "backup for old vector embeddings" and "validate the newly created embeddings" as requirements. Parallelism (Ask AI's 10 goroutines: 5–6 h → ~20 min) is a throughput optimization *within* that safe pattern, not a substitute for it.

**Failure mode (quantified-ish):** re-embed a 7,597-chunk corpus in place and die at 60% → ~40% of queries retrieve stale or empty context with *no error thrown*. With versioned build-then-flip, the same crash is a no-op you retry. Same failure, opposite blast radius.

---

## 3. Embeddings in depth (🟡→🔴)

🟡 An embedding is a learned map from text to a vector where distance encodes meaning. Cosine similarity compares *direction*, so it's robust to text length — useful when chunks vary in size. The query and documents **must** be embedded by the same model, or their vectors live in different spaces and "nearest" is meaningless.

🟡 **What you embed matters as much as the model.** Embedding `title + heading + chunk` often beats embedding the raw chunk, because the title disambiguates ("Indexes → Primary Index" vs a bare paragraph). This is a cheap retrieval win.

🔴 **Swapping the embedding model is a full migration.** Vectors from model A and model B are not comparable, so you must re-embed the entire corpus, build a new versioned index, and switch the *query-side* embedding at the exact moment you switch the index — a query embedded by the new model must never search vectors from the old one. This is the read/write paths' tightest coupling: the embedding model is a shared contract between them.

**Failure mode:** retrieval quality drops after a library or model minor-version bump with no retrieval-code change. Cause is almost always the embedding stage — model version, normalization, or tokenizer drift silently shifted the vectors. Pin and version embeddings like any dependency.

---

## 4. Retrieval: why hybrid beats pure vector (🟡→🔴)

🟡 Dense (vector) retrieval matches *meaning*: "make my database faster" finds performance-tuning docs even without the word "faster." Sparse (full-text/BM25) retrieval matches *exact tokens*: error code `E1234`, `CREATE PRIMARY INDEX`, a version string. Each fails precisely where the other wins — dense misses rare identifiers, sparse misses paraphrase.

🟡 **Documentation is adversarial to pure vector** because it's full of exact identifiers (API names, SQL++ keywords, config flags, error strings). That's the class of query that pushed Ask AI from pure vector to hybrid. Running both and fusing recovers the keyword-precise questions without losing semantic recall.

🔴 **Fusing incomparable scores.** Cosine (bounded, ~0–1) and BM25 (unbounded, corpus-dependent) can't be added directly. Reciprocal Rank Fusion (RRF) sidesteps this by fusing on *rank* (`Σ 1/(k+rank)`), which is robust and parameter-light; weighted score blending is more tunable but needs normalization and per-corpus tuning. Ask AI does both searches in a *single* Couchbase query (one round-trip, engine-native ranking) and falls back to pure vector when hybrid returns nothing — a coverage guarantee for paraphrase-only queries where full-text contributes zero.

---

## 5. Ranking & re-ranking in depth (🟡→🔴)

🟡 Initial retrieval (ANN over the whole corpus) is tuned for cheap recall and returns coarse scores. Re-ranking spends more compute on a *shortlist* to maximize precision at the very top, because only the top K actually enter the prompt. This retrieve-wide-then-rerank-narrow shape is why you can afford good ranking at all.

🟡 **Ask AI's heuristic re-ranker** adds a length preference (favor medium chunks) and content-type bonuses (code, headings, structured content) on top of the base hybrid score. It's cheap, fast, transparent, and domain-aware — sensible for docs. Its weakness is fragility: hand-tuned weights don't transfer across corpora, and a bonus can outrank true relevance. The discipline is to *ablate* each term (turn the code bonus off; does answer quality drop on the eval set?) so every heuristic earns its place.

🔴 **Cross-encoders** score the query and document *jointly*, which is materially more accurate than comparing independent embeddings, but they cost a model pass per candidate — real latency and money. The staff move isn't "cross-encoder good/bad"; it's bounding the cost: re-rank a small shortlist, use a distilled re-ranker, cache by (query, doc), and degrade to the heuristic under load. K itself is an eval-tuned parameter (Ask AI: 5): too low misses grounding, too high inflates cost and triggers lost-in-the-middle.

---

## 6. Query understanding & generation (🟡→🔴)

🟡 **Rephrasing is the cheapest big win in multi-turn RAG.** "And for the paid tier?" is meaningless to an embedding model; resolved against history into "How do rate limits differ for the paid tier?" it retrieves correctly. Ask AI does this with a deliberately *lightweight* LLM call — not a second large one — because the goal is to fix the query cheaply, and a big second call would roughly double cost and latency for diminishing return.

🔴 **Generation is where perfect retrieval still fails.** Even with the right chunk at #1, the model can under-weight the context, lose relevant text in the middle of a long prompt, or fall back on parametric memory that contradicts your context. Mitigations: a system-prompt contract ("answer only from context, cite URLs, else say you don't know"), ordering the strongest chunks at the edges (models attend most to start and end), keeping K tight, and gating on retrieval confidence so weak context yields an honest "I don't know" rather than a fluent hallucination. Streaming (SSE, via `CreateChatCompletionsStream`) doesn't change correctness but massively improves *perceived* latency — at the cost of handling mid-stream failures and measuring time-to-first-token.

---

## 7. Staff-level: scale, freshness, multitenancy, limits (🔴)

- **Scale the paths separately.** Write scales with corpus size (parallel batch embedding — Ask AI's goroutines); read scales with QPS (store replicas, ANN tuning, caching, model/K tuning). Their capacity plans share nothing.
- **Freshness vs cost.** Weekly full re-embed is simple but re-embeds unchanged docs; incremental/event-driven indexing embeds only deltas at the cost of a change-detection pipeline. Choose by how much staleness actually hurts.
- **Multitenancy.** Hard data isolation (per-tenant scope/collection or enforced filters — never leak one tenant's chunks into another's retrieval) plus per-tenant rate/cost limits. Ask AI enforces this through iQ (every call carries Tenant + User ID) with configurable calls/minute, requests/day, and tokens/month, differentiated free vs paid — which also prevents a noisy neighbor from starving others.
- **Know when to stop.** Hybrid + re-ranking must pay for itself on the eval set. A tiny static corpus may be better served by long-context; a purely semantic query mix may not need full-text; a tight latency budget may not afford a cross-encoder. Complexity that doesn't move a metric is just latency and ops burden.
- **Cost levers, in order:** semantic cache for repeat/similar queries, right-size the embedding and generation models, tighten K/prompt, and go incremental on indexing — each validated against eval so quality holds.

---

## 8. Closing cheat sheet

| Layer | The move | The trap |
|---|---|---|
| Split | design write vs read separately | one-pipeline thinking |
| Clean | strip repeated boilerplate | embedding the chrome |
| Chunk | structure-aware + token cap | too big (dilute) / too small (split) |
| Embed | one model for query+docs; version it | mixed spaces; silent model drift |
| Retrieve | hybrid (dense+sparse) + fallback | pure-vector-only misses exact tokens |
| Rank | retrieve-wide → rerank-narrow | precise-rank the whole corpus |
| Re-rank | ablate heuristics / bound cross-encoder | unjustified bonuses; latency blowup |
| Generate | contract + edge-ordering + confidence gate | trust the model to self-ground |
| Ops | version index; per-stage telemetry | in-place re-embed; no rollback |

**The one line:** *A RAG system is a throughput-bound write path and a latency-bound read path meeting at the store; hybrid retrieval + re-ranking earn their keep by recovering exact-token queries and precision — and every failure localizes to write, retrieval, or generation.*

> Next in the ramp-up: the store itself — pgvector vs Pinecone vs Couchbase FTS — in [`../vector-databases/`](../vector-databases/); and measure all of this with [`../llm-eval-and-observability/`](../llm-eval-and-observability/).
