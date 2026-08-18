# RAG & Hybrid Search — Simple Diagram

> Start here. Two diagrams: the bare write/read split first, then the same flow with the concrete Ask AI tech.

---

## 1. Simple mental model

The whole system is **two paths that meet at the vector store.** The write path is *async, batch, throughput-bound* (run it weekly, nobody's waiting). The read path is *synchronous, latency-bound* (a user is watching tokens appear).

```mermaid
flowchart LR
    subgraph WRITE["WRITE / INDEX path — async, batch"]
        direction TB
        DOCS[("Docs corpus")] --> CLEAN["Clean<br/>strip nav/boilerplate"]
        CLEAN --> CHUNK["Chunk<br/>split into passages"]
        CHUNK --> EMB1["Embed each chunk"]
    end

    STORE[("Vector store<br/>+ full-text index")]
    EMB1 --> STORE

    subgraph READ["READ / QUERY path — sync, latency-bound"]
        direction TB
        Q(["User query"]) --> REPH["Rephrase<br/>resolve this/it via history"]
        REPH --> EMB2["Embed query"]
        EMB2 --> HYB["Hybrid search<br/>vector + full-text"]
        HYB --> RANK["Re-rank<br/>pick top K"]
        RANK --> LLM["LLM answer<br/>streamed"]
    end

    STORE --> HYB

    style WRITE fill:#fff7ed,stroke:#ea580c
    style READ fill:#f0fdf4,stroke:#16a34a
    style STORE fill:#dbeafe,stroke:#1d4ed8
    style LLM fill:#e0e7ff,stroke:#4338ca
    style Q fill:#dcfce7,stroke:#16a34a
    style DOCS fill:#fed7aa,stroke:#ea580c
```

### The 7 components to remember

| Component | Path | Job (one line) |
|---|---|---|
| Clean | write | Strip boilerplate so embeddings capture real content, not nav chrome. |
| Chunk | write | Split docs into retrievable, embeddable passages (the highest-leverage knob). |
| Embed | both | Map text → vector so semantic similarity = geometric closeness. |
| Vector store + FTS index | shared | Hold vectors *and* text; serve both search modes. |
| Rephrase | read | Turn a context-dependent query into a self-contained one. |
| Hybrid search | read | Vector (meaning) + full-text (exact terms) in one query. |
| Re-rank → top-K | read | Reorder wide candidates, keep the best K for the prompt. |

### The one idea that ties it together

**A RAG system is a write path and a read path that meet at the store, with opposite constraints — so you design, scale, and fail them separately.** The write path optimizes *throughput and freshness* (batch, parallelizable, can be slow); the read path optimizes *latency and precision* (every millisecond and every one of the top-K matters). Most RAG quality problems are really *which path is at fault*, and the split is what lets you answer that.

---

## 2. Detailed diagram (concrete Ask AI tech)

These are the *actual* Ask AI choices (from the design doc) — defensible, not the only options.

```mermaid
flowchart LR
    subgraph WRITE["WRITE — CP-Jobs weekly cron (CP-Scheduler)"]
        direction TB
        S3[("S3 docsbot-data<br/>HTML docs")] --> CL["Cleanup: drop headers/footers/sidebars"]
        CL --> CH["Chunk (≤1,000 tokens)"]
        CH --> E1["text-embedding-3-small → 1,536-dim"]
        E1 --> VER{"Replace or<br/>version embeddings"}
    end

    CB[("Capella 'Docsbot'<br/>scope=vector · collections: embeddings, pages<br/>FTS index: vector(cosine, recall) + text fields")]
    VER --> CB

    subgraph READ["READ — CP-API → iQ Backend (SSE stream)"]
        direction TB
        UQ(["User query + chat history"]) --> RP["Context-aware rephrase (lightweight LLM)"]
        RP --> QE["iQ CreateEmbeddings → query vector"]
        QE --> HS["Hybrid search: vector + FTS in ONE query (Go SDK)"]
        HS --> FB{"empty?"}
        FB -->|"yes"| PV["Fallback: pure vector"]
        FB -->|"no"| RR
        PV --> RR["Custom re-rank<br/>base + length pref + code/heading bonus"]
        RR --> TK["Top K = 5 chunks"]
        TK --> GEN["iQ CreateChatCompletionsStream<br/>GPT-4o, streamed"]
    end

    CB --> HS

    style WRITE fill:#fff7ed,stroke:#ea580c
    style READ fill:#f0fdf4,stroke:#16a34a
    style CB fill:#dbeafe,stroke:#1d4ed8
    style GEN fill:#e0e7ff,stroke:#4338ca
    style FB fill:#fef9c3,stroke:#ca8a04
    style VER fill:#fef9c3,stroke:#ca8a04
```

### Service cheat-sheet (Ask AI's actual picks)

| Concept | Choice | One-line why |
|---|---|---|
| Corpus source | AWS **S3** (`docsbot-data`) | HTML docs replicated from the docs site; batch-readable. |
| Indexer | **CP-Jobs** cron via **CP-Scheduler**, weekly | Freshness without a streaming pipeline; parallelized with goroutines (5–6h → ~20 min w/ 10 routines). |
| Embedding model | OpenAI **text-embedding-3-small** (1,536-dim) | Cheap, good enough; dims fixed by the model. *(Verify current model options.)* |
| Vector + text store | **Couchbase Capella** (cluster "Docsbot") | Native hybrid search — vectors *and* full-text in one engine/query. |
| Search index | Couchbase **FTS** `fulltext-index`, `embedding` field `dims:1536, similarity:cosine, vector_index_optimized_for:recall` | One index serves vector + lexical. |
| Query rephrase | Lightweight LLM call (context-aware) | Self-contained query; avoids a 2nd large call to save cost/latency. |
| LLM gateway | **iQ Backend** (abstraction over OpenAI) | `CreateEmbeddings` + `CreateChatCompletionsStream`; per-tenant rate limits. |
| Answer model | OpenAI **GPT-4o**, streamed | Quality generation; SSE to the CP-UI. |
| Retrieval width | Top **K = 5** after re-rank | Enough grounding, bounded prompt cost. |

### Protocols / concepts worth naming

- **Dense vs sparse retrieval** — vector similarity (meaning) vs full-text/BM25 (exact terms).
- **Hybrid search** — both run together; here in a *single* Couchbase query, with pure-vector fallback.
- **Fusion / re-ranking** — reconcile incomparable score scales, then reorder (RRF or weighted; Ask AI uses a custom heuristic).
- **Retrieve-wide → rerank-narrow** — fetch many candidates cheaply, spend ranking effort on the shortlist.
- **Context-aware rephrasing** — resolve pronouns/ellipsis from chat history before retrieval.
- **SSE streaming** — token-by-token response for perceived latency.
- **Re-embed & version** — swapping the embedding model means re-embedding the whole corpus; keep versioned backups.

> Cross-links: eval of this system → [`../llm-eval-and-observability/`](../llm-eval-and-observability/); store/index internals & pgvector/Pinecone/Couchbase trade-offs → [`../vector-databases/`](../vector-databases/); turning retrieval into agent tools → [`../agentic-rag-and-mcp/`](../agentic-rag-and-mcp/). See [`../ROADMAP.md`](../ROADMAP.md).
