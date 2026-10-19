# DevRev FDE — Study File (start here)

How to use: read the question, **answer out loud before scrolling**, then check against "Say this" and open
"Your code". If you can't explain your own code without reading it, that question isn't done.

Related: role + gap list → [`README.md`](README.md) · wider question bank → [`questions-answers.md`](questions-answers.md).

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
  and per-field source-of-truth. That's the part you'd add — say so.

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

### [ ] Q6. "Build a secure webhook receiver." — [K] ⚠️ no code yet

**Say this:** HMAC (keyed hash) over the **raw body**, constant-time compare, timestamp window against replay,
ack `2xx` fast and enqueue, dedupe on delivery id, ignore out-of-order by version.

**Bridge to your code:** "The processing half is the same consumer contract I built in FieldSync — dedup table,
retry next tick. The receiving half I haven't shipped; here's how I'd do it." Then draw it.

**Closes when:** plan day 2–3 in [`README.md`](README.md) §4.

---

### [ ] Q7. "Your sync runs in a serverless function with a hard time limit." — [K] + [L]

**Say this:** paginate, checkpoint after every page in durable state, check the remaining budget *before* starting
a page, exit cleanly, resume next invocation. Each page idempotent so a crash replays one page. (DevRev AirSync:
~13-min invocation cap + a state object — verify on developer.devrev.ai.)

**Your code (adjacent):** FieldSync and ticket-booking already split work into Lambdas
(`cmd/*-lambda/main.go`) and rely on idempotent retries — same principle, without the checkpoint part.

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

### [ ] Q9. "How does function calling work end to end?" — [K]

**Say this:** send tool schemas → model returns a tool call (name + JSON args) → **you** validate and execute →
return the result as a tool message → loop until final text. Guardrails: max iterations, per-tool timeout, arg
validation, approval for writes, audit log of every call.

**Bridge:** "My MCP server is the tool side of this loop; the client side is the gap I'm closing." Plan day 5–6.

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

**Self-check:** Why are refusals ~14× cheaper than grounded answers in your measurements?

---

### [ ] Q11. "How do you evaluate an agent, not just an answer?" — [K] ⚠️ partial

**Say this:** trajectory (right tool? right args? step count?), outcome (task done — deterministic check),
final text (judge, calibrated), cost/latency. Golden set from real tickets, CI gate, sampled online traces.

**Your code:** RAG eval harness exists → [`../../evals/`](../../evals/). Agent-trajectory eval is the gap (plan day 5–6).

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

### [ ] Q13. Coding drills still missing (write these, then tick)

- [ ] Token-bucket rate limiter (TS + Python) — you only have LeetCode 359's logger
- [ ] Retry with exponential backoff + full jitter, honouring `Retry-After`
- [ ] Deep diff of two JSON objects → list of field changes (the core of sync)
- [ ] Webhook HMAC verify over raw body (TS)

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

## Before the interview — checklist

- [ ] Q1 result numbers filled in from real data
- [ ] Every Round 1–3 box ticked
- [ ] Q6 and Q9 moved from [K] to [L] (plan days 2–6)
- [ ] One Python drill done per day for the last 5 days
- [ ] Re-read [`README.md`](README.md) §1 (AirSync vocabulary) the morning of
