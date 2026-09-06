# 03 — Grounding the Agent Console: retrieval, citations, and production shape (Week 2)

> **Status:** ✅ built and running — retrieval, citations, multi-turn, abort; 66 tests across Go and TS.
> **Distills into (Track A):** [`../../interviews/vector-databases/`](../../interviews/vector-databases/) ·
> [`../../interviews/rag-hybrid-search/`](../../interviews/rag-hybrid-search/)

**One-line summary:** Put real retrieval in front of the model, surfaced the evidence in the UI, and hardened
both sides — which turned a confabulating demo into something whose answers can be checked.
**Gap closed:** #2 (RAG trade-offs) and part of #3 (LLM-ops).
**Capstone contribution:** the retrieval core and the console's grounded answer view.

---

## Concept notes (the mental model before coding)
- **Grounding, not model size, fixes hallucination.** Note `01` caught `llama3.2:1b` inventing
  `` CREATE VECTORS ON `bucket`.`vector`; `` three runs running. The same model, given retrieved context and
  explicit permission to decline, now answers *"The provided documentation does not cover this."* Nothing
  about the model changed.
- **Retrieval failure must be loud.** The dangerous path is not an outage, it is quietly answering ungrounded.
  A confident answer with no evidence is worse than an error, so a retrieval error aborts the turn rather than
  falling through to the model.
- **Citations belong in the stream, before the tokens.** Sending sources first lets the UI show the evidence
  while the answer is still being written, so a reader can judge the answer against it rather than trusting it.
- **Chunking sets the ceiling.** A perfect index over bad chunks retrieves exactly the wrong thing, reliably.
  Headings are author-declared topic breaks, so they beat a fixed character count as a split point.
- **The write path and read path must use the same embedding model.** Different models produce different
  vector spaces; nothing in the system detects the mismatch, results just quietly get worse.
- **Brute force is the correct index at this size.** Under ~10K chunks, exact cosine is 100% recall by
  construction — no build step, no tuning knob, no recall to lose silently. ANN here would be sophistication
  as a mistake.
- **`EventSource` was the binding constraint on the UI.** GET-only, no body, no clean cancel — so no
  multi-turn and no Stop button. Moving to `POST` + `fetch` + `ReadableStream` cost ~40 lines and removed both.
- **A network chunk is not an SSE event.** One read can hold half an event or three of them. Buffering to the
  `\n\n` terminator is what makes the parse correct rather than usually-correct.
- **Fail fast at startup.** A server that boots misconfigured and then errors on every request is strictly
  worse than one that refuses to start.

## Tools & setup (verified — these commands ran)
```bash
docker exec ollama ollama pull nomic-embed-text       # 274 MB, 768-d

cd fe-hands-on/server && go run .                     # indexes ./corpus at boot
cd fe-hands-on/app/agent-console-ui && npm run dev

cd fe-hands-on/server && go test ./...                # 46 cases, no Docker needed
cd fe-hands-on/app/agent-console-ui && npm test       # 20 cases, node --test
```
> `/api/embed` shape confirmed empirically before writing the client:
> `{"embeddings": [[…768 floats…]]}`. Node 24 strips TypeScript natively, so the frontend tests needed **no**
> test framework — but they do need `allowImportingTsExtensions` in `tsconfig.json`, because the native runner
> requires explicit `.ts` import specifiers and `next build` type-checks them.

## Key code / config (the snippet worth rereading)
```go
// A second swap seam beside `provider`. The store is an implementation detail:
// in-memory today, Couchbase or pgvector when the corpus outgrows exact search.
type Retriever interface {
	Retrieve(ctx context.Context, query string, k int) ([]Chunk, error)
}

// The load-bearing line in the grounded prompt — without explicit permission to
// decline, a model fills gaps with fluent invention.
// "If the context does not contain the answer, reply exactly:
//  \"The provided documentation does not cover this.\""
```
Vectors are normalized once at index time, so query scoring is a plain dot product; ties break by chunk ID so
retrieval order is stable and eval runs stay diffable.

## Trade-offs (name them)
- **Brute force vs ANN index:** exact and zero-tuning vs sub-linear at scale. → brute force under ~10K chunks;
  the interface is the upgrade path.
- **POST/fetch vs EventSource:** ~40 more lines and manual SSE parsing vs multi-turn history and real
  cancellation. → worth it; EventSource cannot do either.
- **Retrieve-then-generate vs answer directly:** ~570 prompt tokens and a retrieval hop vs speed. → the extra
  tokens are what make the answer checkable.
- **Corpus re-embedded at boot vs persisted index:** simple and always consistent with the files vs slower
  startup and no horizontal scaling. → fine at 6 chunks/535ms, wrong at scale. Listed as a known limit.
- **Local 1B model vs hosted frontier model:** free, private, fast to iterate vs much better answers. →
  correct for building plumbing, wrong for judging quality.

## Metrics captured (real, from the run)
```
- corpus: 6 chunks from 2 Markdown files, indexed in 535ms at boot (nomic-embed-text, 768-d)
- grounded answer:  promptTokens=568  completionTokens=162  latencyMs=3921   (4 sources cited)
- refusal path:     promptTokens=648  completionTokens=9    latencyMs=612    ("does not cover this")
- multi-turn:       promptTokens=691  completionTokens=7    latencyMs=5160   (resolved "one" → scope)
- tests: 46 Go cases (0.77s, 62.3% coverage) + 20 TS cases (0.11s); neither needs Docker or network
```
Note the refusal costs **9 completion tokens against 162** — declining is roughly 18× cheaper than answering.
Grounding improves cost as well as correctness.

## Reference links
- Ollama `/api/embed` and `/api/chat` shapes — verified by `curl` against the running server, not from docs.
- [Couchbase Docs — Choose the Right Vector Index](https://docs.couchbase.com/cloud/vector-index/use-vector-indexes.html)
  — the three 8.0 index types behind the Track A write-up.
> ⚠️ Ollama API shapes confirmed empirically on 2026-09-06; re-verify against current docs before quoting.

## Checkpoint Q&A (prove understanding)
1. Why does a retrieval failure abort the turn instead of falling back to the model? — Because the fallback is
   the *worst* outcome, not a safe one: an ungrounded answer is indistinguishable from a grounded one to the
   reader, arrives with full confidence, and carries no evidence. An error is honest; a silent fallback is a
   hallucination with extra steps. There is a test asserting the provider is never called when retrieval fails.
2. Why must the `sources` frame precede the first token? — Two reasons. Product: the reader sees the evidence
   while the answer streams, rather than after they have already believed it. Mechanical: the frame is built
   from the same chunks that produced the prompt, so emitting it first proves the citations correspond to what
   the model actually received rather than being reconstructed afterwards.
3. What breaks first as the corpus grows? — Not the search; brute force over 10K chunks is still fast. It is
   **startup**: the whole corpus is re-embedded on every boot, so boot time scales linearly with corpus size,
   and the in-memory index means every replica pays that cost and none of them share it. Persistence comes
   before ANN — the index type is the *second* problem.

## Next time
- **Persist the index** (and stop re-embedding at boot) — the actual next bottleneck, ahead of any ANN work.
- **Hybrid search:** the corpus is full of identifiers (`CREATE PRIMARY INDEX`, `META().id`) and embeddings
  blur exactly those. Add BM25 alongside vectors and merge with RRF → note `04`.
- **Point the eval suite at `/api/chat`.** It finally has a grounded endpoint worth gating, which is the bridge
  to **Wk4 (note `06`)**: the CI regression gate.
- Then **Wk3 (note `05`):** MCP tool integration behind an approval gate.
