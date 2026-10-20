# DevRev — Forward Deployed Engineer (Delhi NCR)

Source: https://job-boards.greenhouse.io/devrev/jobs/6180279004 (read 2026-10-19).
**Study order:** [`LEVELS.md`](LEVELS.md) (beginner → senior ladder) → [`modules/`](modules/README.md) (every phase of every module, full answers) → [`STUDY.md`](STUDY.md) (deep dives) →
[`STAR.md`](STAR.md) (stories) → [`drills/`](drills/DRILLS.md) (coding). Q&A bank: [`questions-answers.md`](questions-answers.md).

## 1. What the role actually is

~80% with customers (up to 80% travel), ~70–80% hands-on build. You are the person who makes DevRev work inside
one customer's mess of tools: integrations into their **Knowledge Graph**, AI agents on top, then proof (POCs,
demos, SQL dashboards).

The control/data flow they care about:

```
customer systems (Jira, Zendesk, Salesforce, GitHub, homegrown DBs)
   │  webhooks (fast, lossy)      polling/cursor (slow, correct)
   ▼                                   ▼
 extraction ──▶ map/normalize schema ──▶ DevRev objects + links (Knowledge Graph)
                                             │
 data loading ◀── reverse sync (2-way) ◀─────┤
                                             ▼
                             RAG / semantic search / agents (function calling, MCP)
                                             │
                                  evals + telemetry + SQL dashboards
```

DevRev AirSync vocabulary — **verified against developer.devrev.ai on 2026-10-19** (docs change; re-check the
week of the interview). Quotes are from the pages named.

| Concept | What the docs say | Page |
|---|---|---|
| Connector | "An AirSync connector is a snap-in containing code and configuration for one external system." Imports into DevRev and, "when supported, send changes back" (reverse sync). | `/airsync/getting-started` |
| Time limit | Soft timeout `options.timeout` in ms, "capped at ten minutes"; hard kill "at 1.3 times the soft timeout" (→ ~13 min, where my earlier "13 min" came from). Worker checks `adapter.isTimeout` between pages/batches and returns "in time for the SDK to save progress"; `onTimeout` callback. Don't rely on the hard kill as a checkpoint. | `/airsync/worker-timeouts` |
| Resume | State resumes "at the next unconsumed page"; rate limits preserve that page; reads and writes must be replay-safe. "Use compact JSON state for source cursors and per-type completion." | `/airsync/worker-timeouts`, `/airsync/data-extraction` |
| Incremental | "include changed source records in the resolved window without reprocessing unchanged history" | `/airsync/data-extraction` |
| Identity mappers | `Mappers` from `@devrev/airsync-sdk`: `getByExternalId`, `getByTargetId`, `create`, `update`; returns `null` when missing; other failures throw `AirSyncHttpError` — never treat a transient error as "not found" (creates duplicates). | `/airsync/object-mappers` |
| **Loop prevention** | After a write, the SDK records the mapper's `external_versions` `{ modified_date, recipe_version: 0 }`. The connector must return the external system's real `modifiedDate` from the write and keep the same `modified_date` during extraction, so the import recognises DevRev's own change by **version matching**. | `/airsync/loop-prevention` |
| Loading (reverse sync) | "data loading" / loading callbacks, `loadItemTypes()`; mapper exists → `update`, else `create`. A callback error is an **item failure** (counted, then advance — no auto-retry). Rate limits → return a `delay` (e.g. `delaySeconds: 30`), the item stays pending. `item.id.devrev` is "suitable for a stable idempotency key." | `/airsync/load-data` |

No longer on the current pages: the terms *extractor* / *loader* (they say "extraction" and "data loading"),
`adapter.mappers`, and the name "Airdrop". Don't use those words as if they were current.

How your FieldSync build maps to it (say this): your echo memory = their `external_versions` version matching; your
`external_id_map` = identity mappers; your budget-checked resumable extractor = `adapter.isTimeout` + cursor state;
your dead-letter table ≈ their per-item failure report; your 429 `Retry-After` handling ≈ their `delay` outcome.

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
| DSA | DSnAlgoUsingJS (TS + Go); `drills/` token bucket, LRU, sliding window, graphs (TS + Python) | 🟢 |
| LLMs, prompting, RAG, semantic search | Ask AI (P), Agent Console (L) | 🟢 |
| Evals (RAG) | promptfoo harness (L) | 🟢 |
| Third-party API integration, contract mismatch | Workato/NetSuite (P) | 🟢 |
| Data mapping / schema alignment | invoice normalization (P), FTS migration (P) | 🟢 |
| Error surfacing to customer | 502/404→"no PDF yet" (P), 504 degradation (P) | 🟢 |
| Event-driven / pub-sub, outbox, idempotency | streampulse Kafka + Debezium outbox, FieldSync SQS (L) | 🟢 |
| Data sync + conflicts | FieldSync LWW (L) + `internal/twoway`: id map, echo guard, field ownership, resumable extractor, loader w/ backoff, dead letters; 15 integration tests on real Postgres (L) | 🟢 — against a mock Jira, not a real vendor |
| Graph data structures | streampulse `DependencyGraph` + cycle detection (L), DSA graphs | 🟢 |
| Serverless | ticket-booking + FieldSync Lambdas, streampulse function (L) | 🟢 (verify each actually deployed vs only built) |
| CI/CD, containers | streampulse, FieldSync, ticket-booking CI + Docker (L); Capella CI edits (P) | 🟢 |
| Observability / telemetry | streampulse Micrometer + OTel (L); Datadog logs upgrade (P) | 🟢 |
| MCP | streampulse Java `mcp-server` (L); `agent-lab/mcp_server` Python re-implementation + MCP client over stdio (L) | 🟢 |
| Function calling / agents | `agent-lab/agent`: loop, schema-validated args, default-deny approval gate, JSONL audit log, max steps (L) | 🟢 — ran live against `qwen2.5:3b` (60 runs) |
| Evals for agentic AI (trajectory) | `agent-lab/evals`: 13 golden cases incl. prompt injection; 18 deliberately wrong trajectories each fail with a precise reason; live: 82% task success, 0 safety failures, 2 cases 0/5 (model guessed a tenant; explained the suppressed alert) (L) | 🟢 — tiny sample (n=5, one model) |
| **Webhooks** (HMAC verify, replay, retries) | `internal/webhook` (Go, 25 tests) + `drills/` verify (TS + Python); real receiver smoke-tested against mock Jira; delivery id signed; Lambda entrypoint + Terraform (`validate` passes) (L) | 🟢 — deploy-ready, never applied |
| **GraphQL** | `internal/graph` (gqlgen): keyset connections, DataLoader, depth + cost limits; 201 → 3 DB calls asserted; 6 integration tests (L) | 🟢 |
| **Analytics SQL** (window funcs, percentiles) + dashboards | `analytics/`: 14 queries, deterministic seed, EXPLAIN study (6.11→0.105 ms etc.), `QUESTIONS.md`; 34 tests with invariants | 🟢 — synthetic data, local numbers |
| **Python (strong)** | `drills/py` (196 tests, stdlib), `agent-lab` (160 tests) | 🟡 — code exists; **you must be able to write it cold** |
| POCs, demos, customer stories | Workato story exists, not written as STAR | 🟡 |

**Verdict:** across all repos you now cover most of the JD with real, tested code. What's left is not missing
code — it's **ownership**: the sprint code was built with AI assistance, so every item below is only an asset once
you can rebuild it from a blank file and defend it. See `STUDY.md` Round 6.

**Still genuinely open (both need real accounts, so they stay open on purpose):** an actual AWS deploy (`terraform
apply` — code and Terraform are ready and validated), and a real-vendor sync (everything runs against a mock Jira).
Everything else on the original gap list is closed — see STUDY.md Round 6 for the ownership work.

**Defend-every-line risk:** streampulse is 8 services built in ~2 weeks, and several 2026 commits are
co-authored with Claude. Before you cite it, be able to whiteboard the outbox → Debezium → Kafka flow and explain
`OutboxCdcIT` without opening the code. If you can't, demote it to "explored".

## 4. Where each gap lives now (built 2026-10-19)

| Gap | Code | Doc to study | Run it |
|---|---|---|---|
| Webhooks + SaaS two-way sync | `GolangExercise/offline-sync-app/internal/{webhook,twoway,mockjira}` | `docs/two-way-sync.md` | `go test -tags=integration -run Integration ./internal/twoway/` |
| GraphQL + N+1 | `.../internal/graph`, `cmd/graphql` | `docs/graphql.md` | `go test ./internal/graph/` |
| Analytics SQL | `.../analytics/` | `analytics/QUESTIONS.md` | see `analytics/README.md` |
| Function-calling agent + agent evals | `AI/agent-lab/` | `agent-lab/NOTES.md` | `.venv/bin/python -m evals deterministic` |
| Coding drills (TS + Python) | `AI/interviews/devrev-fde/drills/` | `drills/DRILLS.md` | `npx vitest run` / `.venv/bin/pytest -q` |

## 5. Remaining plan — ownership, not building

1. **Rebuild from blank, timed:** each drill in `DRILLS.md`, TS first, then Python. Tick them in `STUDY.md` Round 6.
2. **Explain out loud, no code open (3 min each):** two-way sync flow, outbox → Debezium → Kafka, N+1 and the DataLoader, one agent turn.
3. **Stories:** read [`STAR.md`](STAR.md) out loud; correct anything that isn't how you remember it.
4. **Mock loop (tell me the real date):** TS coding, two-way sync design, decomposition case, behavioural.

Daily: 1 drill from blank alternating TS / Python; 10 min out loud on one `STUDY.md` question.

## 6. Positioning for this JD

Lead with: **"I integrate systems that don't agree with each other, and I put AI on top once the data is
trustworthy."** Then three proofs, one per lane:

1. **[P]** Workato/NetSuite invoices — real contract ≠ assumed contract, hardened, customer-facing errors, flagged
   rollout.
2. **[L]** streampulse / FieldSync — outbox + CDC + idempotent consumers + conflict handling.
3. **[P]+[L]** Ask AI → Agent Console — production RAG, then evals that caught two real bugs.

Keep the two-lane rule from [`../../docs/notes/STUDY-GUIDE.md`](../../docs/notes/STUDY-GUIDE.md) §4: never imply
lab work shipped to customers.
