# System Design: RAG & Hybrid Search (docs chatbots, e.g. Couchbase Ask AI)

> **For:** Senior/Staff engineers designing retrieval-augmented systems over a large, changing corpus.
> **Style:** Interview-grill format — question first, then defended choices.

Second topic of the [knowledge track](../ROADMAP.md). Distills your team's shipped **Ask AI** architecture into interview-ready system design, and closes part of **gap #2** (RAG). Pairs with [`../vector-databases/`](../vector-databases/) (the store) and [`../llm-eval-and-observability/`](../llm-eval-and-observability/) (how you prove it works).

---

## How to Use This Guide

1. Read [`simple-diagram.md`](simple-diagram.md) first — get the central split (write path vs read path) in your head.
2. Attempt [`questions.md`](questions.md) **cold**, level by level, out loud.
3. Check yourself against [`answers.md`](answers.md) — each answer has a table or code and a one-line **Key takeaway**.
4. Whiteboard from [`diagrams.md`](diagrams.md) — practice Diagram 1 (the split), then 3 (read sequence) and 7 (zero-downtime re-embed).
5. Go deep with [`deep-dive.md`](deep-dive.md) — 🟢🟡🔴 tiers, failure modes, the Ask AI grounding.
6. Prose retelling: [`conducive-sentences.md`](conducive-sentences.md).
7. Then build it in the hands-on track: [`../../docs/notes/README.md`](../../docs/notes/README.md) (Wk2: hybrid RAG in Couchbase FTS + the pgvector/Pinecone/Couchbase write-up).

---

## Learning Path

| Level | Topic | You'll learn |
|---|---|---|
| L1 | Fundamentals | What RAG is; RAG vs fine-tune vs long-context; the two paths |
| L2 | Indexing / write path | Clean → chunk → embed → version; safe re-embed |
| L3 | Embeddings | Similarity, dims, what to embed, model swaps |
| L4 | Retrieval | Dense vs sparse vs hybrid; fusion; fallback |
| L5 | Ranking & re-ranking | Retrieve-wide→rerank-narrow; heuristic vs cross-encoder; K |
| L6 | Query understanding | Rephrasing, expansion, HyDE, multi-query |
| L7 | Generation & grounding | Prompt packing, lost-in-the-middle, citations, streaming |
| L8 | Architect/Staff | Scale each path, freshness, multitenancy, when to stop |

---

## Files

| File | Purpose | Start here? |
|---|---|---|
| [`simple-diagram.md`](simple-diagram.md) | Write/read split + concrete Ask AI tech | ⭐ start |
| [`questions.md`](questions.md) | L1→L8 grill + failure-mode Qs + bonus | attempt cold |
| [`answers.md`](answers.md) | One answer per Q (table/code + Key takeaway) + cheat sheet | check |
| [`diagrams.md`](diagrams.md) | 9 interview-ready Mermaid diagrams mapped to Qs | whiteboard |
| [`deep-dive.md`](deep-dive.md) | 🟢🟡🔴 depth, failure modes, Ask AI grounding | go deep |
| [`conducive-sentences.md`](conducive-sentences.md) | Plain-English prose retelling | optional |

---

## Problem Statement

> Design a RAG system that answers questions over a large, frequently-updated documentation corpus (concretely: Couchbase **Ask AI** over the public docs). It must retrieve accurately across both *semantic* and *exact-token* queries, stay fresh as docs change *without serving stale/garbage mid-update*, stream answers with low perceived latency, and stay affordable per tenant.

**Key constraints (from the Ask AI design doc; numbers are planning figures to verify):**
- **Corpus/scale:** ~2,667 docs → ~7,597 chunks (≤1,000 tokens each); embeddings 1,536-dim, cosine, index optimized for recall.
- **Retrieval:** hybrid (vector + full-text) in a single Couchbase query, pure-vector fallback, custom re-rank, top **K = 5**.
- **Freshness:** weekly re-embed (CP-Jobs cron); versioned/backed-up embeddings, validated before promotion.
- **Latency:** streamed answers (SSE) via GPT-4o through the iQ Backend abstraction.
- **Multitenancy/cost:** per-tenant rate limits (free vs paid) on calls/min, requests/day, tokens/month.

---

## How a Senior Engineer Thinks About This

**Lead with the two paths, not the pipeline.** The opening move is: *a RAG system is a write/index path and a read/query path that meet at the store, with opposite constraints — the write path is throughput-bound and can be slow (Ask AI re-embeds weekly), the read path is latency-bound because a user is watching tokens stream.* This split is not just narration; it's the coordinate system you debug in. Every quality complaint resolves to a write-path fault (bad chunk, stale embedding), a read-path retrieval fault (right chunk not in top-K), or a generation fault (right chunk, wrong answer). A candidate who separates these localizes bugs in one sentence; one who treats RAG as a blur guesses.

**The two insights that separate senior from junior.** First, **hybrid exists because documentation is full of exact tokens** — API names, SQL++ keywords, error codes, versions — and pure vector search, which matches paraphrase, quietly loses those. Ask AI's evolution from pure-vector to hybrid (vector + full-text in one Couchbase query, with a pure-vector fallback) is the concrete story to tell, along with *how* you fuse incomparable score scales (RRF on rank, or normalized weighting). Second, **freshness is a versioning problem, not a speed problem**: the failure that takes a system down is mutating the live index in place and half-failing, so the senior pattern is always build-a-new-version-beside, validate, then atomically flip — which is exactly what the design doc's "backup old embeddings / validate new ones" requirements encode. Chunking sits underneath both as the highest-leverage, cheapest quality lever most teams underinvest in.

**Staff-level is scaling and knowing when to stop.** You scale the write path with parallelism and the read path with replicas/caching/ANN-tuning, and you never conflate their capacity plans. You make freshness-vs-cost an explicit choice (weekly full re-embed vs incremental). You enforce hard tenant isolation plus per-tenant rate and token limits (Ask AI threads Tenant+User ID through iQ for exactly this). And — the mark of seniority — you can say when hybrid and re-ranking *aren't* worth it: a tiny static corpus may want long-context instead, a purely semantic query mix may not need full-text, and any complexity that doesn't move the eval-set metric is just latency and ops cost. Which is why this topic is inseparable from [`../llm-eval-and-observability/`](../llm-eval-and-observability/): you only earn the right to add a re-ranker or bump K by showing the number moved.
