# DevRev — Forward Deployed Engineer (Delhi NCR)

Source: https://job-boards.greenhouse.io/devrev/jobs/6180279004 (read 2026-10-19).
Q&A bank: [`questions-answers.md`](questions-answers.md).

## 1. What the role actually is

~80% with customers (up to 80% travel), ~70–80% hands-on build. You are the person who makes DevRev work inside
one customer's mess of tools: integrations into their **Knowledge Graph**, AI agents on top, then proof (POCs,
demos, SQL dashboards).

The control/data flow they care about:

```
customer systems (Jira, Zendesk, Salesforce, GitHub, homegrown DBs)
   │  webhooks (fast, lossy)      polling/cursor (slow, correct)
   ▼                                   ▼
 extractor ──▶ map/normalize schema ──▶ DevRev objects + links (Knowledge Graph)
                                             │
 loader ◀── reverse sync (2-way) ◀───────────┤
                                             ▼
                             RAG / semantic search / agents (function calling, MCP)
                                             │
                                  evals + telemetry + SQL dashboards
```

DevRev-specific vocabulary (from developer.devrev.ai — verify current names before the interview):

- **Snap-ins** — customer/partner extensions running on DevRev's platform (TypeScript functions + manifest).
- **AirSync** — the sync framework; forward sync = *extractor*, reverse sync = *loader*; two-way = both.
  Docs also expose `/airdrop/` paths — looks like a rename, I'm not certain which is current.
- Extraction is **incremental** (changes since the last successful forward-sync start), each invocation is
  **capped at ~13 min**, and a **state object** carries the checkpoint across invocations.
- **Object mappers** (`adapter.mappers`) track external-id ↔ DevRev-id.

## 2. Evidence inventory (all repos under `~/Documents/GitHub`, scanned 2026-10-19)

Lanes: **[P]** shipped at Couchbase · **[L]** your own build · **[K]** knowledge only.

| Repo | Lane | What it proves for this JD |
|---|---|---|
| `couchbase-cloud` — Billing Invoices (AV-141747, 144242, 145301–145303) | **P** | Go client for Workato/NetSuite: rebuilt when the real contract differed (timeout 10s→35s, params renamed); blocks redirects so the token can't leak; caps error-body reads; fail-closed NoOp client. Normalization that reports unreadable fields instead of guessing. Workato 502/404 → "no PDF yet" message to the customer. Feature flag (default off), RBAC, MSW mocks, Cypress e2e |
| `couchbase-cloud` — FTS index migration (AV-125740, 100609, 90296) | **P** | Legacy → new schema conversion, backward compatibility |
| `couchbase-cloud` — React Query resilience (AV-144356) | **P** | Transient 504s no longer surface as errors — degraded-mode UX |
| Ask AI (design doc in this repo) | **P** | Production RAG; ingest 5–6h → ~20 min with 10 goroutines |
| `streampulse` (Java 21/Spring, 8 services, Sep 28 → Oct 13 2026) | **L** | OpenAPI + AsyncAPI contracts; Kafka; **Debezium outbox CDC with an IT** (`OutboxCdcIT.java`); `EventId` idempotency; poison-record IT; `DependencyGraph` + cycle detection; serverless function; Micrometer/Prometheus/OTel; **MCP server** (`McpTools.java`); GH Actions CI; Testcontainers + Playwright |
| `GolangExercise/offline-sync-app` (FieldSync) | **L** | **Data sync + conflict handling** (`internal/sync/sync.go`, `transactional.go`, integration tests); outbox relay; SQS consumer; Lambdas; CI |
| `GolangExercise/ticket-booking` | **L** | Outbox, saga worker, projector, Lambdas, waiting-room rate limiting, sqlc SQL, Terraform eventing/DLQ, CI |
| `AI/fe-hands-on` (Agent Console) + `evals/` | **L** | Grounded RAG, SSE, provider seam, promptfoo eval, judge-inversion story |
| `DSnAlgoUsingJS` | **L** | 93 commits; TS + Go; 69 Vitest files, 337 Go tests; BFS/DFS, topo sort, union-find, DP, intervals, LRU, trie |
| `e-commerce` (Go + Next.js, Cloudflare Pages) | **L** | REST API, SQL migrations, JWT, deployed. No tests |
| `RAG-app`, `Tracker` | **L** | Small: OpenAI + Couchbase vector query; multi-provider LLM switch. Supporting only |

## 3. Gap matrix — updated with the evidence above

🟢 covered with artifact · 🟡 partial · 🔴 nothing

| JD requirement | Evidence | Status |
|---|---|---|
| TypeScript / JavaScript | Capella UI (P), Agent Console, DSA | 🟢 |
| DSA | DSnAlgoUsingJS (TS + Go) | 🟢 — only gap: token-bucket rate limiter |
| LLMs, prompting, RAG, semantic search | Ask AI (P), Agent Console (L) | 🟢 |
| Evals (RAG) | promptfoo harness (L) | 🟢 |
| Third-party API integration, contract mismatch | Workato/NetSuite (P) | 🟢 |
| Data mapping / schema alignment | invoice normalization (P), FTS migration (P) | 🟢 |
| Error surfacing to customer | 502/404→"no PDF yet" (P), 504 degradation (P) | 🟢 |
| Event-driven / pub-sub, outbox, idempotency | streampulse Kafka + Debezium outbox, FieldSync SQS (L) | 🟢 |
| Data sync + conflicts | FieldSync (L) | 🟡 — offline/device sync, **not SaaS↔SaaS two-way with echo-loop prevention** |
| Graph data structures | streampulse `DependencyGraph` + cycle detection (L), DSA graphs | 🟢 |
| Serverless | ticket-booking + FieldSync Lambdas, streampulse function (L) | 🟢 (verify each actually deployed vs only built) |
| CI/CD, containers | streampulse, FieldSync, ticket-booking CI + Docker (L); Capella CI edits (P) | 🟢 |
| Observability / telemetry | streampulse Micrometer + OTel (L); Datadog logs upgrade (P) | 🟢 |
| MCP | streampulse `mcp-server` (L) | 🟡 — server exists; no **function-calling loop / agent** consuming it |
| Function calling / agents | none | 🔴 |
| Evals for agentic AI (trajectory) | none | 🔴 |
| **Webhooks** (HMAC verify, replay, retries) | none — HMAC only signs waiting-room tokens | 🔴 |
| **GraphQL** | none | 🔴 |
| **Analytics SQL** (window funcs, percentiles) + dashboards | sqlc CRUD only | 🔴 |
| **Python (strong)** | ~2 trivial files | 🔴 — biggest risk |
| POCs, demos, customer stories | Workato story exists, not written as STAR | 🟡 |

**Verdict:** the AI repo alone missed most of it; across all repos you cover ~70% of the JD with real code.
Remaining red: **Python, webhooks, GraphQL, analytics SQL, function-calling agent + agent evals, SaaS two-way
sync semantics.**

**Defend-every-line risk:** streampulse is 8 services built in ~2 weeks, and several 2026 commits are
co-authored with Claude. Before you cite it, be able to whiteboard the outbox → Debezium → Kafka flow and explain
`OutboxCdcIT` without opening the code. If you can't, demote it to "explored".

## 4. Plan — 10 days (was 14; assumes interview in ~2 weeks, tell me the real date)

No new big project. Bolt the missing pieces onto what you already have.

| Days | Work | Closes |
|---|---|---|
| 1 | Read AirSync + snap-in docs end to end. One page "how AirSync maps to FieldSync + Workato" | vocabulary, bridges your evidence to their product |
| 1 | Re-walk your own code: FieldSync `internal/sync`, streampulse outbox CDC, Workato `client.go`. Explain each out loud in 3 min | defend-every-line |
| 2–3 | **Webhook receiver in TypeScript** (Cloudflare Worker or Lambda): HMAC over raw body, timestamp tolerance, delivery-id dedupe, enqueue. Add **echo-loop prevention + id map** to FieldSync-style two-way flow against a mock "Jira" | webhooks, SaaS two-way sync |
| 4 | Add a small **GraphQL** read endpoint (TS, e.g. on the webhook project); cursor pagination | GraphQL |
| 5–6 | **Function-calling agent** (TS or Python) that calls streampulse's MCP server tools; write tool behind approval. Agent-loop eval: 10 golden cases asserting tool choice + args, in CI | function calling, agents, agentic evals |
| 7 | **Python day**: port the agent eval or a sync extractor to Python (`httpx`, `pydantic`); 3 DSA problems in Python | Python |
| 8 | **SQL day**: window functions, `percentile_cont`, `date_trunc`, `LAG` on a ticket dataset (Postgres/DuckDB). One dashboard question answered end to end | analytics SQL |
| 9 | Write 5 STAR stories (Workato contract mismatch is #1). Token-bucket rate limiter in TS + Python | behavioural, DSA gap |
| 10 | Mock loop: TS coding, integration design (two-way sync), decomposition case, behavioural | — |

Daily: 1 DSA problem alternating TS / Python; 10 min out loud on one Q&A answer.

## 5. Positioning for this JD

Lead with: **"I integrate systems that don't agree with each other, and I put AI on top once the data is
trustworthy."** Then three proofs, one per lane:

1. **[P]** Workato/NetSuite invoices — real contract ≠ assumed contract, hardened, customer-facing errors, flagged
   rollout.
2. **[L]** streampulse / FieldSync — outbox + CDC + idempotent consumers + conflict handling.
3. **[P]+[L]** Ask AI → Agent Console — production RAG, then evals that caught two real bugs.

Keep the two-lane rule from [`../../docs/notes/STUDY-GUIDE.md`](../../docs/notes/STUDY-GUIDE.md) §4: never imply
lab work shipped to customers.
