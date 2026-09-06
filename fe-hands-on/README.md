# Agent Console

A grounded, streaming documentation assistant. Go backend, Next.js console, local models via Ollama.

Every answer is retrieved-then-generated: the server searches a Markdown corpus, hands the model only what it
found, and instructs it to decline when the corpus does not cover the question. The console shows the sources
alongside the answer, so a reader can check the answer against its evidence.

```
browser ──POST /api/chat──▶ HandleChat ──▶ Retriever ──▶ embeddings + corpus
        ◀── SSE: {sources} {token}* {done} ──┘        └─▶ provider ──▶ LLM
```

---

## Run it

**1. Models** (once)

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest
docker exec ollama ollama pull llama3.2:1b        # generation
docker exec ollama ollama pull nomic-embed-text   # embeddings (768-d)
```

**2. Backend**

```bash
cd server
go run .                     # :8080, indexes ./corpus at startup
curl localhost:8080/healthz  # {"status":"ok","chunks":6,...}
```

**3. Console**

```bash
cd app/agent-console-ui
npm install
npm run dev                  # http://localhost:3000
```

No model server handy? `PROVIDER=fake go run .` streams a canned response so the UI stays developable.

---

## Configuration

All via environment; validated at startup, so a bad value stops the process rather than failing every request.

| Variable | Default | Purpose |
|---|---|---|
| `ADDR` | `:8080` | Listen address |
| `PROVIDER` | `ollama` | `ollama` or `fake` |
| `OLLAMA_URL` | `http://localhost:11434` | Model server |
| `OLLAMA_MODEL` | `llama3.2:1b` | Generation model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model — **must match** the one used to index |
| `CORPUS_DIR` | `corpus` | Markdown to index; empty disables retrieval |
| `TOP_K` | `4` | Chunks passed to the model |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowlist (comma-separated) |
| `REQUEST_TIMEOUT` | `120s` | Upper bound on one generation |
| `SHUTDOWN_GRACE` | `10s` | Time for in-flight streams to finish |

The console reads `NEXT_PUBLIC_API_BASE` (default `http://localhost:8080`).

---

## Tests

```bash
cd server && go test ./...                    # 46 cases, ~0.8s, no Docker or network
cd app/agent-console-ui && npm test           # 20 cases, node --test, native TS
```

Neither suite needs a model server. That is deliberate: the provider and retriever are interfaces, so tests
inject stubs and run in under a second. A test suite that needs Docker is a test suite that stops being run.

---

## Design notes

**Three seams**, each isolating one kind of change:

| Seam | Today | Later |
|---|---|---|
| `provider` | Ollama | Bedrock, OpenAI |
| `Retriever` | in-memory brute force | Couchbase, pgvector |
| SSE event contract | — | names neither the model nor the store, so both swap without UI changes |

**Retrieval is brute-force cosine, on purpose.** Under roughly 10K chunks an ANN index buys nothing: exact
search is 100% recall by construction, with no build step, no tuning knob, and no recall to lose silently.
Reaching for HNSW at this size is the mistake, not the sophistication. The `Retriever` interface is where a
real vector store slots in once that stops being true. (See
[`interviews/vector-databases`](../interviews/vector-databases/).)

**Grounding is the hallucination fix.** Before retrieval, `llama3.2:1b` answered "how do I create a vector
index?" by inventing ``CREATE VECTORS ON `bucket`.`vector`;`` — three runs in a row, which
[the eval suite](../evals/) caught. With retrieval and an explicit instruction that it may say so, the same
model answers *"The provided documentation does not cover this."* A bigger model was not required.

**Failure modes are explicit, not silent:**

- Retrieval failure produces an `error` frame. It never degrades into an ungrounded answer, because a
  confident answer with no evidence is worse than an error.
- Client disconnect cancels generation upstream instead of billing tokens nobody reads.
- Client-supplied `system` messages are rejected — the server owns the prompt, so a page cannot overwrite the
  grounding rules.
- `/healthz` reports dependency health, not just liveness: up-but-cannot-reach-the-model is not "ok".

**Known limits** (honest about what this is): the corpus is re-embedded on every boot with no persistence,
there is no authentication or rate limiting, and the in-memory store is per-process so it does not survive a
restart or scale horizontally. Those are the next things to fix before this faces real traffic.
