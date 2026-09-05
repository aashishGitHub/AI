# System Design: Vector Databases (RAG retrieval, semantic search, recommendations)

> **Target:** engineers who can design a web system and now need to defend a *retrieval* design — index type,
> filtering strategy, and where the vectors live — under interview pressure.
> **Style:** interview-grill format — question first, then defended choices.

---

## How to Use This Guide

1. **Start with [`simple-diagram.md`](simple-diagram.md).** Two diagrams: the bare mental model, then the same
   flow with real tech named. Do not skip it — everything else assumes the central split it states.
2. **Attempt [`questions.md`](questions.md) cold.** 46 questions across 8 levels plus 5 bonus. Speak the
   answers aloud before reading anything. Being unable to answer is the point; that is the diagnostic.
3. **Check [`answers.md`](answers.md).** One answer per question, each with a comparison table or code, each
   ending in a **Key takeaway**. Ends with a ⚡ cheatsheet for the night before.
4. **Whiteboard from [`diagrams.md`](diagrams.md).** 12 Mermaid diagrams; Diagram 1 is the central split. Each
   names the questions it serves and what the interviewer is actually checking.
5. **Go deep with [`deep-dive.md`](deep-dive.md).** 🟢→🟡→🔴 tiers, quantified failure modes, and the staff-level
   material: privacy, GDPR, swappability, and when vector search is the wrong tool.

---

## Learning Path

| Level | Topic | You'll Learn |
|---|---|---|
| 1 | Fundamentals | What an embedding is, why search is *approximate*, and why **recall@K** is the metric nobody measures |
| 2 | Index internals | HNSW vs IVF mechanically; which knob trades recall for latency, and which requires a rebuild |
| 3 | Filtering | Pre-filter vs post-filter, why filtered ANN is genuinely hard, and multi-tenancy |
| 4 | Operating model | pgvector vs managed service vs data platform — and the dual-write tax |
| 5 | Hybrid search & ranking | Why vectors miss error codes; RRF; bi-encoder vs cross-encoder reranking |
| 6 | Operations & lifecycle | Memory arithmetic, deletes and compaction, monitoring, and the embedding-model migration |
| 7 | Applying it to RAG | The full retrieval path, choosing K, chunking, and separating retrieval from generation failures |
| 8 | Architect / Staff | Cost modelling, swappability, GDPR, privacy, and when the premise is wrong |

---

## Files

| File | Purpose |
|---|---|
| [`simple-diagram.md`](simple-diagram.md) | **▶ Start here.** Bare mental model + detailed version with real tech |
| [`questions.md`](questions.md) | 46 leveled questions + 5 bonus; one failure-mode question per level |
| [`answers.md`](answers.md) | One answer per question, each with a table or code + Key takeaway; ⚡ cheatsheet |
| [`diagrams.md`](diagrams.md) | 12 interview-ready Mermaid diagrams mapped to question numbers |
| [`deep-dive.md`](deep-dive.md) | 🟢🟡🔴 depth tiers, production failure modes, staff-level concerns |
| [`conducive-sentences.md`](conducive-sentences.md) | Plain-English prose retelling, for revision without tables |

---

## Problem Statement

> Design the retrieval layer for a documentation assistant. Users ask natural-language questions; the system
> must find the handful of most relevant passages from a large corpus and hand them to an LLM, fast enough to
> stream an answer, and correctly enough that the LLM is not guessing.

**Key Constraints**

- **Corpus:** ~10M chunks, 1536-dimensional embeddings, growing ~10%/quarter.
- **Latency:** retrieval must complete in **≤300ms p95**, inside a ~2s end-to-end answer budget.
- **Quality:** **recall@10 ≥ 0.95** measured against exact brute-force search — and measured on a schedule,
  not once.
- **Multi-tenancy:** every query is filtered by `tenant_id`; tenants range from tiny to very large.
- **Freshness:** a published document must be retrievable within **5 minutes**.
- **Hybrid:** queries contain error codes, SKUs and version strings, so lexical matching cannot be dropped.
- **Cost:** the memory footprint of the index is the dominant line item — see the arithmetic in
  [`answers.md`](answers.md) A31.
- **Durability:** vectors are derived data and can be rebuilt, *provided* the embedding model version is
  recorded alongside them.

---

## How a Senior Engineer Thinks About This

The first thing a senior engineer does is refuse the question as asked. "Which vector database should we use?"
is two independent decisions wearing one costume: **the index** (how much recall you sell for latency and
memory) and **the operating model** (where vectors live relative to the rest of your data). The index question
is a tuning exercise you can redo in any engine in an afternoon. The operating model question is about joins,
consistency, ops and data perimeter — it is expensive to reverse, and it should be decided first, from your
data topology rather than from a benchmark. Most "pgvector vs Pinecone" arguments are conducted entirely on
the first axis while the consequences land entirely on the second.

The second thing they do is name the uncomfortable property of the whole field: **ANN search has no error
message.** A badly tuned index returns exactly K results, with confident-looking scores, at normal latency —
identical, from the outside, to a perfect one. Latency regressions page you at 2am; recall regressions are
found by a customer three months later, if at all. This reframes the design conversation from "how fast is
it" to "what is our recall, at our corpus size, under our real filters, and who is measuring it?" The
follow-through is unglamorous and cheap: sample ~1,000 representative queries, brute-force them offline to
build a ground-truth fixture, and diff against it nightly. Teams that can produce that number are operating a
retrieval system; teams that cannot are hoping.

The third insight is that **filtering is the hard part, and it is where recall dies silently.** Everyone
learns HNSW; far fewer can explain what happens when you add `WHERE tenant_id = 42`. Post-filtering starves
the result set — you ask for 10 and get 3, non-deterministically. Pre-filtering severs the graph's stepping
stones, so the walk cannot reach the region containing the right answer, and you get plausible but wrong
neighbours. The deciding variable is **selectivity**, and it inverts the expected answer at both ends: when a
filter matches 0.1% of a 10M corpus, the correct move is to abandon the index entirely and brute-force the
resulting 10K vectors — exact, fast, 100% recall. Recognising when *not* to use the clever structure is a
stronger signal than knowing how it works. Multi-tenancy is the same problem in disguise, and the senior
answer is usually to stop filtering and start partitioning: an index per tenant turns a hard recall problem
into an easy routing problem.

Finally, they think in years rather than in benchmarks. The embedding model **will** be deprecated, and
because a new model means a new vector space, there is no in-place upgrade — only a versioned dual-index
migration with dual writes, a full corpus re-embed, a shadow-read comparison, and double storage for the
duration. Deletes leave tombstones that quietly erode recall until compaction runs. Corpus growth alone
degrades recall at a fixed `ef_search`, which is why "nothing changed and quality dropped" is not a paradox.
And the questions with the longest half-life are not about throughput at all: embeddings are not
anonymization, so vectors inherit the residency and access rules of their source text — which means personal
data belongs in the retrievable layer, where it can be deleted, and never in fine-tuned weights, where it
cannot.
