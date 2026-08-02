# AI Ramp-Up — Senior/Staff AI-Native Readiness

> **Owner:** Web architect & front-end lead (React/Next.js, TypeScript, AWS, Go, Couchbase), ramping deliberately toward Senior/Staff AI-native roles.
> **What this repo is:** a two-track learning system that produces *knowledge you can whiteboard* and *artifacts you can run* — no passive reading.
> **Anchor case study:** Couchbase **Ask AI** (the shipped docs chatbot) — see [`docs/Ask AI design document.md`](docs/Ask%20AI%20design%20document.md).

---

## 0. The one idea that ties it together

You already **shipped** a production RAG system (Ask AI). The ramp-up doesn't start from zero — it **generalizes what you built** into (a) transferable system-design knowledge and (b) the skills the shipped system deliberately deferred: **evaluation, vector-DB trade-offs beyond Couchbase, and agents/MCP/LLM-ops.** Those three are your named gaps, and every topic below closes one.

Two tracks, one spine:

| Track | Lives in | Format spec | Optimizes for |
|---|---|---|---|
| **A. Knowledge** (whiteboard-ready system design) | [`interviews/<topic>/`](interviews/) | [`docs/instructions-ref.md`](docs/instructions-ref.md) | HLD interviews + architectural fluency |
| **B. Hands-on** (12-week build → capstone) | [`docs/notes/`](docs/notes/) | [`docs/tutor-prompt.md`](docs/tutor-prompt.md) | Runnable artifacts + real metrics |

The tracks share topics and cross-link: you **build** a thing in Track B, then **distill** it into a Track A topic folder. The capstone (**Agent Console**) is where all Track B artifacts converge.

---

## 1. The three gaps (the pressure points)

From [`docs/tutor-prompt.md`](docs/tutor-prompt.md), biased toward your weak spots (not your React/Couchbase strengths):

1. **Evals & evaluation harnesses** — *your #1 gap.* promptfoo + Ragas, LLM-as-judge + rule checks, golden datasets, CI regression gates, observability (latency/cost/drift).
2. **RAG trade-offs *beyond* Couchbase** — pgvector vs Pinecone vs Couchbase FTS. Always name the comparison; don't stay in the Couchbase comfort zone.
3. **Agents / MCP / LLM-ops / AWS Bedrock** — 2+ MCP tools with approval gates, guardrails, deploy in a VPC, observability.

---

## 2. Knowledge track — topic map (Track A)

Each topic is a full `interviews/<topic>/` folder built to the authoring spec (7 files). **Every topic leads with its central split** (its organizing insight) and maps to a gap and to the Ask AI case study.

| # | Topic folder | Central split (the organizing insight) | Gap | Status |
|---|---|---|---|---|
| 1 | **`llm-eval-and-observability`** ⭐ | **Offline eval** (pre-deploy: golden dataset, deterministic + LLM-as-judge, CI regression gate) vs **online eval** (in-prod: sampled telemetry, live judging, drift/cost/latency, feedback loop) | 1 | ✅ **Exemplar built** |
| 2 | **`rag-hybrid-search`** ✅ | **Index/write path** (crawl→clean→chunk→embed→version; async, batch) vs **query/read path** (rephrase→embed→hybrid vector+FTS→re-rank→top-K→stream; latency-bound) | 2 | ✅ **Built** |
| 3 | `vector-databases` | The **recall × latency × cost/ops** triangle, driven by ANN index (HNSW vs IVF/PQ) × operational model (managed SaaS · in-your-RDBMS · in-your-data-platform) | 2 | ⬜ Planned |
| 4 | `llm-serving-and-model-lifecycle` | **Stateless inference plane** (hot-swappable behind a gateway; versioned prompts; multi-provider fallback) vs **stateful knowledge plane** (embeddings/index; re-embed with versioned backups; zero-downtime migration) | — | ⬜ Planned |
| 5 | `agentic-rag-and-mcp` | **Deterministic orchestration** (planner/executor, MCP tool contracts, approval gates, guardrails) vs **model-driven autonomy** (agent loop, tool choice, reflection) — and where to draw the safety/latency/cost line | 3 | ⬜ Planned |
| 6 | `llm-app-scale-and-cost` *(optional)* | The **cost × latency × quality** trade-off: rate limits, semantic caching, token budgets, autoscaling | — | ⬜ Optional/later |

⭐ = the built exemplar and quality template for the rest. Topic 4 directly answers your [`docs/instructions.md`](docs/instructions.md) goals (integrate models, efficient data flow, replace models without downtime).

**Recommended authoring order:** 1 (done) → 2 (done) → **3 (next)** → 5 → 4 → 6. This mirrors the build order in Track B, so each topic is distilled right after you build it.

---

## 3. Hands-on track — the 12-week arc (Track B)

Backbone from [`docs/tutor-prompt.md`](docs/tutor-prompt.md). Each session ends in a runnable artifact **and** a notes file at `docs/notes/{week}-{topic-slug}.md` (index: [`docs/notes/README.md`](docs/notes/README.md)). Capstone = **Agent Console** (agentic RAG: Go/TS backend on AWS Bedrock in a VPC; 2+ MCP tools w/ approval gates; SSE streaming; hybrid RAG + reranking; versioned prompts + guardrails; eval regression suite in CI; React/Next.js console w/ streaming, approvals, generative UI, observability dashboard).

| Phase | Weeks | Focus (from tutor-prompt) | Feeds Track A topic |
|---|---|---|---|
| **Foundations** | 1–4 | Eval fundamentals (promptfoo + Ragas) + MCP/agents study; capstone skeleton + hybrid RAG + first eval suite | 1, 2, 3, 5 |
| **Build + Depth** | 5–8 | Capstone agent + human-in-the-loop approvals UI + observability dashboard (latency/cost/drift); decomposition mocks; Python source reading | 5, 1, 4 |
| **Ship + Apply** | 9–12 | Deploy on AWS Bedrock in a VPC; two write-ups; 15-min demo pitch; targeted applications | 4 + interview prep |

**Weeks explicitly named in the tutor-prompt** (authoritative — the rest of each band I'll refine session-by-session with the tutor, not pre-invent):

- **Wk1 D3 (today):** promptfoo eval harness — first golden dataset + LLM-as-judge → *closes gap #1* → note `01-*`
- **Wk1 weekend:** Agent Console skeleton — Go/TS backend + Next.js shell + SSE token stream
- **Wk2:** Hybrid RAG in Couchbase FTS, then immediately pgvector vs Pinecone vs Couchbase trade-off write-up → *closes gap #2*
- **Wk3:** MCP tool integration with an approval gate (Couchbase MCP server as reference)
- **Wk4:** Wire the eval suite into CI (golden dataset + rule checks + LLM-as-judge) as a regression gate

> Weeks 5–12 are defined at the *phase* level in the tutor-prompt, not week-by-week. I'll fill exact sessions as we go rather than fabricate a precise schedule.

---

## 4. How the two tracks connect (the loop)

```
Track B session (build)  ──►  runnable artifact + docs/notes/NN-*.md
        │                                   │
        │  when a topic's artifacts exist   ▼
        └────────────────────────►  distill into interviews/<topic>/ (Track A, 7 files)
                                            │
                                            ▼
                        whiteboard-ready HLD + the real metrics you measured
```

Example already in place: **eval**. Track B Wk1/Wk4 build the promptfoo harness and CI gate; Track A [`interviews/llm-eval-and-observability/`](interviews/llm-eval-and-observability/) is the distilled, interview-ready version of that knowledge, grounded in how Ask AI actually evaluates today.

---

## 5. Accuracy contract (non-negotiable — applies to every file here)

Per [`docs/instructions-ref.md` §4](docs/instructions-ref.md) and your standing rules:

1. Flag uncertainty ("verify against current docs"); never state a guess as fact.
2. No invented sources, paper titles, URLs, or APIs. Only cite links actually vetted in the tutor-prompt or clearly-real primary docs.
3. Label statistics as "approximately" and mark capacity numbers as order-of-magnitude planning figures.
4. Numbers derive from stated constraints where possible, so the math is checkable.
5. Only 2025+ external material; flag anything older.

**Honesty note carried into all case-study content:** [`docs/instructions.md`](docs/instructions.md) says RAGAS is "used" at Couchbase, but the shipped [Ask AI design doc](docs/Ask%20AI%20design%20document.md) uses a **bespoke** eval (cosine similarity via `text-embedding-ada-002` + a GPT-4 judge/classifier in a Google Sheet) and is **100% Couchbase** (no pgvector/Pinecone). So RAGAS, promptfoo, pgvector, and Pinecone are treated here as **forward-looking learning targets**, not descriptions of the shipped system. Case-study callouts stay matched to what the doc actually says.

---

## 6. Repo layout

```
AI/
├── README.md                         # repo stub
├── RAMPUP.md                         # ← you are here: the master structure
├── docs/
│   ├── instructions-ref.md           # Track A authoring spec (how to build a topic folder)
│   ├── tutor-prompt.md               # Track B tutor prompt + 12-week arc
│   ├── instructions.md               # your stated AI-integration goals
│   ├── Ask AI design document.md     # anchor case study (Couchbase Ask AI)
│   └── notes/
│       ├── README.md                 # 12-week hands-on index + note template
│       └── 01-promptfoo-golden-dataset-llm-judge.md   # Wk1 D3 notes (scaffold)
└── interviews/
    ├── ROADMAP.md                    # Track A dashboard (topic status + quick-ref)
    ├── llm-eval-and-observability/   # ⭐ built exemplar (7 files)
    │   ├── README.md · simple-diagram.md · questions.md · answers.md
    │   └── diagrams.md · deep-dive.md · conducive-sentences.md
    └── rag-hybrid-search/            # ✅ built topic #2 (7 files, same layout)
```

---

## 7. Start here

1. Read this file, then [`interviews/ROADMAP.md`](interviews/ROADMAP.md) for the knowledge-track dashboard.
2. Study the built exemplar [`interviews/llm-eval-and-observability/`](interviews/llm-eval-and-observability/) — start with its `simple-diagram.md`, attempt `questions.md` cold, then check `answers.md`.
3. Run today's Track B session with [`docs/tutor-prompt.md`](docs/tutor-prompt.md) (Wk1 D3: promptfoo harness) → land notes in [`docs/notes/`](docs/notes/).
4. When the next topic's artifacts exist, distill it into its `interviews/<topic>/` folder (order in §2).
