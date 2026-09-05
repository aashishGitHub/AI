# Interviews — System-Design Knowledge Track (Roadmap)

> **Track A** of the [AI ramp-up](../RAMPUP.md). Each topic is a self-contained `interviews/<topic>/` folder built to [`docs/instructions-ref.md`](../docs/instructions-ref.md).
> **How to use a topic:** open `simple-diagram.md` → attempt `questions.md` cold → check `answers.md` → whiteboard from `diagrams.md` → go deep with `deep-dive.md`.

---

## 📊 Dashboard

| Metric | Count |
|---|---|
| Topics planned | 6 (5 core + 1 optional) |
| Topics built | **3** |
| Topics in progress | 0 |
| Files per built topic | 7 / 7 |

---

## Topic status

Legend: ✅ built · 🚧 in progress · ⬜ planned

- ✅ **[`llm-eval-and-observability/`](llm-eval-and-observability/)** — *Central split:* offline eval (pre-deploy, CI-gated) vs online eval (in-prod, sampled). Closes **gap #1**. All 7 files present. **This is the exemplar / quality template.**
- ✅ **[`rag-hybrid-search/`](rag-hybrid-search/)** — *Central split:* index/write path vs query/read path. Grounds directly in the Ask AI system. Closes part of **gap #2**. All 7 files present.
- ✅ **[`vector-databases/`](vector-databases/)** — *Central split:* the **index** (how much recall you sell for latency/memory) and the **operating model** (where vectors live relative to your other data) are two independent decisions, routinely conflated as "pgvector vs Pinecone". Closes **gap #2**. All 7 files present.
- ⬜ **`agentic-rag-and-mcp/`** — *Central split:* deterministic orchestration vs model-driven autonomy; MCP tool contracts + approval gates. The capstone architecture. Closes **gap #3**.
- ⬜ **`llm-serving-and-model-lifecycle/`** — *Central split:* stateless inference plane vs stateful knowledge plane; zero-downtime model/embedding swaps. Answers [`instructions.md`](../docs/instructions.md) directly.
- ⬜ **`llm-app-scale-and-cost/`** *(optional)* — *Central split:* cost × latency × quality; rate limits, semantic caching, token budgets.

**Authoring order:** `llm-eval-and-observability` (done) → `rag-hybrid-search` (done) → `vector-databases` (done) → **`agentic-rag-and-mcp`** (next) → `llm-serving-and-model-lifecycle` → `llm-app-scale-and-cost`.

---

## Quick reference

| Topic | Gap | Anchor in Ask AI | Feeds capstone piece |
|---|---|---|---|
| llm-eval-and-observability | 1 | Custom cosine + GPT-4 judge sheet (§10 Testing) | Eval regression suite in CI + observability dashboard |
| rag-hybrid-search | 2 | Hybrid vector+FTS + custom re-ranking, K=5 (§4.4) | Hybrid RAG retrieval core |
| vector-databases | 2 | Couchbase 8.0 vector indexes — Hyperscale · Composite · Search/FTS (choice is per query shape) | Retrieval store choice + trade-off write-up |
| agentic-rag-and-mcp | 3 | (deferred in Ask AI — new capability) | 2+ MCP tools w/ approval gates, agent loop |
| llm-serving-and-model-lifecycle | — | iQ-backend abstraction + weekly re-embedding w/ versioned backups | Bedrock deploy, versioned prompts, provider fallback |
| llm-app-scale-and-cost | — | Rate limits + cost analysis (§5–6) | Cost/latency guardrails |

---

## Cross-links

- Master plan & two-track model: [`../RAMPUP.md`](../RAMPUP.md)
- Hands-on 12-week build (Track B): [`../docs/notes/README.md`](../docs/notes/README.md)
- Anchor case study: [`../docs/Ask AI design document.md`](../docs/Ask%20AI%20design%20document.md)
- Authoring spec (how to add a topic): [`../docs/instructions-ref.md`](../docs/instructions-ref.md)

> **Accuracy note:** case-study anchors above reflect what the Ask AI design doc actually states. RAGAS/pgvector/Pinecone are learning targets, not part of the shipped system — see [`../RAMPUP.md` §5](../RAMPUP.md).
