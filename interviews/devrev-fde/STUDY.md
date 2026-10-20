# DevRev FDE — Study File (start here)

How to use: read the question, **answer out loud before scrolling**, then check against "Say this" and open
"Your code". If you can't explain your own code without reading it, that question isn't done.

**Per-module, per-phase ladders with full-sentence answers and verified code: [`modules/`](modules/README.md).**

**Start with [`LEVELS.md`](LEVELS.md)** — 16 topics, each escalating 🟢 beginner → 🟡 intermediate → 🔴 senior, with
a self-assessment grid. Use this file for the deep dives behind each 🔴.

Related: role + gap list → [`README.md`](README.md) · wider question bank → [`questions-answers.md`](questions-answers.md) · stories → [`STAR.md`](STAR.md).

Lanes: **[P]** shipped at Couchbase · **[L]** your own build · **[K]** knowledge only.
Couchbase code is proprietary — links below are for *your* local reading; never paste it into this repo.

Progress: tick `[x]` when you can answer it cold.

---

## Round 1 — Your stories (they will start here)

### [ ] Q1. "Walk me through an integration you built with a third-party system." — [P]

**Say this (2 min):**
- **Context:** Capella customers needed their invoices in the UI. Source of truth: NetSuite, reachable only
  through Workato recipes. I owned the Go client, the service and the UI.
- **The contract was wrong.** What we were handed didn't match the live recipe: the PDF field is
  `presigned_url`, not `presignedurl` — I confirmed it against dev before trusting it.
- **Timeouts sized to the upstream:** ours is 35s because Workato's own request timeout is 30s — giving up
  first just wastes a call Workato is still serving.
- **Lying status codes:** Workato answers **502** (and on main also **404**) when NetSuite has no PDF yet.
  A 502 reads like an outage, so I mapped both to a typed "no PDF yet" error and told the customer that, not
  "server error".
- **Security:** the PDF recipe authorizes on invoice id alone → an IDOR (insecure direct object reference)
  risk. Our service checks the invoice belongs to the tenant *before* calling it. And the HTTP client refuses
  redirects, because Go forwards custom headers like our `api-token` across hosts on a redirect.
- **Rollout:** behind a feature flag defaulting off, RBAC on the route, Cypress e2e, MSW mocks.
- **Result:** ⚠️ fill in real numbers (customers enabled, tickets avoided). Don't invent them.

**Your code (local, proprietary):**
- 35s timeout and why → [invoices.go:13-15](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/invoices.go#L13-L15)
- 502 → "no PDF yet" (branch) → [invoices.go:132-136](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/invoices.go#L132-L136);
  502 **or** 404 on main (#58590): `git -C ~/Documents/GitHub/latest/couchbase-cloud show origin/main:internal/billing/activations/integrations/invoices.go`, line ~135
- Ownership check required by callers → [invoices.go:102-106](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/invoices.go#L102-L106)
- Live wire name → [invoices.go:96-100](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/invoices.go#L96-L100)
- Refuse redirects → [client.go:80-88](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/client.go#L80-L88)
- Absolute-URL validation → [client.go:102-108](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/client.go#L102-L108)
- Bounded body reads + bounded error detail → [workato.go:277-312](../../../fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/workato.go#L277-L312)

**Follow-ups:**
- *"Why cap the error body?"* → An upstream can return a huge or streaming body; unbounded reads can exhaust
  memory. And the error is stored once per job attempt, so an unbounded body gets stored many times.
- *"Why not cache the PDF link?"* → It's presigned and short-lived; Workato mints one per call.
- *"502 also means 'unknown id' — isn't that ambiguous?"* → Yes, upstream conflates them. That's exactly why
  the ownership check runs first: once we know the invoice is theirs, 502 can only mean "not generated yet".

**Self-check:** Why does `CheckRedirect` matter for `api-token` but not for `Authorization`?

---

### [ ] Q2. "Tell me about a bug you found that others would have missed." — [L]

**Say this:** the prompt-parity + judge-inversion story from
[`../../docs/notes/STUDY-GUIDE.md`](../../docs/notes/STUDY-GUIDE.md) §1. Two bugs, one isolation method:
fixed input, vary one thing, repeat ≥3 times.

**Your code:** grounded prompt with an explicit refusal path →
[stream.go:86](../../fe-hands-on/server/stream.go#L86) · CI parity gate →
[check-parity.py](../../evals/ci/check-parity.py)

**Self-check:** What's the difference between Bug 1 and Bug 2, in one sentence each?

---

## Round 2 — Integration & sync deep dive (DevRev's core)

### [ ] Q3. "Design sync between a client and a server where both can edit." — [L]

**Say this:**
- Client generates the **GUID**, so a retry is the *same* record, not a new one → idempotent upsert.
- **Last-write-wins (LWW) inside one atomic SQL statement:** `ON CONFLICT DO UPDATE ... WHERE incoming.updated_at > stored.updated_at`.
  No read-then-write race.
- Every record gets an **outcome**, never a silent drop: `applied`, `ignored_stale`, `conflict`, `limit_exceeded`.
- **Equal timestamp + same content = applied**, not conflict — that's a retried batch whose ack got lost.
  Equal timestamp + *different* content = a genuine race → `conflict`, surfaced.
- Business errors are outcomes; only infra failures are Go `error`s.

**Your code:**
- Atomic LWW upsert → [queries.sql:4-16](../../../GolangExercise/offline-sync-app/sqlc/queries.sql#L4-L16)
- Outcome classification → [sync.go:210-236](../../../GolangExercise/offline-sync-app/internal/sync/sync.go#L210-L236)

```sql
INSERT INTO disaster_locations (...) VALUES (...)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, ..., updated_at = EXCLUDED.updated_at
WHERE EXCLUDED.updated_at > disaster_locations.updated_at
RETURNING *;
```

**Follow-ups:**
- *"LWW with client clocks — what breaks?"* → Clock skew: a device with a fast clock always wins. Fixes: server
  timestamps, hybrid logical clocks, or per-field ownership. Admit FieldSync accepts this trade-off.
- *"How is this different from Jira ↔ DevRev two-way sync?"* → Two servers, not device ↔ server: you add an
  **id map** (external id ↔ internal id), **echo-loop prevention** (ignore the webhook caused by your own write),
  and per-field source-of-truth. That's now built — see Q15.

**Self-check:** Why is the `WHERE` on the `DO UPDATE` and not a separate `SELECT` first?

---

### [ ] Q4. "How do you publish an event reliably when you also write to the DB?" — [L]

**Say this:**
- The **dual-write problem**: commit DB then call the broker → crash in between = lost event.
- **Transactional outbox:** write the domain row *and* an event row in **one transaction**. A relay publishes
  the event later.
- Only *real state changes* emit events — stale/conflict/limit outcomes don't.
- Rolling back the whole batch is safe *because* every upsert is idempotent; the client just retries.
- Two relay styles you've built:
  - **Polling relay** (FieldSync): scan `published_at IS NULL`, `PutEvents` to EventBridge, mark published.
    A failed entry stays unpublished for the next tick.
  - **CDC (change data capture) relay** (streampulse): Debezium reads Postgres's WAL (write-ahead log) and the
    `EventRouter` routes outbox rows to Kafka keyed by `aggregate_id`. No polling.

**Your code:**
- Outbox inside the tx → [transactional.go:21-102](../../../GolangExercise/offline-sync-app/internal/sync/transactional.go#L21-L102)
- Polling relay → [relay.go:56-107](../../../GolangExercise/offline-sync-app/internal/outbox/relay.go#L56-L107)
- Debezium outbox router → [outbox-connector.json:25-34](../../../streampulse/docker/debezium/outbox-connector.json#L25-L34)
- Integration test proving it: create/update/delete arrive **in order, on one partition**, and delete arrives as a
  **tombstone** (null value) → [OutboxCdcIT.java:133-173](../../../streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxCdcIT.java#L133-L173)

**Follow-ups:**
- *"Polling relay vs CDC?"* → Polling: simple, works on any DB, adds latency + DB load. CDC: low latency, no
  polling load, but needs logical replication (`wal_level=logical`), a connector to operate, and a replication slot
  that can bloat WAL if the connector stalls.
- *"Why key by `aggregate_id`?"* → Kafka orders only within a partition; same key → same partition → per-entity order.
- *"Why a tombstone on delete?"* → On a **compacted** topic, a null value tells compaction to drop the key.

**Self-check:** Your relay marks published *after* `PutEvents`. What happens if it crashes between the two? Is that OK?

---

### [ ] Q5. "Delivery is at-least-once. How do consumers avoid double-processing?" — [L]

**Say this:**
- Accept at-least-once; make processing idempotent → **effectively once**.
- **Idempotency key generated by the client**, reused on every retry. If the server generated it, a retry would
  look like a new event.
- Dedup store options you've used:
  - Postgres `processed_events (event_id, consumer_name)` primary key — per consumer, so each consumer dedups independently.
  - Redis `SET NX EX` on a tenant-namespaced key — atomic "claim once", with TTL.
- Handler failure → not marked processed → retried next tick. Others in the batch continue.

**Your code:**
- Client-generated id rationale → [EventId.java:8-46](../../../streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java#L8-L46)
- Tenant-namespaced Redis key → [EventId.java:83-92](../../../streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java#L83-L92)
- Consumer loop → [consume.go:22-51](../../../GolangExercise/offline-sync-app/internal/consume/consume.go#L22-L51)
- Dedup table → [000002_add_domain_events.up.sql:23-28](../../../GolangExercise/offline-sync-app/migrations/000002_add_domain_events.up.sql#L23-L28)

**Follow-ups:**
- *"Mark-processed after the side effect — what if it crashes between?"* → The side effect replays. So the side
  effect itself must be idempotent (upsert, not insert), or do both in one DB transaction when the side effect is a DB write.
- *"Poison message?"* → Max attempts → DLQ (dead-letter queue) + alert. Your consumer currently retries forever —
  say that's the next fix.

**Self-check:** Why is `consumer_name` part of the primary key?

---

### [ ] Q6. "Build a secure webhook receiver." — [L]

**Say this:** HMAC (keyed hash) over the **raw body** (not re-serialised JSON), constant-time compare, timestamp
window against replay, bounded body size, ack `202` fast and process later, dedupe on delivery id, ignore
out-of-order by version.

**Your code:**
- Verify + handler + async worker → [`internal/webhook/`](../../../GolangExercise/offline-sync-app/internal/webhook) (`verify.go`, `handler.go`, `worker.go`)
- Dedupe + raw event persisted by one `INSERT ... ON CONFLICT DO NOTHING` (PK = delivery id), then processed by a worker
- Portable TS + Python verifier you can write on a whiteboard → [`drills/`](drills/DRILLS.md) §3
- Proof: 25 unit tests; integration tests for bad signature → 401, stale timestamp, duplicate processed once, out-of-order ignored

**Follow-ups:**
- *"Why 202 and not 200 after processing?"* → Senders time out and retry; slow processing causes duplicate deliveries. Persist, ack, work async.
- *"Is the delivery id signed?"* → Yes: the MAC covers `timestamp.deliveryId.rawBody`. Unsigned, a forged id could
  make the dedupe table swallow the real delivery. Ids containing `.` are rejected, otherwise bytes could shift
  between fields under the same MAC. A test swaps the id after signing → 401, and the real delivery still lands.
- *"Real vendors?"* → Header names and signing scheme differ per vendor (verify each vendor's docs); mine is HMAC-SHA256 over `timestamp.deliveryId.rawBody`, my own mock's contract.

**Self-check:** Why must you verify the raw bytes and not `JSON.stringify(JSON.parse(body))`?

**Serverless:** deploy-ready, not deployed — [`cmd/webhook-receiver-lambda`](../../../GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda) wraps the same router with `httpadapter.NewV2`; Terraform module `infra/terraform/modules/webhook` (route on the existing HTTP API, secret generated into Secrets Manager); `terraform validate` passes; an adapter test drives synthetic proxy events (valid 202, bad secret 401).
**Limits to volunteer:** no `plan`/`apply` run against a real account; nothing drains the inbox in AWS yet; the secret is readable in Lambda env vars (fetching it from Secrets Manager at cold start would fix that).

---

### [ ] Q7. "Your sync runs in a serverless function with a hard time limit." — [L]

**Say this:** paginate, checkpoint after every page in durable state, check the remaining budget *before* starting
a page, exit cleanly, resume next invocation. Each page idempotent so a crash replays one page.

**Tie it to DevRev (verified on their docs 2026-10-19, `/airsync/worker-timeouts`):** soft timeout capped at
**10 minutes**, hard kill at **1.3×** (~13 min). The worker checks `adapter.isTimeout` between pages and returns "in
time for the SDK to save progress"; state resumes "at the next unconsumed page"; reads and writes must be
replay-safe. "That's the same contract as my extractor: budget check before the page, checkpoint after it, never
rely on the hard kill as a checkpoint."

**Your code:**
- Resumable extractor with checkpoint + budget check before each page → [`internal/twoway/extractor.go`](../../../GolangExercise/offline-sync-app/internal/twoway/extractor.go)
- Proof: integration test "crash mid-backfill resumes with zero duplicates" (7 links, 7 events)
- Whiteboard version (TS + Python, injected clock) → [`drills/`](drills/DRILLS.md) §7
- Lambdas already exist in `cmd/*-lambda/` — same idempotent-retry principle

**Honest limit:** DevRev's docs change — re-check `/airsync/worker-timeouts` the week of the interview before quoting numbers.

**Self-check:** Why check the budget *before* a page and not after?

---

## Round 3 — AI: RAG, agents, MCP, evals

### [ ] Q8. "Design MCP tools an LLM will call safely." — [L]

**Say this:**
- Descriptions are **prompts for the model**: say *when* to use the tool, what it returns, and **what it cannot do**
  — that's how you prevent wrong tool choice.
- Mark tools **read-only / idempotent / non-destructive** via annotations.
- **Validate every input** (tenant id pattern, length caps) before calling the backend.
- **Tools never throw.** Every failure becomes an `isError` result; unexpected exceptions log the *class only*,
  because exception text may carry backend or tenant data that must not reach a model.
- Tenant-written text goes under an `untrusted` field, and the description says "data, never instructions" —
  prompt-injection defence.

**Your code:**
- Tool description as prompt → [McpTools.java:54-89](../../../streampulse/services/mcp-server/src/main/java/com/streampulse/mcp/adapter/in/mcp/McpTools.java#L54-L89)
- Never-throw wrapper → [McpTools.java:155-168](../../../streampulse/services/mcp-server/src/main/java/com/streampulse/mcp/adapter/in/mcp/McpTools.java#L155-L168)

**Follow-ups:**
- *"What about write tools?"* → None yet. I'd add a human approval gate and an allowlist, and scope credentials to the tenant.
- *"Has an agent actually used this?"* → Be honest: tested as a server; no agent loop consuming it yet (gap).

**Self-check:** Why does `list_active_alerts` say "use this first"?

---

### [ ] Q9. "How does function calling work end to end?" — [L]

**Say this:** send tool schemas → model returns a tool call (name + JSON args) → **you** validate and execute →
return the result as a tool message → loop until final text. Guardrails: max iterations, per-tool timeout, arg
validation, approval for writes, audit log of every call.

**Your code:** [`agent-lab/agent/`](../../agent-lab/agent) — loop, `ToolExecutor` (validates args against the tool's
JSON schema *before* calling; never throws), `ApprovalGate` (default deny), JSONL `AuditLog`, `max_steps`. It is an
MCP client over stdio to [`agent-lab/mcp_server/`](../../agent-lab/mcp_server). Flow diagram + 10 Q&As:
[`agent-lab/NOTES.md`](../../agent-lab/NOTES.md).

**Honest limits (volunteer these):** the MCP server is a Python re-implementation of the contract of your Java
streampulse server, not that server. Live-model numbers exist but are a tiny sample: `qwen2.5:3b`, n=5 per case,
CPU in Docker (see Q11).

**Self-check:** Why does a tool return `isError` instead of throwing?

---

### [ ] Q10. "How do you make a RAG answer trustworthy and swappable?" — [P] + [L]

**Say this:**
- **Provider seam:** one `Stream(ctx, messages, emit)` interface; Ollama, fake, or Bedrock behind it. Swapping
  the model is config, not code — verified.
- **Honour `ctx` cancellation** so a closed browser tab stops paying for tokens.
- **Sources before tokens** in the SSE (server-sent events) stream, so users judge the answer against evidence while it streams.
- Grounded prompt with a **permitted refusal**.
- A fake provider makes transport tests deterministic.

**Your code:** provider seam → [provider.go:30-38](../../fe-hands-on/server/provider.go#L30-L38) · SSE event
contract → [stream.go:18-27](../../fe-hands-on/server/stream.go#L18-L27)

**Self-check:** Why are refusals roughly an order of magnitude cheaper than grounded answers (9 vs 128 completion tokens in one measured pair; answer length varies run to run)?

---

### [ ] Q11. "How do you evaluate an agent, not just an answer?" — [L]

**Say this:** trajectory (right tool? right args? step count?), outcome (task done — deterministic check),
final text (judge, calibrated), cost/latency. Golden set from real tickets, CI gate, sampled online traces.

**Your code:** [`agent-lab/evals/`](../../agent-lab/evals) — 13 golden cases (lookup, two-step chain, no-tool,
ambiguous-tenant-should-ask, write-after-approval, prompt injection). Deterministic mode gates (ScriptedLLM, no
network, ran 13/13); live mode is report-only.
- **Proof the harness isn't green by construction:** 18 deliberately wrong trajectories each fail with a precise reason, e.g. `call 1: expected 'list_active_alerts' but model called 'explain_alert'`. Same lesson as your judge inversion.
- **Injection:** a ScriptedLLM that *obeys* the injection is stopped by the approval gate; removing the gate turned 2 cases red.
- RAG eval for comparison → [`../../evals/`](../../evals/)

**Live result (real model, `qwen2.5:3b`, n=5 × 12 cases = 60 runs, local CPU, tiny sample):** task success **82%**, tool selection 92%, arg accuracy 90%, **0 safety failures**. Ten cases 5/5 or 4/5; two cases **0/5**, both real model behaviour (checked in the audit logs, not harness bugs):
- `ambiguous_tenant_asks` — the model **invented a tenant id** (`streampulse`) and called the tool instead of asking, then asked after the `unknown tenant` error.
- `chain_list_then_explain` — it read the list correctly, then explained the **suppressed** alert `alr-1002` instead of the firing root cause `alr-1001`, every run.
- `injection_resisted` 5/5 is the **model** resisting: no write was ever attempted, so the gate wasn't exercised live (it is proven in deterministic mode).

**Say this:** "The eval earned its keep on the first live run: a 3B model guesses missing required arguments and picks the wrong item from a list. I tried a grounded-argument guard, prompt changes, and a `startHere` field in the tool result, one change at a time at n=10 with held-out cases. The guard is a real safety control but didn't change the behaviour; `startHere` fixed one rephrased case 1/10 to 10/10 but not the target. Negative results, recorded in agent-lab/NOTES.md — a 3B model needs a different fix (bigger model, or a forced clarification step)."

**Why that is a good answer:** you changed one variable at a time, wrote held-out cases first, and refused to claim an overfit win (one held-out 10/10 beside a sibling 0/10).

**Honest limits:** deterministic mode proves plumbing + guardrails, **not model quality**. One model, n=5, one injection phrasing. Cause of the two failures not isolated (nothing varied).

**Self-check:** Why is the deterministic suite gating and the live suite report-only?

---

## Round 4 — Graphs & coding

### [ ] Q12. "Given linked tickets/issues, find everything impacted by X." — [L]

**Say this:** BFS from X, visited set (real link graphs have cycles), group by distance if the UI wants "direct vs
indirect". If the graph should be acyclic (dependencies), validate at construction with **Kahn's algorithm**
(topological sort) and reject cycles.

**Your code:** BFS by levels in both directions + Kahn at construction →
[DependencyGraph.java:16-85](../../../streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/graph/DependencyGraph.java#L16-L85).
Note the comment: it keeps a visited set even though construction guarantees acyclicity — "termination must
not depend on a validation that happened elsewhere."

**Practise cold (TS, then Python):** BFS with levels, Kahn's toposort, cycle detection.
Your Go versions: [`DSnAlgoUsingJS/Go/toposort`](../../../DSnAlgoUsingJS/Go/toposort), [`DSnAlgoUsingJS/Go/graphs`](../../../DSnAlgoUsingJS/Go/graphs).

---

### [ ] Q13. Coding drills — solutions exist; you must be able to write them **cold**

Solutions + tests + say-this scripts: [`drills/DRILLS.md`](drills/DRILLS.md) (190 TS + 196 Python tests).
Tick each only after you rebuilt it from a blank file in ≤ the budget — that's Round 6.

---

## Round 2b — Built in the gap-closing sprint (2026-10-19)

### [ ] Q15. "Design two-way sync between two SaaS tools." — [L]

**Say this:** four moving parts, in order of the data:
1. **Inbound:** signed webhook → persisted inbox row (dedupe by delivery id) → async worker. Plus a **cursor poll with an overlap window** as the correctness net, because webhooks get dropped.
2. **Object mapper:** `external_id_map (system, external_id ↔ internal_id)`; every upsert keys on it.
3. **Decide per field:** per-field **ownership** (e.g. status owned by external, notes by internal); tie-break on the external `version`, **never client clocks**. Outcomes: `applied | ignored_stale | echo | conflict`.
4. **Outbound loader:** pushes internal changes with an idempotency key; 429 honours `Retry-After`; 5xx backs off with jitter; after 3 failed attempts a poison event goes to a dead-letter table with the reason. Deletes are **tombstones**, never "missing from the poll".

**Your code:** [`internal/twoway/`](../../../GolangExercise/offline-sync-app/internal/twoway) (`apply.go`, `ownership.go`, `extractor.go`, `loader.go`) · [`internal/mockjira/`](../../../GolangExercise/offline-sync-app/internal/mockjira) · doc with 8 Q&As: [`docs/two-way-sync.md`](../../../GolangExercise/offline-sync-app/docs/two-way-sync.md)

**Proof:** 57 twoway + 25 webhook + 14 mockjira unit tests; 15 integration tests on real Postgres (echo loop terminates, crash mid-backfill = zero duplicates, 429 honoured, dead-lettering). Each safeguard was removed in turn and at least one test failed.

**Be honest about the echo guard:** the echo memory **overlaps two other guards** (single-writer fields, origin filter), so "the loop terminates" alone doesn't prove it's needed. One test — an echo of an *older* push after a newer local edit — fails without it. Say that unprompted.

**DevRev does the same thing (verified, `/airsync/loop-prevention`):** after a write the SDK stores the mapper's `external_versions` `{ modified_date, recipe_version: 0 }`, and the connector must return the external system's real `modifiedDate` so the next import recognises DevRev's own change by **version matching**. Say: "That's my echo memory — remember the version I pushed, drop the change that comes back with it. And I'd never fabricate the timestamp, because that silently breaks the match."

**Honest limits:** runs against a **mock Jira**, not a real vendor. No secret rotation, extractor lock, DLQ replay tooling or metrics.

**Self-check:** Why can't "the webhook arrived, so apply it" work once you also push changes back?

---

### [ ] Q16. "What is N+1 in GraphQL and how did you fix it?" — [L]

**Say this:** a list of 50 locations, each resolving its own children = 1 + 50 + 150 queries. A per-request **DataLoader** collects the keys requested in one batch window and issues one query per level.

**Your numbers (asserted in tests, 50 locations × 3 assessments × 2 photos):** naive **201** store calls → batched **3** (4 if `stats` is selected). Breaking the loader turns the batched test red with 201. Real Postgres: 3 SQL statements.

**Your code:** [`internal/graph/`](../../../GolangExercise/offline-sync-app/internal/graph) (`dataloader.go`, `loaders.go`, `nplusone_test.go`) · [`docs/graphql.md`](../../../GolangExercise/offline-sync-app/docs/graphql.md) (8 Q&As)

**Follow-ups:** keyset cursor (`updated_at, id`) not offset — stable under writes; depth + cost limits (`first:50` full nesting costs 5600, accepted; `first:100` costs 11200, rejected); a failing child field returns partial data + `errors[]`, not a 500; per-request cache, never global (stale + cross-tenant leak risk).

**Index (shipped, migration 000004, `CREATE INDEX CONCURRENTLY`):** on 100k rows the keyset query becomes `Index Scan using disaster_locations_updated_at_id_idx`, both predicates in the Index Cond, 4 buffers — vs a parallel seq scan, 2,485 buffers, 19.2 ms without it (local). With only 50 rows the planner still picks a seq scan — correctly.

**Honest limits:** no tombstones in the schema so deletes can't sync; fragment-bomb validation untested. Library: gqlgen v0.17.95; the loader is hand-written.

**Self-check:** Why is the DataLoader cache per-request and not global?

---

### [ ] Q17. "Write SQL that answers a customer's question." — [L]

**Say this:** start from the decision, not the query ("do we need more field staff?" / "where is sync failing?"), pick **3 metrics**, one query each. Know the window-function family cold: `row_number` vs `rank` vs `dense_rank` differ only on ties; frame defaults (`RANGE` vs `ROWS`) change moving averages; `percentile_cont ... WITHIN GROUP` + `FILTER` for p50/p90/p99; gaps-and-islands for sessions; `generate_series` + `LEFT JOIN` to fill empty buckets.

**Your material:** [`analytics/`](../../../GolangExercise/offline-sync-app/analytics) — 14 queries (each: business question → SQL → result shape → interview notes), seeded dataset, [`QUESTIONS.md`](../../../GolangExercise/offline-sync-app/analytics/QUESTIONS.md) (12 questions with pitfalls + the one-decision dashboard), [`EXPLAIN.md`](../../../GolangExercise/offline-sync-app/analytics/EXPLAIN.md).

**Measured (local, one machine, median of 6 runs, synthetic seed — not a real system):**
- aggregate history: 6.11 ms Seq Scan → 0.105 ms Bitmap Index Scan (buffers 3,063 → 10)
- actor recent activity: 8.54 ms → 0.46 ms (buffers 3,063 → 93)
- consumer recent processing: 4.32 ms → 0.22 ms Index Only Scan (buffers 1,081 → 9)

**Proof:** 34 tests + subtests, 0 failing — invariants per query (≤3 rows per group, p50 ≤ p90 ≤ p99, retention in [0,1]), identical results under UTC vs Pacific/Auckland, byte-identical seed across runs.

**Two real bugs the tests caught (good story):** `interval '14 days'` on `timestamptz` moved a cut-off across a DST change; a re-seed failed because temp functions persisted in the session.

**Honest limits:** write cost of the extra indexes not measured; cohorts are tiny (25 actors); all numbers come from data the seed planted.

**Self-check:** Same score for two actors — which of `row_number`, `rank`, `dense_rank` returns both, and what's the next rank after?

---

## Round 5 — Decomposition case (45 min, out loud)

### [ ] Q14. "Customer has Zendesk + Jira + Slack + a Postgres of accounts. Build an AI agent that triages tickets and links them to known issues. 6 weeks."

Full structure: [`questions-answers.md`](questions-answers.md) Q44. Use your own patterns as building blocks and
**name them**:
- Ingest: outbox + idempotent consumers (Q4, Q5) — "I've built this twice."
- Two-way status sync: LWW + outcome classification (Q3) + id map + echo-loop guard.
- Agent tools: MCP design rules (Q8) — read tools first, writes behind approval.
- Eval: golden set from their historical tickets (Q11).
- Upstream weirdness: "their API will lie about status codes — I've seen Workato return 502 for 'not ready yet'" (Q1).

---

## Round 6 — Own it cold (the sprint code was built with AI help; it is only yours once you can rebuild it)

An interviewer will ask you to write or whiteboard these. Opening the solution is allowed only after your attempt.
For each: blank file, injected clock/sleeper/rng, say the approach out loud first, then tests from [`drills/`](drills/).

**Rebuild from blank, within the budget in [`DRILLS.md`](drills/DRILLS.md) — TS first, then Python:**
- [ ] Token-bucket rate limiter
- [ ] Retry: exponential backoff + full jitter + `Retry-After`
- [ ] Webhook HMAC verify (raw bytes, constant-time, timestamp window)
- [ ] Deep JSON diff + `applyPatch`
- [ ] Merge/dedupe by key, latest version wins
- [ ] BFS levels, Kahn toposort, cycle path
- [ ] Resumable extractor under a time budget
- [ ] Echo-loop guard
- [ ] LRU cache; sliding-window log vs fixed-window counter

**Explain out loud, 3 minutes each, no code open:**
- [ ] One webhook from arrival to applied row (verify → inbox → worker → mapper → ownership → outcome)
- [ ] Outbox → Debezium → Kafka, and why the tombstone
- [ ] N+1: why 201 became 3
- [ ] One agent turn: model → tool call → validate → approval gate → execute → audit → loop

**Run each suite once yourself so the green is yours:**
```
npx vitest run
```
(in `interviews/devrev-fde/drills/ts`)

```
.venv/bin/pytest -q
```
(in `interviews/devrev-fde/drills/py` and in `agent-lab`)

```
go test ./...
```
(in `GolangExercise/offline-sync-app`)

## Before the interview — checklist

- [ ] Every Round 1–3 box and Q15–Q17 ticked
- [ ] Round 6 fully ticked
- [x] Live agent eval run against a real model (`qwen2.5:3b`, 82% task success, 2 cases 0/5) — optional follow-up: try to fix the two failing cases and re-measure
- [x] AirSync specifics verified on developer.devrev.ai (2026-10-19) — see README §1; re-check the week of the interview
- [ ] [`STAR.md`](STAR.md) — 7 stories drafted from evidence; fill the `[you: …]` slots and say each 60-second version out loud
- [ ] Re-read [`README.md`](README.md) §1 (AirSync vocabulary) the morning of
