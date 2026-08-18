# LLM Eval & Observability — Interview Questions

> Attempt all questions before reading [`answers.md`](answers.md) · work level-by-level · speak your answers aloud.
> Central split to keep in mind: **offline eval** (pre-deploy, golden dataset, CI-gated) vs **online eval** (in-prod, sampled telemetry, live judging). Every question sits on one side or bridges them.

---

## Level 1 — Fundamentals
*Goal: say what eval is, why LLM eval is different from classic ML eval, and where offline vs online each apply.*

**Q1.** What is "evaluation" for an LLM feature, and why can't you just reuse classic ML metrics (accuracy, F1) unchanged?

**Q2.** Define the offline-vs-online split. What decision does each one gate?

**Q3.** Name the main *families* of eval signal (deterministic/rule-based, reference-based, model-graded/LLM-as-judge, human, production/implicit) and one example of each.

**Q4.** For a RAG feature like Ask AI, what are you actually trying to measure — and why is "the answer looked good" not an acceptable metric?

**Q5.** *(Failure mode)* You have no eval at all and ship a prompt change on Friday. What are the concrete ways this hurts you, and what's the minimum eval that would have caught it?

---

## Level 2 — Golden datasets
*Goal: design, size, and maintain the dataset that offline eval runs against.*

**Q6.** What is a golden dataset, and what does one row contain for a RAG feature?

**Q7.** How do you *build* the first golden set when you have no labeled data? Where do the cases come from?

**Q8.** How big should it be, and how do you decide the mix of cases (happy path, edge, adversarial, regression)?

**Q9.** How do you keep a golden set from rotting as the product, docs corpus, and models change?

**Q10.** *(Failure mode)* Your eval score is 0.95 and stable, but users complain. What's likely wrong with the dataset, and how do you detect it?

---

## Level 3 — Metrics & scoring
*Goal: choose the right scorer per criterion; know deterministic vs model-graded trade-offs.*

**Q11.** When do you use a deterministic/rule-based check vs a model-graded one? Give two criteria that must be rule-based.

**Q12.** Decompose RAG quality into retrieval metrics vs generation metrics. Name the standard ones and what each catches.

**Q13.** What is faithfulness (a.k.a. groundedness) and how is it distinct from answer relevancy? Why does a RAG system need both?

**Q14.** Reference-based vs reference-free scoring — when are you forced into reference-free, and what do you lose?

**Q15.** *(Failure mode)* Two scorers disagree on the same output (rule check passes, judge fails). How do you reconcile, and which do you trust in CI?

---

## Level 4 — LLM-as-judge
*Goal: use a model to score, while controlling its well-known biases.*

**Q16.** How does LLM-as-judge work mechanically (pointwise vs pairwise), and what is G-Eval's contribution over a naive "rate 1–5" prompt?

**Q17.** List the judge biases you must design around (position, verbosity, self-preference, leniency) and one mitigation for each.

**Q18.** How do you *validate the judge itself* — i.e., prove the judge agrees with humans before you trust it in CI?

**Q19.** Cost and latency: a judge call per test case doubles your token spend. How do you keep judge-based eval affordable at CI scale?

**Q20.** *(Failure mode)* Your judge model gets upgraded by the provider and scores shift 8 points overnight with no code change. What happened and how do you prevent silent drift?

---

## Level 5 — Harness & CI (offline, automated)
*Goal: turn eval into a regression gate engineers actually keep green.*

**Q21.** What does an eval harness (e.g. promptfoo) give you over a hand-rolled script? Sketch the config shape (providers × prompts × tests × assertions).

**Q22.** How do you set pass/fail thresholds for a regression gate without making CI flaky or permanently red?

**Q23.** Eval is non-deterministic (temperature, judge variance). How do you make a CI gate stable enough to block merges?

**Q24.** Where does the eval gate sit in the dev loop — pre-commit, PR CI, nightly, pre-deploy — and what runs at each stage?

**Q25.** *(Failure mode)* The eval suite takes 40 minutes and costs $12 per run, so people skip it. How do you fix the incentive without dropping coverage?

---

## Level 6 — Online eval & observability (in-prod)
*Goal: measure quality on live traffic and detect regressions you can't see offline.*

**Q26.** What can online eval catch that offline eval structurally cannot?

**Q27.** What do you instrument per request for an LLM feature (the trace/span model), and which signals feed quality vs cost vs latency?

**Q28.** You can't judge 100% of production traffic (cost). How do you sample, and how do you turn implicit user signals (thumbs, copy, retry, abandon) into a quality proxy?

**Q29.** Define drift for an LLM feature (input drift, output/quality drift, cost drift) and how you'd alert on each.

**Q30.** Guardrails/hallucination detection at request time — what's cheap enough to run inline, and what belongs in async online eval?

**Q31.** *(Failure mode)* At 2 AM answer quality silently degrades (provider changed a model, or the docs re-embed job half-failed). What do users see, what fires, and what's your response runbook?

---

## Level 7 — Evaluating a RAG system end-to-end
*Goal: apply everything to the Ask AI–shaped system; separate retrieval failures from generation failures.*

**Q32.** Given a wrong answer, how do you attribute blame between retrieval and generation? What experiment isolates each?

**Q33.** How do you evaluate the *re-ranking* step specifically (Ask AI adds a custom re-ranker on top of hybrid search)?

**Q34.** Ask AI today evaluates with cosine similarity (`text-embedding-ada-002`) + a GPT-4 judge/classifier in a Google Sheet. Critique that approach — what's good, what's missing, and what would you add first?

**Q35.** *(Failure mode)* Retrieval recall is fine (right chunk is in top-K) but the answer is still wrong. Name three generation-side causes and how eval surfaces each.

---

## Level 8 — Architect / Staff
*Goal: own eval as a system across teams, agents, and cost — and know when eval itself is lying.*

**Q36.** Design an org-wide eval strategy: who owns golden sets, where thresholds live, how many judges, and how eval cost is budgeted.

**Q37.** How does eval change for *agents* (multi-step, tool-calling, MCP) vs single-shot RAG? What new failure surfaces appear?

**Q38.** How do you evaluate without leaking PII/customer data into a third-party judge model, and what governance do you put around judge prompts?

**Q39.** When does eval *lie to you* — metrics green while UX degrades? Give two concrete mechanisms and the guardrail against each (Goodhart, contaminated golden set, judge collusion).

**Q40.** *(Failure mode)* Leadership asks "is the AI getting better or worse over the last quarter?" and you have offline scores, online proxies, and cost curves that disagree. How do you answer honestly?

---

## Bonus — questions a senior raises unprompted

**QB1.** What's the *cost of eval itself* as a line item, and at what point does eval spend need its own budget and caching?

**QB2.** How do you version and diff eval results over time so "we improved" is a claim you can defend with data, not vibes?

**QB3.** What's your policy on putting the *same* model in the judge seat as the one under test — and when is that disqualifying?

**QB4.** If you could keep only one offline metric and one online metric for a RAG feature, which two, and why those?
