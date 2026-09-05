# 01 — promptfoo eval harness: first golden dataset + LLM-as-judge (Week 1 D3)

> **Status:** ✅ run — harness built and executed against local Ollama; metrics + findings below are from the real run.
> **Distills into (Track A):** [`../../interviews/llm-eval-and-observability/`](../../interviews/llm-eval-and-observability/)

**One-line summary:** Stand up promptfoo, write a first golden dataset for a RAG-style prompt, and add both a deterministic assertion and an LLM-as-judge (G-Eval) assertion — the offline half of the eval loop.
**Gap closed:** #1 (evals).
**Capstone contribution:** the seed of the "eval regression suite in CI" for the Agent Console (CI wiring comes Wk4, note `06`).

---

## Concept notes (the mental model before coding)
- Eval splits into **offline (gate, pre-deploy)** vs **online (monitor, post-deploy)**. Today builds *offline*.
- A promptfoo test = **vars** (inputs) + **assert** (scorers). A config matrixes **providers × prompts × tests**.
- **Assertion layers, cheapest first:** deterministic (`contains`, `is-json`, regex) → then model-graded (`g-eval`/`llm-rubric`). Short-circuit expensive judge calls behind cheap checks.
- **LLM-as-judge** scores open-ended quality no rule can express; **G-Eval** has the judge reason over decomposed criteria before scoring.
- Judge hygiene from day one: **use a different model than the one under test**, **pin the judge model version**, and plan to **validate judge vs human labels** before trusting it to gate.
- Keep eval runs **deterministic**: temperature 0; report pass *rate* over enough cases.
- A golden row = input + expectation + scorers + tags; seed from **real queries** (logs/support/docs-search), not invented ones.

## Tools & setup (verified — these are the commands that actually ran)
No API key was available, so both the system-under-test and the judge run **locally on Ollama in Docker**.
That also makes `$/run = $0`, which is why more golden cases are cheap to add later.
```bash
# 1. local model server (CPU-only: Docker Desktop on macOS can't pass through Apple's GPU)
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest
docker exec ollama ollama pull llama3.2:1b     # system under test  (1.3 GB)
docker exec ollama ollama pull qwen2.5:1.5b    # judge, different family (986 MB)

# 2. harness
cd evals/
npx promptfoo@latest init                      # scaffolds promptfooconfig.yaml
npx promptfoo@latest eval --no-cache           # run the suite
npx promptfoo@latest eval -o result.json       # same, but machine-readable (needed to see WHY a case failed)
npx promptfoo@latest view                      # local results UI
```
> The CLI table truncates output columns, so a failing case shows `[FAIL]` without a usable reason.
> `-o result.json` → `gradingResult.componentResults[]` gives per-assertion `pass`/`score`/`reason`. Use it.
> Gotcha: Docker Desktop quit twice mid-session on this machine; its embedded DNS also failed to resolve
> Ollama's CDN once (`no such host`) while the host resolved it fine. Retry, or run Ollama natively.
> Reference URLs (from tutor-prompt; confirm live/current): getting started `https://www.promptfoo.dev/docs/getting-started/` · g-eval `https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/g-eval/`

## Key code / config (as shipped — [`../../evals/promptfooconfig.yaml`](../../evals/promptfooconfig.yaml))
```yaml
# providers × prompts × tests × assertions
description: "Ask AI-style RAG answer eval — first golden set"

providers:
  - id: ollama:chat:llama3.2:1b        # system under test

prompts:
  - file://prompts/answer.txt          # RAG answer prompt; {{context}}/{{question}} injected via vars

defaultTest:
  options:
    provider:
      id: ollama:chat:qwen2.5:1.5b     # JUDGE: different family than the subject (self-preference bias)
      config:
        passthrough:
          format: json                 # REQUIRED for small local judges — see failure #1 below

tests:
  - description: "primary index creation (happy path)"
    vars:
      question: "How do I create a primary index in Capella?"
      context: file://golden/contexts/primary-index.md
    assert:
      - type: contains                 # deterministic, cheap, runs regardless
        value: "CREATE PRIMARY INDEX"
      - type: g-eval                   # model-graded — treat as WARN until the judge is calibrated
        value: "Answer is faithful to the provided context and gives actionable steps."
    metadata: { tags: [indexes, happy-path] }
```
Layout: `evals/promptfooconfig.yaml` · `evals/prompts/answer.txt` · `evals/golden/contexts/primary-index.md`.
`file://` paths resolve relative to the config, so run `promptfoo eval` from inside `evals/`.

## Trade-offs (name them)
- **Deterministic vs model-graded:** `contains`/`is-json` are free and non-flaky but can't judge "faithful/helpful"; `g-eval` can, at token cost + variance. → rule-first, judge for semantics.
- **Same vs different judge model:** same-model is convenient but invites self-preference bias. → prefer a different judge.
- **Absolute vs baseline threshold:** absolute bars go permanently red; gate on regression vs a baseline (matters more at Wk4 CI).

## Metrics captured (real, from the run)
Harness lives in [`../../evals/`](../../evals/). Ran against **local Ollama in Docker** (no API key available):
system-under-test `ollama:chat:llama3.2:1b`, judge `ollama:chat:qwen2.5:1.5b`.

```
- # golden cases: 1     pass rate (deterministic `contains`): 1/1 (100%)     g-eval: 1.0 (threshold 0.7)
- tokens/run: 1,179 total — provider 278 (217 prompt / 61 completion), grading 901 (841 prompt / 60 completion)
- $/run: $0.00 (local inference)     wall-clock: 12s     generation latency: 5,148ms
```

**Judge cost dominates: 901 grading tokens vs 278 provider tokens — the judge cost ~3.2× the thing it judged.**
That ratio is the whole argument for putting cheap deterministic assertions first.

### Two real failures found by running it (not from reading about it)
1. **The judge couldn't be parsed.** First run: `contains` passed, `g-eval` failed with
   `LLM-proposed evaluation result is not in JSON format`. The judge had actually scored the answer
   *correctly* (`"score": 1`) but wrapped its JSON in a ```` ```json ```` markdown fence, which the parser rejects.
   Small local models follow strict output-format instructions less reliably than hosted ones.
   **Fix:** force JSON mode on the judge provider —
   ```yaml
   provider:
     id: ollama:chat:qwen2.5:1.5b
     config:
       passthrough: { format: json }   # raw JSON, no markdown fencing
   ```
   Note the failure mode: a *formatting* problem in the judge presented as a *quality* failure of the answer.

2. **The judge passed a hallucination.** On the passing run the model answered with
   ``CREATE PRIMARY INDEX ON `bucket_name`.*`` — a `.*` wildcard form that appears **nowhere** in the supplied
   context (the context gives only the fully-qualified and bare-bucket forms). `contains` passed (it only greps
   for the literal substring, by design). `g-eval` scored it **1/1, "faithfully follows the context."** It did not.
   → A green suite is not evidence the judge works. This is exactly what "validate judge vs human labels" means.

### Round 2 — adding a negative case, and measuring the judge
Added a second golden case: a question the context **cannot** answer ("how do I create a vector index?"
against a primary-index-only context). The prompt says *use ONLY the context*, so the correct behaviour is to
decline. Three more findings, each from a real run.

**3. `g-eval` is unusable with a local judge; `llm-rubric` is not.** Both are model-graded, but they extract
the judge's JSON differently — traced in promptfoo's own source:

| assertion | extraction | multi-line JSON |
|---|---|---|
| `g-eval` | `resp.output.match(/\{.+\}/g)` | ❌ JS `.` skips `\n`, so pretty-printed JSON never matches |
| `llm-rubric` | `extractJsonObjects()` (brace parser) | ✅ fine |

Ollama's `format: json` emits **pretty-printed** JSON (`'{\n  "score": 1,...'`). So `g-eval` failed
intermittently with `LLM-proposed evaluation result is not in JSON format` — while the JSON was perfectly
valid. It "passed" once only because the model happened to emit one line that run. → **use `llm-rubric` with
local models.**

**4. A negative string assertion only catches the wording you guessed.** First attempt was
`not-icontains: "CREATE VECTOR INDEX"`. It passed — while the model invented
`CREATE INDEX index_name ON bucket_name`. Different wording, same hallucination.
→ Assert the **refusal is present** (`icontains-any: ["does not cover", "no information", …]`) instead of
guessing which invention is absent. **There are few ways to decline and infinite ways to hallucinate; match
the small set.** After the swap the case correctly went red on
``CREATE VECTORS ON `bucket_name`.`vector_name`;``.

**5. Judge agreement, measured: 1/2 = 50%.** Hand-label vs judge on the two cases:

| case | human label | `llm-rubric` (qwen2.5:1.5b) | agree? |
|---|---|---|---|
| primary index (happy path) | pass | pass | ✅ |
| vector index (unanswerable) | **fail** — invented syntax | **pass** | ❌ |

On the grounding case the judge was wrong **three runs in a row**, each time asserting *"correctly states the
provided context does not cover vector indexes"* about an answer that did the opposite. It did not merely
score generously — **it fabricated its justification.**

**The headline:** the `icontains-any` check — 8 strings, $0, instant — caught the hallucination that the
LLM judge missed every single time. Cheap and dumb beat expensive and smart. That inverts the usual
intuition, and it is why the assertion order in this suite is not just a cost optimisation.

> **Status of the judge: NOT fit to gate.** 50% agreement on n=2 is a coin flip. Until agreement is measured
> over a real batch and is high, `llm-rubric` here is a warning signal only. A green suite proved nothing —
> it went green while passing a fabrication.

## Reference links (2025+, primary; title — url — why)
- promptfoo getting started — `https://www.promptfoo.dev/docs/getting-started/` — harness setup + config schema.
- promptfoo G-Eval — `https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/g-eval/` — the model-graded assertion used here.
- Golden dataset guide — `https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/` — dataset construction.
> ⚠️ I have not re-verified these are live/current — confirm before relying on them. Flag anything pre-2025 if cited later.

## Checkpoint Q&A (prove understanding)
1. Why put the deterministic assertion *before* the g-eval one? — **Cost and flakiness, both measured.**
   `contains` is a substring match: 0 tokens, 0ms, same answer every time. The `g-eval` call burned 901 tokens
   and ~5s. Measured ratio this run: judge cost **3.2×** the generation it was judging. If a cheap rule can
   already prove the answer is wrong, spending a judge call to re-confirm it is waste. Rule-first, judge for
   semantics only.
2. Why pin the judge model version and use a different model than the subject? — **Different model** avoids
   self-preference bias (a model rates its own output generously). **Pinning** matters because judges are
   fragile in ways that have nothing to do with answer quality: this run, the *only* thing that flipped the
   assertion from FAIL to PASS was the judge's output *format* (markdown-fenced vs raw JSON). The answer never
   changed. An unpinned judge upgrade can silently move every score in the suite, and you'd read it as a
   quality regression.
3. What can this offline suite *not* catch that only online eval will? — Real query-distribution shift,
   provider/corpus changes, long-tail inputs, and real user dissatisfaction. Tonight added a sharper one:
   **it cannot catch a judge that is confidently wrong.** The suite went green while passing a hallucinated
   syntax form. Nothing inside the offline loop flagged it — only a human reading the output did. That's the
   argument for judge calibration (score a batch by hand, compare human vs judge agreement, only then let it
   gate) and for online feedback signals.
   (See also [`../../interviews/llm-eval-and-observability/answers.md`](../../interviews/llm-eval-and-observability/answers.md) A26.)
   (Expected: real query-distribution shift, provider/corpus changes, long-tail inputs, real user dissatisfaction — see [`../../interviews/llm-eval-and-observability/answers.md`](../../interviews/llm-eval-and-observability/answers.md) A26.)

## Next time
- **Calibrate the judge before trusting it.** Sample size of 1 proves nothing either way. Add golden cases
  (including deliberate hallucinations as negative cases), hand-label them, measure human-vs-judge agreement.
  Until that number exists, `g-eval` is a warning signal, not a gate.
- Add a **negative case** for the exact bug found tonight: an answer using unsupported syntax should FAIL.
  Right now nothing in the suite would catch it.
- **Note `02` (done, out of order — built Wk1 wknd before this session):** Agent Console skeleton, Go SSE +
  Next.js shell. Its `/stream` handler still returns a hardcoded string — no LLM in the loop, so there is
  nothing for a judge to judge. **Wiring it to real Ollama streaming is what makes this suite point at the
  capstone** instead of a standalone prompt.
- Then **Wk4 (note `06`):** wire this suite into CI as a regression gate (baseline-relative thresholds + cached judge).
