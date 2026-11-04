# 05 · AI frontend system design: six full walkthroughs

Framework: **RADIO** — **R**equirements → **A**rchitecture → **D**ata model → **I**nterface (API) → **O**ptimisations
(perf, reliability, a11y, security, observability). Deep version: [whetstone/12-01 RADIO](../../fe-hands-on/whetstone/12-frontend-system-design/01-radio-framework-45-minutes.md).
45-minute template and the non-AI classics (news feed, autocomplete, spreadsheet, collab editor, offline):
[`career/03-interview-kit.md` §2](../../career/03-interview-kit.md) · [whetstone/12](../../fe-hands-on/whetstone/12-frontend-system-design/README.md) · [`frontend-system-design/`](../frontend-system-design/).

**Timing for 45 min:** R 5 · A 8 · D 7 · I 7 · O 13 · wrap-up 5. Draw boxes early. Say trade-offs out loud.

**Questions to ask first, every AI design:**
1. Who are the users, and what is the one main task? 2. Text only, or actions (tools)? Which actions are irreversible?
3. Latency expectation (chat vs inline)? 4. Data sensitivity / multi-tenant? 5. Scale (DAU, messages/day)? 6. Devices, offline? 7. What does "good answer" mean, and how is it measured?

---

## D1. Design a ChatGPT-style chat application (the most likely prompt)

**R — requirements.** Functional: conversations list, new chat, send message, streamed reply with Markdown + code, stop, regenerate, edit-and-resend, attachments (images/PDF), share link, feedback 👍👎. Non-functional: TTFT shown < ~1 s after click (as a target to agree on, not a fact), smooth at 60 fps while streaming, works on mobile networks, a11y, XSS-safe rendering, history synced across devices.
Out of scope (say it): model training, billing.

**A — architecture.**
```
Browser (Next.js)
 ├─ RSC/SSR shell: sidebar (conversation list), settings
 └─ Client ChatPanel
     ├─ Composer (draft → IndexedDB)
     ├─ MessageList (virtualised; last message streaming)
     ├─ StreamClient (fetch + SSE parser + AbortController)
     └─ ChatStore (reducer: SEND / DELTA / TOOL / DONE / ERROR / ABORT)
        │  POST /api/chat (SSE)        GET /api/conversations (JSON)
        ▼
BFF / API gateway: auth · rate limit · prompt build (versioned) · moderation · stream proxy · cancel on disconnect · trace + usage logs
        ▼
Model gateway (provider abstraction, retries, fallback)   Conversation DB   Object storage (attachments)
```
Why BFF: keys never reach the browser; prompt and safety live server-side; one place for rate limits and cost metering.

**D — data model.**
```ts
Conversation { id, title, createdAt, updatedAt, activeLeafId }
Message { id, conversationId, parentId, role, parts: Part[], status, model, promptVersion, usage, createdAt }
Part = text | code | tool_call | tool_result | sources | attachment_ref
```
`parentId` makes a tree → edit/regenerate = new branch. Client keeps a normalised map `messagesById` + `activePath`.

**I — interface.**
- `POST /api/chat` body `{ conversationId, parentId, content, attachments[] }` → `text/event-stream` with events `meta {messageId}` · `delta {text}` · `tool {…}` · `done {usage, stopReason}` · `error {code, retryable}`.
- `GET /api/conversations?cursor=` (cursor pagination) · `GET /api/conversations/:id/messages` · `PATCH` title · `DELETE`.
- `POST /api/messages/:id/feedback { rating, reason }`.
- Upload: `POST /api/uploads` → signed URL → PUT direct to storage → send `attachment_ref` in chat.

**O — optimisations and deep dives (pick 2–3, go deep).**
- **Streaming render:** rAF batching, memoised completed Markdown blocks, highlight closed code blocks lazily, `role="log"` with start/end announcements only.
- **Scroll:** stick-to-bottom only if at bottom; "Jump to latest" button.
- **Long histories:** virtualise (variable heights, measure + cache), or `content-visibility: auto`; load older messages on scroll up with cursor pagination while preserving scroll position.
- **Reliability:** stop = abort + server cancels upstream; network drop → keep partial, Retry; 429 → show `Retry-After` countdown; AI panel in its own error boundary; drafts survive reload.
- **Security:** no raw HTML, link/image allowlist, CSP, share links are read-only snapshots with revocable tokens.
- **Perf budget:** chat shell SSR for LCP; Markdown/highlighter lazy chunks; INP < 200 ms while streaming.
- **Observability:** client spans click→first token→done with trace ID; per prompt-version dashboards; feedback joined to traces.

**Follow-ups they ask:** "Two tabs open on the same conversation?" (server is truth; BroadcastChannel to refresh; one tab owns the stream) · "Offline?" (read cached history from IndexedDB; queue sends? usually no — show offline state) · "How do you test it?" (parser + reducer units, MSW streamed component tests, Playwright with a fake provider) · "10× traffic?" (it's mostly a backend concern; FE: backoff, fewer retries, client-side debounce, don't refetch lists on every message).

---

## D2. Design an AI copilot sidebar inside an existing SaaS console (your Capella story fits here)

**R.** Users of a cloud console ask questions ("why is my cluster slow?") and request actions ("scale to 5 nodes"). Copilot must know **page context** (which cluster, which screen), answer from docs + live account data, and propose actions that the user confirms. Multi-tenant, RBAC (role-based access control), audit required. Must not slow the console.

**A.**
```
Console (existing app, many routes)
 ├─ ContextProvider: route, selected resource IDs, user role → serialised "page context"
 ├─ CopilotPanel (lazy-loaded chunk, own error boundary, own store)
 │    ├─ Chat stream (as D1)
 │    ├─ Action cards (tool approvals)
 │    └─ Deep links: "Open cluster settings" → console router
 └─ Event bus: console → copilot (context changes), copilot → console (navigate, refresh data after action)
BFF: copilot API → orchestrator (RAG over docs + read tools on account APIs with the *user's* token) → model
```
Key decision: tools call the **same public APIs** the console uses, with the user's own permissions → the copilot can never do what the user couldn't do by clicking.

**D.** Page context `{ route, resource: { type, id }, role, consoleVersion }` · tool-call part with `{ risk: 'read' | 'write' | 'destructive', argsPreview, diff }` · audit record `{ who, what, args, approvedAt, result }`.

**I.** `POST /copilot/chat` (SSE) with `context` · `POST /copilot/actions/:id/decision { approve | reject, argsHash }` · events `delta`, `tool_proposed`, `tool_running`, `tool_result`, `navigate_suggestion`.

**O.**
- **Zero cost when closed:** panel code lazy-loaded on first open; prefetch on hover of the copilot button.
- **Context privacy:** send IDs, not page contents; the server fetches data with the user's token.
- **Action safety:** server pauses for approval, re-checks RBAC on resume, idempotency key per action, show the exact API call/diff, Undo where possible, rate limits per tenant.
- **After an action:** invalidate the console's query cache for that resource so the main UI updates (shared TanStack Query client or an event).
- **Rollout:** feature flag per tenant, canary, kill switch; measure deflection (fewer support tickets), task success, thumbs rate.
- **A11y:** panel is a landmark (`complementary`), keyboard shortcut to open/close, focus moves in and returns.

---

## D3. Design AI search (answer + citations + classic results) for a docs site

**R.** User types a query → gets a generated answer with citations **and** a list of classic search results. Public docs, high traffic, SEO matters for the results page, must be cheap per query.

**A.** Two parallel paths from one query: (1) **fast classic results** (keyword/hybrid search API, < ~200 ms, server-rendered), (2) **streamed AI answer** on top (RAG over the same index). The results never wait for the AI.
```
/search?q=… (SSR: results list from search API → good LCP + SEO + shareable URL)
  └─ AnswerCard (client): POST /api/answer (SSE) → sources first → tokens → done
```
**D.** `Result { id, title, url, snippet, highlights }` · `AnswerEvent: sources[] | delta | done | refusal` · cache key `(normalisedQuery, docsVersion, locale)`.

**I.** `GET /api/search?q&cursor` (JSON, CDN-cacheable for popular queries) · `POST /api/answer {q}` (SSE) · `POST /api/answer/feedback`.

**O.**
- **Cost:** exact-match answer cache for popular queries keyed by docs version (invalidate on re-index); only generate when the user pauses/submits, never per keystroke; small model + re-ranking keeps context short.
- **Trust:** citations inline + source cards; "I couldn't find this in the docs" refusal state when retrieval confidence is low (better than a confident wrong answer); show doc "last updated".
- **Autocomplete** on the input is a separate, cheap path (prefix index, debounce, latest-wins) — don't call the LLM.
- **SEO:** the AI answer is client-only (not indexed); the classic results are SSR.
- **Eval:** golden queries with expected doc IDs (recall@k) + faithfulness; online: click-through on citations, thumbs, reformulation rate.

---

## D4. Design an agent console: long-running tasks with tool approvals (your `agent-lab` + Agent Console)

**R.** User gives a task ("triage these 30 support tickets", "fix this failing test"); the agent runs for minutes, calls tools, sometimes needs approval, produces artifacts. User can leave and come back, watch live, stop, approve, and review an audit trail.

**A.** **Job model, not request model.**
```
UI ──POST /runs──▶ API ──enqueue──▶ Orchestrator (durable: each step persisted)
UI ◀─SSE /runs/:id/events?after=<lastEventId>── event log (append-only)
UI ──POST /runs/:id/approvals/:stepId──▶ API ──resume──▶ Orchestrator
```
Run state lives server-side in an append-only event log, so the UI is a **projection of events**: reload, a second device, or a dropped connection all just replay from `lastEventId`.

**D.** `Run { id, status: queued|running|awaiting_approval|succeeded|failed|cancelled, budget, createdBy }` · `Event { seq, runId, type: step_started|tool_call|tool_result|log|approval_requested|approval_decided|artifact|status, payload, ts }`.

**I.** `POST /runs` · `GET /runs/:id/events` (SSE, supports `Last-Event-ID`) · `POST /runs/:id/cancel` · `POST /runs/:id/approvals/:stepId`.

**O.**
- **UI:** step timeline (collapsed rows, durations, statuses), live "current step" line, approval cards pinned at the top with focus + notification (browser notification / email if the tab is closed), artifact viewer (diffs, files), cost/time meter vs budget.
- **Reliability:** idempotent event application in the reducer (dedupe by `seq`), reconnect with backoff, approvals expire, cancel is a request (server confirms).
- **Safety:** risk classes per tool; approvals re-validated server-side with the approver's identity; audit view = the event log.
- **Scale:** virtualise long event logs; group noisy log events; paginate history.
- **Eval:** trajectory evals offline; online: task success rate, approval-reject rate (a signal the agent proposes bad actions), time to completion.

---

## D5. Design an AI writing/code assistant inside a document editor (inline suggestions + "rewrite selection")

**R.** Two features: **ghost-text completion** while typing, and **select text → "Improve / Shorten / Translate"** with a preview diff. Must never block typing; collaborative doc (other users editing).

**A.** Editor (ProseMirror/Lexical/Monaco class — say "a structured editor") with a plugin layer: `CompletionPlugin` (debounce → request → ghost decoration) and `RewritePlugin` (selection → streamed rewrite in a popover → accept applies one transaction).
**D.** Suggestion `{ requestId, anchorPos, docVersion, text }` — discard if `docVersion` changed in a conflicting way. Rewrite `{ range, original, proposed, status }`.
**I.** `POST /complete { prefix, suffix, lang }` (short, non-streamed or streamed small) · `POST /rewrite { text, instruction }` (SSE).
**O.**
- **Latency:** debounce ~200 ms (tune), abort previous, latest-wins by request ID, small fast model, cache by prefix hash; show nothing rather than a late suggestion.
- **Correctness in collab:** apply accepted rewrite as a single editor transaction mapped through concurrent changes (OT/CRDT position mapping); if the range changed underneath, ask again.
- **UX:** Tab accept / Esc dismiss / keep typing = ignore; diff preview for rewrites; undo restores original in one step.
- **Metrics:** acceptance rate, partial-accept rate, latency p95, characters accepted per session.
- **Privacy:** only send a bounded window around the cursor; respect "AI off" per doc/tenant.

---

## D6. Design "ask your data": natural language → chart/table (text-to-SQL dashboard)

**R.** User asks "monthly revenue by region last year" → system generates a query, runs it, shows a chart + table + the query, user can refine ("only EMEA"). Must not leak data across tenants; must be correct or visibly uncertain.

**A.** Model generates a **structured query spec** (or SQL) → server validates against the schema, applies tenant row-level filters, read-only role, timeouts and row limits → executes → returns data + a **chart spec** (validated JSON: chart type, x, y, series) → client renders from a component registry (generative UI).
**D.** `QuerySpec { metric, dimensions[], filters[], timeRange }` or SQL text · `ChartSpec { type: 'line'|'bar'|'table', x, y[], series? }` · conversation keeps prior spec so "only EMEA" edits it.
**I.** `POST /ask { question, previousSpec? }` (SSE: `spec` → `rows` → `chart` → `summary` → `done`).
**O.**
- **Trust:** show the generated query (editable for power users), the row count, and a plain-language explanation ("Revenue = sum of invoice.amount, grouped by month"); highlight assumptions.
- **Safety:** never let the model's SQL run unvalidated: parse, allowlist tables/columns, enforce `LIMIT`, read-only credentials, tenant filter injected server-side, query cost limits.
- **Perf:** big results → server aggregates; client renders charts with canvas for many points; virtualised table.
- **Eval:** golden questions with expected result sets (execution accuracy, not string match on SQL).

---

## Self-grading checklist for any design answer

- [ ] Asked about actions/risk, latency type, data sensitivity before drawing.
- [ ] BFF between browser and model; keys and prompts server-side.
- [ ] Named the stream event types and the client message/part model.
- [ ] Stop/abort end to end (including server cancel).
- [ ] Safe rendering (no raw HTML, link/image policy, CSP).
- [ ] Approval flow re-validated server-side for writes.
- [ ] Perceived-latency tactics + how you'd measure TTFT.
- [ ] Failure states: rate limit, provider down, network drop, partial answer.
- [ ] a11y of streaming + approvals.
- [ ] Evals offline + online metrics + rollout behind flags.
