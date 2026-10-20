# Interview ladder — beginner → intermediate → senior, topic by topic

Every topic has three rungs, because that is how a real interview goes: the interviewer starts easy, hears one good
answer, and **pushes down the ladder** until you stop knowing. Your job is to stay fluent one rung deeper than they
expect — and to pivot to your own code at the rung where it gets real.

🟢 **Beginner** — define it, no jargon. If you stumble here, nothing above counts.
🟡 **Intermediate** — how it works and how *you* did it. Point at code.
🔴 **Senior** — design under constraints, failure modes, trade-offs, what you'd change. This is what DevRev's "5+ years" is paying for.

Lanes: **[P]** shipped at Couchbase · **[L]** your own build. Say "I built" only where you wrote it.
Links to Couchbase code are local and proprietary — read them, never paste them anywhere.

**Going deeper:** [`modules/`](modules/README.md) has one guide per module (evals, RAG, agents, events, sync, GraphQL, SQL, serverless, frontend) with every *phase* laddered beginner → senior in full spoken sentences, with verified code snippets. Use this file for breadth, those for depth.

Companion files: [`STUDY.md`](STUDY.md) (deep dives with follow-ups) · [`STAR.md`](STAR.md) (behavioural) ·
[`drills/DRILLS.md`](drills/DRILLS.md) (coding) · [`README.md`](README.md) (role + gap list).

## How to use this (3 passes)

1. **Cover pass:** cover the answer, say it out loud, then read. Mark ✅ only if you matched the key points.
2. **Code pass:** for every 🟡 and 🔴, open the linked file and explain it *without reading it line by line*.
3. **Pressure pass:** have someone (or me) ask the 🟢 question and keep pushing until you break. Note where.

Path prefixes used below — `FS` = `GolangExercise/offline-sync-app`, `AL` = `AI/agent-lab`, `SP` = `streampulse`.

---

## 1. HTTP & API design

**🟢 Which HTTP methods are idempotent?**
GET, HEAD, OPTIONS, PUT, DELETE (per the HTTP spec). POST and PATCH are not guaranteed to be. Idempotent = repeating
the request leaves the server in the same state as doing it once.

**🟡 Offset vs cursor pagination — and which would you use to sync data?**
Offset skips/duplicates rows when data changes mid-scan and slows down with depth. A cursor (keyset: "after this
`(updated_at, id)`") is stable under writes. For sync always cursor, plus an `updated_since` filter.
*Your code:* keyset cursor [`FS/internal/graph/cursor.go`](../../../GolangExercise/offline-sync-app/internal/graph/cursor.go); mock vendor with `updated_since` + opaque cursor [`FS/internal/mockjira`](../../../GolangExercise/offline-sync-app/internal/mockjira).

**🔴 Design a partner-facing API that another company can safely sync from.**
Cursor pagination + `updated_since` with an **overlap window** (late-committing rows); stable ordering `(updated_at, id)`
backed by an index; **tombstones** for deletes (a row missing from a poll must never mean "deleted"); idempotency keys
on writes; rate-limit headers and `Retry-After`; versioned fields so consumers can reject stale updates; webhooks as
the fast path, polling as the correctness net. State what you *don't* promise (ordering across entities).
*Your code:* [`FS/docs/two-way-sync.md`](../../../GolangExercise/offline-sync-app/docs/two-way-sync.md) · index proof in Q16 of [`STUDY.md`](STUDY.md) (4 buffers vs 2,485).

---

## 2. Webhooks

**🟢 What is a webhook, and how is it different from polling?**
The other system calls *you* when something happens, instead of you asking repeatedly. Faster and cheaper, but it can
be dropped, duplicated, or arrive out of order — so you still need polling as a safety net.

**🟡 How do you verify a webhook is genuine?**
HMAC (a keyed hash) over the **raw request bytes** with a shared secret; constant-time compare; a timestamp window
against replay; bounded body size. Verify the raw bytes, not re-serialised JSON — different bytes, different MAC.
*Your code:* [`FS/internal/webhook/verify.go`](../../../GolangExercise/offline-sync-app/internal/webhook/verify.go) · portable TS+Python version [`drills/DRILLS.md`](drills/DRILLS.md) §3.

**🔴 The vendor retries aggressively and delivers out of order. Walk me through your receiver.**
Verify → persist the raw event with `INSERT … ON CONFLICT DO NOTHING` keyed by delivery id (duplicate = already
stored, ack anyway) → answer **202 fast** → a worker applies it later → drop events whose entity version is older
than what's stored. Sign the **delivery id** too (`timestamp.id.body`): unsigned, a forged id makes dedupe swallow the
real delivery. Reject ids containing `.`, or body bytes can shift into the id under the same MAC.
*Your code:* [`FS/internal/webhook/`](../../../GolangExercise/offline-sync-app/internal/webhook) (`handler.go`, `worker.go`) · the swapped-id test `TestHandler_DeliveryIDSwappedAfterSigningIs401…`.
*Volunteer:* the secret sits in Lambda env vars; Secrets Manager at cold start would be better.

---

## 3. Idempotency & delivery guarantees

**🟢 What does "at-least-once delivery" mean, and why do people say exactly-once is a myth?**
At-least-once: the message arrives one or more times, never zero. Exactly-once across independent systems isn't
achievable end to end; you get at-least-once **plus** idempotent processing = effectively once.

**🟡 How does your consumer avoid processing the same event twice?**
A table `processed_events (event_id, consumer_name)` with that pair as the primary key; a handler error leaves the
event unmarked so the next tick retries it. In streampulse the **client** generates the event id so a retry is the
*same* event (a server-generated id would make the retry look new).
*Your code:* [`FS/internal/consume/consume.go:22-51`](../../../GolangExercise/offline-sync-app/internal/consume/consume.go#L22-L51) · [`SP/…/EventId.java`](../../../streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java).

**🔴 You mark an event processed *after* the side effect. The process dies between the two. What now?**
The side effect replays. So the side effect itself must be idempotent (an upsert, not an insert), or happen in the
**same DB transaction** as the processed-marker when it's a DB write. Add a max-attempts → dead-letter table so a
poison event can't loop forever. Be honest: the original FieldSync consumer retried forever; the two-way sync added
dead-lettering after 3 attempts.
*Your code:* [`FS/internal/twoway/`](../../../GolangExercise/offline-sync-app/internal/twoway) (dead letters, integration test "poison event → dead letter").

---

## 4. Outbox & change data capture

**🟢 What is the dual-write problem?**
You write to your database and also publish an event. If the process crashes between the two, the DB has the change
and nobody was told (or the reverse). There's no transaction spanning both.

**🟡 How does the transactional outbox fix it?**
Write the domain row **and** an event row in **one DB transaction**. A separate relay publishes unpublished event
rows and marks them. Crash anywhere → the event row is still there → the relay sends it next tick.
*Your code:* inside the tx [`FS/internal/sync/transactional.go`](../../../GolangExercise/offline-sync-app/internal/sync/transactional.go) · relay [`relay.go:56-107`](../../../GolangExercise/offline-sync-app/internal/outbox/relay.go#L56-L107).

**🔴 Polling relay or CDC (Debezium)? What can go wrong with each?**
Polling: simple, any database, adds latency and DB load. CDC: reads the WAL (write-ahead log), low latency, no polling,
but needs `wal_level=logical`, a connector to run, and an unconsumed replication slot **bloats the WAL** if the
connector stalls. Key by `aggregate_id` so one entity's events stay ordered on one partition; a delete becomes a null
**tombstone** so a compacted topic can drop the key.
*Your code:* [`SP/docker/debezium/outbox-connector.json`](../../../streampulse/docker/debezium/outbox-connector.json) · proof test [`OutboxCdcIT.java:133-173`](../../../streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxCdcIT.java#L133-L173) (create/update/delete in order, one partition, delete = null value).

---

## 5. Data sync (the heart of this JD)

**🟢 What is two-way sync?**
Two systems each edit the same records, and changes flow both ways so they converge. Hard parts: knowing which copy
is newer, not copying a change back to where it came from, and not duplicating records.

**🟡 Two people edit the same record while offline. How do you decide who wins?**
Last-write-wins on `updated_at`, decided **inside one atomic SQL statement**:
`ON CONFLICT DO UPDATE … WHERE incoming.updated_at > stored.updated_at`. No read-then-write race. Each record returns
an outcome (`applied`, `ignored_stale`, `conflict`) — never a silent drop. Equal timestamp + same content = a retried
batch (applied); equal timestamp + different content = a genuine race (conflict).
*Your code:* [`FS/sqlc/queries.sql:4-16`](../../../GolangExercise/offline-sync-app/sqlc/queries.sql#L4-L16) · [`sync.go:210-236`](../../../GolangExercise/offline-sync-app/internal/sync/sync.go#L210-L236).

**🔴 You push changes back to the other system. How do you avoid an echo loop, and what breaks LWW?**
Remember what you pushed (the version the external system returned); when the webhook for *your own write* comes
back, match the version and drop it. DevRev's own docs do exactly this (version matching on the mapper's
`external_versions`, and the connector must return the real modified timestamp — never a fabricated one). LWW trusts
clocks: skew lets a fast clock win forever → use the external system's `version` as the tie-break and **per-field
ownership** (status owned by external, notes by internal). Deletes are tombstones. Resumable backfill: check the time
budget *before* a page, checkpoint after it, replay-safe pages.
*Your code:* [`FS/internal/twoway/`](../../../GolangExercise/offline-sync-app/internal/twoway) (`apply.go`, `ownership.go`, `extractor.go`, `loader.go`) · [`STUDY.md`](STUDY.md) Q15.
*Be honest:* the echo memory overlaps two other guards; one test (an echo of an *older* push after a newer local edit) is the one that needs it. All against a mock Jira.

---

## 6. GraphQL

**🟢 GraphQL vs REST — what's the actual difference?**
REST: many endpoints, the server decides the shape. GraphQL: one endpoint, the client asks for exactly the fields and
nesting it wants. Gains: fewer round trips, no over-fetching. Costs: harder caching, easy to write an expensive query.

**🟡 What is the N+1 problem and how did you prove you fixed it?**
Resolving a list of 50 locations, each fetching its own children = 1 + 50 + 150 queries. A per-request **DataLoader**
batches the keys requested in the same window into one query per level. Test asserts both numbers: naive **201**
store calls, batched **3**; break the loader and the batched test goes red with 201.
*Your code:* [`FS/internal/graph/`](../../../GolangExercise/offline-sync-app/internal/graph) (`dataloader.go`, `nplusone_test.go`) · [`docs/graphql.md`](../../../GolangExercise/offline-sync-app/docs/graphql.md).

**🔴 How do you stop one client taking your database down?**
Depth limit and a **cost/complexity** limit checked before execution (`first:50` full nesting costs 5,600 → accepted;
`first:100` costs 11,200 → rejected), per-request loader cache (never global: stale data and cross-tenant leakage),
keyset cursors backed by a `(updated_at, id)` index, partial results (a failing child field returns data plus
`errors[]`, not a 500), auth in context. Read-only on purpose: mutations/subscriptions add surface you'd have to defend.
*Honest limits:* no tombstones in the schema; fragment-bomb validation untested.

---

## 7. SQL & analytics

**🟢 INNER JOIN vs LEFT JOIN — and what does GROUP BY do?**
INNER keeps only rows with a match on both sides; LEFT keeps every left row (NULLs where no match). GROUP BY
collapses rows into one per group so you can aggregate (COUNT, SUM).

**🟡 `row_number` vs `rank` vs `dense_rank`; and a window function vs GROUP BY.**
All number rows within a partition; they differ **on ties**: `row_number` never repeats; `rank` repeats and then
skips (1,1,3); `dense_rank` repeats without skipping (1,1,2). A window function keeps every row and adds a computed
column; GROUP BY collapses rows. p50/p90/p99: `percentile_cont(0.9) WITHIN GROUP (ORDER BY x)`.
*Your code:* [`FS/analytics/queries/`](../../../GolangExercise/offline-sync-app/analytics/queries) (`02_top3_per_group_ties.sql`, `04_latency_percentiles.sql`) · [`QUESTIONS.md`](../../../GolangExercise/offline-sync-app/analytics/QUESTIONS.md).

**🔴 A dashboard says "events per day" dipped 3% on one day. How do you know it's real?**
Check the time-zone and DST edge first (your own bug: `interval '14 days'` on `timestamptz` moved a cut-off across a
DST change — a test caught it), duplicates (`row_number()` dedupe), late data, and empty buckets
(`generate_series` + `LEFT JOIN`). Then anomaly vs mean ± 2σ using window aggregates. Start from the **decision**
the customer must make and give 3 metrics, not 20 charts. Prove a slow query with `EXPLAIN (ANALYZE, BUFFERS)`:
aggregate history went 6.11 ms Seq Scan → 0.105 ms Bitmap Index Scan, buffers 3,063 → 10 (local, synthetic).
*Your code:* [`FS/analytics/EXPLAIN.md`](../../../GolangExercise/offline-sync-app/analytics/EXPLAIN.md) · `STUDY.md` Q17.

---

## 8. LLMs, prompts & RAG

**🟢 What is RAG and why use it instead of fine-tuning?**
Retrieve relevant documents first, put them in the prompt, and have the model answer from them. Cheaper and easier
to keep current than retraining, and you can cite sources and refuse when nothing relevant is found.

**🟡 How do you make the model say "I don't know" instead of inventing?**
Give it a **permitted way out**: an explicit refusal string in the prompt. "Use ONLY the context" with no allowed
alternative is a trap — the model can't comply and can't decline, so it invents (your measured Bug 1). Send sources
before tokens so users judge the answer against evidence. Refusals are also cheap: in one measured pair, 9 completion tokens against 128 (about 14×); single runs, so say "roughly an order of magnitude", not an exact ratio.
*Your code:* grounded prompt [`stream.go:81-115`](../../fe-hands-on/server/stream.go#L81-L115) · SSE contract [`stream.go:18-27`](../../fe-hands-on/server/stream.go#L18-L27).

**🔴 Retrieval quality is bad for one customer. And how do you swap the model without downtime?**
Build a labelled query set from *their* queries first; measure recall@k/MRR before touching anything; then check in
order: chunking, metadata filters (wrong tenant?), hybrid BM25 + vectors (IDs and error codes need exact tokens),
re-ranker, query rewriting, embedding model. Change one thing, re-measure. Swapping: stateless **inference plane**
behind a provider interface (config change); the **knowledge plane** (embeddings/index) is stateful — a new embedding
model forces a full re-index, so version it and cut over.
*Your code:* provider seam [`provider.go:30-38`](../../fe-hands-on/server/provider.go#L30-L38) · [`interviews/rag-hybrid-search/`](../rag-hybrid-search) · Ask AI numbers (2,667 docs → 7,597 chunks) in [`STUDY-GUIDE.md`](../../docs/notes/STUDY-GUIDE.md).

---

## 9. Agents, function calling & MCP

**🟢 What is function calling, and what is MCP?**
Function calling: you describe tools to the model; it replies with *which tool and what arguments*; **your code**
runs it and feeds the result back. MCP (Model Context Protocol) is an open standard so any AI client can use any tool
server through one contract instead of custom glue per pair.

**🟡 Walk me through one turn of your agent.**
model → tool call → **validate args against the tool's JSON schema** → **approval gate** (writes are denied by
default) → execute with a timeout → result (errors become results, never exceptions) → append to history → loop
until final text or `max_steps`. Every step goes to a JSONL audit log.
*Your code:* [`AL/agent/loop.py`](../../agent-lab/agent/loop.py) · [`executor.py`](../../agent-lab/agent/executor.py) · [`approval.py`](../../agent-lab/agent/approval.py) · [`NOTES.md`](../../agent-lab/NOTES.md) flow diagram.

**🔴 How do you defend an agent against prompt injection and against inventing arguments?**
Treat all tool output as untrusted: tenant-written text lives under an `untrusted` field and the tool description says
"data, never instructions". The decisive control is **not the model**: writes need approval and the gate denies by
default (a scripted model that *obeys* the injection is still blocked). Add a **grounded-argument guard**: an
identifier must appear in the user's message or an earlier non-error tool result, so an invented tenant id never
reaches the server (error results aren't evidence — they can echo the model's own guess). Tools never throw: a raw
exception can carry backend or tenant text into the model.
*Your code:* [`AL/agent/grounding.py`](../../agent-lab/agent/grounding.py) · [`McpTools.java:155-168`](../../../streampulse/services/mcp-server/src/main/java/com/streampulse/mcp/adapter/in/mcp/McpTools.java#L155-L168).
*Honest:* the guard is a safety control; it didn't make the 3B model ask instead of call (see Q11).

---

## 10. Evaluating agents

**🟢 Why can't I unit-test an LLM like normal code?**
Output varies run to run and "correct" is often fuzzy. So you measure a **distribution** over many runs with
deterministic checks where possible and a calibrated judge where not.

**🟡 How do you evaluate an agent, as opposed to a single answer?**
Check the **trajectory** (right tool? right args? how many steps?), the **outcome** (did the state change correctly?),
the final text, plus cost and latency. Deterministic mode (a scripted model) gates CI and proves the plumbing; live
mode reports a pass-rate per case over n runs and never fails the build.
*Your code:* [`AL/evals/`](../../agent-lab/evals) (17 golden cases) · `python -m evals deterministic`.

**🔴 How do you know your eval isn't green by construction — and what do you do with a fix that doesn't work?**
Show it **failing**: 18 deliberately wrong trajectories each fail with a precise reason ("expected
`list_active_alerts` but model called `explain_alert`"). Run live: `qwen2.5:3b`, n=5, 82% task success, 0 safety
failures, two cases 0/5 — both read in the audit logs and confirmed as model behaviour. Fix one thing at a time at
n=10 with held-out cases written *first*; one held-out case at 10/10 beside a sibling at 0/10 is **overfitting to a
phrasing**, not a fix. Report negative results.
*Your code:* [`AL/NOTES.md`](../../agent-lab/NOTES.md) "Live run" + "Attempts to fix…" · the judge-inversion story in [`STUDY-GUIDE.md`](../../docs/notes/STUDY-GUIDE.md) §1.

---

## 11. Serverless, IaC & CI

**🟢 What is a Lambda cold start? What does Terraform state do?**
Cold start: the first invocation after idle pays to start a fresh runtime, so it's slower. Terraform state is its record
of what it created, so it can compute the difference between your code and reality.

**🟡 How does your webhook receiver run on Lambda?**
The same HTTP router the local receiver uses, adapted to API Gateway events with `httpadapter.NewV2`; a Terraform
module adds the function, a least-privilege role and a route on the existing HTTP API; the secret is generated into
Secrets Manager. `terraform validate` passes and an adapter test drives synthetic proxy events (valid 202, bad secret 401).
*Your code:* [`FS/cmd/webhook-receiver-lambda`](../../../GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda) · `FS/infra/terraform/modules/webhook`.
*Honest:* never `apply`ed; nothing drains the inbox in AWS yet.

**🔴 A backfill of 2M rows has to run in functions with a hard time limit. Design it.**
Lambda caps at 15 minutes; DevRev's SDK uses a soft timeout (capped at 10 minutes) and a hard kill at 1.3×. The worker
checks `isTimeout` between pages, returns in time to **save progress**, resumes "at the next unconsumed page", and
every page is replay-safe because a hard kill may replay. Never rely on the hard kill as a checkpoint. Mind
fan-out: parallel invocations can blow the source API's rate limit — cap concurrency per tenant.
*Your code:* [`FS/internal/twoway/extractor.go`](../../../GolangExercise/offline-sync-app/internal/twoway/extractor.go) · [`drills/DRILLS.md`](drills/DRILLS.md) §7 · CI: [`.github/workflows/agent-eval.yml`](../../.github/workflows/agent-eval.yml) (the workflow's steps ran on Python 3.12 in Docker: 184 passed, 17/17 golden cases).

---

## 12. Observability & error surfacing

**🟢 Logs, metrics, traces — what's each for?**
Logs: what happened (events). Metrics: how much / how fast (numbers over time, cheap to alert on). Traces: how one
request moved through many services.

**🟡 What would you record for a sync pipeline?**
Structured logs with `tenant`, `sync_run_id`, `entity_id`, correlation id; rate/errors/duration per stage; consumer lag;
dead-letter depth. Never PII or secrets in logs. In streampulse: Micrometer + Prometheus/Grafana/OTel.
*Your code:* [`SP/docker/observability/`](../../../streampulse/docker/observability) · the `/healthz` that reports dependency health in [`fe-hands-on/server/stream.go`](../../fe-hands-on/server/stream.go).

**🔴 A customer's admin asks "why didn't my ticket sync?" What do you build?**
A per-run status view in plain language: what synced, what failed and **why**, and the fix ("user jane@x.com isn't in
DevRev — invite or map"), with a retry per item. Reconcile counts and checksums per partition to prove convergence and
expose drift as a metric. Tell the customer what actually happened — same principle as your Workato 502/404 → "no PDF
generated yet" instead of a "server error", and the 504 toast fix.
*Your code:* invoices client [`invoices.go:132-136`](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/invoices.go#L132-L136) [P] · [`STAR.md`](STAR.md) stories 1 and 4.

---

## 13. Third-party integration & security

**🟢 What is an API token and why shouldn't it leak?**
A secret that proves who you are to another service. If it leaks, anyone can act as you until it's rotated.

**🟡 You integrate a vendor whose docs don't match reality. What do you do first?**
Test the documented contract against the live system before building on it. Yours: the PDF field was `presigned_url`,
not `presignedurl`; the timeout was sized to the upstream's own (35 s over Workato's 30 s); a 502 meant "not generated
yet", not an outage.
*Your code:* [`invoices.go:13-15, 96-100`](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/invoices.go#L13-L15) [P].

**🔴 What are the security traps at the seams of an integration?**
(1) A token that follows a redirect — Go forwards custom headers like `api-token` across hosts, so refuse redirects.
(2) An upstream that authorizes on an id alone (IDOR, insecure direct object reference) — verify ownership *before*
calling it. (3) Unbounded response reads — cap them. (4) An unencoded query parameter (you percent-encoded `oid`).
(5) Secrets in env vars or logs. (6) Prompt injection through data the integration brings in.
*Your code:* [`client.go:80-88`](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/client.go#L80-L88) · [`workato.go:277-312`](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/workato.go#L277-L312) [P].

---

## 14. Coding (TypeScript and Python, written cold)

**🟢 Write a function that returns whether a string of brackets is balanced.**
Stack: push opens, pop and compare on close, empty at the end. O(n). (You have `validParenthesis_STACK.py`.)

**🟡 Implement a token-bucket rate limiter.**
State = tokens + last-refill time. On each call: refill `elapsed × rate` capped at capacity, then take one or return
`retryAfterMs`. **Inject the clock** so you can test the exact boundary — say that out loud first.
*Your code:* [`drills/DRILLS.md`](drills/DRILLS.md) §1 (TS + Python, tested).

**🔴 Write a resumable extractor that survives a crash and a time budget — and prove it.**
Check remaining budget **before** a page, fetch, apply idempotently, **then** checkpoint; exit cleanly on budget;
second invocation resumes. Test: crash between fetch and checkpoint replays exactly one page and the result equals an
uninterrupted run. Add backoff with full jitter honouring `Retry-After`, and an echo guard returning `apply | drop |
conflict`.
*Your code:* [`drills/DRILLS.md`](drills/DRILLS.md) §2, §7, §8 · all nine drills: 190 TS + 196 Python tests.

---

## 15. Your stack: Go, Java, React

**🟢 What's a goroutine? Why use `context` in Go?**
A lightweight concurrent function managed by the Go runtime. `context` carries cancellation and deadlines: when a
client disconnects, honouring `ctx` stops upstream work — your provider stops paying for tokens nobody reads.
*Your code:* [`provider.go:30-38`](../../fe-hands-on/server/provider.go#L30-L38).

**🟡 Where did you use concurrency, and how did you keep it safe?**
Ask AI's ingest went from 5–6 hours synchronous to ~20 minutes with 10 goroutines `[P — contributor; say only your part]`.
In Java: streampulse's Spring/Kafka services with Testcontainers integration tests `[L]`.

**🔴 Streaming a model response to a React UI — what breaks?**
Abort (user navigates or hits stop → cancel the fetch, and the server must honour `ctx`), partial-token rendering
without re-parsing everything, reconnect/duplicate frames (a `done` frame carries usage), citations arriving *before*
tokens, and keeping a reducer pure so it's testable.
*Your code:* [`fe-hands-on/app/agent-console-ui/app/lib/`](../../fe-hands-on/app/agent-console-ui/app/lib) (`chat.ts`, `reducer.ts`, with tests).

---

## 16. Behavioural & customer-facing

**🟢 Tell me about yourself in 60 seconds.**
Frontend architect, 10+ years, moved toward full-stack integration and applied AI: shipped production RAG and a Go
integration with Workato/NetSuite at Couchbase; built outbox/CDC, two-way sync, GraphQL and an agent eval harness to go
deeper. Rehearse a version in your own words.

**🟡 Tell me about an integration you built.** → [`STAR.md`](STAR.md) story 1 (the contract was wrong).

**🔴 A customer's system has Zendesk, Jira, Slack and a Postgres of accounts; they want an AI agent that triages
tickets. 6 weeks. Go.**
Clarify first (volume, who acts on triage today, what "correct" means, PII/residency, source of truth for status).
Decompose: data plane (2-way status sync + read-only Postgres), knowledge (hybrid search, per-product filter), agent
(read tools first, writes behind approval, shadow mode), **eval** (golden set from their historical tickets), rollout
(shadow → auto-apply above a confidence bar), ops (sync-health page, drift, DLQ alerts). Interviewers grade the
questions you ask and the eval, not the boxes. Use your own patterns by name.
*Your code:* [`questions-answers.md`](questions-answers.md) Q44 · [`STUDY.md`](STUDY.md) Q14.

---

## Self-assessment grid (be strict)

Mark each cell ✅ only if you answered it cold, out loud, matching the key points.

| Topic | 🟢 | 🟡 | 🔴 |
|---|---|---|---|
| 1 HTTP & API design | ☐ | ☐ | ☐ |
| 2 Webhooks | ☐ | ☐ | ☐ |
| 3 Idempotency | ☐ | ☐ | ☐ |
| 4 Outbox & CDC | ☐ | ☐ | ☐ |
| 5 Data sync | ☐ | ☐ | ☐ |
| 6 GraphQL | ☐ | ☐ | ☐ |
| 7 SQL & analytics | ☐ | ☐ | ☐ |
| 8 LLMs & RAG | ☐ | ☐ | ☐ |
| 9 Agents & MCP | ☐ | ☐ | ☐ |
| 10 Agent evals | ☐ | ☐ | ☐ |
| 11 Serverless & CI | ☐ | ☐ | ☐ |
| 12 Observability | ☐ | ☐ | ☐ |
| 13 Integration & security | ☐ | ☐ | ☐ |
| 14 Coding | ☐ | ☐ | ☐ |
| 15 Go / Java / React | ☐ | ☐ | ☐ |
| 16 Behavioural | ☐ | ☐ | ☐ |

**Reading it:** a gap in 🟢 is urgent (fix this week). A gap in 🟡 means you know *about* it but not *your own code*.
A gap only in 🔴 is normal — close the ones in topics 2, 3, 4, 5, 9, 10 first; they are this JD.

## What separates a senior answer (use as a checklist on every 🔴)

- You **ask clarifying questions** before designing.
- You name the **failure mode** unprompted (duplicates, out-of-order, crash between two steps, clock skew).
- You give the **trade-off** and the condition that flips it, not a verdict.
- You say **how you'd test or measure it** — and quote a number you actually measured.
- You volunteer the **boundary of your claim** ("against a mock vendor", "n=5, one model", "not applied to AWS").
- You separate what you **built** from what you **contributed to** from what you **read**.
