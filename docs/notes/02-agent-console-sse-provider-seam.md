# 02 — Agent Console: SSE token streaming behind a provider seam (Week 1 weekend)

> **Status:** ✅ built and running — real `llama3.2:1b` tokens streaming end-to-end, 6 Go tests green.
> **Distills into (Track A):** [`../../interviews/agentic-rag-and-mcp/`](../../interviews/) (planned) and
> `llm-serving-and-model-lifecycle` (planned) — the swap-seam idea belongs to the latter.

**One-line summary:** Turned the SSE skeleton into a real streaming LLM console, with the model behind an
interface so it can be replaced without touching the transport or the frontend.
**Gap closed:** #3 (agents / LLM-ops).
**Capstone contribution:** the Agent Console's streaming core — and the first thing note `01`'s eval suite can
legitimately be pointed at, since `/stream` finally has a model behind it.

---

## Concept notes (the mental model before coding)
- **Streaming exists for time-to-first-token.** A 40-token answer that starts in 200ms feels faster than one
  that arrives complete in 2s. So a provider must emit tokens as they arrive and never buffer the full answer.
- **SSE vs WebSocket:** SSE is one-way (server→client), plain HTTP, auto-reconnecting, and enough for token
  streaming. WebSocket buys bidirectional frames you don't need yet, at the cost of a second protocol.
- **`EventSource` is GET-only and cannot send a body.** That is a real constraint, not a detail: the prompt has
  to travel as a query param (`?q=`). Multi-turn history later forces a move to `POST` + `fetch` +
  `ReadableStream`.
- **Every vendor streams in a different dialect.** Ollama returns **NDJSON** (one JSON object per line);
  the browser wants **SSE** (`data: {...}\n\n`). Something must translate, and that something is the provider.
- **The wire contract is the stable interface.** `{type:"token"}` / `{type:"done"}` says nothing about which
  model produced it. Swapping Ollama for Bedrock changes no frontend code.
- **Dependency injection is what makes transport testable.** A handler that constructs its own provider can
  only be tested with a live model. A handler that receives one can be tested with a stub, in milliseconds.
- **Cancellation is a cost control.** A request context that propagates to the upstream call means closing the
  tab stops generation. Without it you keep paying for tokens nobody will read.
- **Usage belongs on the done frame.** Token counts and latency per turn are the raw material of the
  observability dashboard. You cannot tune what you do not measure.

## Tools & setup (verified — these commands actually ran)
```bash
# model server (same one note 01's eval judge uses)
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest
docker exec ollama ollama pull llama3.2:1b

# backend — stdlib only, no third-party deps
cd fe-hands-on && go run server.go              # PROVIDER=fake for no-LLM mode
go test .                                        # NOT ./... — it descends into node_modules

# frontend
cd fe-hands-on/app/agent-console-ui && npx next dev   # localhost:3000
```
> Env knobs: `PROVIDER=fake|ollama`, `OLLAMA_MODEL`, `OLLAMA_URL`. Changing model = restart, not a rewrite.

## Key code / config (the snippet worth rereading)
```go
// The swap seam. streamHandler never mentions Ollama; newProvider() picks the
// implementation from the environment.
type provider interface {
	Stream(ctx context.Context, prompt string, emit func(token string) error) (usage, error)
}

// Taking the provider as an ARGUMENT (not building it inside) is what lets a
// test inject a stub and assert on SSE frames with no model server running.
func streamHandler(p provider) http.HandlerFunc { … }
```
Two implementations: `ollamaProvider` (NDJSON→token adapter) and `fakeProvider` (deterministic, no model).
`http.NewRequestWithContext(ctx, …)` is the line that makes a browser disconnect cancel generation upstream.

## Trade-offs (name them)
- **SSE + `?q=` vs POST/fetch streaming:** `EventSource` is ~10 lines and auto-reconnects, but is GET-only, so
  the prompt sits in the URL and conversation history has nowhere to live. → fine for one-shot turns; revisit
  when multi-turn lands.
- **Provider interface vs calling Ollama directly:** the interface costs one indirection and buys
  model-swappability plus testability. → worth it, and it is literally the
  [`instructions.md`](../instructions.md) requirement ("replace models without significant downtime").
- **Local 1B model vs hosted frontier model:** free, private, offline, and fast to iterate — but low quality,
  which note `01` proves (it hallucinates SQL syntax freely). → correct for building *plumbing*, wrong for
  judging *quality*.
- **Streaming vs buffering:** streaming wins on perceived latency but makes error handling harder — once you
  have flushed 200 tokens you cannot retract them, so a mid-stream failure must surface as an `error` frame
  rather than an HTTP status.

## Metrics captured (real, from the run)
```
- backend: Go 1.25.6, stdlib only, no go.sum (zero third-party deps)
- real turn (llama3.2:1b): promptTokens=32  completionTokens=46  latencyMs=1680
- short turn:              promptTokens=32  completionTokens=8   latencyMs=154
- fake provider:           16 tokens @ 120ms/token = 1940ms (simulated pace)
- tests: 6 tests, 0.87s wall-clock, 60.9% statement coverage, no Docker/network needed
```
Cancellation verified in the log: killing the client mid-stream produced
`client disconnected: read stream: context canceled` — generation stopped rather than running to completion.

## Reference links
- Ollama `/api/chat` streaming shape — verified by `curl` against the running server, not from docs.
  Frames: `{"message":{"content":"…"},"done":false}` … final `{"done":true,"prompt_eval_count":N,"eval_count":M}`.
- MDN `EventSource` — the GET-only / no-body constraint that shapes the whole transport.
> ⚠️ Not re-verified against live docs; the API shape above was confirmed empirically on 2026-09-05.

## Checkpoint Q&A (prove understanding)
1. Why does `streamHandler` take a `provider` argument instead of calling `newProvider()` inside? —
   Because the argument *is* the test seam. With injection, `stubProvider` drives the handler and the suite
   runs in 0.87s with no Docker. Without it, every transport test needs a live model, so in practice those
   tests never get written.
2. Why must the empty `content` on Ollama's final frame not be forwarded? — It would render as a stray token
   and, worse, arrive *after* the semantic end of the answer. The adapter's job is to hide vendor framing;
   `done:true` becomes the `done` SSE frame, not a token. There is a test asserting exactly this.
3. What breaks first when you add multi-turn conversation? — `EventSource`. It is GET-only with no body, so
   history would have to be crammed into the URL. That forces `POST` + `fetch` + `ReadableStream` — and note
   that the reducer and the `{token|done}` contract survive that change untouched. The transport is swappable
   for the same reason the model is.

## Next time
- **Point note `01`'s eval suite at this endpoint.** It finally has a model behind it. That is the bridge to
  **Wk4 (note `06`)**: the CI regression gate.
- **Wk2 (note `03`):** hybrid RAG in Couchbase FTS — real retrieval to put in front of this stream, replacing
  the single-shot prompt with retrieved context.
- Multi-turn history (forces the POST/fetch transport switch), then approval gates for tool calls (Wk3).
