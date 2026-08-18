# RAG & Hybrid Search — Diagrams

> Start with **Diagram 1** (the write/read split); the rest zoom into one stage each.
> **Reference:** pairs with [`answers.md`](answers.md) and [`simple-diagram.md`](simple-diagram.md).
> **Cross-links:** eval → [`../llm-eval-and-observability/`](../llm-eval-and-observability/); store/index & pgvector/Pinecone/Couchbase → [`../vector-databases/`](../vector-databases/); agents → [`../agentic-rag-and-mcp/`](../agentic-rag-and-mcp/). See [`../ROADMAP.md`](../ROADMAP.md).

---

## Diagram 1 — The central split: write path vs read path

> **When to use:** Q3, Q4, Q36 — the framing you open any RAG answer with.

```mermaid
flowchart LR
    subgraph W["WRITE — async, batch, throughput-bound"]
        direction TB
        D[("Docs")] --> C["clean"] --> K["chunk"] --> E["embed"]
    end
    S[("Vector store + FTS index")]
    E --> S
    subgraph R["READ — sync, latency-bound"]
        direction TB
        U(["query"]) --> RP["rephrase"] --> QE["embed"] --> H["hybrid search"] --> RR["re-rank top-K"] --> G["stream answer"]
    end
    S --> H

    style W fill:#fff7ed,stroke:#ea580c
    style R fill:#f0fdf4,stroke:#16a34a
    style S fill:#dbeafe,stroke:#1d4ed8
    style G fill:#e0e7ff,stroke:#4338ca
```

**What the interviewer is checking:**
- You *lead* with the two paths, not a pipeline blur.
- You name the opposite constraints (throughput/freshness vs latency/precision).
- You know they scale and fail independently.
- You place the store as the meeting point.

---

## Diagram 2 — Write path in detail (Ask AI CP-Jobs weekly cron)

> **When to use:** Q6–Q10 — indexing, freshness, safe re-embed.

```mermaid
flowchart TB
    START(["CP-Scheduler: weekly trigger"]) --> FETCH["Fetch HTML from S3 (docsbot-data)"]
    FETCH --> CLEAN["Cleanup: drop headers/footers/sidebars"]
    CLEAN --> CHUNK["Chunk (≤1,000 tokens)"]
    CHUNK --> EMB["Embed each chunk<br/>text-embedding-3-small → 1,536-d"]
    EMB --> NEW[("New embedding version")]
    NEW --> VAL{"Validate new<br/>embeddings?"}
    VAL -->|"fail"| KEEP["Keep old version live (no-op)"]
    VAL -->|"pass"| FLIP["Promote / switch query path"]

    style START fill:#fed7aa,stroke:#ea580c
    style NEW fill:#dbeafe,stroke:#1d4ed8
    style VAL fill:#fef9c3,stroke:#ca8a04
    style KEEP fill:#fee2e2,stroke:#dc2626
    style FLIP fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Clean before chunk before embed (order matters).
- Build-new-then-validate-then-flip (no in-place mutation).
- A failed run is a no-op, not an outage.
- Parallelism (goroutines) is a throughput lever, not correctness.

---

## Diagram 3 — Read path sequence (request → streamed answer)

> **When to use:** Q4, Q26, Q34 — the live query lifecycle.

```mermaid
sequenceDiagram
    participant UI as CP-UI
    participant API as CP-API
    participant IQ as iQ Backend
    participant CB as Couchbase (hybrid)
    participant LLM as GPT-4o
    UI->>API: query + history (JWT)
    API->>IQ: rephrase (lightweight LLM, context-aware)
    IQ->>IQ: CreateEmbeddings(rephrased) → vector
    IQ->>CB: hybrid search (vector + FTS) single query
    CB-->>IQ: candidates (or empty → pure-vector fallback)
    IQ->>IQ: custom re-rank → top K=5
    IQ->>LLM: CreateChatCompletionsStream(query + K chunks)
    LLM-->>UI: SSE tokens (streamed)
```

**What the interviewer is checking:**
- Rephrase happens *before* embedding.
- Hybrid is one round-trip; fallback is explicit.
- Only rephrased query + K chunks reach the big model.
- Streaming is end-to-end (SSE).

---

## Diagram 4 — Hybrid retrieval + fallback

> **When to use:** Q16–Q19 — dense vs sparse and how they combine.

```mermaid
flowchart TB
    Q(["rephrased query"]) --> V["Vector search<br/>(meaning / paraphrase)"]
    Q --> F["Full-text search<br/>(exact terms / IDs)"]
    V --> FUSE["Fuse + score (single Couchbase query)"]
    F --> FUSE
    FUSE --> E{"empty?"}
    E -->|"yes"| PV["Fallback: pure vector"]
    E -->|"no"| OUT["candidate set"]
    PV --> OUT

    style V fill:#dcfce7,stroke:#16a34a
    style F fill:#fed7aa,stroke:#ea580c
    style E fill:#fef9c3,stroke:#ca8a04
    style OUT fill:#dbeafe,stroke:#1d4ed8
```

**What the interviewer is checking:**
- You know what each mode catches (meaning vs exact tokens).
- Why single-query hybrid (latency, engine-native).
- Why a fallback exists (never return nothing).

---

## Diagram 5 — Retrieve-wide → rerank-narrow funnel

> **When to use:** Q20, Q21, Q24 — the efficiency pattern behind ranking.

```mermaid
flowchart LR
    CORP[("millions of chunks")] --> ANN["ANN retrieve<br/>top ~20–100 (recall, cheap)"]
    ANN --> RR["Re-rank shortlist<br/>(precision, pricier)"]
    RR --> K["Top K=5 → prompt"]

    style CORP fill:#dbeafe,stroke:#1d4ed8
    style ANN fill:#dcfce7,stroke:#16a34a
    style RR fill:#fef9c3,stroke:#ca8a04
    style K fill:#e0e7ff,stroke:#4338ca
```

**What the interviewer is checking:**
- Recall-first retrieve, precision-later re-rank.
- Why you can't precisely rank the whole corpus.
- K is the final, eval-tuned narrowing.

---

## Diagram 6 — Re-ranker anatomy (Ask AI heuristic)

> **When to use:** Q22, Q23 — critiquing/choosing a re-ranker.

```mermaid
flowchart TB
    IN["candidate chunk + base score"] --> BASE["base = hybrid score"]
    BASE --> LEN["+ length preference<br/>(favor medium chunks)"]
    LEN --> CT["+ content-type bonus<br/>(code · headings · structured)"]
    CT --> FINAL["final score → sort → top K"]
    ALT["Alternative: cross-encoder<br/>(joint query+doc, higher precision, +latency/cost)"] -.->|"when quality gates value"| FINAL

    style BASE fill:#dbeafe,stroke:#1d4ed8
    style CT fill:#dcfce7,stroke:#16a34a
    style FINAL fill:#e0e7ff,stroke:#4338ca
    style ALT fill:#fef9c3,stroke:#ca8a04
```

**What the interviewer is checking:**
- Each heuristic term should earn its place (ablation).
- Trade-off vs a cross-encoder is explicit.
- Bonuses can override true relevance if unchecked.

---

## Diagram 7 — Zero-downtime re-embed (versioned swap)

> **When to use:** Q9, Q10, Q14, Q37 — model swap / freshness without a broken window.

```mermaid
stateDiagram-v2
    [*] --> ServingV1
    ServingV1: Serving index v1 (live)
    ServingV1 --> BuildingV2: start re-embed (new model/corpus)
    BuildingV2: Building index v2 (offline, beside v1)
    BuildingV2 --> Validate: build done
    Validate: Validate v2 (quality/coverage checks)
    Validate --> ServingV2: pass, atomic flip (query path → v2)
    Validate --> ServingV1: fail, discard v2 (v1 stays live)
    ServingV2 --> [*]
```

**What the interviewer is checking:**
- New index built beside the old, never in place.
- Query embedding + index flip happen together.
- Failure path keeps v1 live (no outage).

---

## Diagram 8 — Prompt packing & lost-in-the-middle

> **When to use:** Q31, Q32 — turning K chunks into a grounded prompt.

```mermaid
flowchart TB
    subgraph PROMPT["Prompt to GPT-4o"]
        direction TB
        SYS["System: answer ONLY from context · cite URLs · else say I don't know"]
        C1["chunk #1 (strongest) — edge"]
        CM["chunks #2..#4 — middle (under-attended)"]
        CK["chunk #5 (strong) — edge"]
        UQ["User: rephrased query"]
    end
    SYS --> C1 --> CM --> CK --> UQ

    style SYS fill:#e0e7ff,stroke:#4338ca
    style CM fill:#fee2e2,stroke:#dc2626
    style C1 fill:#dcfce7,stroke:#16a34a
    style CK fill:#dcfce7,stroke:#16a34a
```

**What the interviewer is checking:**
- Behavior rules live in the system prompt.
- Strong chunks at the edges (middle is under-attended).
- Sources carried for citations; refuse-if-unknown contract.

---

## Diagram 9 — 2 AM degradation: triage by layer

> **When to use:** Q40 — production incident with no deploy.

```mermaid
flowchart TB
    ALERT(["Quality drop, no deploy"]) --> L1{"Retrieval healthy?"}
    L1 -->|"no"| R["Re-embed job failed / index stale<br/>→ rollback index version"]
    L1 -->|"yes"| L2{"Generation changed?"}
    L2 -->|"yes"| G["Provider model drift / refusals<br/>→ pin or failover model"]
    L2 -->|"no"| L3["Infra: latency / rate-limit rejects<br/>→ scale, raise limits, shed load"]

    style R fill:#fed7aa,stroke:#ea580c
    style G fill:#fee2e2,stroke:#dc2626
    style L3 fill:#fef9c3,stroke:#ca8a04
```

**What the interviewer is checking:**
- Triage in path order: retrieval → generation → infra.
- Each layer has a concrete rollback/mitigation.
- Version pinning + per-stage telemetry make this possible.

---

## Quick Interview Reference

### Scale numbers (Ask AI — planning figures, verify)
- 2,667 docs → 7,597 chunks; ≤1,000 tokens/chunk; 1,536-d cosine; K=5.
- Re-embed 5–6 h → ~20 min with 10 goroutines (weekly).
- iQ rate limits: free 100 calls/60s · 2,000 req/day · 500K tok/mo; paid 2,000 req/day · 2M tok/mo.

### Domain quick-ref
| Stage | Key idea | Diagram |
|---|---|---|
| Split | write vs read, opposite constraints | 1 |
| Index | clean→chunk→embed→version→flip | 2, 7 |
| Query lifecycle | rephrase→embed→hybrid→rerank→stream | 3 |
| Retrieval | dense+sparse+fallback | 4 |
| Ranking | retrieve-wide → rerank-narrow | 5, 6 |
| Generation | pack prompt, edges > middle | 8 |
| Incident | triage retrieval/gen/infra | 9 |

### Canonical trade-offs
- Write vs read path · RAG vs fine-tune vs long-context · dense vs sparse vs hybrid · heuristic vs cross-encoder · weekly vs incremental re-embed · K low vs high.

### Common mistakes
- One-pipeline thinking · pure-vector-only · in-place index mutation · mixed embedding spaces · ignoring chunking · unbounded cross-encoder latency · no retrieval-vs-generation attribution · huge K (lost-in-the-middle).
