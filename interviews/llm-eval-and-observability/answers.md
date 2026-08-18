# LLM Eval & Observability — Answers

> Keyed to [`questions.md`](questions.md). Each answer includes a comparison table **or** code, and ends with a **Key takeaway**.
> Accuracy note: tool/metric names change fast — where flagged, **verify against current docs**. Ask AI facts are drawn from [`../../docs/Ask AI design document.md`](../../docs/Ask%20AI%20design%20document.md).

---

## Level 1 — Fundamentals

### A1. What eval is, and why classic ML metrics don't transfer cleanly
Eval = a repeatable way to turn a model's *behavior on chosen inputs* into a *number or verdict* you can compare across changes. LLM outputs are open-ended text, so there's usually no single correct string to match.

| Classic ML | LLM feature |
|---|---|
| Fixed label space, one right answer | Many acceptable answers, phrased differently |
| Accuracy/F1 vs ground truth | Often no ground-truth string → need judges/rubrics |
| Deterministic given input | Stochastic (temperature, provider changes) |
| Metric is the target | Metric is a *proxy* that can be gamed (Goodhart) |

**Key takeaway:** LLM eval measures *quality of open-ended behavior with proxies*, so you combine deterministic checks, model-graded judgment, and production signals rather than trusting one accuracy number.

### A2. Offline vs online, and the decision each gates

| | Offline eval | Online eval |
|---|---|---|
| Runs on | Fixed golden dataset | Sampled live traffic |
| When | Pre-deploy (CI) | Post-deploy (prod) |
| Gates | *Should this change ship?* | *Is what shipped still good?* |
| Cost model | Bounded (N cases) | Unbounded → must sample |
| Blind spot | Only what's in the set | Only what traffic exercises |

**Key takeaway:** Offline is a **gate**, online is a **monitor** — they answer different questions and neither replaces the other.

### A3. Families of eval signal

| Family | Example | Cost | Catches |
|---|---|---|---|
| Deterministic/rule | JSON-schema valid? contains citation? | ~free | Format/safety violations |
| Reference-based | similarity to a gold answer | low | Drift from known-good |
| Model-graded (LLM-as-judge) | "is this answer faithful to context?" | high | Open-ended quality |
| Human | SME rates 50 answers | very high | Ground truth, judge calibration |
| Production/implicit | thumbs-down, retry, abandon | ~free at scale | Real-world dissatisfaction |

**Key takeaway:** Layer cheap deterministic checks first, model-graded for nuance, and treat human + production signal as the calibration/ground-truth anchors.

### A4. What you actually measure for RAG
Not "looked good" — decompose into **retrieval quality** (did we fetch the right context?) and **generation quality** (did we answer faithfully from it?).

| Dimension | Question | Example metric |
|---|---|---|
| Retrieval | Is the answer-bearing chunk in top-K? | context recall / precision, hit@K |
| Faithfulness | Is every claim grounded in retrieved context? | faithfulness/groundedness |
| Relevancy | Does the answer address the question? | answer relevancy |
| Format/safety | Citations present? no PII? | rule checks |

**Key takeaway:** "It looked good" isn't reproducible; decomposing into retrieval vs generation makes failures *attributable and fixable*.

### A5. *(Failure mode)* Shipping a prompt change with zero eval
Concrete harms and the minimum guard:

| Harm | How it manifests | Minimum eval that catches it |
|---|---|---|
| Regression on old cases | Previously-good answers break | Golden set of ~20 cases + rule checks |
| Format break | Downstream parser fails on new output | JSON-schema/regex assertion |
| Hallucination increase | Confident wrong answers | Faithfulness judge on golden set |
| Cost/latency spike | Longer prompt → more tokens | Token/latency assertion |

**Key takeaway:** Even 20 golden cases with deterministic + one faithfulness check would turn a silent Friday regression into a red CI check.

---

## Level 2 — Golden datasets

### A6. What a golden dataset row contains (RAG)
```yaml
# one golden case for a RAG feature
- id: capella-index-create-001
  query: "How do I create a primary index in Capella?"
  # optional gold context / answer if you have them (reference-based)
  expected_contexts: ["doc://capella/indexes/primary"]
  expected_answer_points:            # rubric points, not exact string
    - "use CREATE PRIMARY INDEX"
    - "names the bucket/scope/collection"
  assertions:                        # scorers to run
    - type: contains
      value: "CREATE PRIMARY INDEX"
    - type: llm-rubric               # model-graded
      value: "answer is faithful to expected_contexts and actionable"
  tags: [indexes, sql++, happy-path]
```
**Key takeaway:** A golden row is *input + expectation + the scorers to apply + tags* — not necessarily an exact answer string.

### A7. Bootstrapping the first golden set with no labels

| Source | How |
|---|---|
| Real queries | Mine production/support logs, FAQ, docs search terms |
| SME seeding | Ask domain experts for the 20 questions users always ask |
| Synthetic-from-corpus | Generate Q from known doc chunks (the chunk *is* the gold context) |
| Incident harvest | Every reported bad answer becomes a permanent case |

**Key takeaway:** Start from *real questions you already have* (logs + support + docs), then grow the set from every production failure — don't wait for a "perfect" dataset.

### A8. Size and mix

| Bucket | Rough share | Purpose |
|---|---|---|
| Happy path | ~40% | Guard core quality |
| Edge/rare | ~25% | Ambiguity, multi-hop, long context |
| Adversarial | ~20% | Prompt injection, out-of-scope, "I don't know" cases |
| Regression | ~15% | Exact past incidents |

Start ~30–50 cases; grow to a few hundred. *(These are planning ratios to tune, not a rule.)*

**Key takeaway:** Coverage of *failure shapes* matters more than raw count; a curated 50 beats an unlabeled 5,000.

### A9. Keeping the set from rotting

| Rot source | Countermeasure |
|---|---|
| Corpus changes (docs edited) | Pin expected_context by stable doc id, re-verify on corpus refresh |
| Product changes | Review golden set each release; retire dead features |
| Model changes | Re-baseline scores, keep the cases |
| Staleness | Quarterly SME review; track "last verified" per case |

**Key takeaway:** Treat the golden set as *versioned code with an owner and a review cadence*, not a one-time artifact.

### A10. *(Failure mode)* Score 0.95 but users unhappy
Likely dataset pathologies:

| Cause | Detection |
|---|---|
| Set doesn't reflect real traffic | Compare golden query distribution vs prod logs |
| Contaminated/too-easy cases | Inspect: are answers trivially in the prompt? |
| Metric measures the wrong thing | Correlate golden scores with production thumbs-down |
| Overfit to the set | Hold out a fresh, never-tuned slice |

**Key takeaway:** A high, flat offline score with unhappy users means the *golden set or metric is wrong* — validate it against real traffic and a held-out slice.

---

## Level 3 — Metrics & scoring

### A11. Deterministic vs model-graded

| Use deterministic when | Use model-graded when |
|---|---|
| Criterion is objective/structural | Criterion is subjective/semantic |
| JSON valid, regex, contains, exact | "faithful", "helpful", "on-topic" |
| Safety/format must be **guaranteed** | Nuance no rule can express |

Two criteria that **must** be rule-based: (1) **format/schema validity** (downstream parsing depends on it), (2) **hard safety** (PII pattern, blocklist) — you never want a stochastic judge deciding those.

**Key takeaway:** Rule-based for anything objective or safety-critical; reserve the expensive judge for genuinely semantic criteria.

### A12. Retrieval vs generation metrics

| Layer | Metric | Catches |
|---|---|---|
| Retrieval | context recall | answer-bearing chunk missing from top-K |
| Retrieval | context precision | right chunk buried under noise |
| Generation | faithfulness/groundedness | claims not supported by context |
| Generation | answer relevancy | on-topic but doesn't answer the question |

*(Names follow the Ragas-style taxonomy — verify exact names/definitions in current docs.)*

**Key takeaway:** Split metrics by layer so a bad answer points you at *retrieval or generation*, not a vague "quality" number.

### A13. Faithfulness vs answer relevancy
- **Faithfulness:** every claim is entailed by the retrieved context (no hallucination).
- **Answer relevancy:** the answer actually addresses the user's question.

| | Faithful | Unfaithful |
|---|---|---|
| **Relevant** | ✅ ideal | plausible but hallucinated |
| **Irrelevant** | grounded but off-topic | worst case |

**Key takeaway:** You need both — a grounded answer to the wrong question and a fluent hallucination are *both* failures, and they're different axes.

### A14. Reference-based vs reference-free

| | Reference-based | Reference-free |
|---|---|---|
| Needs | A gold answer/context | Nothing but the output (+context) |
| Forced into reference-free when | — | Open-ended gen, no single right answer, fresh prod traffic |
| You lose | — | Ability to measure *correctness* vs truth; judge becomes the only arbiter |

**Key takeaway:** Reference-free scales to production but only measures *plausibility/consistency*; keep a reference-based golden core for true correctness.

### A15. *(Failure mode)* Rule passes, judge fails

| Step | Action |
|---|---|
| 1 | Inspect the actual output — which scorer is right? |
| 2 | If rule is too loose (e.g. `contains` matched coincidentally) → tighten it |
| 3 | If judge is wrong → check judge prompt/bias, add a few-shot anchor |
| 4 | In CI, **block on the deterministic check**; treat judge as a *trend/soft signal* unless the judge is validated (A18) |

**Key takeaway:** In a hard gate, trust validated deterministic checks to *block*; use the judge to *flag*, because a mis-calibrated judge shouldn't fail builds.

---

## Level 4 — LLM-as-judge

### A16. Mechanics + G-Eval

| Mode | Prompt | Output |
|---|---|---|
| Pointwise | "Rate this answer 1–5 on faithfulness, with reasons" | score + rationale |
| Pairwise | "Which answer is better, A or B?" | preference |

**G-Eval** (as offered in promptfoo's model-graded assertions) improves on a naive "rate 1–5" by having the judge *decompose criteria and reason step-by-step (chain-of-thought) before scoring*, which aligns better with human judgment. *(Verify current behavior in promptfoo's g-eval docs.)*

**Key takeaway:** Pairwise is more reliable for "did we improve?"; G-Eval's criteria-decomposition + reasoning beats a bare numeric prompt.

### A17. Judge biases + mitigations

| Bias | Symptom | Mitigation |
|---|---|---|
| Position | Prefers whichever answer is shown first | Randomize/swap order; average both orders |
| Verbosity | Longer answer scores higher | Penalize length in rubric; normalize |
| Self-preference | Judge favors outputs from its own model family | Use a *different* model as judge |
| Leniency/clustering | Everything gets 4/5 | Force a rubric with explicit fail criteria + few-shot fails |

**Key takeaway:** Judges have systematic, documented biases — design the prompt and protocol to neutralize them, don't assume the judge is neutral.

### A18. Validating the judge itself
```text
1. SME hand-labels N cases (say 50–100).
2. Run the judge on the same cases.
3. Measure judge↔human agreement (e.g. Cohen's kappa / % agreement).
4. Accept judge for CI only if agreement clears a bar you set (e.g. kappa "substantial").
5. Re-validate whenever the judge model/prompt changes.
```
*(Kappa thresholds are conventional bands — verify the interpretation you cite.)*

**Key takeaway:** An unvalidated judge is just another opinion; prove judge↔human agreement *before* letting it gate merges, and re-prove it on every judge change.

### A19. Keeping judge eval affordable

| Lever | Effect |
|---|---|
| Use a smaller/cheaper judge model | Lower $/call; re-validate agreement |
| Cache by (prompt+output) hash | Skip re-judging unchanged outputs |
| Judge only changed/failing cases in PR CI | Full judge run nightly |
| Deterministic checks first, judge only if they pass | Judge fewer cases |
| Sample in production (not 100%) | Bounds online cost |

**Key takeaway:** Tier the judge — cheap model, cached, gated behind rule checks, full run nightly — so per-case judging doesn't dominate your bill.

### A20. *(Failure mode)* Provider silently upgrades the judge model
What happened: the judge model version drifted, so the *measurement instrument* changed, not the system under test.

| Prevention | How |
|---|---|
| Pin judge model version | Reference an explicit dated model id, not a floating alias |
| Track judge version in results | Store it alongside every score |
| Re-baseline on judge change | Re-run A18 validation |
| Alert on baseline shift | Flag if unchanged-input scores move |

**Key takeaway:** Pin and version the judge like any dependency — an unpinned judge means your scores move for reasons that have nothing to do with your product.

---

## Level 5 — Harness & CI

### A21. Why a harness (promptfoo) over a script
```yaml
# promptfoo-style config: providers × prompts × tests × assertions (verify current schema)
providers: [openai:gpt-4o]         # can matrix multiple models/prompts
prompts: [file://prompts/answer.txt]
tests:
  - vars: { query: "How do I create a primary index in Capella?" }
    assert:
      - type: contains
        value: "CREATE PRIMARY INDEX"
      - type: g-eval
        value: "answer is faithful to retrieved context and actionable"
```
A harness gives you the **matrix** (providers × prompts × tests), a library of **assertion types**, result diffing/caching, and a CI reporter — all of which you'd otherwise rebuild.

**Key takeaway:** A harness turns eval into declarative config with a built-in matrix, assertions, and CI output — reuse it instead of hand-rolling and re-inventing scorers.

### A22. Setting thresholds without a permanently-red gate

| Strategy | Description |
|---|---|
| Baseline-relative | Fail if score drops > X vs the last green baseline (not an absolute bar) |
| Per-assertion pass rate | e.g. "≥ 95% of format checks pass, faithfulness ≥ baseline − 2pts" |
| Warn vs block tiers | Deterministic → block; judge → warn until trusted |
| Ratchet | Raise the bar only after sustained improvement |

**Key takeaway:** Gate on *regression vs a baseline*, not a fixed absolute score, and tier block-vs-warn so the gate stays credible and green-able.

### A23. Making a non-deterministic gate stable

| Source of variance | Control |
|---|---|
| Sampling temperature | Set temperature = 0 for eval runs |
| Judge variance | Pin judge; average k judgments if needed |
| Small-sample noise | Enough cases per assertion; report pass *rate* |
| Flaky single cases | Quarantine known-flaky, run n-times, require majority |

**Key takeaway:** Remove avoidable randomness (temp=0, pinned judge) and design thresholds on *rates over enough cases* so normal variance doesn't flip the gate.

### A24. Where the gate sits

| Stage | Runs | Cost budget |
|---|---|---|
| Pre-commit (local) | fast rule checks on a few cases | seconds |
| PR CI | rule checks + judge on changed/critical cases | minutes, $ low |
| Nightly | full golden set + full judge matrix | longer, $ higher |
| Pre-deploy | smoke subset + safety checks | fast |

**Key takeaway:** Cheap-and-fast on every PR, expensive-and-thorough nightly — match eval depth to how often the stage runs.

### A25. *(Failure mode)* 40-min, $12 eval that people skip
Fix the incentive by cutting cost/latency, not coverage:

| Action | Effect |
|---|---|
| Split PR subset vs nightly full run | PR gate → minutes |
| Cache judge results by input hash | Skip unchanged |
| Parallelize provider calls | Wall-clock down |
| Cheaper judge model + rule-first | $ down |
| Show eval diff in PR (fast feedback) | Devs *want* to run it |

**Key takeaway:** If eval is skipped it isn't protecting anything — make the PR path fast/cheap (subset + cache + parallel) and push the full run to nightly.

---

## Level 6 — Online eval & observability

### A26. What online catches that offline can't

| Only visible online |
|---|
| Real query distribution shift (users ask new things) |
| Corpus/provider changes after deploy |
| Long-tail inputs never in the golden set |
| Real user dissatisfaction (thumbs, abandon) |
| Cost/latency under real load |

**Key takeaway:** Offline is bounded by what you imagined; online is the only place you see the inputs and failures you *didn't* anticipate.

### A27. What to instrument per request
```text
trace: one user question
 ├─ span: rephrase LLM call      { tokens_in/out, latency, model, cost }
 ├─ span: embed query            { latency, dims }
 ├─ span: hybrid retrieve        { k, scores, doc_ids, latency }
 ├─ span: re-rank                { input_n, chosen_ids }
 └─ span: answer LLM call (SSE)  { tokens_in/out, latency, ttft, cost }
attributes: request_id, tenant_id, prompt_version, model_version, feedback
```
| Signal | Feeds |
|---|---|
| tokens_in/out, model | **cost** |
| latency, time-to-first-token | **latency** |
| doc_ids/scores, faithfulness sample | **quality** |

**Key takeaway:** Model each request as a trace of spans with tokens/latency/ids per step, plus prompt/model *versions* as attributes — that's what lets you tie a complaint to a root cause.

### A28. Sampling + implicit signals

| Implicit signal | Quality interpretation |
|---|---|
| 👍 / 👎 | explicit satisfaction (sparse) |
| Copied answer / code | likely useful |
| Immediate retry / rephrase | likely unhelpful |
| Abandon / bounce | likely failed |
| Follow-up "no, I meant…" | misunderstood |

Sample a small % (e.g. 1–5%, tune to budget) for async LLM-judge scoring; use implicit signals on 100% since they're ~free.

**Key takeaway:** Judge a *sample* for depth, but mine *free implicit signals on all traffic* — retries and abandons are your highest-volume quality proxy.

### A29. Drift and alerting

| Drift type | Signal | Alert on |
|---|---|---|
| Input drift | embedding distribution of queries moves | new-topic clusters, OOD rate ↑ |
| Output/quality drift | sampled judge score, thumbs-down rate | score ↓ vs rolling baseline |
| Cost drift | tokens/request, $/request | > threshold vs baseline |

**Key takeaway:** Watch three drifts separately (input, quality, cost) against rolling baselines — they have different causes and different runbooks.

### A30. Inline guardrails vs async online eval

| Inline (blocking, must be cheap/fast) | Async (online eval, sampled) |
|---|---|
| PII/secret regex, blocklist | Faithfulness judging |
| JSON-schema validity | Answer-relevancy scoring |
| Max-token / cost cap | Drift analytics |
| Simple injection heuristics | Trend dashboards |

**Key takeaway:** Only cheap, deterministic safety belongs inline on the request path; anything model-graded runs async on a sample so you don't add latency/cost to every call.

### A31. *(Failure mode)* 2 AM silent quality drop — runbook

| Phase | Action |
|---|---|
| Detect | thumbs-down rate / judge-sample score breaches alert vs baseline |
| Triage | check dashboards: provider model version? re-embed job status? latency? |
| Attribute | trace a few bad requests: retrieval empty? faithfulness low? |
| Mitigate | roll back prompt/model version pin; re-run/repair embed job; failover provider |
| Prevent | pin versions, alert on embed-job success, canary deploys |

Users likely see confidently-wrong or empty-context answers with no error.

**Key takeaway:** Silent degradation needs *alerting on quality proxies* + *version pins to roll back to* + *job-success monitoring* — because nothing throws an exception when answers merely get worse.

---

## Level 7 — Evaluating a RAG system end-to-end

### A32. Attributing blame: retrieval vs generation
```text
Experiment 1 — retrieval in isolation:
  Is the answer-bearing chunk in top-K?  → measure context recall.
  If NO  → retrieval fault (chunking, embedding, K, re-ranker, query rephrase).

Experiment 2 — generation given gold context:
  Feed the KNOWN-correct context to the LLM.
  If answer now correct → generation was fine; retrieval was the fault.
  If answer still wrong → generation fault (prompt, model, faithfulness).
```
**Key takeaway:** Fix retrieval and generation separately: check "is the right chunk retrieved?" then "given the right chunk, is the answer right?" — the second experiment cleanly isolates generation.

### A33. Evaluating the re-ranker (Ask AI adds a custom one)
Ask AI's re-ranker = base score + length preference (favor medium chunks) + content-type bonuses (code/headings).

| Metric | Question |
|---|---|
| nDCG / MRR @K | Are the *most* relevant chunks ranked highest? |
| Recall@K before vs after re-rank | Does re-ranking keep the gold chunk in the window? |
| Ablation | Turn each bonus off — does answer quality drop? |

**Key takeaway:** Evaluate a re-ranker with rank-aware metrics (nDCG/MRR) and *ablations* of each heuristic, so you know each bonus earns its place rather than assuming it helps.

### A34. Critique of Ask AI's current eval (cosine `ada-002` + GPT-4 classifier in a sheet)

| Good | Missing / to add first |
|---|---|
| Has a repeatable script + labels | Not in CI → no regression gate (add promptfoo gate — this is Wk4) |
| Human-readable classes (Matched / Improves / Partial / Different) | No retrieval-vs-generation split → can't attribute failures |
| Uses a real similarity signal | `ada-002` is an older embedding for scoring — verify vs current models |
| GPT-4 judge gives nuance | Judge not validated vs humans (A18); no bias controls |
| — | No online eval loop from production signals |

**Key takeaway:** The sheet is a solid *manual baseline*; the highest-value upgrades are **(1) put it in CI as a gate, (2) split retrieval vs generation metrics, (3) validate the judge** — which is exactly the Track B Wk1/Wk4 work.

### A35. *(Failure mode)* Recall fine but answer still wrong — generation causes

| Generation-side cause | How eval surfaces it |
|---|---|
| Prompt ignores/underweights context | faithfulness low despite good context |
| Context lost in the middle (long prompt) | faithfulness ↓ as context length ↑ |
| Model over-relies on parametric memory | answer contradicts provided context |
| Over-truncation / K too low for synthesis | partial answers on multi-chunk questions |

**Key takeaway:** When retrieval is good but answers are wrong, it's a *generation* problem — measure faithfulness given known-good context to pinpoint prompt/model/positional causes.

---

## Level 8 — Architect / Staff

### A36. Org-wide eval strategy

| Concern | Design |
|---|---|
| Golden-set ownership | Each feature team owns its set; platform owns the harness |
| Threshold location | Versioned in-repo with the prompts they gate |
| Judges | Central, validated, version-pinned judge service |
| Cost | Eval spend budgeted + dashboarded per team; cache shared |
| Standards | Shared assertion library + a "definition of eval done" |

**Key takeaway:** Centralize the *harness, judges, and standards*; decentralize *golden sets and thresholds* to the teams who own the features.

### A37. Eval for agents vs single-shot RAG

| New surface (agents) | What to eval |
|---|---|
| Multi-step trajectory | Did it take a sensible path, not just end state? |
| Tool calls (MCP) | Right tool, right args, handled errors? |
| Approval gates | Did it stop for human approval where required? |
| Cost/loops | Did it terminate; token/step budget respected? |
| State across steps | No context dropped/corrupted mid-trajectory |

**Key takeaway:** Agents need *trajectory and tool-use* eval (path, tool correctness, termination, approvals), not just final-answer scoring — the process can fail even when the last message looks fine.

### A38. Eval without leaking PII to a third-party judge

| Control | Mechanism |
|---|---|
| Redact/synthesize | Strip PII from cases before judging; prefer synthetic data |
| Data residency | Use an in-VPC/self-hosted judge for sensitive data (ties to Bedrock-in-VPC) |
| Contractual | No-train/no-retain terms with the judge provider |
| Governance | Version + review judge prompts; log what data each judge saw |

**Key takeaway:** Sensitive-data eval needs *redaction/synthetic cases + an in-boundary judge + no-retain terms*, and judge prompts are governed artifacts, not ad-hoc strings.

### A39. When eval lies to you

| Mechanism | Guardrail |
|---|---|
| Goodhart (optimizing the metric, not quality) | Rotate held-out cases; correlate with production signal |
| Contaminated golden set (answers leaked into prompt) | Audit cases; keep a never-tuned holdout |
| Judge collusion (judge = model under test) | Different judge model; validate vs humans |

**Key takeaway:** A green metric with degrading UX usually means Goodhart, contamination, or judge collusion — defend with holdouts, a distinct judge, and correlation to real user signal.

### A40. *(Failure mode)* Offline, online, and cost curves disagree
Answer honestly by stating *what each measures and its limits*:

| Signal | Says | Limit |
|---|---|---|
| Offline scores | quality on a fixed set | may not reflect current traffic |
| Online proxies | real satisfaction trend | noisy, indirect |
| Cost curve | efficiency | orthogonal to quality |

Reconcile: weight *online user signal* highest for "better/worse for users," use offline for regression control, report cost separately — and say explicitly where they conflict.

**Key takeaway:** Don't average incommensurable signals into one fake number — report each with its meaning and limits, lead with real user signal, and name the disagreement rather than hiding it.

---

## Bonus

### AB1. Cost of eval as a line item
| Driver | Control |
|---|---|
| Judge calls per case | cheaper judge, cache, rule-first |
| Matrix size (providers × prompts × cases) | subset in PR, full nightly |
| Online sampling rate | tune % to budget |

**Key takeaway:** Eval is real recurring spend — budget it, cache aggressively, and sample online; when it rivals inference cost it needs its own owner.

### AB2. Versioning/diffing eval results
```text
Store per run: {git_sha, prompt_version, model_version, judge_version,
                dataset_version, per-assertion scores, timestamp}
→ diff run N vs N-1; plot score over time; attribute changes to a specific version bump.
```
**Key takeaway:** "We improved" is only defensible if every eval run records the versions that produced it and you can diff runs over time.

### AB3. Same model as judge and subject
| When acceptable | When disqualifying |
|---|---|
| Quick local dev signal | Any gate/report where self-preference bias matters |
| No cross-model option at all (note the caveat) | Comparing two versions of that same model |

**Key takeaway:** Prefer a *different* model in the judge seat; using the model under test as its own judge invites self-preference bias and is disqualifying for A/B or release decisions.

### AB4. One offline + one online metric
| Offline | Online |
|---|---|
| **Faithfulness/groundedness** on the golden set (RAG's core failure is hallucination) | **User dissatisfaction proxy** (thumbs-down + retry/abandon rate) |

**Key takeaway:** If forced to one each: faithfulness offline (catches the defining RAG failure) and a dissatisfaction proxy online (the ground truth of whether users are helped).

---

## ⚡ Quick Revision Cheatsheet

### Scale numbers (planning figures — verify/tune)
- Golden set: start **~30–50** cases → grow to a few hundred; mix ≈ 40/25/20/15 (happy/edge/adversarial/regression).
- Online judge sampling: **~1–5%** of traffic (bounds cost); implicit signals on **100%** (≈free).
- Ask AI real scale (from design doc): **2,667 docs → 7,597 chunks**, chunk ≤ **1,000 tokens**, embeddings **1,536-dim** cosine, retrieval **K = 5**.
- PR eval budget: target **minutes / low-$**; push full matrix to **nightly**.

### Key technology choices
| Component | Choice | Why |
|---|---|---|
| Harness/gate | promptfoo | declarative matrix + assertions + CI + G-Eval |
| RAG metrics | Ragas | faithfulness, context precision/recall, answer relevancy *(verify names)* |
| Model-graded | LLM-as-judge / G-Eval | scores open-ended quality; CoT criteria decomposition |
| Deterministic | regex / JSON-schema / contains | free, instant, non-flaky; mandatory for safety/format |
| Tracing | OpenTelemetry + LLM-aware tool | per-span tokens/latency/cost; complaint → root cause |

### Canonical trade-offs to memorize
- **Offline gate vs online monitor:** bounded+pre-deploy vs sampled+post-deploy — need both.
- **Deterministic vs model-graded:** cheap/objective vs expensive/semantic.
- **Reference-based vs reference-free:** correctness vs scales-to-prod plausibility.
- **Pointwise vs pairwise judging:** absolute score vs reliable "did we improve?".
- **Inline guardrail vs async eval:** cheap safety on-path vs model-graded off-path.

### Common interview mistakes to avoid
- Saying "we check outputs look good" — not reproducible.
- One accuracy number for open-ended text — ignores Goodhart + no ground truth.
- Trusting an *unvalidated* LLM judge to gate merges.
- Using the model under test as its own judge.
- Ignoring retrieval-vs-generation attribution in RAG.
- No version pinning → scores move because the *judge/provider* changed.
- 100% online judging → unbounded cost; forgetting free implicit signals.
