# System Design: LLM Eval & Observability (RAG chatbots, e.g. Couchbase Ask AI)

> **For:** Senior/Staff engineers who ship LLM features and need to *prove* they work and *keep* them working.
> **Style:** Interview-grill format — question first, then defended choices.

This is the ⭐ **exemplar topic** for the [knowledge track](../ROADMAP.md) and the quality template for every other `interviews/<topic>/` folder. It closes **gap #1** (evals) of the [ramp-up](../../RAMPUP.md).

---

## How to Use This Guide

1. Read [`simple-diagram.md`](simple-diagram.md) first — get the central split (offline gate vs online monitor) in your head.
2. Attempt [`questions.md`](questions.md) **cold**, level by level, out loud. Don't peek.
3. Check yourself against [`answers.md`](answers.md) — each answer has a table or code and a one-line **Key takeaway** to say under pressure.
4. Whiteboard from [`diagrams.md`](diagrams.md) — practice drawing Diagram 1, then 2 and 7 (the highest-signal ones).
5. Go deep with [`deep-dive.md`](deep-dive.md) — 🟢🟡🔴 tiers, failure modes, and the Ask AI critique.
6. (Prose retelling: [`conducive-sentences.md`](conducive-sentences.md).)
7. Then *build it* in the hands-on track: [`../../docs/notes/README.md`](../../docs/notes/README.md) (Wk1 promptfoo harness → Wk4 CI gate).

---

## Learning Path

| Level | Topic | You'll learn |
|---|---|---|
| L1 | Fundamentals | Why LLM eval ≠ classic ML; offline vs online; signal families |
| L2 | Golden datasets | Build/size/maintain the set offline eval runs on |
| L3 | Metrics & scoring | Deterministic vs model-graded; retrieval vs generation metrics |
| L4 | LLM-as-judge | Pointwise/pairwise, G-Eval, biases, validating the judge |
| L5 | Harness & CI | promptfoo, regression gates, thresholds, flakiness, cost |
| L6 | Online eval & observability | Traces, sampling, implicit signals, drift, guardrails |
| L7 | RAG end-to-end | Retrieval-vs-generation attribution; the Ask AI baseline |
| L8 | Architect/Staff | Org-wide eval, agent eval, governance, when eval lies |

---

## Files

| File | Purpose | Start here? |
|---|---|---|
| [`simple-diagram.md`](simple-diagram.md) | Central split + concrete tooling diagram | ⭐ start |
| [`questions.md`](questions.md) | L1→L8 grill + failure-mode Qs + bonus | attempt cold |
| [`answers.md`](answers.md) | One answer per Q (table/code + Key takeaway) + cheat sheet | check |
| [`diagrams.md`](diagrams.md) | 9 interview-ready Mermaid diagrams mapped to Qs | whiteboard |
| [`deep-dive.md`](deep-dive.md) | 🟢🟡🔴 depth, failure modes, Ask AI critique | go deep |
| [`conducive-sentences.md`](conducive-sentences.md) | Plain-English prose retelling | optional |

---

## Problem Statement

> Design the evaluation and observability system for a production RAG chatbot (concretely: Couchbase **Ask AI** over the docs corpus). You must be able to (a) **block** a prompt/model/RAG change from shipping if it regresses quality, and (b) **detect** quality/cost/latency degradation on live traffic before users churn — while keeping eval affordable.

**Key constraints (from the Ask AI design doc + your [instructions.md](../../docs/instructions.md); numbers are planning figures to verify):**
- **Corpus/scale:** ~2,667 docs → ~7,597 chunks (≤1,000 tokens each); embeddings 1,536-dim, cosine; retrieval K=5.
- **Real-time requirement:** eval must run *in CI* (block bad ships) **and** *on live traffic* (real-time quality assessment) — per instructions.md's "robust evaluation framework … in real-time."
- **Model-swap without downtime:** models/embeddings get replaced (weekly re-embedding, versioned backups) — eval must survive and re-baseline across swaps.
- **Cost SLA:** eval spend must be bounded (judge calls dominate) — sample online, subset in PR CI.
- **Honesty:** the shipped Ask AI eval today is a bespoke cosine + GPT-4 classifier in a Sheet; RAGAS/promptfoo are *upgrades to build*, not the current state.

---

## How a Senior Engineer Thinks About This

**Lead with the split, not a metric list.** The first thing out of your mouth is: *offline eval is a gate (pre-deploy, fixed golden set, cheap enough to block CI); online eval is a monitor (post-deploy, sampled real traffic, catches what the golden set never contained).* Everything — datasets, judges, CI, tracing — clips onto one of those two loops, and the loop closes when production's hard cases are harvested back into the golden set. A candidate who opens with "we'd track faithfulness and relevancy" has skipped the architecture; one who opens with the split has it.

**The two insights that separate senior from junior.** First, **attribution**: a wrong RAG answer is either a retrieval failure or a generation failure, and you *prove which* with one experiment — is the gold chunk in top-K, and if you feed known-good context does the answer become correct? Without this, every bug is a vague "quality" problem you can't fix. Second, **the judge is an instrument you must calibrate**: an LLM-as-judge has systematic biases (position, verbosity, self-preference) and drifts silently when the provider bumps the model, so you pin it, use a *different* model than the one under test, and validate it against human labels before it's allowed to block a merge. Most teams skip judge validation and then wonder why their green metrics don't match unhappy users.

**Staff-level is where eval becomes a governed system with a cost.** Eval is recurring spend (judge calls × matrix × runs), it can leak PII into third-party models, and — worst — *it can lie to you* via Goodhart, contaminated datasets, or judge collusion. The staff move is to centralize the harness/judges/standards, decentralize golden sets to feature teams, budget eval like any dependency, keep the judge inside the trust boundary for sensitive data (this is why "Bedrock in a VPC" matters), and never fuse offline/online/cost signals into one fake number — report each with its meaning and lead with real user signal. Applied to Ask AI, the honest read is that today's Sheet-based eval is a fine *baseline* whose three highest-value upgrades are: put it in CI as a regression gate, split retrieval-vs-generation metrics, and validate the judge — which is exactly what the hands-on track builds next.
