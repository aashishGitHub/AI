# Hands-On Notes — 12-Week Build Track (Index)

> **Track B** of the [AI ramp-up](../../RAMPUP.md). Driven by [`../tutor-prompt.md`](../tutor-prompt.md).
> **Rule:** every session ends in a *runnable artifact* **and** a notes file here. No passive learning.
> **File convention:** `docs/notes/{NN}-{topic-slug}.md` (NN = week/session number, zero-padded).

---

## Capstone this all feeds — "Agent Console"

Agentic RAG service: **Go/TS backend on AWS Bedrock in a VPC** · 2+ **MCP** tool integrations with approval gates · **SSE streaming** · hybrid RAG (vector + keyword + reranking) · versioned prompts + guardrails · **eval regression suite in CI** (golden dataset, LLM-as-judge + rule checks) · **React/Next.js** console with streaming tokens, approvals, generative UI, and an observability dashboard.

Log **real metrics** from it every session: latency, token cost, recall.

---

## Session log

Legend: ✅ done · 🚧 in progress · ⬜ upcoming

| Session | Week | Topic | Artifact | Gap | Distills into (Track A) | Notes |
|---|---|---|---|---|---|---|
| 01 | Wk1 D3 | promptfoo eval harness — first golden dataset + LLM-as-judge | [`evals/`](../../evals/) — 2 golden cases (happy + negative), `contains`/`icontains-any`/`llm-rubric`, on local Ollama | 1 | [`llm-eval-and-observability`](../../interviews/llm-eval-and-observability/) | ✅ [`01-*`](01-promptfoo-golden-dataset-llm-judge.md) — judge fixed: false PASS was a malformed **rubric**, not model size (1.5b & 3b both 5/5 vs 0/5 on prompt shape) |
| 02 | Wk1 wknd | Agent Console — SSE token streaming behind a provider seam | [`fe-hands-on/`](../../fe-hands-on/) — real `llama3.2:1b` tokens over SSE behind a swappable `provider`, usage on the done frame, 6 Go tests | 3 | agentic-rag-and-mcp, llm-serving-and-model-lifecycle | ✅ [`02-*`](02-agent-console-sse-provider-seam.md) |
| 03 | Wk2 | Hybrid RAG in Couchbase FTS | hybrid search returning ranked chunks | 2 | rag-hybrid-search | ⬜ |
| 04 | Wk2 | pgvector vs Pinecone vs Couchbase — trade-off write-up + micro-benchmark | written comparison + latency/recall numbers | 2 | vector-databases | ⬜ |
| 05 | Wk3 | MCP tool integration with an approval gate | 1 MCP tool callable behind a human approval | 3 | agentic-rag-and-mcp | ⬜ |
| 06 | Wk4 | Eval suite into CI as a regression gate | CI job that fails on eval regression | 1 | llm-eval-and-observability | ⬜ |
| … | Wk5–8 | Build+Depth: capstone agent + approvals UI + observability dashboard; decomposition mocks; Python source reading | *(sessions set with tutor)* | 3,1,— | agentic-rag-and-mcp, llm-serving-and-model-lifecycle | ⬜ |
| … | Wk9–12 | Ship+Apply: deploy on AWS Bedrock in a VPC; two write-ups; 15-min demo; applications | *(sessions set with tutor)* | — | llm-serving-and-model-lifecycle | ⬜ |

> Weeks 1–4 are the sessions the tutor-prompt names explicitly. Weeks 5–12 are phase-level in the prompt; I add exact rows as each session is planned rather than pre-inventing them.

---

## Note template (copy for each new session)

Mirrors the "Revision guide output" in [`../tutor-prompt.md`](../tutor-prompt.md) step 6.

```markdown
# {NN} — {Topic} (Week {W}, {Date})

**One-line summary:** {what this session bought me}
**Gap closed:** {1 evals | 2 RAG trade-offs | 3 agents/MCP/ops}
**Capstone contribution:** {which Agent Console piece this advances}

## Concept notes (the mental model — dense, correct, not padded)
- {5–12 bullets: definitions, the 2–3 trade-offs, where it fits the architecture}

## Tools & setup (assume a clean machine; verify versions)
```bash
# exact install/setup commands used
```

## Key code / config (the snippet worth rereading)
```{lang}
# smallest thing that captures the pattern; comment non-obvious lines; name the pattern + trade-off
```

## Trade-offs
- {A vs B: when each wins}

## Metrics captured (real, from the capstone)
- latency: … · token cost: … · recall/quality: …

## Reference links (2025+, primary sources; title + URL + why)
- {title} — {url} — {one line}

## Checkpoint Q&A (prove I understood, not copied)
1. Q: … / A: …

## Next time
- {sets up the following session in the arc}
```

---

## Vetted references (from tutor-prompt; add better 2025+ ones as found)

> I have **not** re-verified these URLs are live or current — treat as starting points and confirm against the primary source, per the accuracy contract. Anything pre-2025 must be flagged when cited.

- **Couchbase AI Engineering** book + notebooks (Jake Wood) — `https://github.com/wooyakob/couchbase-ai-engineering` — runnable RAG, MCP server, LangGraph agent, Ragas evals, hybrid search. *Couchbase-centric + uses Ragas; pair with promptfoo + pgvector/Pinecone.*
- **promptfoo** docs — `https://www.promptfoo.dev/docs/getting-started/` · guides `https://www.promptfoo.dev/docs/guides/` · model-graded/G-Eval `https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/g-eval/`
- **Golden dataset** guide — `https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/`
- **LLM Evaluation in 2025** (metrics/RAG/LLM-as-judge) — `https://medium.com/@QuarkAndCode/llm-evaluation-in-2025-metrics-rag-llm-as-judge-best-practices-ad2872cfa7cb`

---

## Cross-links

- Master plan: [`../../RAMPUP.md`](../../RAMPUP.md) · Knowledge track: [`../../interviews/ROADMAP.md`](../../interviews/ROADMAP.md) · Case study: [`../Ask AI design document.md`](../Ask%20AI%20design%20document.md)
