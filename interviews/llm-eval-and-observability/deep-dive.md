# LLM Eval & Observability — Deep Dive

> Depth tiers: 🟢 fundamentals · 🟡 senior · 🔴 staff/architect.
> Pairs with [`answers.md`](answers.md). Accuracy: tool/metric specifics change fast — **verify against current docs**; Ask AI facts come from [`../../docs/Ask AI design document.md`](../../docs/Ask%20AI%20design%20document.md).

---

## 1. Why eval is the hard part (🟢→🔴)

🟢 A demo works on the ten prompts you tried. Eval is the discipline that tells you whether it works on the *thousands* you didn't, and whether it *still* works after the next change.

🟡 The reason it's hard: LLM output is open-ended and stochastic, so there's rarely one correct string. You're forced to measure *proxies* (faithfulness, relevancy, satisfaction) rather than exact correctness, and every proxy can be gamed. The senior skill is choosing proxies that correlate with real user value and *knowing their failure modes*.

🔴 At staff level the problem is organizational: eval is a shared system (harness, judges, standards, budget) that many teams depend on, and its own cost and trustworthiness must be governed. The metric you optimize becomes the metric that gets gamed (Goodhart), so you design *against* your own metrics.

---

## 2. Offline eval in depth (🟢→🔴)

🟢 **The loop:** fixed golden dataset → run current system → score with assertions → compare to baseline → block if regressed. It's a unit/regression test suite for behavior.

🟡 **Assertion layering.** Run cheapest-first: deterministic (regex/schema) → reference-based (similarity to gold) → model-graded (judge/G-Eval). Short-circuit: don't spend a judge call on an output that already failed a format check. Set thresholds *relative to a baseline* so normal judge variance doesn't turn CI permanently red.

🟡 **Determinism controls.** Temperature 0 for eval; pin model + judge versions; report pass *rates* over enough cases rather than single-case pass/fail; quarantine known-flaky cases and require majority-of-n.

🔴 **The contamination trap.** If your golden answers leak into the prompt (e.g. the doc chunk contains the exact answer text), scores are inflated and meaningless. Keep a *never-tuned holdout* slice and periodically confirm offline scores still correlate with production signal — the moment they diverge, the offline set has drifted from reality.

**Failure mode (quantified-ish):** a 50-case golden set with only happy-path cases can sit at ~0.95 for months while a growing fraction of real, long-tail traffic fails — because none of that traffic is *in the set*. The fix is distribution matching (A10), not a higher score.

---

## 3. Golden datasets in depth (🟢→🟡)

🟢 A golden case = input + expectation + the scorers to apply + tags. Expectation can be a full gold answer (reference-based) or rubric points (reference-free).

🟡 **Bootstrapping order that works in practice:** (1) mine real queries from logs/support/docs-search, (2) SME-seed the 20 always-asked questions, (3) synthesize Q from known chunks so the chunk is the gold context, (4) make every incident a permanent case. Tag by failure shape (happy/edge/adversarial/regression) so you can slice scores.

🟡 **Ownership.** Assign an owner and a review cadence (e.g. quarterly). Track "last verified" per case. Pin `expected_context` by *stable doc id*, not by text, so a docs edit doesn't silently invalidate the case.

**Real-world grounding:** Ask AI's corpus is **2,667 documents → 7,597 chunks** (≤1,000 tokens/chunk). A golden set for it should sample across doc *sections* (SQL++, indexes, security…), not just the popular pages, or retrieval recall on rare sections goes unmeasured.

---

## 4. LLM-as-judge in depth (🟡→🔴)

🟡 **Pointwise vs pairwise.** Pointwise ("rate 1–5 on faithfulness") is easy to aggregate but suffers score clustering/leniency. Pairwise ("is A better than B?") is more reliable for the question you usually care about — *did this change improve things?* — because relative judgments are more stable than absolute ones.

🟡 **G-Eval** (available as a promptfoo model-graded assertion) has the judge decompose the criterion and reason step-by-step before emitting a score, which tends to align better with humans than a bare numeric ask. *(Verify current behavior in promptfoo's g-eval docs.)*

🔴 **Biases are systematic, not random** (documented across the LLM-as-judge literature — verify specific studies before citing):
- *Position bias* — favors the first (or last) option → swap order and average.
- *Verbosity bias* — longer looks better → normalize/penalize length in the rubric.
- *Self-preference* — a model rates its own family higher → use a different judge model.
- *Leniency* — everything gets 4–5 → force explicit fail criteria + few-shot *failing* examples.

🔴 **Validate the instrument.** Before a judge can gate merges: SME-label ~50–100 cases, measure judge↔human agreement (e.g. Cohen's kappa), accept only above a bar you set, and *re-validate on every judge/prompt change*. An unpinned judge is a measuring tape that changes length — the Ask AI-style "GPT-4 classifier" needs this validation step added before it can gate CI.

---

## 5. Online eval & observability in depth (🟡→🔴)

🟡 **Trace model.** Model each request as a trace of spans (rephrase → embed → retrieve → re-rank → answer), each span carrying tokens/latency/ids, with `prompt_version` and `model_version` as attributes. OpenTelemetry gives the transport; an LLM-aware tool (Langfuse / Arize Phoenix / LangSmith — *confirm each tool's current features*) gives LLM-specific views. Without version attributes you cannot answer "did quality drop because of *my* change or the provider's?"

🟡 **Sampling + implicit signals.** Judging 100% of traffic is unaffordable; sample ~1–5% for async LLM-judging (tune to budget). Meanwhile implicit signals — thumbs, copy-to-clipboard, immediate retry/rephrase, abandonment — are ~free at 100% and are your highest-volume quality proxy. A spike in "retry within 5s" is often a faster regression signal than any judge.

🔴 **Drift, split three ways** (different causes → different runbooks):
- *Input drift* — query embedding distribution shifts (users ask new things) → expand corpus/golden set.
- *Quality drift* — sampled judge score / thumbs-down worsens vs a rolling baseline → roll back a version, check the embed job.
- *Cost drift* — tokens or $/request climb → prompt bloat, retry storms, or a runaway agent loop.

**Failure mode (the 2 AM incident):** answer quality degrades with *no exception thrown* — a provider silently ships a new model minor version, or the weekly re-embed job half-fails so retrieval returns stale/empty context. Users see confidently-wrong or thin answers. Nothing pages unless you alert on *quality proxies* and *job success*, and you can only recover fast if versions are pinned to roll back to. This is why Ask AI's design calls out "backup for old vector embeddings … validate the newly created embeddings" — a half-failed re-embed must be detectable and reversible.

---

## 6. Evaluating RAG specifically (🟡→🔴)

🟡 **Attribution is the core skill.** Given a wrong answer: is the gold chunk in top-K? If not → retrieval fault. If yes → feed the *known-good* context to the LLM; if the answer becomes correct, retrieval (ranking/precision) was to blame; if still wrong, it's generation (prompt/model/faithfulness/lost-in-the-middle). Measuring an undifferentiated "answer quality" number throws this signal away.

🟡 **Re-ranker eval.** Ask AI layers a custom re-ranker (base score + preference for medium-length chunks + bonuses for code/headings). Evaluate it with rank-aware metrics (nDCG/MRR@K) and *ablate each heuristic* — turn the code bonus off and see if answer quality drops. Heuristics that don't move a metric are just latency.

🔴 **Ask AI baseline, critiqued.** Its current eval (§10): cosine similarity via `text-embedding-ada-002` + a GPT-4 "insights" prompt + a GPT-4 classifier into {Matched, Improves upon, Partially correct, Completely different}, run from a Google Sheet via a script. Strengths: repeatable, human-readable classes, real similarity signal. Gaps, highest-value first: **(1)** not in CI → no regression gate; **(2)** no retrieval-vs-generation split → failures aren't attributable; **(3)** the GPT-4 judge is unvalidated and uncontrolled for bias; **(4)** `ada-002` is an older scoring embedding (verify against current options); **(5)** no online loop from production signals. Items (1) and (4-in-CI) are exactly the Track B Wk1/Wk4 work.

---

## 7. Staff-level: eval as a governed system (🔴)

- **Org shape:** platform team owns the *harness, judge service, and standards*; feature teams own their *golden sets and thresholds* (versioned next to the prompts they gate). A shared assertion library + a "definition of eval done" keeps quality even across teams.
- **Cost governance:** eval is recurring spend (judge calls × matrix size × runs, plus online sampling). Budget it, cache judgments by input hash, subset in PR and full-run nightly. When eval spend approaches inference spend, it needs its own owner and dashboard.
- **Data governance:** for sensitive data, redact/synthesize cases and run an in-VPC/self-hosted judge (this is where "Bedrock in a VPC" from the capstone matters — the judge can stay inside the trust boundary). Judge prompts are versioned, reviewed artifacts, and you log what data each judge saw.
- **Agent eval:** trajectory + tool-use, not just final answer — right tool/args via MCP, error handling, approval-gate adherence, termination within a step/token budget, state integrity across steps. The process can fail while the last message looks fine.
- **When eval lies:** Goodhart (optimizing the metric), contaminated golden set, judge collusion (judge = subject). Defend with rotating holdouts, a distinct validated judge, and correlation to real user signal. If offline/online/cost curves disagree, report each with its meaning and *lead with real user signal* — don't fuse incommensurable numbers into one fake score.

---

## 8. Closing cheat sheet

| Layer | The move | The trap |
|---|---|---|
| Offline gate | golden set + layered assertions + baseline-relative threshold | contaminated / non-representative set |
| Scorers | rule-first, judge for semantics | unvalidated judge blocking CI |
| Judge | pinned, different model, bias-controlled, human-validated | self-judging + silent version drift |
| CI | PR subset (cached) + nightly full | slow/expensive → devs skip it |
| Online | traces + sampled judge + implicit signals (100%) | judging 100% (cost) / no version attributes |
| RAG | retrieval-vs-generation attribution | one undifferentiated quality number |
| Drift | input/quality/cost, baseline-relative | no alert on silent quality drop |
| Staff | governed harness/judges/budget/data | eval that lies (Goodhart/contamination/collusion) |

**The one line:** *Offline eval decides whether a change ships; online eval decides whether what shipped is still good — build both, validate your judges, and always attribute RAG failures to retrieval vs generation.*

> Next in the ramp-up: build the offline half for real in Track B (promptfoo golden set + LLM-as-judge, Wk1) then gate it in CI (Wk4). See [`../../docs/notes/README.md`](../../docs/notes/README.md).
