# AI Ramp-Up & Agent Console

A senior/staff AI-native ramp-up: a **12-week hands-on build track** (evals → RAG → agents/MCP → deploy) plus a
**knowledge track** of whiteboard-ready system-design topics — both anchored in a real, shipped case study
(Couchbase **Ask AI**) and proven locally with runnable code, real tests, and measured numbers. No passive
reading: every claim below is either cited to a shipped design doc or measured on this machine.

**Start here:** [`RAMPUP.md`](RAMPUP.md) (full structure) → [`docs/notes/STUDY-GUIDE.md`](docs/notes/STUDY-GUIDE.md)
(single file to follow for daily learning, revision, and interview prep).

---

## What's built

**[Agent Console](fe-hands-on/)** — a grounded, streaming RAG assistant. Go backend, Next.js console, local
models via Ollama in Docker. Retrieve-then-generate: the server searches a Markdown corpus, hands the model
only what it found, and instructs it to decline when the corpus doesn't cover the question.

```
browser ──POST /api/chat──▶ HandleChat ──▶ Retriever ──▶ embeddings + corpus
        ◀── SSE: {sources} {token}* {done} ──┘        └─▶ provider ──▶ LLM
```

- **66 tests**, no Docker or network needed (46 Go + 20 TS) — 0.82s / 0.61s
- Three seams: `provider` (Ollama → Bedrock/OpenAI), `Retriever` (in-memory → Couchbase/pgvector), an SSE
  contract that names neither — verified: swapping `OLLAMA_MODEL` changes the model family with **zero code
  change**
- `/healthz` reports **dependency** health, not just liveness

**[Eval harness](evals/)** — promptfoo golden-dataset suite, graded by a local Ollama judge (different model
family than the system under test, to avoid self-preference), running in Docker with no API key.

- Deterministic rule checks first (cheap, run first), `llm-rubric` second (expensive, uncalibrated — treat as
  a warning until proven otherwise)
- [`evals/ci/check-parity.py`](evals/ci/check-parity.py) — a zero-model CI gate proving the eval prompt carries
  every rule the server's grounding prompt does, after those two drifted apart and let a real bug through (see
  below)
- Wired into CI: [`.github/workflows/eval-gate.yml`](.github/workflows/eval-gate.yml)

**[`interviews/`](interviews/)** — whiteboard-ready topic folders (7-file spec) distilled from what's built here:
[`llm-eval-and-observability`](interviews/llm-eval-and-observability/) ⭐ exemplar,
[`rag-hybrid-search`](interviews/rag-hybrid-search/), [`vector-databases`](interviews/vector-databases/).

---

## The finding worth reading first

Same 1B model, same question, two harnesses, opposite behaviour:

| | Eval prompt (before fix) | Server prompt |
|---|---|---|
| "use ONLY the context" | ✅ | ✅ |
| a refusal string it's *allowed* to emit | ❌ absent | ✅ present |
| result | **fabricated** `CREATE INDEX ON \`bucket_name\`:vindex_name;` | refused correctly, 9 tokens |

**A prohibition with no permitted alternative is a trap, not a constraint.** The eval was silently grading a
weaker prompt than the one shipping — fixed 2026-09-07, with a CI gate so it can't drift back unnoticed. Full
write-up, plus a second real bug found the same day (an "uncalibrated" judge that deterministically inverted a
correct answer, fixed by swapping judge model — confirmed 3/3 on a controlled input):
[`docs/notes/ai-lifecycle-business-cases.md`](docs/notes/ai-lifecycle-business-cases.md) §6,
[`docs/notes/STUDY-GUIDE.md`](docs/notes/STUDY-GUIDE.md) §0.

**Measured, same day:** refusing an out-of-scope question costs **~14× fewer tokens** than answering one (9 vs
128 completion tokens) — scope discipline is a cost control, not just a liability control. And across repeated
runs, this exact 1B model refuses correctly roughly **1 time in 5** on this exact question — the grounded
prompt helps, it does not guarantee compliance. That gap is real information about the model, not a harness bug.

---

## Repo map

```
AI/
├── RAMPUP.md                          # master structure — the two tracks, the 3 named gaps
├── docs/
│   ├── Ask AI design document.md      # anchor case study (shipped, Couchbase)
│   └── notes/
│       ├── STUDY-GUIDE.md             # ← single file for daily learning/revision/prep
│       ├── README.md                  # 12-week session log
│       ├── ai-lifecycle-business-cases.md   # 8 lifecycle stages, each measured locally
│       ├── application-readiness.md   # claim-by-claim resume/skills audit
│       └── career-roadmap.md          # evidence log, topic tiers, weekly cadence
├── evals/                             # promptfoo golden set + CI parity gate
├── fe-hands-on/                       # Agent Console: Go server + Next.js console
└── interviews/                        # whiteboard-ready topic folders
```

## Run it

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest
docker exec ollama ollama pull llama3.2:1b        # generation
docker exec ollama ollama pull qwen2.5:3b         # judge — different family, calibration-checked
docker exec ollama ollama pull nomic-embed-text   # embeddings

cd fe-hands-on/server && go run .                 # :8080
cd fe-hands-on/app/agent-console-ui && npm run dev # :3000

cd evals && npx --yes promptfoo@latest eval       # golden set, local judge, no API key
```

Full config, env vars, and failure-mode notes: [`fe-hands-on/README.md`](fe-hands-on/README.md).

## Accuracy contract

Every file in this repo flags uncertainty rather than stating a guess as fact, marks statistics
"approximately" unless independently re-derived, and keeps the shipped Ask AI system (Lane P) and this lab
build (Lane L) explicitly separate — see [`RAMPUP.md` §5](RAMPUP.md) and
[`docs/notes/application-readiness.md`](docs/notes/application-readiness.md).
