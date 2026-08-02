# 01 — promptfoo eval harness: first golden dataset + LLM-as-judge (Week 1 D3)

> **Status:** 🚧 scaffold — concept notes + setup are pre-filled; the `⟳ FILL DURING SESSION` blocks get completed when you run it with [`../tutor-prompt.md`](../tutor-prompt.md).
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

## Tools & setup (assume clean machine — ⚠️ verify current CLI/schema in promptfoo docs)
```bash
# Node LTS assumed. promptfoo is typically run via npx (verify current invocation):
npx promptfoo@latest init          # scaffolds promptfooconfig.yaml
export OPENAI_API_KEY=sk-...        # provider key; use a separate judge key/model if desired
npx promptfoo@latest eval          # run the suite
npx promptfoo@latest view          # open the local results UI
```
> Reference URLs (from tutor-prompt; confirm live/current): getting started `https://www.promptfoo.dev/docs/getting-started/` · g-eval `https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/g-eval/`

## Key code / config (⚠️ schema names may differ — verify)
```yaml
# promptfooconfig.yaml — providers × prompts × tests × assertions
description: "Ask AI-style RAG answer eval — first golden set"
providers:
  - openai:gpt-4o                      # system under test
prompts:
  - file://prompts/answer.txt          # your RAG answer prompt (context injected via vars)
defaultTest:
  options:
    provider: openai:gpt-4o-2024-08-06 # JUDGE: pin an explicit version; ideally a different model
tests:
  - description: "primary index creation (happy path)"
    vars:
      question: "How do I create a primary index in Capella?"
      context: file://golden/contexts/primary-index.md
    assert:
      - type: contains                 # deterministic, blocks
        value: "CREATE PRIMARY INDEX"
      - type: is-json                  # only if you require structured output
      - type: g-eval                   # model-graded, warn until judge validated
        value: "Answer is faithful to the provided context and gives actionable steps."
    metadata: { tags: [indexes, happy-path] }
```

## Trade-offs (name them)
- **Deterministic vs model-graded:** `contains`/`is-json` are free and non-flaky but can't judge "faithful/helpful"; `g-eval` can, at token cost + variance. → rule-first, judge for semantics.
- **Same vs different judge model:** same-model is convenient but invites self-preference bias. → prefer a different judge.
- **Absolute vs baseline threshold:** absolute bars go permanently red; gate on regression vs a baseline (matters more at Wk4 CI).

## Metrics captured (real, from the run)
```
⟳ FILL DURING SESSION
- # golden cases: …    pass rate (deterministic): …    g-eval avg: …
- tokens/run: …        $/run: …        wall-clock: …
```

## Reference links (2025+, primary; title — url — why)
- promptfoo getting started — `https://www.promptfoo.dev/docs/getting-started/` — harness setup + config schema.
- promptfoo G-Eval — `https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/g-eval/` — the model-graded assertion used here.
- Golden dataset guide — `https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/` — dataset construction.
> ⚠️ I have not re-verified these are live/current — confirm before relying on them. Flag anything pre-2025 if cited later.

## Checkpoint Q&A (prove understanding)
1. Why put the deterministic assertion *before* the g-eval one? — ⟳
2. Why pin the judge model version and use a different model than the subject? — ⟳
3. What can this offline suite *not* catch that only online eval will? — ⟳
   (Expected: real query-distribution shift, provider/corpus changes, long-tail inputs, real user dissatisfaction — see [`../../interviews/llm-eval-and-observability/answers.md`](../../interviews/llm-eval-and-observability/answers.md) A26.)

## Next time
- **Wk1 weekend (note `02`):** Agent Console skeleton — Go/TS backend + Next.js shell + SSE token stream.
- Then **Wk4 (note `06`):** wire this suite into CI as a regression gate (baseline-relative thresholds + cached judge).
