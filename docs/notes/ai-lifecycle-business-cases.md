# AI Lifecycle — Business Cases, Locally Provable

> **Cross-cutting reference**, not a session note. Deliberately **unnumbered**: the `NN-` slots are session
> artifacts and `04` is reserved for the pgvector/Pinecone write-up in
> [`README.md`](README.md). This file is the *why-it-matters* layer under Track A and Track B.
>
> **Anchor case study:** [`../Ask AI design document.md`](../Ask%20AI%20design%20document.md) (shipped).
> **Local proof rig:** [`../../fe-hands-on/`](../../fe-hands-on/) + [`../../evals/`](../../evals/) on Ollama in Docker.
> **Reads with:** [`../../RAMPUP.md`](../../RAMPUP.md) · [`curriculum.md`](curriculum.md) · [`positioning.md`](positioning.md)

**Purpose.** Every stage of the AI lifecycle costs money, carries a named risk, and has an owner who feels it
when it breaks. This file states each stage as a *business case*, cites the **evidence from a system that
actually shipped**, and gives the **command that demonstrates it on your laptop** — no cloud account, no API
key. That combination is the thing interviews actually probe: not "what is RAG", but "what breaks, who pays,
and how do you know before the customer does".

---

## 0. The spine — two planes, one loop

Topic 4's central split ([`../../RAMPUP.md` §2](../../RAMPUP.md)) is the organizing idea, and it is a *cost*
split as much as an architectural one:

```
        KNOWLEDGE PLANE (stateful, cheap to rebuild, expensive to get wrong)
   ┌──────────┬───────────┬──────────────┬──────────────────┐
   │ 2 ingest │ 3 chunk + │ 4 index +    │  versioned,      │
   │ + clean  │   embed   │   retrieve   │  backed up       │
   └──────────┴───────────┴──────────────┴──────────────────┘
                              │ context
                              ▼
        INFERENCE PLANE (stateless, hot-swappable, ~all of the bill)
   ┌──────────────┬─────────────┬────────────────────────────┐
   │ 1 frame/     │ 5 serve     │ 8 iterate · swap · retire  │
   │   scope      │ (rephrase → │    (model deprecation,     │
   │              │  retrieve → │     re-embed, fallback)    │
   │              │  generate)  │                            │
   └──────────────┴─────────────┴────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      6 EVALUATE (pre-ship gate)      7 OBSERVE (in-prod truth)
      golden set · rules · judge      cost · latency · drift · feedback
              └───────────────┬───────────────┘
                              ▼
                      back into 3 / 5 / 8
```

**The one sentence:** the knowledge plane is nearly free to rebuild and catastrophic to corrupt; the inference
plane is where essentially the entire bill lives. Stage 6 exists because nothing else in the loop can tell you
which of the two just broke.

---

## 1. Summary table

| # | Stage | Business case (what it costs when it fails) | Who feels it | Local Docker proof | Gap |
|---|---|---|---|---|---|
| 1 | Frame & scope | Answering out-of-scope questions creates legal/reputational liability | Legal, Support | negative eval case: model must decline | 1 |
| 2 | Ingest & clean | Stale docs → wrong answers on the newest product; churn is weekly | Docs, Product | `CORPUS_DIR` swap, re-index at boot | 2 |
| 3 | Chunk & embed | Bad chunking silently destroys recall; no rollback = outage | Eng, Support | `EMBED_MODEL` swap → recall shift | 2 |
| 4 | Index & retrieve | Wrong docs retrieved → confident wrong answer | Support, Users | `TOP_K` sweep, brute-force = 100% recall baseline | 2 |
| 5 | Serve | Downtime and per-token cost; streaming is a *perceived-latency* lever | SRE, Finance | SSE stream, `PROVIDER=fake`, abort-cancels-generation | 3 |
| 6 | Evaluate | Ship-gate. Without it, every prompt edit is an uncontrolled deploy | Eng, PM | `promptfoo eval` on Dockerized judge | **1** |
| 7 | Observe & operate | Abuse, cost blowout, silent drift | SRE, Finance | `/healthz` dependency health, `docker stats` | 3 |
| 8 | Iterate, swap, retire | Provider deprecates your model on their timeline, not yours | Eng, Finance | `OLLAMA_MODEL=` swap behind the provider seam | — |

---

## 2. Stage detail

### Stage 1 — Frame & scope

**Business case.** A docs assistant that answers *anything* is a liability surface. The shipped design names
this explicitly: the **Ethical & Legal Risks** entry imagines a user seeking **medical advice**, with impact
"legal issues and reputational damage" and mitigation "usage policies, guardrails, disclaimers"
([design doc §7.7](../Ask%20AI%20design%20document.md)). Scope refusal is not a limitation you apologise for —
it is the product boundary that makes the thing shippable.

**Ask AI evidence.** The troubleshooting runbook opens by telling the operator that *"What is React?"* →
*"I'm sorry, I don't have enough information to answer that"* is **expected, correct behaviour** (§8.1). A
refusal is a pass, not a bug.

**Local proof.** Your golden set already encodes this as the harder half — test 2 in
[`../../evals/promptfooconfig.yaml`](../../evals/promptfooconfig.yaml) asks an unanswerable question and
asserts the *presence of a refusal*, because "there are few ways to decline and infinite ways to hallucinate".

**Measured 2026-09-07 — scope discipline is also a cost control.** Through the server, the unanswerable question
returned *"The provided documentation does not cover this."* in **9 completion tokens / 0.90 s**, against
**128 tokens / 7.09 s** for the answerable one. Prompt tokens were near-identical (648 vs 571), so retrieval
cost is flat and the whole saving is generation: a refusal is **~14x cheaper in output tokens** and **~8x
faster**. Every out-of-scope question you decline is a question you barely pay for.

**Interview line.** *"Grounding gave us the refusal for free — before retrieval, a 1B model invented
`CREATE VECTORS ON …` three runs in a row; after retrieval with an explicit permission to say 'not covered',
the same model declined. We didn't need a bigger model, we needed a scope contract."* (from
[`../../fe-hands-on/README.md`](../../fe-hands-on/README.md))

---

### Stage 2 — Ingest & clean

**Business case.** Documentation is "frequently revised" (§4.4.7). Every day the index lags is a day the
assistant confidently describes the previous release. This is the support-deflection metric quietly bleeding
out: users who get a stale answer file a ticket *and* stop trusting the tool.

**Ask AI evidence.** A weekly cron in CP-Jobs fetches HTML from S3, strips headers/footers/sidebars, chunks,
embeds, stores (§4.4.7). Two numbers worth carrying into an interview:

- The job took **5–6 hours synchronous**, reduced to **~20 minutes** with **10 goroutines** (§4.4.7). That is
  a concurrency win expressed in the only unit that matters to a business: how fresh the index can be.
- S3 replication creates a new version of every object daily → **linear storage growth**, still an open
  question with a proposed Lambda retain-latest-*n* sweep (§12.2). Ingest has a *storage* bill, not just a
  compute one.

**Local proof.** Your server indexes a corpus directory at boot, so freshness is a config change:

```bash
CORPUS_DIR=./corpus go run .          # in fe-hands-on/server
curl localhost:8080/healthz           # {"status":"ok","chunks":6,...} — chunk count proves the re-index
CORPUS_DIR= go run .                  # empty → retrieval disabled, the honest degraded mode
```

**Trade-off to name.** Boot-time indexing buys simplicity and pays for it in start-up time and no
persistence — [`../../fe-hands-on/README.md`](../../fe-hands-on/README.md) lists exactly that under *Known
limits*. At Ask AI's 7,597 chunks that trade flips.

---

### Stage 3 — Chunk & embed

**Business case.** This is the stage where quality is destroyed *silently*. A bad chunk boundary or a switched
embedding model doesn't throw — it just returns worse neighbours, and no alert fires. Hence the shipped
system's P1 requirement, stated in business terms: **"Have backup for old vector embeddings. And validate the
newly created embeddings"** (§3.5.3).

**Ask AI evidence.** 2,667 documents → **7,597 chunks**, each ≤1,000 tokens, embedded with
`text-embedding-3-small` (§6.1). Re-embedding the *entire* corpus costs **$0.12** per full pass, or **$0.48/month**
weekly (**$3.12** with `-3-large`). **Rebuilding the whole knowledge plane costs less than a coffee.** That is
the single most useful cost fact in the document, because it means the correct engineering answer to "should we
re-embed?" is almost always yes — the constraint is validation and rollback, never money.

**Local proof.** The embedding model is a validated env var, and the README states the invariant that makes
this stage dangerous — *`EMBED_MODEL` must match the one used to index*:

```bash
docker exec ollama ollama pull nomic-embed-text   # 274 MB, 768-d
EMBED_MODEL=nomic-embed-text go run .             # index and query must agree, or recall silently degrades
```

**Interview line.** *"Embeddings are cheap to recompute and expensive to get wrong, so the design question is
never cost — it's whether you can validate the new index and roll back to the old one. Ask AI made that a P1
requirement, not an optimisation."*

---

### Stage 4 — Index & retrieve

**Business case.** The #1 named risk in the shipped design is **Irrelevant Document Retrieval**: a user asks
about "Operational Cluster", gets "Columnar Cluster" docs, and receives a confident wrong answer (§7.1). Impact
recorded as "inaccurate or hallucinated responses"; mitigation "semantic filtering and hybrid retrieval
combining keyword and vector search". Retrieval quality *is* answer quality — the generator can only be as
right as its context.

**Ask AI evidence.** Hybrid search with re-ranking (§4.4.5); **vector-DB downtime** is its own risk entry with
read replicas, circuit breakers, and cached responses for common queries as mitigation (§7.3).

**Local proof.** Brute-force cosine over the corpus, `TOP_K` configurable:

```bash
TOP_K=4 go run .        # default; sweep 1→8 and watch grounding vs prompt cost
```

**The defensible position** (already argued in your README): under ~10K chunks, exact search is **100% recall
by construction** — no build step, no tuning knob, no recall to lose silently. Reaching for HNSW at that size
is the mistake, not the sophistication. The `Retriever` interface is where a real store slots in when that
stops being true. Note the honest gap: **hybrid/BM25 is still owed** ([`README.md` session 03](README.md)).

---

### Stage 5 — Serve

**Business case.** Two levers, both financial. **Perceived latency:** the NFRs commit to "streaming responses
to enhance perceived performance" (§9.2) — streaming changes nothing about total time and everything about
abandonment. **Per-token cost:** every request is a metered API call, so the *shape* of the request pipeline is
a budget decision.

**Ask AI evidence — the cheap-model trick worth stealing.** Before retrieval, the query plus recent history
goes to a **lightweight** LLM for context-aware rephrasing, resolving "this"/"it"/"these" into a self-contained
query (§4.4.8). Stated benefit: better retrieval *and* "we avoid using a second large LLM call, thus keeping
cost and latency low". Last **5** interactions are included in the prompt. **LLM API failure** is its own risk
entry, mitigated with retries and **multiple provider fallbacks** (§7.4).

**Local proof.** Real SSE token streaming behind a swappable seam, and the failure modes are explicit:

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest
docker exec ollama ollama pull llama3.2:1b
go run .                       # SSE: {sources} {token}* {done}
PROVIDER=fake go run .          # no model server → UI stays developable
```

Three behaviours here are the interview-grade details, all from your README: retrieval failure emits an
`error` frame and **never** degrades into an ungrounded answer; **client disconnect cancels generation
upstream** instead of billing tokens nobody reads; client-supplied `system` messages are **rejected** so a page
cannot overwrite the grounding rules.

---

### Stage 6 — Evaluate (your named #1 gap)

**Business case.** Without a regression gate, every prompt tweak is an unreviewed production deploy of
non-deterministic behaviour. The Arize framing you captured ([`../../Arize/Evaluation.md`](../../Arize/Evaluation.md))
puts it precisely: adding *"respond politely"* can fix one case and break others, so you need a representative
test set rerun on every change. Same prompt → different output means traditional pass/fail testing doesn't
transfer.

**Ask AI evidence (and the honesty note).** Today it is a **Google Sheet** plus a manually triggered Python
script producing three metrics: cosine similarity via **`text-embedding-ada-002`**, GPT-4 **insights**, and a
GPT-4 **classification** into Matched / Improves upon / Partially correct / Completely different (§10). Per
[`../../RAMPUP.md` §5](../../RAMPUP.md): RAGAS, promptfoo, pgvector and Pinecone are **forward-looking learning
targets here, not descriptions of the shipped system.** The business case for automating this is exactly the
word *manually* — a gate a human has to remember to pull is not a gate.

**The eval split, as business cases:**

| Eval type | Business question it answers | Cost profile |
|---|---|---|
| Deterministic rule (`contains`, `not-contains`) | "Did we reintroduce a bug we already fixed?" | ~free, runs first |
| LLM-as-judge (`llm-rubric`) | "Is this *good*, on axes no regex can express?" | a model call per case, needs calibration |
| Online/sampled | "Is production drifting from the golden set?" | continuous, needs telemetry |

**Local proof — both models in Docker, no API key:**

```bash
docker exec ollama ollama pull llama3.2:1b     # system under test  (1.3 GB)
docker exec ollama ollama pull qwen2.5:3b      # judge, DIFFERENT family, calibration-checked (1.9 GB)
cd evals && npx --yes promptfoo@latest eval    # `promptfoo` is NOT on PATH on this machine
npx --yes promptfoo@latest view
```

> Correction to [`../../evals/README.md`](../../evals/README.md): it says `promptfoo eval`, but no global binary
> exists here, so the bare command fails with `promptfoo not found`. Use `npx`, or install it.

**Measured 2026-09-07, first pass (before either fix below):** **1 passed / 1 failed (50%)**, 13 s,
**1,206 tokens** (574 SUT, 632 grading). The happy path passed. **The grounding case failed** — precisely as
note 01 predicted for a 1B model. It invented ``CREATE INDEX ON `bucket_name`:vindex_name;``.

**Two bugs fixed the same day, both found by reading the failure instead of trusting the red X:**

**Bug 1 — prompt parity (fixed).** Detailed just below.

**Bug 2 — judge inversion (fixed).** After fixing the prompt, the server started refusing correctly, but the
`llm-rubric` judge (`qwen2.5:1.5b`) still marked the case FAIL — its own stated reason *agreed* the output had
no SQL statement, then scored the rubric false anyway. **Isolated with a fixed, non-varying SUT output**
("The provided documentation does not cover this.") graded 3x at temperature 0: `qwen2.5:1.5b` returned
`pass=false` deterministically, all 3 runs, same wrong reasoning each time — a real, reproducible calibration
bug, not sampling noise. `qwen2.5:3b` returned `pass=true`, 3/3, on the identical input. Swapped the eval's
judge to `qwen2.5:3b` — see the comment above `defaultTest.options.provider` in
[`../../evals/promptfooconfig.yaml`](../../evals/promptfooconfig.yaml).

**After both fixes, characterized over 6 independent runs** (SUT temperature is not pinned, so wording varies
run to run): **1 refusal, 5 fabrications** — this specific 1B model, on this exact question, complies with the
grounded prompt roughly **1 time in 5** (small sample; order-of-magnitude, not a rate to cite precisely). The
fixed harness now grades this correctly every time — the intermittent red is the model's real behaviour, not a
harness artifact. That is the entire point of fixing the harness: a red result should mean something.

**The finding that matters: your eval grades a weaker prompt than your server ships.** Same `llama3.2:1b`, same
question, opposite behaviour — because the two harnesses send different instructions:

| Instruction | [`../../evals/prompts/answer.txt`](../../evals/prompts/answer.txt) | `groundedSystemPrompt`, [`stream.go:86`](../../fe-hands-on/server/stream.go) |
|---|---|---|
| "use ONLY the context" | yes | yes |
| **an exact refusal string to emit** | **absent** | `"The provided documentation does not cover this."` |
| "never invent syntax, commands, parameters" | absent | yes |
| cite sources by `[n]` | absent | yes |

The eval prompt forbids ungrounded answers but supplies **no licensed alternative**, so a model that cannot
comply has only one move left: answer anyway. **A prohibition without a permitted alternative is not a
constraint, it is a trap.** The server's prompt hands the model an exit, and the same model takes it.

The code comment at [`stream.go:84`](../../fe-hands-on/server/stream.go) already says a model with no such
instruction "fills gaps with fluent invention, which is precisely the failure the eval suite's negative case
exists to catch" — the insight was known, the eval prompt just never caught up. **Consequence:** that red case
currently measures a prompt nobody ships, so it cannot tell you whether the *shipped* grounding still works.
Prompt parity between eval and production is the fix, and it is the highest-value item in section 7.

**Two hard-won lessons already banked** — carry both, they are the credibility:

1. **A false PASS was a malformed rubric, not a weak judge.** A rubric phrased as *instructions* made the judge
   evaluate the rubric's own truth ("the context doesn't cover vector indexes" — true!) and so it passed a
   fabricated answer. Rephrased as an **assertion about the output**, both `qwen2.5:1.5b` and `3b` went 0/5 →
   5/5. Model size was never the variable.
2. **A negative string check is not evidence of grounding.** `not-icontains: "CREATE VECTOR INDEX"` passed while
   the model invented different wording. Assert the **refusal is present** instead.

Plus a tooling trap worth its own sentence: `g-eval` extracts JSON with `/\{.+\}/g`, and JS `.` doesn't match
newlines — so Ollama's pretty-printed `format: json` never matched. `llm-rubric` uses a real brace parser.
Same "model-graded" label, different extraction, and that decides whether a local judge works at all.

---

### Stage 7 — Observe & operate

**Business case.** Three distinct bills. **Abuse:** rate limiting exists to stop DoS and resource abuse (§4.4.9).
**Cost:** token limits are a *finance* control expressed in code. **Silent failure:** an up-but-degraded
dependency is the worst outage because nothing pages.

**Ask AI evidence — real, tiered limits (§4.4.9):** calls/minute per tenant (DoS), requests/day per user
(e.g. 2,000), and **tokens/month per tenant** (e.g. 2M paid / 500K free, from
`IQ_INTEGRATION_TOKENS_RATE_LIMIT_ALLOWED`). Three different limits because there are three different threats:
burst, per-user fairness, and spend. Also shipped: logging across UI and backend for debuggability (§9.3), a
thumbs up/down **feedback store** (§3.2, §4.3.3), and a 7-step troubleshooting runbook that walks S3 → pages
collection → embedding collection → returned chunks (§8) — i.e. an operator can localise a failure to a
*specific plane*.

**Local proof.**

```bash
curl localhost:8080/healthz    # reports DEPENDENCY health: up-but-cannot-reach-model is NOT "ok"
docker stats ollama            # CPU/memory ceiling of the local model server
```

**Honest state of this stage.** Tracing is the least-built part of your rig. [`curriculum.md`](curriculum.md)
targets "Phoenix traces on your Go SSE endpoint". **Verified 2026-09-07:** `docker manifest inspect
arizephoenix/phoenix:latest` succeeds, so that image does exist on Docker Hub. What is **still unverified** is
everything that matters operationally — the port, the OTLP endpoint, and the Go instrumentation needed to emit
spans. Also, [`../../Arize/Evaluation.md`](../../Arize/Evaluation.md) records course concepts (trace
instrumentation, eval runner, datasets, human feedback, prompt playground), not a Docker recipe — **confirm the
current image and port against Phoenix's own docs before writing one down.**

---

### Stage 8 — Iterate, swap & retire

**Business case.** Model deprecation runs on the *provider's* schedule. If a model name is compiled into your
call sites, deprecation is a refactor; if it sits behind a seam, it's a config change. Note the shipped system
already spans **three** model identities — `gpt-4o` for serving (§6.1), `text-embedding-3-small` for indexing
(§4.4.7), `text-embedding-ada-002` + `gpt-4` in the eval script (§10) — so "which model?" is already a
per-plane question there, and each moves on its own clock.

**Ask AI evidence.** The **OpenAI Embedding Service Disruption** risk (§7.5) is the whole stage in one entry:
impact "will continue using old vector embeddings", mitigation "resumable cron jobs with retries" and
"**alternative embedding models** can be used in case of longer disruptions". Swappability is written down as a
*business continuity* control. Phase 2 additionally plans private LLMs and embedding models behind an
**AI-gateway** for private-preview docs (§3.1) — a routing seam, driven by data sensitivity.

**Local proof — the swap is one env var, because the seam exists:**

```bash
OLLAMA_MODEL=llama3.2:1b go run .      # baseline
OLLAMA_MODEL=qwen2.5:1.5b go run .     # swap generation; no code change
```

**Verified 2026-09-07:** `ADDR=:8081 OLLAMA_MODEL=qwen2.5:1.5b go run .` came up reporting
`{"model":"qwen2.5:1.5b","chunks":6,"retrieval":true,"status":"ok"}`. Generation model swapped to a different
*family*; the knowledge plane was untouched, and not a line of code changed. That is the seam paying for
itself — and the contrast with the knowledge plane is the whole point: swapping `EMBED_MODEL` would have
forced a full re-index.

Your three seams, from the README — `provider` (Ollama → Bedrock/OpenAI), `Retriever` (in-memory →
Couchbase/pgvector), and an SSE event contract that **names neither the model nor the store**, so both swap
without UI changes. That last one is the actual architecture answer: the contract is the thing that has to stay
still.

**Interview line.** *"The inference plane is stateless, so I can swap it with an env var. The knowledge plane
is stateful, so swapping it means a re-embed with a validated index and a backup to roll back to — which is why
Ask AI made embedding backup and validation a P1 requirement."*

---

## 3. The cost curve — where the money actually goes

Derived from the design doc's own per-call figures (§6.1), so the arithmetic is checkable:

| Component | Per call | Per 1M requests |
|---|---|---|
| Rephrasing call (GPT-4o, 2.293K in / 0.016K out) | $0.0058925 | **$5,892.50** |
| Main call (GPT-4o, 3.051K in / 0.38K out) | $0.0114275 | **$11,427.50** |
| Query embedding (`text-embedding-3-small`) | $0.00000032 | $0.32 |
| **Total model spend** | **$0.01732** | **≈ $17,320** |

**⚠️ Arithmetic flag — worth fixing in the source doc.** §6.1's rephrasing row prints **$589.25** per 1M
requests, but its own per-call cost × 1M gives **$5,892.50** — a 10× discrepancy. The corrected figure is the
right one, and the doc corroborates it elsewhere: §6.3 lists "Ask AI API Calls **$17.32**/month" at a stated
1,000 requests/month, and $0.01732 × 1,000 = $17.32 exactly. So the printed `589.25` is a typo; `5,892.50` is
consistent with the monthly total. Worth correcting, because the typo makes rephrasing look ~19× cheaper than
the main call when it is really ~**1.9×** — which changes whether the two-call design looks obviously right.

**The crossover, and why it's the interesting number.** Fixed Capella cluster cost is **$208.80/month**;
model spend is **$0.01732/request**:

- At the doc's assumed **1,000 req/month**: total **$227.61**, of which the cluster is **~92%**. Infrastructure
  dominates; model cost is noise.
- Crossover at **208.80 ÷ 0.01732 ≈ 12,000 requests/month** — past that, model calls exceed the entire cluster
  bill.
- At **1M req/month**: ~$17,320 model vs $208.80 cluster — model spend is **~99%**, and the weekly full
  re-embed ($0.48) is roughly **36,000× smaller** than generation.

**The business conclusion:** below ~12K requests/month, optimise infrastructure and ignore token cost; above it,
every optimisation that matters is a token optimisation — semantic caching (already a Future Improvement, §11),
prompt trimming, a smaller rephrasing model, shorter history than 5 turns. *Cost engineering has a threshold,
and naming it is the senior answer.*

---

## 4. Measured run — 2026-09-07 (live Ollama in Docker)

Executed on this machine, not transcribed. Docker Engine **29.5.3**, CPU-only (Docker Desktop on macOS cannot
pass through Apple's GPU, per note 01), models already resident in the `ollama` volume.

**Model inventory** (`docker exec ollama ollama list`) — every size this file quotes, confirmed:
`llama3.2:1b` 1.3 GB (1.2B params) · `qwen2.5:1.5b` 986 MB · `nomic-embed-text` 274 MB (137M, 768-d) · plus
`qwen2.5:3b` 1.9 GB left over from note 01's judge-size experiment.

**Test suites, no model server needed — the claim holds:** **46** Go cases in **0.819 s**, **20** TS cases in
**0.61 s**. 66 total, matching note 03.

**Serving** — `/healthz` → `{"chunks":6,"retrieval":true,"model":"llama3.2:1b","provider":"ollama","status":"ok"}`,
`TOP_K=4`:

| Query | Retrieved | Prompt tok | Completion tok | TTFT | Wall | Server latency |
|---|---|---|---|---|---|---|
| primary index (answerable) | 4 chunks | 571 | 128 | 4.94 s | 7.09 s | 6,957 ms |
| vector index (unanswerable) | 4 chunks | 648 | **9** | 0.75 s | **0.90 s** | 678 ms |

Retrieval pulled `indexes.md` x3 + `data-model.md` for both. The answerable query returned
`CREATE PRIMARY INDEX ON` with scope/collection qualifiers and **no** wildcard form — so note 01's
``not-contains: "`.*`"`` regression guard would pass on this output.

**Eval harness:** 1 pass / 1 fail (50%), 13 s, 1,206 tokens (574 SUT + 632 grading). See stage 6 — the failure
is real and it exposed a prompt-parity defect between the eval and the server.

**Seam swap:** `ADDR=:8081 OLLAMA_MODEL=qwen2.5:1.5b go run .` -> `model: qwen2.5:1.5b`, `chunks: 6`. One env
var, different model family, zero code change.

**Two incidental confirmations of design intent.** Starting a second server on the busy port died with
`listen tcp :8080: bind: address already in use` and **exited non-zero** rather than serving broken — the
"validated at startup, so a bad value stops the process" rule, observed. And `/healthz` reporting `retrieval`
and `model` (not just liveness) is what let me confirm the swap without sending a single query.

---

## 5. What this local rig cannot prove

Stated plainly so no claim outruns the evidence:

- **Scale and concurrency** — one CPU-only Ollama container. Note 01 records that Docker Desktop on macOS
  **can't pass through Apple's GPU**; latency numbers here are not transferable to a GPU deployment.
- **Multi-tenancy** — tenant-scoped call/request/token limits (§4.4.9) need a gateway; there is no auth or rate
  limiting in the Go server at all (its own *Known limits*).
- **Drift over time** — needs sampled production telemetry. Offline evals cannot detect drift by construction.
- **Judge calibration** — the local judge is explicitly **UNCALIBRATED** in your own config comments; treat
  `llm-rubric` scores as warnings, not measurements.
- **Hybrid retrieval** — BM25/hybrid + re-ranking (§4.4.5) is still owed; brute-force cosine is the current
  baseline.
- **VPC/Bedrock deployment, GDPR, auto-scaling** — weeks 9–12 in [`../../RAMPUP.md`](../../RAMPUP.md); nothing
  here demonstrates them.
- **Single-run numbers** — section 4's latencies are **one sample each on a cold-ish CPU-only container**, not
  a benchmark. Treat them as order-of-magnitude. The token counts are exact (server-reported); the wall times
  are not repeatable to two significant figures.
- **Environment flakiness** — note 01 records Docker Desktop quitting twice mid-session and its embedded DNS
  failing to resolve; the daemon was also down at the start of this session. Budget for it.

---

## 6. Accuracy ledger

Per [`../../RAMPUP.md` §5](../../RAMPUP.md):

**Verified by execution, 2026-09-07** (section 4): model inventory and sizes; 46 + 20 tests; `/healthz` shape
and `chunks:6`; both chat behaviours with real token counts; the `promptfoo eval` 1-pass/1-fail result; the
`OLLAMA_MODEL` swap; `arizephoenix/phoenix:latest` existing on Docker Hub; and the fail-fast bind behaviour.

**Verified in-repo** (read directly): every env var (`CORPUS_DIR`, `TOP_K`, `EMBED_MODEL`, `OLLAMA_MODEL`,
`PROVIDER`, `ADDR`); the promptfoo assertions and both eval lessons; `groundedSystemPrompt` at
[`stream.go:86`](../../fe-hands-on/server/stream.go); all Ask AI section references (§3, §4.4.5, §4.4.7–9,
§6.1, §6.3, §7, §8, §9, §10–12).

**Corrected by execution:** [`../../evals/README.md`](../../evals/README.md)'s bare `promptfoo eval` fails here
(`promptfoo not found`) — no global binary on this machine; use `npx --yes promptfoo@latest eval`.

**Derived arithmetic** (recomputed from stated per-call costs — recheck if any price changes): $17,320/1M
requests, the ~12,000 req/month crossover, ~92% / ~99% infrastructure-vs-model shares, ~36,000× re-embed ratio,
and the ~1.9× rephrasing-to-main ratio. The **$5,892.50** correction is derived, not quoted.

**Not verified — do not cite without checking:** Phoenix's port, OTLP endpoint, or Go instrumentation (the
image exists; the wiring is unproven); that OpenAI's
current prices still match §6.1 (that table is a snapshot and model pricing moves); whether `text-embedding-ada-002`
and `gpt-4` are still what the eval script uses today. Nothing here is dated 2025+ by an external source
because **no new external URLs were added** — every citation points at your own repo or the design doc.

**Open question for you:** §6.1's `589.25` — is that a typo in the doc, or is the per-call figure the wrong
one? The §6.3 monthly total says typo, but you have access to the source spreadsheet and I don't.

---

## 7. Next

1. ~~Prompt parity between eval and server~~ **DONE 2026-09-07** — stage 6 above.
2. ~~Judge calibration~~ **DONE 2026-09-07** — swapped to `qwen2.5:3b`; re-run the same fixed-output isolation
   method before trusting any future judge swap.
3. **CI gate on a real runner** — [`.github/workflows/eval-gate.yml`](../../.github/workflows/eval-gate.yml)
   passes locally; push a PR and confirm it executes on GitHub's own runners, not just this laptop.
4. Fix or confirm the `589.25` cell in the Ask AI design doc — needs you, not more local execution — then this
   file's cost section becomes fully quotable in an interview.
5. Stage 7 is still the thinnest. The Phoenix image exists; wire one SSE request end-to-end and this file gains
   its missing observability proof.
6. Grow past 2 golden cases now that the harness grades correctly — citation fidelity, multi-turn, injection.
- Stage 4 is the next *build*: hybrid/BM25 is owed from session 03, and it closes the largest gap between this
  rig and the shipped system.
- When [`../../interviews/llm-serving-and-model-lifecycle/`](../../interviews/) gets authored, stages 5 and 8
  here are its business-case source material; stage 6 already has its exemplar in
  [`../../interviews/llm-eval-and-observability/`](../../interviews/llm-eval-and-observability/).
