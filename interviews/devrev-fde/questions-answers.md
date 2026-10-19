# DevRev FDE — Questions & Answers

Interview loop is **not described** in the JD. These questions are my prediction from the JD bullets, not a
leaked list. Answers are terse on purpose — say them out loud, expand from the bullets.

Tags: **[P]** = shipped at Couchbase, **[L]** = your own lab build, **[K]** = knowledge only, no artifact yet.

---

## A. Role fit & behavioural

**1. Why FDE and not a product SWE role?**
- I like the last mile: the product works in the demo; the job is making it work in *this* customer's data.
- Ask AI [P] taught me most failures are integration and data quality, not the model.
- Field work → product feedback loop is where I add the most leverage as an architect.

**2. 80% travel / on-site — are you OK with it?**
Answer honestly. Don't say yes if it's no; it's an explicit filter.

**3. Tell me about a customer/stakeholder requirement that was ambiguous.**
STAR. Structure: what they *said* → what they *needed* → questions you asked → thin MVP → metric that proved it.

**4. A demo broke live. What did you do?**
Have a real one. Key signals: you had a fallback (recorded run, seeded data), you named the failure plainly,
you followed up in writing with root cause within 24h.

**5. How do you feed field learnings back to product?**
Pattern, not anecdote: tag every custom workaround; when the same workaround appears at 3 customers, write it up
as a product gap with the evidence (customers, effort, revenue at risk).

**6. You disagree with a customer's architecture choice. How?**
Show the trade-off with their numbers, offer two options, document the decision and who made it, then commit.

**7. Hardest bug you've debugged end to end.**
Use the prompt-parity + judge-inversion story [L] (STUDY-GUIDE §1). Isolation method is the point:
fixed input, vary one thing, repeat ≥3 times.

**7b. Tell me about a third-party integration you built. (Your #1 story — [P])**
Capella Billing Invoices via Workato → NetSuite (Go, `internal/billing/activations/integrations/`).
- **S/T:** customers needed invoices in the Capella UI; source of truth was NetSuite behind a Workato recipe.
- **A:** built against the assumed contract → real contract differed → rebuilt the client: renamed params,
  timeout 10s → 35s (sized to the recipe's real latency), dropped a per-request DB lookup.
  Hardened it: no redirect-following (token leak), capped error-body reads, absolute-URL check, fail-closed
  NoOp client when unconfigured. Normalized their data and **reported unreadable fields instead of guessing**.
  Mapped Workato's 502/404 to "no PDF generated yet" for the customer (a 502 reads like an outage but isn't). NetSuite URLs never reach the browser.
  Shipped behind `enable-billing-invoices` (default off) with RBAC and Cypress e2e.
- **R:** fill in the real outcome before the interview (rollout %, tickets avoided, customers enabled) — don't
  invent it.
- **Lesson to say out loud:** "The contract you're given is a hypothesis. I test it against the real system
  first, then build."

---

## B. Data sync & integration (their core — expect depth here)

**8. Design a two-way sync between Jira and DevRev.**
1. **Identity map** — durable table `(sync_unit, external_id) ↔ devrev_id`. Every upsert keys on it.
2. **Change detection** — webhooks for latency, plus periodic **cursor/watermark poll** for correctness
   (`updated_at > last_cursor - overlap`). Webhooks get dropped; polling catches it.
3. **Echo-loop prevention** — when we write to Jira, Jira fires a webhook back. Store the last-synced
   hash/version per field; if the incoming value equals what we wrote, drop it. Optionally mark writes with an
   origin marker.
4. **Conflict policy** — per field: source-of-truth ownership (status owned by Jira, priority by DevRev), or
   last-writer-wins on server timestamps (not client clocks). Unresolvable → surface to a human.
5. **Idempotency** — dedupe on delivery/event id; all writes are upserts.
6. **Deletes** — tombstones/soft delete; never hard-delete on a missing poll result.
7. **Initial backfill vs incremental** — backfill in pages with a checkpoint; incremental from the last
   successful sync start.
8. **Ops** — per-run metrics (extracted, loaded, failed, lag), DLQ for poison items, per-item error surfaced
   in UI.

DevRev's AirSync splits this as extractor (forward) + loader (reverse), with object mappers for the id map
[K — from developer.devrev.ai; verify].

Your evidence: FieldSync `GolangExercise/offline-sync-app/internal/sync/` [L] — conflict handling + outbox.
Be honest that it's device↔server sync; the SaaS↔SaaS echo-loop part is what you'd add.

**9. Your sync function has a hard time limit (~13 min per invocation in AirSync). Initial import is 2M records.**
- Paginate, checkpoint after every page into the platform's state object, exit cleanly before the budget,
  resume from the checkpoint on the next invocation.
- Make each page's processing idempotent so a crash mid-page just replays the page.
- Budget-aware loop: check remaining time before starting a page, not after.
- Throughput bound is usually the source's rate limit, not CPU.

**10. Source API returns 429s.**
Respect `Retry-After`; else exponential backoff with full jitter; cap retries; client-side token bucket sized
to the documented limit; share the limiter across concurrent workers for the same tenant.

**11. Webhooks vs polling — when which?**
| | Webhooks | Polling |
|---|---|---|
| Latency | seconds | interval |
| Reliability | at-least-once at best, can drop | you control it |
| Cost | cheap | wasteful at scale |
| Needs | public endpoint, signature check | cursor + rate budget |
Production answer: both. Webhook triggers fast path; poll reconciles.

**12. Build a secure webhook receiver.**
- Verify HMAC over the **raw body** (not re-serialized JSON) with constant-time compare.
- Timestamp tolerance window to block replays.
- Ack `2xx` fast, enqueue, process async — senders time out and retry.
- Idempotent by delivery id (sender retries are normal).
- Out-of-order: compare entity version/`updated_at`, ignore stale.

```ts
export async function handle(req: Request, env: Env): Promise<Response> {
  const raw = await req.text();
  const sig = req.headers.get("x-signature") ?? "";
  if (!(await verifyHmac(raw, sig, env.SECRET))) return new Response(null, { status: 401 });

  const evt = JSON.parse(raw) as WebhookEvent;
  if (await env.seen.has(evt.deliveryId)) return new Response(null, { status: 200 });

  await env.queue.send(evt);
  await env.seen.put(evt.deliveryId, "1", { ttlSeconds: 7 * 24 * 3600 });
  return new Response(null, { status: 202 });
}
```
`verifyHmac`, `env.seen`, `env.queue` are placeholders — pick real APIs per platform (Workers KV/Queues, SQS,
etc.) and verify signatures against each vendor's documented header and algorithm.

**13. Schema mapping: customer has 40 custom Jira fields, DevRev has a fixed schema.**
- Map core fields 1:1 (title, description, status, priority, assignee).
- **Enum mapping tables** for status/priority — never string-guess.
- **User mapping** by email; unmapped user → placeholder + report.
- Custom fields → DevRev custom fields/schema extension; don't drop data silently.
- Mapping as **config, not code**, versioned, with a dry-run that shows a diff before the first write.
- Validate every record; failures → DLQ with the reason.

**14. One-way sync that's "eventually consistent" — how do you prove it's correct?**
Reconciliation job: count + checksum per partition (e.g., per project per day) on both sides; diff, re-sync
the delta. Expose drift as a metric.

**15. How would you handle a non-SaaS source (on-prem DB, no API)?**
CDC (change data capture) from the DB log if allowed (e.g., Debezium-style), else timestamp-column polling,
else nightly export file. Agent/connector runs inside their network and pushes out (no inbound firewall hole).

---

## C. API patterns & event-driven

**16. REST vs GraphQL for an integration?**
- REST: simple, HTTP caching, predictable rate limits, easy to debug with curl.
- GraphQL: fetch exactly the graph you need in one round trip (good for related entities); but query-cost
  rate limits, N+1 on the server, caching is harder.
- For sync I prefer whatever has **cursor pagination + `updated_since` filtering** — that matters more than
  the style.

**17. Offset vs cursor pagination?**
Offset skips/duplicates when data changes mid-scan and gets slow at depth. Cursor (opaque, keyset-based) is
stable under writes. Always cursor for sync.

**18. Pub/sub: what goes wrong?**
- Delivery is at-least-once → consumers must be idempotent.
- Ordering only within a partition/ordering key → key by entity id.
- Poison messages → max attempts → DLQ + alert.
- Dual-write (DB + publish) inconsistency → **transactional outbox**.
- Backpressure: consumer lag metric, bounded concurrency.

Your evidence [L]: streampulse — Debezium outbox connector + `OutboxCdcIT.java`, `EventId` idempotency,
`PoisonRecordIT.java`; ticket-booking outbox relay + saga worker + Terraform DLQ.

**19. Exactly-once delivery?**
Not end to end across systems in practice. You get at-least-once + idempotent processing = effectively once.

---

## D. LLMs, prompts, RAG, semantic search

**20. Walk me through a RAG system you built.**
Ask AI [P]: crawl → clean → chunk (≤1,000 tokens) → embed → Couchbase vector + FTS hybrid → re-rank → stream.
2,667 docs → 7,597 chunks; ingest 5–6h → ~20 min with 10 goroutines. Then Agent Console [L]: grounded prompt,
SSE contract, provider seam, eval gate. Keep P and L separate.

**21. Retrieval quality is bad for one customer. How do you tune it?**
1. Build a labeled set from their real queries (30–50 to start).
2. Measure recall@k / MRR before touching anything.
3. Check in order: chunking (splitting tables/code?), metadata filters (wrong tenant/product?), hybrid
   (add BM25 for IDs, error codes, product names), re-ranker, query rewriting, embedding model.
4. Change one thing, re-measure.

**22. Why hybrid search?**
Vectors miss exact tokens (ticket IDs, error codes, SKUs); BM25 misses paraphrase. Fuse with RRF
(reciprocal rank fusion — merge by rank, not raw score, since scores aren't comparable).

**23. Prompt engineering principles you actually use.**
- Give the model a **permitted way out** (explicit refusal string) — your Bug 1 story [L].
- Delimit untrusted content (tickets, emails) and say it's data, not instructions.
- Structured output with a JSON schema; validate, retry once on parse failure.
- Few-shot from real customer examples, not invented ones.
- Version prompts; eval every change.

**24. Prompt injection in a ticket that the agent reads?**
Treat all retrieved/tool content as untrusted. Least-privilege tool credentials scoped to the tenant.
Side-effecting tools behind approval or strict allowlists. Never let model output pick the tenant/account id.

**25. Hallucinations in a customer demo.**
Ground + cite sources, allow refusal, lower temperature, eval for faithfulness. Measure; don't argue.

---

## E. Agents, function calling, MCP

**26. How does function calling work?**
Send tool definitions (name, description, JSON-schema params). Model returns a tool call (name + args).
Your code validates args, executes, returns the result as a tool message. Loop until the model returns final
text. Guardrails: max iterations, per-tool timeout, arg validation, approval for writes, audit log.

**27. What is MCP and why does it matter for integrations?**
- Open protocol (introduced by Anthropic, late 2024) so any AI client can use any tool/data server through one
  contract instead of N×M custom integrations.
- JSON-RPC 2.0 messages; server exposes **tools**, **resources**, **prompts**.
- Transports: stdio (local) and Streamable HTTP (remote); remote auth is OAuth-based.
- Spec moves fast — verify the current spec version and transport names at modelcontextprotocol.io before the
  interview.
- FDE angle: wrap a customer's internal system as an MCP server once → every agent can use it.
- Your evidence [L]: streampulse `services/mcp-server` (`McpTools.java`) exposes the telemetry platform as
  tools. Gap to admit: no agent loop consuming it yet.

**28. Design an agent that triages incoming support tickets.**
Tools: `search_similar_tickets`, `search_kb`, `get_account`, `link_to_issue`, `set_priority`.
Read tools free; write tools (`link`, `set_priority`) behind confidence threshold + human approval initially.
Output: suggested category, priority, linked issue, draft reply with citations. Shadow mode first (suggest,
don't act), measure agreement with human triagers, then gradually auto-apply above a confidence bar.

**29. Single agent vs multi-agent?**
Start single agent + good tools. Multi-agent adds latency, cost, and harder evals; justify it only when
sub-tasks need different tools/context windows.

---

## F. Evals (agentic)

**30. How do you evaluate an agent, not just a RAG answer?**
- **Trajectory**: right tool chosen? right args? number of steps? unnecessary calls?
- **Outcome**: task success (deterministic check where possible — was the right issue linked?).
- **Final text**: faithfulness/citations via LLM judge, calibrated.
- **Cost/latency** per task.
- Golden set from real (anonymized) tickets; CI regression gate; online sampled traces + human review.

**31. Your LLM judge disagrees with humans.**
Calibrate: fixed inputs, run multiple times, measure agreement with human labels; fix the rubric before
swapping the model. Your judge-inversion isolation story [L].

**32. Customer asks "is it good enough to go live?"**
Agree the bar up front: e.g., ≥X% triage agreement with humans on N labeled tickets, zero critical
misroutes, p95 latency < Y, cost/ticket < Z. Ship in shadow mode, then to a % of traffic.
(Pick X/Y/Z with the customer — don't invent numbers.)

---

## G. Deploy, serverless, observability

**33. Serverless gotchas for integrations?**
Cold starts; hard timeouts (AWS Lambda max 15 min); stateless → checkpoint externally; platform retries →
idempotency required; fan-out concurrency can blow the downstream API's rate limit (cap concurrency).

**34. Edge vs regional serverless?**
Edge (V8 isolates, e.g., Cloudflare Workers): low latency, tiny cold start, limited runtime APIs and CPU time
— good for webhook ingress/auth. Regional (Lambda/Cloud Functions): full runtime, longer jobs — good for
extract/load.

**35. What do you log/trace for a sync pipeline?**
- Structured logs with `tenant`, `sync_run_id`, `entity_id`, `correlation_id`.
- RED metrics (rate, errors, duration) per stage; consumer lag; DLQ depth; drift from reconciliation.
- Trace spans: webhook → queue → transform → load (OpenTelemetry).
- Never log customer PII or secrets; redact at the logger.

Your evidence: streampulse Micrometer + Prometheus/Grafana/OTel [L]; Capella Datadog browser-logs upgrade [P].

**36. "Error surfacing" for a non-technical admin?**
Per-sync-run status page: what synced, what failed, **why in plain language**, and the fix
("User jane@x.com not found in DevRev — invite or map"). Retry button per item.

**37. CI/CD for a customer-specific integration?**
Lint + unit tests + contract tests against recorded API fixtures + eval gate for prompts; deploy per
environment (sandbox tenant → prod tenant); feature flag to roll back without redeploy.

---

## H. SQL & data

**38. Median resolution time per priority, last 30 days.** (Postgres)
```sql
SELECT priority,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY closed_at - created_at) AS p50
FROM tickets
WHERE closed_at >= now() - interval '30 days'
GROUP BY priority;
```

**39. Top 3 accounts by open tickets, per region.**
```sql
SELECT * FROM (
  SELECT region, account_id, count(*) AS open_cnt,
         rank() OVER (PARTITION BY region ORDER BY count(*) DESC) AS rnk
  FROM tickets
  WHERE status <> 'closed'
  GROUP BY region, account_id
) t
WHERE rnk <= 3;
```
Know: `rank` vs `dense_rank` vs `row_number`; `LAG` for week-over-week; `date_trunc` for buckets.

**40. Dashboard that informs a customer decision?**
Start from the decision ("do we need more L2 staff?"), pick 3 metrics (backlog trend, p50/p90 resolution,
reopen rate), one chart each. Not 20 charts.

---

## I. Graph / Knowledge Graph & DSA

**41. Model a knowledge graph for support + engineering.**
Nodes: account, user, ticket, conversation, issue, part/feature, PR, release. Edges: `reported_by`,
`belongs_to`, `linked_to`, `fixes`, `part_of`. Edges typed and timestamped. Enables "which customers are
affected by this PR's bug?" = traversal.

**42. "Find all tickets impacted by issue X through any chain of links."**
BFS from X over `linked_to`/`duplicate_of`, visited set (cycles exist), optional depth cap. O(V+E).
Your evidence [L]: streampulse `DependencyGraph` + `RuleGraphValidator` (cycle detection); Go `toposort`,
`graphs` packages in DSnAlgoUsingJS.

**43. Likely coding asks — practise in TS, then Python:**
- Rate limiter (token bucket), retry with backoff + jitter
- LRU cache
- Deep diff of two JSON objects (sync!) → list of field changes
- Merge/dedupe records by key with latest-wins
- BFS/DFS, topological sort (dependency order), cycle detection
- Interval merge (on-call / SLA windows)
- Parse + transform a paginated API response into a normalized shape

---

## J. Decomposition case (practise out loud, 45 min)

**44. "A fintech customer has Zendesk, Jira, Slack and an internal Postgres of accounts. They want an AI agent
that triages new tickets and links them to known engineering issues. 6 weeks. Go."**

1. **Clarify** (5 min): ticket volume/day? languages? who acts on triage today? what's "correct" triage?
   data residency/PII limits? which system is source of truth for status?
2. **Data plane**: Zendesk + Jira → DevRev (2-way for status, 1-way for history); Postgres accounts via
   read-only connector; Slack for notifications only.
3. **Knowledge**: index past resolved tickets + Jira issues; hybrid search; metadata filter by product.
4. **Agent**: tools as in Q28; shadow mode weeks 1–3.
5. **Eval**: 200 historical tickets labeled by their L2 leads; metrics = category/priority agreement, link
   precision, p95 latency, cost/ticket.
6. **Rollout**: shadow → auto-apply above confidence for low-risk categories → expand.
7. **Ops**: sync health page, drift, DLQ alerts, weekly review with the customer.
8. **Feedback to product**: what was custom here that should be a product feature.

Interviewers grade the questions and the eval, not the architecture boxes.

---

## K. Questions to ask them

- What does a typical FDE engagement look like in weeks 1, 4, 12?
- How much of the integration work is AirSync snap-ins vs custom code outside the platform?
- How are agent evals done today — per customer or shared?
- How does field feedback reach the product roadmap?
- What does success look like at 6 months for this role?
