# RAG & Hybrid Search — Answers

> Keyed to [`questions.md`](questions.md). Each answer has a table **or** code, and ends with a **Key takeaway**.
> Ask AI facts are drawn from [`../../docs/Ask AI design document.md`](../../docs/Ask%20AI%20design%20document.md). Tool/model specifics change fast — **verify current docs** where flagged.

---

## Level 1 — Fundamentals

### A1. What RAG is and what it solves
RAG = retrieve relevant text from an external store, then condition the LLM's generation on it.

| Bare LLM | With RAG |
|---|---|
| Knows only training data (stale, no private docs) | Answers from *your* current corpus |
| Hallucinates confidently | Grounded in retrieved passages |
| No citations | Can cite the source URL |
| Update = retrain/fine-tune | Update = re-index (cheap) |

**Key takeaway:** RAG makes an LLM answer from *current, private, citable* knowledge by moving the knowledge into a retrieval step instead of the weights.

### A2. RAG vs fine-tuning vs long context

| Approach | Best for | Weakness |
|---|---|---|
| RAG | Large/changing knowledge, citations, freshness | Retrieval quality is now your problem |
| Fine-tuning | Style/format/behavior, narrow skills | Doesn't add fresh facts; costly to update |
| Long context (stuff it all) | Small, static corpus that fits | Cost/latency scale with tokens; "lost in the middle" |

**Key takeaway:** Fine-tune for *behavior*, RAG for *knowledge*, long-context only when the whole corpus is small and static — and combine RAG+fine-tuning when you need both.

### A3. The two paths and why to separate them

| | Write / index path | Read / query path |
|---|---|---|
| Trigger | Corpus change (batch) | User query (real-time) |
| Constraint | Throughput, freshness | Latency, precision |
| Can be slow? | Yes (weekly, offline) | No (user waiting) |
| Scales with | Corpus size | Query volume |

**Key takeaway:** The two paths have opposite constraints, so you build, scale, and debug them independently — and most RAG bugs reduce to "which path failed?"

### A4. Ask AI end-to-end happy path
```text
1. User types question in CP-UI → CP-API (/docsbot/stream, JWT)
2. iQ Backend rephrases query using chat history (lightweight LLM, context-aware)
3. iQ CreateEmbeddings → query vector (1,536-dim)
4. Hybrid search (vector + full-text) in ONE Couchbase query via Go SDK
   → (fallback to pure vector if empty)
5. Custom re-rank → top K = 5 chunks (+ source URLs, titles, token counts)
6. Rephrased query + K chunks → prompt
7. iQ CreateChatCompletionsStream (GPT-4o) → SSE tokens back to CP-UI
```
**Key takeaway:** Query → rephrase → embed → hybrid retrieve (+fallback) → re-rank → top-5 → stream: the read path is a short, latency-bound pipeline with the store in the middle.

### A5. *(Failure mode)* Fact isn't in the docs at all
Not a retrieval failure — a *grounding/coverage* problem.

| Situation | Right behavior |
|---|---|
| Answer not in corpus | Say "I don't have that in the docs" — don't invent |
| Weak/low-score retrieval | Hedge or refuse rather than fabricate |
| Genuinely missing docs | Log as a corpus gap → candidate new content |

**Key takeaway:** When the corpus can't support an answer the system must *decline*, not hallucinate — and log the gap so retrieval coverage improves.

---

## Level 2 — Indexing / write path

### A6. Write-path stages and the cost of doing each badly

| Stage | Do it badly → |
|---|---|
| Fetch | Miss/duplicate docs → coverage holes |
| Clean | Keep nav/boilerplate → embeddings capture chrome, not content |
| Chunk | Wrong size → split answers or dilute relevance |
| Embed | Wrong/mismatched model → query & doc in different spaces |
| Store + version | No versioning → a bad run corrupts live retrieval |

**Key takeaway:** Every write-path stage silently degrades *read* quality later; chunking and cleaning are where most retrieval quality is won or lost.

### A7. Chunking strategies and sizing

| Strategy | When |
|---|---|
| Fixed-size (tokens) | Simple, uniform; risks splitting mid-idea |
| Fixed + overlap | Preserves context across boundaries; more chunks/cost |
| Semantic/structural (by heading/section) | Respects document structure (great for docs) |
| Recursive (split on structure, then size-cap) | Common default: structure first, size as backstop |

Pick size by: embedding model's sweet spot, answer granularity, and prompt budget (K × chunk ≤ context). Ask AI caps at **≤1,000 tokens/chunk**.

**Key takeaway:** Prefer structure-aware chunking with a token cap; size is a trade-off between "whole idea per chunk" and "precise, non-diluted retrieval."

### A8. Why clean + cap at ~1,000 tokens
```text
Clean (drop headers/footers/sidebars):
  - nav/boilerplate repeats on every page → embeddings cluster on chrome, not content
  - inflates tokens (cost) and dilutes the vector's meaning
Cap ~1,000 tokens/chunk:
  - keeps each vector focused on one idea (better precision)
  - bounds prompt size when K chunks are concatenated
```
**Key takeaway:** Cleaning removes repeated boilerplate that would poison similarity; the token cap keeps each embedding focused and the prompt affordable.

### A9. Freshness without downtime

| Technique | Effect |
|---|---|
| Scheduled re-embed (Ask AI: weekly cron) | Bounded staleness window |
| Version embeddings, don't mutate in place | Old index serves while new one builds |
| Atomic switch / alias flip after validation | No half-built index ever serves |
| Validate new embeddings before promoting | Catch a bad run pre-cutover |

**Key takeaway:** Build the new index *beside* the live one, validate, then flip — never mutate the serving index in place, so a re-embed is invisible to users.

### A10. *(Failure mode)* Half-failed re-embed job

| If you… | Users experience |
|---|---|
| Mutate live index in place | Broken window: 60% new, 40% stale/missing → wrong/empty answers |
| Build new version + validate + flip | Nothing — old version keeps serving; failed run never promoted |

Ask AI's design explicitly calls for "backup for old vector embeddings … validate the newly created embeddings."

**Key takeaway:** Versioned, validate-then-swap indexing turns a half-failed re-embed from an outage into a no-op you retry.

---

## Level 3 — Embeddings

### A11. Embeddings and why cosine
An embedding maps text → a vector so that *semantically similar text is geometrically close*. Cosine similarity measures the **angle** (direction), ignoring magnitude.

| Metric | Measures | Note |
|---|---|---|
| Cosine | angle/direction | robust to length; the common default |
| Dot product | direction + magnitude | equals cosine if vectors are normalized |
| Euclidean (L2) | straight-line distance | sensitive to magnitude |

Ask AI: `dims: 1536, similarity: cosine, vector_index_optimized_for: recall`.

**Key takeaway:** Embeddings turn "meaning" into geometry; cosine compares *direction* so answers aren't skewed by text length.

### A12. Choosing an embedding model / dimensionality

| Lever | Higher dims | Lower dims |
|---|---|---|
| Quality ceiling | usually higher | may lose nuance |
| Storage/index size | larger | smaller |
| Search latency | slower | faster |
| Cost | higher | lower |

Also weigh: domain fit, max input length, multilingual need, price. *(Verify current model options/benchmarks.)*

**Key takeaway:** Dimensionality trades quality against storage/latency/cost; pick the smallest model that clears your retrieval-quality bar on *your* eval set.

### A13. What text to embed; shared space
- Embed the **chunk**, often prefixed with **page title / section** for context.
- The **query** and **documents must be embedded by the same model** so they share one vector space — otherwise "closeness" is meaningless.

**Key takeaway:** Query and document vectors must come from the *same* model/space, and enriching a chunk with its title/heading usually lifts retrieval.

### A14. Swapping embedding models → re-embed everything
```text
Vectors from model A and model B are NOT comparable (different spaces).
So: re-embed the ENTIRE corpus with the new model, build a NEW versioned index,
validate, then switch the query path to embed with the new model at the same instant.
Never mix: a query embedded by B searching A's vectors returns garbage.
```
**Key takeaway:** An embedding-model change is a full corpus migration — re-embed all, dual-write/version, and flip query + index together atomically.

### A15. *(Failure mode)* Silent retrieval drop after an "unrelated" upgrade

| Likely cause | Why |
|---|---|
| Embedding model/version changed under you | New space; old vectors incomparable |
| Library changed normalization/pooling | Vectors subtly shifted |
| Tokenizer/preprocessing drift | Different text → different vector |

**Key takeaway:** If retrieval degrades with no retrieval-code change, suspect the *embedding* stage (model/version/normalization) — pin and version it like any dependency.

---

## Level 4 — Retrieval: vector vs lexical vs hybrid

### A16. Dense vs sparse

| | Dense (vector) | Sparse (FTS/BM25) |
|---|---|---|
| Matches | meaning/paraphrase | exact terms |
| Wins on | "how do I make my DB faster" → perf docs | error code `E1234`, `CREATE PRIMARY INDEX` |
| Fails on | rare exact tokens, IDs, versions | synonyms, paraphrase |

**Key takeaway:** Dense finds meaning, sparse finds exact tokens — each fails exactly where the other succeeds, which is the whole argument for hybrid.

### A17. Why Ask AI went hybrid
Pure vector missed queries that hinge on **exact tokens** — API names, SQL++ keywords, error strings, version numbers — where paraphrase-based similarity underperforms lexical match. The doc notes the system "evolved from pure vector search to … hybrid."

**Key takeaway:** Docs queries are full of exact identifiers, so hybrid (vector + full-text) was needed to stop losing keyword-precise questions.

### A18. Combining incomparable score scales

| Method | How | Trade-off |
|---|---|---|
| RRF (Reciprocal Rank Fusion) | sum `1/(k+rank)` across lists; ignores raw scores | robust, scale-free, simple |
| Weighted score blend | `α·norm(cos) + (1-α)·norm(bm25)` | tunable but needs normalization + tuning |
| Custom heuristic | base + feature bonuses (Ask AI) | domain-tuned, more fragile |

**Key takeaway:** Cosine and BM25 aren't on the same scale — fuse by *rank* (RRF) for a robust default, or normalize + weight when you want tunable control.

### A19. Single-query hybrid + fallback

| Choice | Why |
|---|---|
| Both searches in ONE Couchbase query | one round-trip, one ranking pass, lower latency, engine-native |
| Fallback to pure vector if hybrid empty | full-text can zero-out on paraphrase-only queries; vector guarantees coverage |

**Key takeaway:** One engine-native query keeps the read path low-latency; the pure-vector fallback guarantees you never return *nothing* on a paraphrase-only query.

### A20. *(Failure mode)* Right doc retrieved but ranked #14 (below K=5)

| Lever | Effect |
|---|---|
| Add/tune re-ranking | promote the true match above noise |
| Raise retrieval width before re-rank | ensure #14 is in the candidate pool |
| Adjust hybrid weighting / add lexical | if it's an exact-term query vector buried |
| Revisit chunking | maybe the answer is split across chunks |

**Key takeaway:** "Retrieved but not in top-K" is a *ranking* problem — retrieve wider, then re-rank — not a reason to blame the embedding model first.

---

## Level 5 — Ranking & re-ranking

### A21. Why re-rank; retrieve-wide → rerank-narrow
Initial retrieval optimizes recall cheaply (ANN over millions); it's approximate and its scores are coarse. Re-ranking spends more compute on a *small shortlist* to maximize precision at the top.

```text
retrieve top ~20–100 (cheap, recall-oriented)  →  re-rank  →  keep top K=5 (precise)
```
**Key takeaway:** Retrieve wide and cheap for recall, then re-rank a shortlist for precision — you can't afford precise ranking over the whole corpus, only over candidates.

### A22. Critique Ask AI's heuristic re-ranker
Re-ranker = base score + length preference (favor medium chunks) + content-type bonuses (code/headings/structured).

| Smart | Fragile |
|---|---|
| Cheap, fast, no extra model call | Hand-tuned weights → brittle across corpora |
| Domain-aware (code/headings matter in docs) | Bonuses can override true relevance |
| Transparent/debuggable | No learning; needs ablation to justify each term |

**Key takeaway:** A heuristic re-ranker is cheap and transparent and often "good enough," but each bonus must earn its place via ablation or it's just tunable noise.

### A23. Heuristic vs cross-encoder re-ranker

| | Heuristic | Cross-encoder |
|---|---|---|
| Accuracy | decent | usually best (query+doc scored jointly) |
| Latency | ~0 | adds a model pass per candidate |
| Cost | ~0 | GPU/inference per candidate |
| Ops | simple | another model to serve/monitor |

**Key takeaway:** A cross-encoder buys top-end precision at real latency/cost — worth it when retrieval quality gates business value and you can bound the shortlist size.

### A24. Choosing K

| K too low | K too high |
|---|---|
| Answer-bearing chunk missed | Prompt cost/latency up |
| Under-grounded answers | "Lost in the middle" dilutes signal |
| — | More chance of contradictory context |

Ask AI uses **K=5**. Tune K on an eval set, not by feel.

**Key takeaway:** K balances grounding vs prompt cost and lost-in-the-middle; 3–8 is typical, and the right value is whatever your eval set says.

### A25. *(Failure mode)* Cross-encoder doubles p95 latency

| Mitigation | Effect |
|---|---|
| Shrink the shortlist re-ranked | fewer model passes |
| Smaller/distilled re-ranker | faster per pass |
| Cache re-rank by (query,doc) | skip repeats |
| Re-rank async / speculative | overlap with other work |
| Fall back to heuristic under load | graceful degradation |

**Key takeaway:** Keep cross-encoder quality but bound latency by re-ranking a *smaller* shortlist with a distilled model, caching, and degrading to heuristic under load.

---

## Level 6 — Query understanding

### A26. Why rephrase with chat history
Multi-turn queries are context-dependent; embeddings need a *self-contained* query.

```text
Turn 1: "How do I create a primary index in Capella?"
Turn 2: "and for a specific collection?"   ← "and for" is meaningless alone
Rephrase → "How do I create a primary index on a specific collection in Capella?"
```
**Key takeaway:** Follow-ups rely on pronouns/ellipsis; rephrasing into a self-contained query is what makes retrieval work in a conversation.

### A27. Lightweight rephrase, not a 2nd large call

| | Lightweight rephrase | Second large LLM call |
|---|---|---|
| Cost | low | ~doubles gen cost |
| Latency | small add | large add |
| Value | big retrieval-quality lift | diminishing |

Ask AI deliberately keeps rephrasing cheap "to keep cost and latency low."

**Key takeaway:** Query rephrasing is a high-ROI *small* call — spend a little to fix the query, don't burn a second big model on it.

### A28. Query expansion / HyDE / multi-query

| Technique | Idea | Helps when |
|---|---|---|
| Query expansion | add synonyms/related terms | vocabulary mismatch |
| HyDE | LLM drafts a hypothetical answer, embed *that* | query ≠ document phrasing |
| Multi-query | generate N paraphrases, retrieve each, merge | recall on hard/ambiguous queries |

All add latency/cost — justify with eval. *(Verify current best practices.)*

**Key takeaway:** These trade extra LLM calls for recall; reach for them only when eval shows a vocabulary/phrasing gap that plain hybrid can't close.

### A29. Rephrase × fallback × follow-ups
- A good rephrase reduces empty hybrid results (fewer fallbacks).
- Follow-ups ("and for the paid tier?") *must* be rephrased or they retrieve on meaningless fragments.
- Rephrase uses history but should not drag stale topic context into an unrelated new question.

**Key takeaway:** Rephrasing is what makes multi-turn RAG coherent, but it must incorporate *just enough* history — too much and a topic switch retrieves the old subject.

### A30. *(Failure mode)* Rephraser flips the intent

| Detect | Contain |
|---|---|
| Log original + rephrased; sample-judge for drift | Keep rephrase conservative (low temp, tight prompt) |
| Watch retrieval-empty / thumbs-down after rephrase | Fall back to original query on low retrieval score |
| Eval rephrase quality on a golden set | Show the interpreted question in UI for correction |

**Key takeaway:** A rephraser can silently change meaning — log both versions, eval it, and fall back to the raw query when the rephrase retrieves poorly.

---

## Level 7 — Generation & grounding

### A31. Prompt construction from K chunks
```text
System: role + "answer ONLY from the provided context; cite sources; if unknown, say so"
Context: [chunk 1 + url] ... [chunk K + url]   (delimit clearly; keep source ids)
User: <rephrased query>
```
Citations: carry each chunk's source URL (Ask AI enriches results with the public docs URL) and ask the model to reference them.

**Key takeaway:** Put behavior rules in the system prompt, delimit the K chunks with their source URLs in the context, and instruct grounded, cited, refuse-if-unknown answering.

### A32. Lost in the middle
LLMs attend most to the **start and end** of a long context; relevant text buried in the middle is under-used.

| Mitigation |
|---|
| Keep K small (less middle) |
| Order best chunks at the edges (top and bottom) |
| Shorter, denser chunks; re-rank so #1 is truly first |

**Key takeaway:** Because models under-weight the middle, keep K tight and place the strongest chunks at the beginning and end of the context block.

### A33. Enforcing grounding + "I don't know"

| Mechanism | Role |
|---|---|
| System instruction "answer only from context" | sets the contract |
| Low max retrieval score → refuse/hedge | avoids ungrounded answers |
| Faithfulness eval (offline + sampled online) | measures adherence |
| Cite-or-abstain prompting | forces traceability |

**Key takeaway:** Grounding is enforced by prompt contract *plus* a retrieval-confidence gate *plus* faithfulness eval — instructions alone won't stop a confident model.

### A34. Why stream (SSE)

| Streaming changes | How |
|---|---|
| Perceived latency | first token fast; user sees progress |
| Error handling | must handle mid-stream failure (partial answer) |
| Eval | score the *assembled* answer; also track time-to-first-token |
| UX | enables stop/interrupt |

Ask AI uses `CreateChatCompletionsStream` → SSE to CP-UI.

**Key takeaway:** Streaming trades a simple request/response for far better perceived latency, at the cost of handling partial/mid-stream failures and measuring time-to-first-token.

### A35. *(Failure mode)* Perfect retrieval, wrong answer — generation causes

| Cause | Signal |
|---|---|
| Prompt ignores/underweights context | faithfulness low despite good context |
| Lost in the middle | fails as K/context grows |
| Model over-relies on parametric memory | answer contradicts provided chunk |

**Key takeaway:** When the right chunk is #1 but the answer is wrong, it's generation — prompt contract, chunk ordering, or the model trusting its memory over your context.

---

## Level 8 — Architect / Staff

### A36. Scaling the two paths independently

| | Write path | Read path |
|---|---|---|
| Bottleneck | embedding throughput, corpus size | retrieval + LLM latency, QPS |
| Scale by | parallel workers (Ask AI: goroutines), batch | replicas, ANN tuning, caching, K/model tuning |
| Elasticity | scheduled/bursty | continuous |

Ask AI: 10 goroutines cut the job 5–6h → ~20 min.

**Key takeaway:** Write scales with *corpus* (parallel batch embedding); read scales with *QPS* (replicas, ANN/index tuning, caching) — never conflate their capacity plans.

### A37. Freshness vs cost

| | Scheduled full re-embed (weekly) | Incremental / event-driven |
|---|---|---|
| Freshness | up to a week stale | near-real-time |
| Cost | re-embeds unchanged docs (wasteful) | embeds only deltas |
| Complexity | simple cron | change-detection pipeline |

**Key takeaway:** Batch re-embed is simple and fine for slow-changing docs; go incremental only when staleness hurts enough to justify a change-data pipeline.

### A38. Multi-tenant RAG

| Concern | Mechanism |
|---|---|
| Data isolation | per-tenant scope/collection or filter; never cross-leak retrieval |
| Fair usage | per-tenant rate limits (Ask AI: calls/min, requests/day, tokens/month; free vs paid) |
| Cost attribution | track tokens per tenant/user (iQ requires Tenant+User ID) |
| Noisy neighbor | limits + isolation prevent one tenant starving others |

**Key takeaway:** Multi-tenant RAG needs hard data isolation *and* per-tenant rate/cost limits — Ask AI enforces both via iQ (Tenant+User ID) and configurable call/request/token caps.

### A39. When hybrid + re-ranking isn't worth it

| Drop to simpler when |
|---|
| Corpus tiny/static → long-context or pure vector suffices |
| Queries are pure semantic (no exact-token need) → FTS adds little |
| Latency/cost budget can't absorb re-ranking |
| Eval shows hybrid/re-rank don't move the metric |

**Key takeaway:** Complexity must pay for itself on your eval set — if hybrid or re-ranking doesn't move retrieval quality, it's just latency and ops burden.

### A40. *(Failure mode)* 2 AM org-wide quality drop, no deploy

| Layer | Check | Fix |
|---|---|---|
| Retrieval | re-embed job status? index healthy? empty results ↑? | repair/rollback index version |
| Generation | provider model version changed? refusal/hallucination ↑? | pin/roll back model; failover provider |
| Infra | latency/error spikes? rate-limit rejections? | scale, raise limits, shed load |

**Key takeaway:** Triage by path — retrieval (index/embed job), generation (provider/model drift), infra (latency/limits) — which is exactly why version pinning + per-stage telemetry exist.

---

## Bonus

### AB1. Evaluating so a change is a measurable win
| Split eval by path |
|---|
| Retrieval: context recall/precision, hit@K |
| Generation: faithfulness, answer relevancy |
| Gate chunking/K/model changes on a golden set in CI |

**Key takeaway:** Measure retrieval and generation separately on a golden set so a chunking or K tweak is a number, not a vibe — see [`../llm-eval-and-observability/`](../llm-eval-and-observability/).

### AB2. Where the vector-store choice bites
| Bite point | Why it matters |
|---|---|
| Native hybrid in one query | Couchbase FTS does it; pgvector/Pinecone may need two systems + fusion |
| Ops model | managed (Pinecone) vs in-your-DB (pgvector) vs in-your-data-platform (Couchbase) |
| Filtering + freshness + scale | metadata filters, upsert latency, index rebuild cost differ |

**Key takeaway:** The store dictates whether hybrid is one query or two systems, and its ops model sets your freshness/scale/cost ceiling — see [`../vector-databases/`](../vector-databases/).

### AB3. Cheapest change that most improves retrieval
| Usual highest-ROI moves |
|---|
| Fix chunking (structure-aware + right size) |
| Add query rephrasing / self-contained queries |
| Add lexical to a pure-vector system (go hybrid) |
| Enrich chunks with titles/headings |

**Key takeaway:** In practice the biggest cheap wins are chunking and query rephrasing — fix the inputs to retrieval before reaching for fancier models.

### AB4. Cut RAG cost 50% without wrecking quality
| Move | Saves |
|---|---|
| Semantic cache for repeat/similar queries | whole pipeline on cache hits |
| Smaller embedding + cheaper/smaller gen model where eval allows | per-call cost |
| Lower K / shorter chunks | prompt tokens |
| Incremental re-embed (stop re-embedding unchanged docs) | write-path compute |

**Key takeaway:** Attack cost in priority order — cache hits, right-sized models, tighter K/prompt, incremental indexing — validating each against the eval set so quality holds.

---

## ⚡ Quick Revision Cheatsheet

### Scale numbers (Ask AI, from the design doc — planning figures to verify)
- Corpus: **2,667 docs → 7,597 chunks**, chunk **≤1,000 tokens**.
- Embeddings: **text-embedding-3-small, 1,536-dim, cosine**, index optimized for **recall**.
- Retrieval width: top **K = 5** after custom re-rank.
- Re-embed job: **5–6 h synchronous → ~20 min with 10 goroutines** (weekly cron via CP-Scheduler).
- Rate limits (iQ): free **100 calls/60s · 2,000 req/day · 500K tokens/mo**; paid **2,000 req/day · 2M tokens/mo**.

### Key technology choices
| Component | Choice | Why |
|---|---|---|
| Corpus | AWS S3 (`docsbot-data`) | batch-readable HTML mirror of docs |
| Indexer | CP-Jobs cron (goroutine-parallel) | freshness w/o streaming infra |
| Embeddings | OpenAI text-embedding-3-small (1536-d) | cheap, sufficient |
| Store + index | Couchbase Capella FTS (vector+text) | native hybrid in one query |
| Retrieval | hybrid + pure-vector fallback | meaning + exact terms, guaranteed coverage |
| Re-rank | custom heuristic (base+length+content-type) | cheap, domain-aware |
| Query understanding | lightweight context-aware rephrase | self-contained query, low cost |
| Gen | GPT-4o via iQ, SSE stream | quality + perceived latency |

### Canonical trade-offs to memorize
- **Write vs read path:** throughput/freshness vs latency/precision.
- **RAG vs fine-tune vs long-context:** knowledge vs behavior vs small-static.
- **Dense vs sparse vs hybrid:** meaning vs exact terms vs both.
- **Heuristic vs cross-encoder re-rank:** cheap/transparent vs precise/expensive.
- **Weekly re-embed vs incremental:** simple vs fresh.
- **K low vs high:** under-grounded vs cost + lost-in-the-middle.

### Common interview mistakes to avoid
- Treating RAG as one pipeline instead of two paths with opposite constraints.
- Defaulting to pure vector; forgetting exact-token queries need lexical.
- Mutating the live index in place (no versioning) → broken-window re-embeds.
- Mixing query and doc embeddings from different models/spaces.
- Ignoring chunking (the highest-leverage, cheapest lever).
- Adding a cross-encoder without bounding shortlist/latency.
- No retrieval-vs-generation attribution when debugging a bad answer.
- Stuffing huge K and hitting "lost in the middle."
