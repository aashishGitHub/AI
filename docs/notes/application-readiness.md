# Application Readiness — Fullstack + AI Integration (RAG & Eval)

> **What this file is:** a claim-by-claim audit of the *exact* skills line and resume bullet being submitted,
> against artifacts that actually exist in this repo. Every claim gets a colour, the artifact to cite, the
> number to quote, and the boundary to hold when probed.
>
> **What this file is not:** market research (that's [`positioning.md`](positioning.md)), the learning roadmap
> (that's [`career-roadmap.md`](career-roadmap.md) + [`../../RAMPUP.md`](../../RAMPUP.md)), or screening answers
> (that's [`screening-prep.md`](screening-prep.md)). This is the **pre-apply gate**: what must be true before
> you hit send.
>
> **Governing rule:** [`../../RAMPUP.md` §5](../../RAMPUP.md). A claim you cannot demo or derive unaided is a
> claim that loses the interview more expensively than omitting it would have cost you the screen.

**Two-lane distinction that the whole audit rests on** — keep these verbally separate at all times:

- **Lane P (production, shipped):** Couchbase **Ask AI** — real users, real cost, 100% Couchbase.
  See [`../Ask AI design document.md`](../Ask%20AI%20design%20document.md).
- **Lane L (lab, built by you to learn):** **Agent Console** + eval harness —
  [`../../fe-hands-on/`](../../fe-hands-on/), [`../../evals/`](../../evals/).

Blending them is the single fastest way to get caught. "In production we did X; in my own build I went further
and did Y" is strong. Implying the lab work shipped to customers is fatal.

---

## 1. Claim ledger — the skills line

Source line being claimed:

> AI / GenAI LLM integration · RAG · vector & hybrid search · re-ranking · embeddings · prompt architecture ·
> AI agents / agentic workflows · MCP tool integration · LLM evaluation (golden sets, LLM-as-judge, CI regression)

| Claim | Status | Lane | Evidence to cite | Number you can quote |
|---|---|---|---|---|
| **LLM integration** | 🟢 solid | P + L | Ask AI GPT-4o serving; Agent Console SSE token streaming behind a provider seam | 571 prompt / 128 completion tokens, TTFT 4.94 s, measured 2026-09-07 |
| **RAG** | 🟢 solid | P + L | Ask AI retrieve-then-generate; Agent Console corpus indexed at boot, `sources` frame + citations | Ask AI: 2,667 docs → 7,597 chunks ≤1,000 tokens |
| **Embeddings** | 🟢 solid | P + L | `text-embedding-3-small` (prod); `nomic-embed-text` 768-d local | full corpus re-embed = **$0.12/pass, $0.48/mo weekly** |
| **Prompt architecture** | 🟢 **strongest** | L | `groundedSystemPrompt` — [`stream.go:86`](../../fe-hands-on/server/stream.go); plus the prompt-parity finding below | refusal in **9 tokens / 0.90 s** vs 128 / 7.09 s |
| **Vector search** | 🟢 solid | P + L | Couchbase Vector (prod); brute-force cosine + the "why not HNSW" argument; [`vector-databases`](../../interviews/vector-databases/) topic built | 100% recall by construction under ~10K chunks |
| **Hybrid search** | 🟡 **prod only** | **P only** | Ask AI §4.4.5 hybrid + re-ranking — shipped. **Local rig is vector-only; BM25 owed from session 03** | — |
| **Re-ranking** | 🟡 **prod only** | **P only** | Ask AI §4.4.5. You have not built one yourself | — |
| **LLM eval — golden sets** | 🟢 solid | L | [`evals/promptfooconfig.yaml`](../../evals/promptfooconfig.yaml) | 2 golden cases (happy + negative) |
| **LLM eval — LLM-as-judge** | 🟢 solid, 🟡 calibration | L | `llm-rubric` on a *different-family* local judge (`qwen2.5:1.5b`) | 1 pass / 1 fail, 13 s, 1,206 tokens |
| **LLM eval — CI regression** | 🟡 **built, unverified in real CI** | L | [`.github/workflows/eval-gate.yml`](../../.github/workflows/eval-gate.yml) — 2-tier gate (parity, then eval). Both tiers pass locally 2026-09-07; **not yet run on an actual GitHub Actions runner** | tier 1: seconds, no model; tier 2: ~11-16s locally |
| **AI agents / agentic workflows** | 🔴 **not built** | — | No agent loop, no tool routing, no approval gate anywhere in the repo | — |
| **MCP tool integration** | 🔴 **not built** | — | Zero MCP code. Session 05 ⬜, [`agentic-rag-and-mcp`](../../RAMPUP.md) ⬜ | — |

**Verdict on the skills line as written (updated 2026-09-07): 2 of 12 claims are unbacked, 1 is built-but-unrun-in-CI,
and 2 more are production-only.** CI regression moved from 🔴 to 🟡 the same day this file was written — the gate
exists and both tiers pass locally; it has not yet executed on a real GitHub Actions runner. Agents and MCP
remain the two genuine 🔴s. The line is not dishonest — it is *unevenly defensible*, and an interviewer who
probes agents/MCP first will form their impression there.

---

## 2. Claim ledger — the resume bullet

Source bullet being claimed:

> Drove AI capability — built RAG features and mentored engineers on vector-DB and production RAG patterns;
> prototyped MCP tool integrations and evaluated AWS Bedrock for in-VPC inference; standing up an eval harness
> (golden dataset, LLM-as-judge, CI regression).

| Fragment | Status | Why |
|---|---|---|
| "built RAG features" | 🟢 | Ask AI shipped. Strongest thing in the bullet; currently buried mid-sentence |
| "mentored engineers on vector-DB and production RAG patterns" | ⚪ **unverifiable here** | No repo artifact — but mentoring rarely leaves one. **Not a false claim; an unevidenced one.** Be ready with names, forum, cadence, and what changed as a result |
| "prototyped MCP tool integrations" | 🔴 **cannot back** | No MCP code exists. If "prototyped" means work-side work with no repo trace, fine — but you must be able to describe the tool, the transport, and the approval model unaided |
| "evaluated AWS Bedrock for in-VPC inference" | 🔴 **cannot back** | Nothing in repo; Weeks 9–12 ⬜. "Evaluated" is a low bar you can legitimately meet with a written comparison — but you must survive "how does traffic reach Bedrock without internet egress?" |
| "standing up an eval harness (golden dataset, LLM-as-judge, CI regression)" | 🟢 **now defensible as "built"** | Golden set 🟢, judge 🟢 (calibration bug found + fixed 2026-09-07 — see §6), CI regression 🟡 built + locally verified, not yet run on a real runner. "Built an eval harness with a CI gate; the gate hasn't executed in anger yet" is now true and precise |

**The one thing to fix before submitting:** the bullet leads with the vaguest word ("Drove") and buries the only
production-shipped claim. Two of its four clauses are the least defensible things you could say.

---

## 3. Defensible rewrites

Same facts, ordered by how well they survive contact. Pick per JD using the role-targeting map in
[`career-roadmap.md`](career-roadmap.md).

**Bullet — AI-heavy JD:**

> Shipped production RAG for Couchbase docs (**2,667 docs → 7,597 chunks**, hybrid vector+FTS with re-ranking,
> streaming answers with citations); mentored engineers on vector-DB selection and production RAG patterns.
> Standing up an eval harness — golden dataset, LLM-as-judge, rule-based regression checks — after eval gaps
> let a grounding bug reach review.

**Bullet — fullstack JD:**

> Built and shipped an AI documentation assistant end-to-end: React/Next.js streaming UI, Go/Node services,
> Couchbase FTS+Vector retrieval, versioned prompts, and an eval harness (golden set + LLM-as-judge) that
> catches grounding regressions before merge.

**Skills line — reordered so the strong claims land first, weak ones dropped until built:**

> LLM integration · RAG (retrieve-then-generate, grounding & citations) · vector & hybrid search · embeddings ·
> prompt architecture & guardrails · LLM evaluation (golden sets, LLM-as-judge, rule-based regression) ·
> streaming AI UIs (SSE, human-in-the-loop)

Add back **"AI agents · MCP tool integration · CI eval gates"** the day sessions 05 and 06 land — not before.
Note "streaming AI UIs" is a real differentiator you *have* built and the original line omitted entirely.

---

## 4. Minimum work to turn 🔴 → 🟢

Ordered by interview value per hour. Sessions map to the log in [`README.md`](README.md).

| # | Gap | Minimum credible deliverable | Effort (est.) | Unlocks |
|---|---|---|---|---|
| 1 | ~~CI regression gate~~ **DONE 2026-09-07** | [`.github/workflows/eval-gate.yml`](../../.github/workflows/eval-gate.yml) — parity tier + eval tier. **Remaining:** push a PR and watch it actually run once on GitHub's runners; a workflow that has only run on your laptop is not yet proven in CI | — | ~30 min to verify on a real PR |
| 2 | ~~Prompt parity~~ **DONE 2026-09-07** | Fixed [`evals/prompts/answer.txt`](../../evals/prompts/answer.txt); verified both directions (fails on old prompt, passes on new) via [`check-parity.py`](../../evals/ci/check-parity.py) | — | Closed the hole in your best story — see §6 |
| 3 | **MCP tool** (session 05) | **One** MCP tool called from the Go server behind an explicit approval gate + 2 tests. One tool, done properly, beats three half-wired | ~1–2 sessions | "MCP tool integration" + "agentic workflows" → 🟢 |
| 4 | **Agent loop eval** | Assert tool *selection* and *parameters*, not just final text — the axes in [`Arize/Evaluation.md`](../../Arize/Evaluation.md) | ~half a session | Separates you from everyone who evals only final output |
| 5 | **Bedrock / in-VPC** | A Bedrock implementation of the existing `provider` interface + a written comparison (cost, latency, data-residency) vs Ollama/OpenAI | ~1 session | "evaluated Bedrock" → 🟢 honestly |
| 6 | **Hybrid/BM25 locally** (owed from 03) | Keyword scoring merged with cosine + a recall delta on your golden set | ~1 session | Moves hybrid/re-ranking from prod-only to *built by you* |

⚠️ **On item 5 — verify before you speak.** I have **not** verified current AWS specifics for reaching Bedrock
without internet egress (VPC interface endpoints / PrivateLink availability per region, IAM and
data-residency guarantees). Confirm against AWS's own documentation before claiming it in an interview; AWS
networking details change and this is exactly the claim a cloud interviewer will drill.

---

## 5. Pre-apply gate — must be true before you hit send

| # | Item | Status | Why it gates |
|---|---|---|---|
| 1 | **3 rewritten Couchbase resume bullets** | 🔴 open since Week 1 (TODO §D in [`career-roadmap.md`](career-roadmap.md)) | Nothing else in this file matters if the resume still uses feature-language |
| 2 | **Root [`README.md`](../../README.md) is a 2-line stub** | 🔴 | First thing a hiring manager opening this repo sees. It should state: what was built, the measured numbers, and where to look. **Highest-leverage 30 minutes available to you** |
| 3 | **15-min recorded demo** | 🔴 Weeks 9–12 | The presentation round asset; also your referral artifact |
| 4 | **Write-up: "How I eval my RAG"** | 🔴 | Your #1 gap turned into your #1 credential. §6 below is the spine of it |
| 5 | **Write-up: "AI-native UI patterns"** | 🔴 | Covers the streaming/approvals differentiator |
| 6 | **CI gate green** | 🔴 (item 1, §4) | Lets "CI regression" leave the bullet's hedge |
| 7 | Fix the `589.25` cost-table error | 🟡 flagged | A candidate who found a 10× error in their own design doc's cost model is *exactly* the signal senior loops want |
| 8 | Repo hygiene | 🟢 **verified clean** | No tracked `node_modules`/`.next`; `.git` 77 MB |

---

## 6. Your best interview story (use this one)

Better than any story about building RAG, because it shows *measurement*, not construction — and it happened
today, so it is fresh and fully yours.

**Setup.** Same model (`llama3.2:1b`), same question ("How do I create a vector index in Capella?"), two
harnesses, opposite behaviour:

| Path | Prompt | Result |
|---|---|---|
| Eval harness | [`answer.txt`](../../evals/prompts/answer.txt) — "use ONLY the context", **no permitted alternative** | **Fabricated** ``CREATE INDEX ON `bucket_name`:vindex_name;`` |
| Agent Console | [`groundedSystemPrompt`](../../fe-hands-on/server/stream.go) — same rule **plus** an exact refusal string, "never invent syntax", `[n]` citations | **Refused** correctly in 9 tokens |

**The line.** *"A prohibition without a permitted alternative isn't a constraint, it's a trap. The model
couldn't comply and couldn't decline, so it invented. The fix was one sentence of prompt, not a bigger model."*

**The follow-through that makes it senior.** It also exposed a process bug: **the eval was grading a prompt we
don't ship.** So the red result was uninformative about production. Prompt parity between eval and
runtime is now a fix in flight (§4 item 2).

**Two more from the same harness, if pushed:**

1. **A false PASS was a malformed rubric, not a weak judge.** A rubric phrased as instructions made the judge
   grade *the rubric's own truth* and pass a fabricated answer. Rephrased as an assertion about the output:
   0/5 → 5/5 on both `qwen2.5:1.5b` and `3b`. **Model size was never the variable** — the thing everyone
   reaches for first was the wrong knob.
2. **A negative string check is not evidence of grounding.** `not-icontains: "CREATE VECTOR INDEX"` passed
   while the model invented different wording. Assert the refusal is *present*; there are few ways to decline
   and infinite ways to hallucinate.

**Boundaries to volunteer before you're caught holding them** — volunteering these reads as rigour:

- The local judge is **uncalibrated**; treated as a warning, with deterministic rules as the actual gate.
- 2 golden cases is a *seed*, not a suite.
- Ask AI's shipped eval is a **bespoke cosine + GPT-4 classifier in a Google Sheet, manually triggered** — the
  promptfoo harness is your own forward-looking work, not what runs in production.

---

## 7. Kill-questions → your answer → the boundary

| They ask | Lead with | Hold this boundary |
|---|---|---|
| "How do you know your RAG works?" | Golden set; deterministic rules first (cheap, run first), judge second | 2 cases is a seed; judge uncalibrated |
| "Your judge is a 1.5B model — why trust it?" | I don't. Rules are the gate; the judge is a warning. It's a *different family* from the SUT to avoid self-preference | No calibration study run yet |
| "Give me a bug eval caught" | The wildcard `` `.*` `` primary-index form that a g-eval judge scored faithful; §6's prompt-parity finding | The g-eval failure was partly a JSON-extraction bug, not only a judge error |
| "Why brute force, not HNSW?" | 100% recall by construction under ~10K chunks; no build step, no tuning, no silent recall loss. `Retriever` interface is where a real store slots in | Ask AI's 7,597 chunks is where that flips |
| "Swap a model without downtime?" | Stateless inference plane behind a provider seam — verified: one env var, different family, zero code change | Knowledge plane is stateful: swapping `EMBED_MODEL` forces a full re-index + validated backup |
| "MCP experience?" | **Say the honest thing.** Describe the contract, approval-gate design, and what you'd build | Do not imply shipped MCP code exists |
| "Bedrock in a VPC?" | The provider seam makes it a config swap; data-residency is the driver | Verify AWS networking specifics first (§4) |
| "What did RAG cost?" | $0.01732/request; **~12,000 req/month** is where model spend overtakes the whole cluster bill | Snapshot pricing; re-verify |
| "Biggest weakness in your AI work?" | Evals were the gap — which is why the harness exists and why I can name what's still uncalibrated | Don't perform humility; name the real one |

---

## 8. What NOT to claim

Accuracy contract, applied to a resume. Each of these is currently unbacked by any artifact:

- ❌ "Built agentic workflows" / "production MCP integrations" — no agent loop, no MCP code.
- ❌ "CI eval gates in production" — the gate does not exist yet.
- ❌ "Built hybrid search / re-ranking" — **shipped at Couchbase (Ask AI), not built by you locally.** Say
  "shipped hybrid retrieval with re-ranking in production" — true — never "I built a re-ranker".
- ❌ "Used RAGAS" — [`../../RAMPUP.md` §5](../../RAMPUP.md): `instructions.md` says RAGAS, the shipped design doc
  does not. Do not repeat it.
- ❌ "pgvector / Pinecone experience" — comparison study, not operational experience.
- ❌ Any Ask AI cost or latency number without "approximately" and "as of the design doc".
- ❌ Fine-tuning, training, RLHF, model registries — **nothing in either lane.** If a JD centres on these,
  it's the wrong JD; see the role-targeting map.

---

## 9. Next

1. Root `README.md` (§5 item 2) — 30 minutes, highest leverage, gates every referral.
2. Prompt parity (§4 item 2) — 30 minutes, protects your best story.
3. CI gate (§4 item 1) — closes gap #1; upgrades the resume bullet's weakest clause.
4. Then MCP (session 05) — the only 🔴 that needs real build time, and the one that unlocks two skills-line claims.
5. Re-audit this file after each lands; move the colour, quote the new number.

> Evidence entries for the AI artifacts now live in [`career-roadmap.md`](career-roadmap.md) §REAL EVIDENCE LOG.
> Keep that table and this file's ledger in sync — one is the artifact list, this is the claim list.
