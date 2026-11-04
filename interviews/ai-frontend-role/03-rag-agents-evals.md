# 03 · RAG, agents, MCP, evals: what an AI-product FE lead is expected to know

Deep material: [`rag-hybrid-search/`](../rag-hybrid-search/README.md) · [`vector-databases/`](../vector-databases/README.md) ·
[`llm-eval-and-observability/`](../llm-eval-and-observability/README.md) · [`agent-engineer-screen/QNA.md`](../agent-engineer-screen/QNA.md) ·
[`devrev-fde/modules/`](../devrev-fde/modules/README.md) · your harness [`evals/`](../../evals/README.md) · your agent [`agent-lab/`](../../agent-lab/NOTES.md).

Anchor case study you can speak to: **Ask AI** ([design doc](../../docs/Ask%20AI%20design%20document.md)) — hybrid vector + FTS search with re-ranking, K=5, feedback store, rate limits, cost analysis. Only claim the parts you personally did.

---

## A. RAG

### Q1 🟢 Explain RAG in 30 seconds.
**A.** Retrieval-augmented generation: at question time, search your own content for the most relevant passages, put them in the prompt, and tell the model to answer from them and cite them. Two paths:
**Write/index path** (offline): load docs → clean → chunk → embed → store vectors + text + metadata.
**Read/query path** (per request): (rewrite query) → retrieve (vector + keyword) → re-rank → build prompt with top K → generate → stream with citations.
It gives fresh/private knowledge and checkable answers without retraining.

### Q2 🟡 How do you chunk documents?
**A.** Split on structure first (headings, sections, code blocks), then by size (a few hundred tokens is a common starting point; tune it with an eval), with small overlap so sentences on a boundary aren't lost. Keep metadata per chunk: doc ID, title, heading path, URL anchor, last updated, permissions/tenant. Prepend the heading path to the chunk text before embedding so "Configure it" knows what "it" is.
Trade-off: small chunks = precise retrieval but missing context; big chunks = more context but noisier and costlier. Only an eval with recall@k tells you which is better for your corpus.

### Q3 🟡 Why hybrid search (vector + keyword)?
**A.** Vectors capture meaning ("how do I make replication faster" ≈ "XDCR throughput tuning") but miss exact tokens (error codes, IDs, API names, version numbers). Keyword/BM25 (full-text search) nails exact tokens but misses paraphrases. Run both, merge (e.g. **Reciprocal Rank Fusion**, which merges by rank position, not raw scores — scores from different systems aren't comparable), then re-rank.

### Q4 🟡 What does a re-ranker do?
**A.** A second-stage model (often a cross-encoder) scores each (query, chunk) pair together, more accurately than embedding similarity, but too slowly to run over the whole corpus. So: retrieve ~20–50 candidates cheaply, re-rank, keep the top 3–8. Costs latency (tens to hundreds of ms, approximately; measure it) and money; improves precision, which lets you send fewer chunks → lower cost and less distraction for the model.

### Q5 🟡 The RAG answer is wrong. How do you debug it?
**A.** Split the failure in two, using the trace:
1. **Retrieval failure:** was the right chunk in the top K? (Check the logged retrieved IDs against the doc that has the answer.) Fixes: chunking, hybrid weights, query rewriting, metadata filters, re-ranker, stale index.
2. **Generation failure:** the chunk was there but the answer ignored or misread it. Fixes: prompt (answer only from context, cite, say "I don't know"), chunk order, fewer distracting chunks, stronger model.
Then add the case to the golden set so it stays fixed. This split is the most important RAG debugging idea; say it first.

### Q6 🟡 What metrics do you use for RAG?
**A.**
| Layer | Metric | Meaning |
|---|---|---|
| Retrieval | **recall@k** | Is the relevant chunk in the top k? |
| Retrieval | **MRR / nDCG** | How high is the relevant chunk ranked? |
| Generation | **Faithfulness / groundedness** | Is every claim supported by the retrieved context? |
| Generation | **Answer relevance** | Does it answer the question asked? |
| Generation | **Citation accuracy** | Do the cited sources actually support the sentence? |
| Product | Thumbs up rate, regenerate rate, deflection (for support), time-to-answer | Does it help users? |
Faithfulness is usually graded by an LLM-as-judge with a rubric, calibrated against human labels.

### Q7 🟡 How do you handle permissions in RAG?
**A.** Filter **at retrieval time** by the user's identity/tenant/ACL metadata, so unauthorised chunks never reach the model (once in the prompt, the model can leak it; the UI can't un-leak it). Re-check on citation click. Keep ACL metadata in sync with the source system; stale ACLs are a real incident class.

### Q8 🟡 How do you keep the index fresh?
**A.** Incremental re-indexing on change events (webhooks/CDC) plus a periodic full re-sync for drift; content hashes to skip unchanged chunks; tombstones for deletes. Show "last updated" on sources in the UI. When changing the **embedding model**, build a new index side by side (versioned), backfill, run the eval on both, then switch reads atomically — never mix vectors from two models in one index. (Ask AI's design has weekly re-embedding with versioned backups.)

### Q9 🔴 pgvector vs a managed vector DB vs the search engine you already have?
**A.** Two separate decisions people mix up: **the index type** (HNSW / IVF etc.: recall vs latency vs memory) and **the operating model** (where vectors live relative to your other data). If your data and ACLs already live in Postgres/Couchbase and the corpus is small to medium, keep vectors next to it (one system, transactional consistency, joins/filters with business data). A dedicated vector DB pays off at large scale, heavy filtered-vector workloads, or when the team wants a managed service. Decide with a benchmark on your own data and filters, not vendor charts. Deep: [`vector-databases/`](../vector-databases/README.md).

### Q10 🟡 What is "agentic RAG"?
**A.** Instead of one fixed retrieve-then-generate pass, the model decides when and what to search (search as a tool), can search several times, reformulate, or call other tools. Better on multi-hop questions; slower, costlier, harder to evaluate and to make predictable. Start with fixed RAG; add agentic retrieval only for the question types an eval shows it helps.

---

## B. Agents

### Q11 🟢 What is an agent?
**A.** An LLM in a loop with tools: model decides an action → system executes the tool → result goes back to the model → repeat until it answers or hits a limit. Workflows (code decides the steps, LLM fills them in) vs agents (the model decides the steps). Prefer workflows when the steps are known; they're cheaper, faster, testable.

### Q12 🟡 What guardrails does an agent loop need?
**A.** Max iterations and a token/cost budget per run; timeouts per tool; tool allowlist per agent; schema validation of tool args; permission check with the end user's identity on every tool call; approval gates for risky tools; idempotency keys on write tools (so a retry doesn't double-charge/double-send); full audit log (every step, args, result, who approved); a kill switch. My `agent-lab` has the approval gate, audit log, and trajectory evals — say "I built" only for those.

### Q13 🟡 How do you evaluate an agent, not just a single answer?
**A.** Final-outcome evals (did the task succeed? check end state) plus **trajectory evals** (did it call the right tools, in a sensible order, without forbidden calls, within N steps?). Use deterministic checks where possible (state assertions, tool-call matchers), LLM-as-judge for open-ended parts. Run each case several times because agents are non-deterministic; report pass rate, not pass/fail.

### Q14 🟡 Agent memory: what kinds exist?
**A.** **Short-term** = the current context (conversation + scratchpad), managed by trimming/summarising. **Long-term** = facts stored outside the model (user preferences, past decisions) and retrieved when relevant, i.e. RAG over memories. Product questions: what's remembered, can the user see/edit/delete it, how do you avoid stale or wrong memories persisting. UI: a visible "memory" panel with delete — that's a trust feature.

### Q15 🔴 Multi-agent systems: when are they worth it?
**A.** When subtasks are genuinely separable and parallel (e.g. research several sources at once), or need different tool permissions. Costs: more tokens (often several times a single agent), harder debugging, coordination failures. Default: one agent with good tools; split only when evals or context limits force it. Durable execution (a workflow engine that persists each step — e.g. Temporal-style) matters for long runs so a crash resumes instead of restarting.

---

## C. MCP (Model Context Protocol)

### Q16 🟢 What is MCP?
**A.** An open protocol (introduced by Anthropic in late 2024, now adopted by many tools and model vendors) that standardises how an AI application (host/client) connects to **servers** that expose **tools** (actions), **resources** (readable data), and **prompts** (templates). Write a tool server once; any MCP-capable client can use it. Think "USB-C for AI tools". Transport: stdio for local servers, Streamable HTTP for remote (this replaced the earlier HTTP+SSE transport in the 2025 spec revision; verify the current spec).

### Q17 🟡 Where does MCP touch the frontend?
**A.** (1) The chat/agent UI shows MCP tool calls and their results like any tool call. (2) Approval UX for MCP tools (hosts commonly ask the user before running a tool). (3) OAuth flows: remote MCP servers can require the user to authorise access — the UI must handle the redirect/consent and per-user tokens. (4) Tool discovery UI: which servers/tools are connected and enabled. (5) Emerging: MCP-based embedded UIs inside chat hosts — moving fast; verify before claiming specifics.

### Q18 🔴 Security concerns with MCP?
**A.** Tool descriptions themselves are input to the model → a malicious server can inject instructions via its descriptions ("tool poisoning"). A server can change its tools after you approved it. Over-broad tokens (one server with admin scope). Confused deputy: the agent acts with more privilege than the user. Mitigations: allowlisted/reviewed servers, least-privilege per-user tokens, show and pin tool definitions, approval for writes, audit, run local servers sandboxed.

---

## D. Evals and observability

### Q19 🟢 What is an eval?
**A.** A repeatable test for model behaviour: a dataset of inputs (+ expected outputs or grading criteria), a way to run the system on them, and a grader (exact match, code assertion, or an LLM-as-judge with a rubric). Produces scores you track across prompt/model/retrieval changes. It's the unit test suite for non-deterministic systems.

### Q20 🟡 Offline vs online evals?
**A.** **Offline**: before deploy, on a fixed golden set, in CI, gating merges (regression gate). **Online**: in production, on sampled real traffic, graded async + user feedback + business metrics. Offline catches regressions you can anticipate; online catches what users actually do. Bad online cases feed back into the offline set. Central split in [`llm-eval-and-observability/`](../llm-eval-and-observability/README.md).

### Q21 🟡 How do you build a golden set?
**A.** Start with 30–50 real questions (support tickets, search logs, SME interviews), covering common, hard, adversarial (injection, out-of-scope → must say "I don't know"), and permission-sensitive cases. For each: the expected answer or key facts, and the source doc IDs (so you can compute retrieval recall). Grow it from production failures. Version it. Don't let it go stale. (Your plan: 30–50 Q/A + recall@k + faithfulness, 7 Nov.)

### Q22 🟡 LLM-as-judge: how do you make it trustworthy?
**A.** A specific rubric (binary or small scale per criterion, not "rate 1–10"), ask for reasoning before the verdict, use a different model family from the one being judged where possible (reduces self-preference), randomise order in pairwise comparisons (position bias), and **calibrate against human labels** on a sample — report agreement. Re-check when you change the judge model. Your harness uses a cross-family judge.

### Q23 🟡 What's a CI regression gate for prompts?
**A.** On every PR that touches prompts, retrieval config, or model version: run the golden set, compare against the baseline, **fail the build** if a key metric (faithfulness, recall@k, pass rate) drops beyond a threshold. Run several samples per case to average out noise; set thresholds above noise level. Your real story: the gate caught that the server prompt and the eval prompt had drifted; you added a zero-model parity check (`evals/ci/check-parity.py`). That's a strong, concrete answer — tell it.

### Q24 🟡 What do you log/trace for an LLM request?
**A.** Trace ID (propagated from the browser), user/tenant (hashed if needed), prompt template ID + version, model + parameters, retrieved chunk IDs + scores, tool calls with args/results/latency, token usage, TTFT, total latency, stop reason, errors, user feedback joined later by message ID. Tools: OpenTelemetry-based tracing, or LLM observability products (Langfuse, Arize Phoenix, LangSmith, Braintrust — know names, verify features). Redact PII.

### Q25 🔴 How do you roll out a new prompt or model safely?
**A.** Prompt in version control with an ID → offline eval vs baseline in CI → ship behind a feature flag → canary a small % of traffic → compare online metrics by version (thumbs rate, regenerate rate, latency, cost, error rate) → ramp or roll back by flipping the flag (no deploy). Keep old versions runnable for rollback. Same pattern for model upgrades: provider "same model name" updates can also shift behaviour, so pin versions where the provider allows.

---

## E. Cost and scale (talk numbers carefully)

### Q26 🟡 How do you estimate the cost of an AI feature?
**A.** cost/request ≈ (input tokens × input price + output tokens × output price) + retrieval + re-ranking. Input usually dominates for RAG (system prompt + chunks + history). Multiply by requests/user/day × users. Then levers: caching (prompt + response), routing, trimming context, capping output. Always say "prices change; I'd take current numbers from the provider's pricing page". Ask AI's design doc has a cost-analysis section you can use as a worked example if you worked on it.

### Q27 🟡 Semantic caching — good idea?
**A.** Cache answers keyed by query embedding; serve the cached answer when a new query is similar enough. Saves cost and latency for FAQ-style traffic. Risks: wrong answer for a query that's similar but different ("enable" vs "disable"), stale answers, permission leaks across users if not keyed by tenant/ACL. Use a high threshold, scope by tenant + content version, and eval it. Exact-match caching is the safe first step.
