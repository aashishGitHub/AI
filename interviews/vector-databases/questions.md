# Vector Databases — Interview Questions

> Attempt all questions before reading [`answers.md`](answers.md) · work level-by-level · speak your answers aloud.
> Central split to keep in mind: the **index** (how you buy recall with latency and memory) and the
> **operating model** (where vectors live relative to your other data) are *two independent choices*. Most
> "pgvector vs Pinecone" arguments confuse them. Every question below sits on one side or bridges them.

---

## Level 1 — Fundamentals
*Goal: say what a vector index actually does, and why "approximate" is the whole point.*

**Q1.** What is an embedding, and what does "distance" between two embeddings actually mean? Why must the write path and read path use the same model?

**Q2.** Why do vector databases use *approximate* nearest-neighbour (ANN) search instead of exact search? What is the cost of exact search over 10M vectors, and what do you gain by approximating?

**Q3.** Define **recall@K** for a vector index. Why is it the metric that matters, and why is it the one teams most often fail to measure?

**Q4.** Name the three distance metrics in common use (cosine, inner product, L2). How do you decide which to use, and what happens if you pick one the embedding model wasn't trained for?

**Q5.** Is a "vector database" a distinct category of database, or a feature? Defend your answer.

**Q6.** *(Failure mode)* Your retrieval quality silently degrades after a deploy. Nothing errors, latency is unchanged, and every query returns K results. Name three causes and how you would tell them apart.

---

## Level 2 — Index internals
*Goal: explain HNSW and IVF mechanically, and name the knob that trades recall for latency in each.*

**Q7.** Explain **HNSW** to someone who knows graphs but not ANN. What are the layers for, and why is search logarithmic-ish rather than linear?

**Q8.** Name HNSW's three knobs (`m`, `ef_construction`, `ef_search`). Which are build-time, which is query-time, and why does that distinction matter operationally?

**Q9.** Explain **IVF** (inverted file / cluster-based) search. What are `lists`/`nlist` and `probes`/`nprobe`, and what does IVF require before you can build the index that HNSW does not?

**Q10.** Compare HNSW vs IVFFlat on: build time, query latency, memory footprint, recall at a fixed latency, and behaviour under heavy updates. When would you actually choose IVF?

**Q11.** What is **quantization** (PQ, scalar, binary)? What does it buy, what does it cost, and what technique repairs the damage?

**Q12.** *(Failure mode)* Your HNSW index has excellent recall in staging and poor recall in production, with the same code and same `ef_search`. What differs, and how do you confirm it?

---

## Level 3 — Filtering (where recall silently dies)
*Goal: reason about pre-filter vs post-filter, and why filtered ANN is genuinely hard.*

**Q13.** Explain **pre-filtering** vs **post-filtering** for a query like "find similar docs *where tenant_id = 42*". Describe the failure mode of each.

**Q14.** Why can't you just apply a `WHERE` clause to an HNSW graph search the way you would to a B-tree scan? What breaks?

**Q15.** A filter matches 0.1% of your corpus. Which strategy wins, and why does the *selectivity* of the filter change the right answer?

**Q16.** How do you support **multi-tenancy** in a vector store? Compare: one shared index with a tenant filter, one index per tenant, and namespace/partition-based isolation.

**Q17.** *(Failure mode)* After adding a metadata filter, a query that used to return 10 results now returns 3, intermittently. Explain the mechanism and name two fixes.

---

## Level 4 — The operating model
*Goal: choose where vectors live, from data and consistency needs — not from benchmarks.*

**Q18.** Compare the three operating models: vectors **in your RDBMS** (pgvector), in a **dedicated managed service** (Pinecone), and in your **data platform** alongside the documents (Couchbase). What does each buy and cost?

**Q19.** What is the **dual-write / sync problem**, and which operating model avoids it? Describe what goes wrong when the source of truth and the vector store diverge.

**Q20.** When is pgvector the *right* answer, and at roughly what point does it stop being? Name the specific pressures that push you off it.

**Q21.** Couchbase 8.0 offers three vector index types (Hyperscale, Composite, Search). Explain when each is correct — and why this is a *per-query-shape* decision rather than a per-project one.

**Q22.** Your vectors must be filtered by a value that lives in Postgres, but your vectors live in Pinecone. Describe three ways to resolve this and the trade-off of each.

**Q23.** *(Failure mode)* Your managed vector service has a regional outage. What does your RAG feature do? Design the degradation path.

---

## Level 5 — Hybrid search & ranking
*Goal: combine lexical and semantic retrieval, and fix ordering before spending context tokens.*

**Q24.** Why is pure vector search insufficient for queries containing error codes, SKUs, product names or exact identifiers? What does keyword/BM25 search catch that embeddings blur?

**Q25.** Explain **Reciprocal Rank Fusion (RRF)** and why it is the common default for merging two ranked lists. What is the alternative and why is it harder to operate?

**Q26.** What does a **cross-encoder reranker** do that the ANN index cannot? Why over-fetch N ≫ K and rerank down, rather than just asking the index for K?

**Q27.** You have a latency budget of 300ms end-to-end for retrieval. Allocate it across embedding, ANN search, filtering, and reranking, and say what you cut first under pressure.

**Q28.** *(Failure mode)* Adding a reranker improved offline relevance metrics but users complain the assistant "got slower and no better". Diagnose.

---

## Level 6 — Operations & lifecycle
*Goal: run this thing for a year, including the day the embedding model changes.*

**Q29.** Your embedding model is upgraded (new dims, new vector space). Describe a **zero-downtime re-embedding migration** for 50M vectors.

**Q30.** How do you handle **deletes and updates** in an HNSW graph? Why is deletion harder than insertion, and what is a tombstone/compaction strategy?

**Q31.** How do you capacity-plan memory for a vector index? Show the arithmetic for 10M vectors × 1536 dims × float32, and then say how quantization changes it.

**Q32.** What do you monitor in production for a vector store? Name metrics that would catch a *recall* regression, not just a latency one.

**Q33.** How do you back up and restore a vector index? Do you back up the index or rebuild it, and why?

**Q34.** *(Failure mode)* Index build for a nightly refresh now takes 9 hours and overruns into business hours. Give three levers, ordered by what you would try first.

---

## Level 7 — Applying it to a RAG system
*Goal: put the whole thing behind the Ask AI–shaped system and defend each parameter.*

**Q35.** Walk the full retrieval path for a documentation assistant, from user question to the K chunks handed to the LLM. Name every place recall can be lost.

**Q36.** How do you choose **K**? What is the cost of K too large, and of K too small — and how does the LLM's context window and the "lost in the middle" effect factor in?

**Q37.** How does **chunking strategy** interact with vector search quality? Why can a perfect index still retrieve useless context?

**Q38.** How would you *measure* whether your retrieval is good, offline? Design the golden dataset and the metrics. (Cross-link: [`../llm-eval-and-observability/`](../llm-eval-and-observability/).)

**Q39.** Separate a **retrieval failure** from a **generation failure** given only a bad answer. What do you instrument to tell them apart?

**Q40.** *(Failure mode)* Users report the assistant "doesn't know" about a document that is definitely indexed. Give your debugging order, most likely cause first.

---

## Level 8 — Architect / Staff
*Goal: own the choice across teams and years, including when the premise is wrong.*

**Q41.** Argue the case *against* adopting a dedicated vector database at a company already running Postgres. Then argue the case for. What evidence would settle it?

**Q42.** How do you make the vector store **swappable**? What is the right abstraction boundary, and what leaks through it no matter how hard you try?

**Q43.** Model the cost of a RAG retrieval layer at 1M queries/month across the three operating models. Which cost dominates, and which is most likely to surprise you?

**Q44.** When is vector search the **wrong tool** entirely? Name three problems where teams reach for embeddings and shouldn't.

**Q45.** How do you handle **GDPR deletion** ("delete everything about this user") when their data is baked into an ANN index and possibly into a fine-tuned model?

**Q46.** *(Failure mode)* Recall@10 has degraded 15% over six months with no deploys, no config changes, and no infrastructure changes. What happened?

---

## Bonus — questions a senior raises unprompted

**QB1.** "What is our recall, and how do we know?" — how would you establish a brute-force ground-truth baseline without it costing a fortune?

**QB2.** "What happens the day the embedding provider deprecates this model?" — what is the plan, and what does it cost?

**QB3.** "Are we paying to store vectors nobody ever retrieves?" — how would you find out, and what would you do about it?

**QB4.** "Who owns the corpus?" — when the index is stale, whose pager fires, and what is the freshness SLA?

**QB5.** "Is the embedding model leaking anything?" — can an attacker reconstruct source text from stored vectors, and does that change where they may live?
