# Study Guide — the one file to open daily

> **How to use this file.** This is the single spine for learning, revision, and interview prep. Everything
> else in this repo is depth you read *from here*, not a parallel plan. If you only open one file before a
> study session or an interview, open this one.
>
> **What lives elsewhere, on purpose (don't duplicate, follow the link):**
> [`../../RAMPUP.md`](../../RAMPUP.md) — the two-track structure and the 3 named gaps ·
> [`career-roadmap.md`](career-roadmap.md) — full topic tiers, evidence log, weekly cadence detail ·
> [`application-readiness.md`](application-readiness.md) — claim-by-claim resume/skills audit ·
> [`ai-lifecycle-business-cases.md`](ai-lifecycle-business-cases.md) — 8 lifecycle stages, each measured locally ·
> [`positioning.md`](positioning.md) / [`screening-prep.md`](screening-prep.md) — market framing and screening answers ·
> [`README.md`](README.md) — the 12-week session log.

---

## 0. State of the world (updated 2026-09-07 — update this date whenever you revisit)

**Built and measured, today:**

- Agent Console (Go + Next.js): **66 tests**, 0.82s + 0.61s, no Docker needed for tests themselves
- Live-run proof: grounded answer (TTFT 4.94s, 128 completion tok) vs refusal (0.90s, **9** completion tok —
  refusals are **~14× cheaper**)
- Model swap by env var alone, zero code change, verified: `qwen2.5:1.5b` on a second port, knowledge plane
  untouched
- **Two real bugs found and fixed today** (§1 below) — this is your best interview material, because it's
  measured, not constructed
- CI eval gate written, both tiers pass locally — **not yet run on a real GitHub Actions runner** (§2, item 3)
- Root [`../../README.md`](../../README.md) rewritten from a 2-line stub into a real entry point

**Still open, in priority order:** see §2.

---

## 1. The story to have cold (this is now your #1 interview asset)

**Setup.** Same model (`llama3.2:1b`), same question — *"How do I create a vector index in Capella?"* — asked
through two different harnesses.

**Bug 1 — prompt parity.** The eval prompt said "use ONLY the context" with no permitted way to decline; the
server's `groundedSystemPrompt` added an exact refusal string. Same model: eval path **fabricated**
``CREATE INDEX ON `bucket_name`:vindex_name;``; server path **refused** correctly.

> *"A prohibition without a permitted alternative isn't a constraint, it's a trap. The model couldn't comply
> and couldn't decline, so it invented. The fix was one sentence of prompt, not a bigger model."*

**Bug 2 — judge inversion, found while verifying the fix for Bug 1.** After the prompt fix, the server refused
correctly — but the eval's judge (`qwen2.5:1.5b`) still marked it FAIL, and its own stated reason *agreed* the
output had no SQL statement, then scored the rubric false anyway. Isolated with a **fixed, non-varying output**
graded 3× at temperature 0: the 1.5b judge inverted the same correct verdict all 3 runs — a reproducible
calibration bug, not noise. A 3b judge from the same family got it right 3/3 on the identical input. Judge
swapped.

> *"I don't trust a single judge run — I isolate. Hold the input fixed, vary only the judge, run it more than
> once. If it's not deterministic and correct on an unambiguous case, it's not ready to gate anything."*

**The honest number that follows.** After fixing both bugs, characterized over 6 independent runs: **1 refusal,
5 fabrications** — this exact 1B model complies with the grounded prompt roughly **1 time in 5** on this exact
question (small sample, order-of-magnitude only). The fixed harness now grades this *correctly every time* —
the intermittent red is the model's real behaviour, not a harness artifact. **That's the whole point of fixing
the harness: a red result should mean something.**

**Boundaries to volunteer, not wait to be caught on:**
- 2 golden cases is a seed, not a suite.
- The 1-in-5 figure is 6 runs, not a benchmark.
- Ask AI's *shipped* eval is a bespoke cosine + GPT-4 classifier in a Google Sheet, manually triggered — this
  harness is your own forward-looking work, not a description of production.

Full derivation and every number: [`ai-lifecycle-business-cases.md`](ai-lifecycle-business-cases.md) §6.

---

## 2. Open gaps, in the order to close them

| # | Gap | What "done" looks like | Effort | Status |
|---|---|---|---|---|
| 1 | **Push a PR, watch the CI gate run for real** | [`../../.github/workflows/eval-gate.yml`](../../.github/workflows/eval-gate.yml) executes on GitHub's own runners, not just this laptop | ~30 min | 🟡 built + passes locally |
| 2 | **3 rewritten Couchbase resume bullets** | Deployment-oriented language per [`positioning.md`](positioning.md) §3 | — | 🔴 **needs you** — the original feature-language bullets aren't in this repo; I can rewrite once you paste them |
| 3 | **Fix or confirm the `589.25` cost-table cell** | Ask AI design doc §6.1 — the doc's own §6.3 total implies `5,892.50` is correct | — | 🔴 **needs you** — you have the source spreadsheet, I don't |
| 4 | **MCP tool integration** (session 05) | One tool, called from the Go server, behind an explicit approval gate + tests | ~1–2 sessions | 🔴 not started — closes 2 skills-line claims (agents, MCP) |
| 5 | **Agent-loop eval** | Assert tool *selection* and *parameters*, not just final text | ~half a session | 🔴 depends on #4 |
| 6 | **Hybrid/BM25 locally** (owed since session 03) | Keyword scoring merged with cosine, recall delta measured on the golden set | ~1 session | 🔴 not started |
| 7 | **Bedrock provider + written comparison** | A Bedrock implementation of the existing `provider` interface; cost/latency/residency write-up | ~1 session | 🔴 not started. **Verify AWS VPC-endpoint/PrivateLink specifics against AWS's own docs before claiming this aloud** |
| 8 | **Grow past 2 golden cases** | Citation fidelity, multi-turn, injection, PII | ongoing | 🔴 now safe to do — harness grades correctly |
| 9 | **Root README + write-ups + demo** | 2 write-ups ("How I eval my RAG" / "AI-native UI patterns") + 15-min recorded demo | Weeks 9–12 | 🟢 README done; write-ups/demo 🔴 |

Items 2 and 3 are the only two on this list I cannot complete without you — everything else is either done or
schedulable as a build session.

---

## 3. Weekly cadence (detail in [`career-roadmap.md`](career-roadmap.md) — this is the compressed version)

| Day | Focus |
|---|---|
| Mon | DSA (senior patterns: arrays, sliding window, trees, graphs, heaps, DP-light) |
| Tue | Frontend system design / complex UI |
| Wed | AI build session — work the gap list in §2, top to bottom |
| Thu | UI coding drill + Python reading fluency |
| Fri | Mock — alternate behavioral / decomposition |
| Weekend | Capstone deep work — frontend + AI sessions compounding on the Agent Console |

**Rule that governs all of it:** breadth work (Java, distributed systems, multi-cloud) is *keep-warm reps only*
— read, review, one refresher. The moment it starts eating build time on the gap list above, stop it. The spike
(frontend + AI) is the paycheck.

---

## 4. Revision spine — facts to have cold before any interview

**Numbers (all measured or derived, dated 2026-09-07 unless noted; snapshot pricing — re-verify before quoting):**

| Fact | Number |
|---|---|
| Agent Console test suite | 46 Go (0.82s) + 20 TS (0.61s) = 66, no Docker needed |
| Grounded answer | TTFT 4.94s, 571 prompt / 128 completion tokens |
| Refusal | 0.90s, 648 prompt / **9** completion tokens — **~14× cheaper** |
| Grounding compliance (this 1B model, this question) | ~1-in-5 across 6 runs — order-of-magnitude only |
| Ask AI corpus | 2,667 docs → 7,597 chunks, ≤1,000 tokens each |
| Full re-embed cost | $0.12/pass, $0.48/month weekly |
| Ask AI ingest cron | 5–6h synchronous → ~20min with 10 goroutines |
| Model cost per request (design-doc snapshot) | ~$0.01732 |
| Crossover: model spend > entire cluster bill | ~12,000 requests/month |
| eval-gate exit code on any failed assertion | 100 (verified empirically) |

**The two-lane rule (never blend these in an interview answer):**
- **Lane P** — Couchbase Ask AI: shipped, real users, 100% Couchbase.
- **Lane L** — Agent Console + eval harness: your own lab build, forward-looking.
"In production we did X; in my own build I went further and did Y" is strong. Implying the lab work shipped to
customers is fatal. Full ledger: [`application-readiness.md`](application-readiness.md).

**What NOT to claim** (unbacked by any artifact as of today): agentic workflows, production MCP integrations,
CI eval gates running in anger, "built" hybrid search/re-ranking (shipped at Couchbase, not built by you),
RAGAS usage, pgvector/Pinecone operational experience, anything about fine-tuning/training/RLHF. Full list with
reasons: [`application-readiness.md`](application-readiness.md) §8.

---

## 5. Kill-questions quick reference

| They ask | Lead with | Boundary to hold |
|---|---|---|
| "How do you know your RAG works?" | Golden set, deterministic rules first, judge second | 2 cases is a seed; state the judge fix unprompted |
| "Give me a bug your eval caught" | The prompt-parity story, §1 above | Say which was Bug 1 vs Bug 2 clearly |
| "Your judge is a small model — why trust it?" | I isolate: fixed input, vary only the judge, run 3×. Found it inverted, swapped it | No formal calibration study beyond that isolation |
| "Why brute-force, not HNSW?" | 100% recall by construction under ~10K chunks; no tuning knob to silently lose recall on | Ask AI's 7,597 chunks is where that trade flips |
| "Swap a model without downtime?" | Stateless inference plane behind a provider seam — verified live | Knowledge plane is stateful; swapping the embed model forces a full re-index |
| "MCP / agent experience?" | Describe the contract and approval-gate design you'd build | Never imply shipped code exists — there is none yet |
| "Bedrock in a VPC?" | Provider seam makes it a config swap; residency is the driver | Verify AWS networking specifics before asserting them |

Full version with more questions: [`application-readiness.md`](application-readiness.md) §7.

---

## 6. Next time you open this file

1. Check §2 — did an item move? Update its status.
2. If you built something new, add its number to §4 and its story to §1 or a new numbered bug.
3. Update the date at the top of §0.
