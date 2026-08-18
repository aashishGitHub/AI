# RAG & Hybrid Search — Interview Questions

> Attempt all questions before reading [`answers.md`](answers.md) · work level-by-level · speak your answers aloud.
> Central split to keep in mind: **index/write path** (crawl→clean→chunk→embed→version; async, batch, throughput-bound) vs **query/read path** (rephrase→embed→hybrid search→re-rank→top-K→stream; latency-bound). Every question sits on one path or bridges them.
> Concrete anchor: Couchbase **Ask AI** — see [`../../docs/Ask AI design document.md`](../../docs/Ask%20AI%20design%20document.md).

---

## Level 1 — Fundamentals
*Goal: say what RAG is, when it's the right tool, and name the two paths.*

**Q1.** What is Retrieval-Augmented Generation, and what problem does it solve that a bare LLM call does not?

**Q2.** RAG vs fine-tuning vs stuffing everything into a long context window — when do you reach for each?

**Q3.** Name the two paths of a RAG system and their opposite performance characteristics. Why is separating them the key design move?

**Q4.** Walk the end-to-end happy path of Ask AI from "user types a question" to "tokens stream back." Name each stage.

**Q5.** *(Failure mode)* The LLM answers confidently but the fact isn't in your docs at all. Is that a RAG failure? What *should* the system do?

---

## Level 2 — Indexing / write path
*Goal: turn a messy corpus into clean, chunked, embedded, versioned vectors.*

**Q6.** Walk the write path stages (fetch → clean → chunk → embed → store). What does each stage cost you if you do it badly?

**Q7.** Chunking is the highest-leverage decision. What are the strategies (fixed-size, overlap, semantic/structural) and how do you pick a size?

**Q8.** Why does Ask AI strip headers/footers/sidebars before chunking, and cap chunks at ~1,000 tokens? What breaks if you don't clean?

**Q9.** The corpus changes. How do you keep the index fresh, and how do you update embeddings *without downtime or serving stale/garbage results mid-run*?

**Q10.** *(Failure mode)* A weekly re-embed job half-fails (embeds 60% of chunks, dies). What do users experience, and what makes this safe vs catastrophic?

---

## Level 3 — Embeddings
*Goal: reason about the vector representation and its knobs.*

**Q11.** What is an embedding, and what does "similarity" actually measure? Why cosine (Ask AI uses `dims: 1536`, `similarity: cosine`)?

**Q12.** How do you choose an embedding model? What trade-offs move with dimensionality (1536 vs smaller/larger)?

**Q13.** What text do you actually embed — the raw chunk, chunk+title, a summary? Why does the *query* and the *document* need to land in the same space?

**Q14.** If you swap embedding models, why must you re-embed the *entire* corpus, and how do you migrate without a broken window?

**Q15.** *(Failure mode)* Retrieval quality silently drops after a model/library upgrade with no code change to retrieval. What happened?

---

## Level 4 — Retrieval: vector vs lexical vs hybrid
*Goal: defend hybrid search and know how the two components combine.*

**Q16.** Dense (vector) vs sparse (keyword/BM25/FTS) retrieval — what does each catch that the other misses? Give a query that fails each.

**Q17.** Why does Ask AI run *hybrid* (vector + full-text) instead of pure vector? What class of query forced this evolution?

**Q18.** How do you combine two result lists with incomparable scores (cosine vs BM25)? Explain a fusion approach (e.g. RRF) vs weighted score blending.

**Q19.** Ask AI executes both searches *simultaneously in a single Couchbase query* and falls back to pure vector if hybrid returns nothing. Why single-query, and why the fallback?

**Q20.** *(Failure mode)* Hybrid returns the right document but ranked #14, below K. What levers fix "it's retrieved but not in top-K"?

---

## Level 5 — Ranking & re-ranking
*Goal: get the best K into the prompt; know heuristic vs model re-rankers.*

**Q21.** Why re-rank at all after retrieval? What is the retrieve-wide-then-rerank-narrow pattern and why is it efficient?

**Q22.** Ask AI's re-ranker = base score + length preference (favor medium chunks) + content-type bonuses (code/headings). Critique it: what's smart, what's fragile?

**Q23.** Heuristic re-ranker vs a cross-encoder re-ranker — accuracy, latency, and cost trade-offs. When is a cross-encoder worth it?

**Q24.** How do you choose K? What goes wrong at K too low vs K too high (cost, latency, lost-in-the-middle)?

**Q25.** *(Failure mode)* You add a cross-encoder re-ranker and p95 latency doubles. How do you keep the quality but bound the latency?

---

## Level 6 — Query understanding
*Goal: fix the query before retrieval; pay for it wisely.*

**Q26.** Why does Ask AI rephrase the query using chat history before embedding it? Give a multi-turn example where this is mandatory.

**Q27.** The rephrase is a *lightweight* LLM call, deliberately not a second large one. What's the cost/latency/quality reasoning?

**Q28.** Query expansion, HyDE (hypothetical document embeddings), and multi-query — what are they and when do they help retrieval?

**Q29.** How does rephrasing interact with the fallback and with follow-up questions like "and for the paid tier?"

**Q30.** *(Failure mode)* The rephraser "corrects" a query into the wrong intent and retrieval goes off the rails. How do you detect and contain this?

---

## Level 7 — Generation & grounding
*Goal: turn retrieved context into a faithful, streamed answer.*

**Q31.** How do you construct the prompt from K chunks? What belongs in the system prompt vs the context block, and how do you handle citations?

**Q32.** What is "lost in the middle," and how does it change how you order the K chunks in the prompt?

**Q33.** How do you enforce grounding (answer only from context) and handle "I don't know" when context is weak?

**Q34.** Why stream the response (SSE), and what does streaming change about latency perception, error handling, and eval?

**Q35.** *(Failure mode)* Retrieval is perfect (right chunk is #1) but the answer is still wrong or hallucinated. Name three generation-side causes.

---

## Level 8 — Architect / Staff
*Goal: scale both paths, own freshness/cost/multitenancy, know the limits.*

**Q36.** Scale the two paths independently: what's the bottleneck on the write path vs the read path, and how does each scale?

**Q37.** Freshness vs cost: weekly re-embedding (Ask AI) vs incremental/event-driven indexing. When is each right?

**Q38.** Multi-tenant RAG: how do you isolate tenants' data, rate limits, and cost (Ask AI enforces per-tenant call/request/token limits)? What are the risks?

**Q39.** When is hybrid + re-ranking *not* worth the complexity? What would make you drop back to pure vector, or drop RAG entirely?

**Q40.** *(Failure mode)* Answer quality degrades org-wide at 2 AM with no deploy. Walk retrieval-side vs generation-side vs infra-side triage.

---

## Bonus — questions a senior raises unprompted

**QB1.** How do you *evaluate* this system so a chunking or K change is a measurable win, not a vibe? (Cross-link: [`../llm-eval-and-observability/`](../llm-eval-and-observability/).)

**QB2.** Where does the vector-store choice (pgvector vs Pinecone vs Couchbase FTS) actually bite this design? (Cross-link: [`../vector-databases/`](../vector-databases/).)

**QB3.** What's the single cheapest change that most improves retrieval quality in a typical RAG system, in your experience?

**QB4.** If you had to cut RAG cost by 50% without wrecking quality, what are your first three moves?
