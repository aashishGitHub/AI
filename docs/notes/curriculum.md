# Curriculum — Courses Mapped to the Three Gaps

> Companion to [`../../RAMPUP.md`](../../RAMPUP.md) (gaps + tracks) and [`README.md`](README.md) (session log).
> **Rule this file obeys:** courses are **stretch** material, never the core 90. Operating rule #2 says every block ends in an artifact. A video is not an artifact.
> Last updated: 2026-08-25. Course details verified against the vendor pages on that date — re-check before enrolling.

---

## 0. The diagnosis first

Read [`../../interviews/llm-eval-and-observability/conducive-sentences.md`](../../interviews/llm-eval-and-observability/conducive-sentences.md). You can already narrate: the offline/online split, golden-set construction and rot, rule-first vs model-graded scoring, judge bias (position, verbosity, self-preference, leniency), pinning and validating the judge, baseline-relative CI gates, trace spans, sampled async judging, the three drifts, retrieval-vs-generation attribution, Goodhart and dataset contamination.

**That is not a knowledge gap. That is staff-level fluency, written down.**

The actual gap is reps on tooling. Evidence from this repo:

| Signal | What it means |
|---|---|
| `docs/notes/01-promptfoo-golden-dataset-llm-judge.md` — every `⟳ FILL DURING SESSION` block still blank, untouched since Jul 24 | promptfoo has never been run |
| No `promptfooconfig.yaml` anywhere in the repo | same |
| `Arize/Evaluation.md` covers lessons 2–3 only, stops right before "Lab 1: Building your agent" | you stopped the course exactly where the hands-on started |

So the selection rule below is: **prefer courses with labs you will actually run against your capstone. Skip anything that only re-teaches what `conducive-sentences.md` already says.**

---

## 1. DeepLearning.AI — ranked

### ✅ #1 — Finish *Evaluating AI Agents* (Arize AI)
`https://www.deeplearning.ai/courses/evaluating-ai-agents` · Short Course · 2h36m · 15 lessons · 6 code examples · free

You are already 3 lessons in. **Resume at Lab 1, skip nothing after it.** The remaining ~2h is entirely labs: Phoenix tracing, router + skill evals, trajectory evals, convergence score, judge improvement, production monitoring.

- **Closes:** gap #1, and the observability half of gap #3.
- **Why it's #1:** it is the running-code version of the doc you already wrote. Phoenix gives you span-level tracing — the exact thing `conducive-sentences.md` describes ("rephrase, embed, retrieve, re-rank, answer, with tokens/latency/ids per span") and that you have never instrumented.
- **Artifact it must ship:** Phoenix traces from **your** Agent Console Go SSE endpoint, not the course's toy agent. Port the lab.
- **Budget:** 2 evening stretch blocks.

### ✅ #2 — *MCP: Build Rich-Context AI Apps with Anthropic*
`https://www.deeplearning.ai/courses/mcp-build-rich-context-ai-apps-with-anthropic` · Short Course · free · Python

- **Closes:** gap #3. The capstone spec requires 2+ MCP tools behind approval gates; you have zero today.
- **Do:** build and deploy an MCP server, connect a chatbot to it.
- **Artifact:** one MCP tool your Agent Console calls, with a human approval gate in the Next.js UI. That is session `05` in [`README.md`](README.md).
- **Budget:** 3 stretch blocks.

### ✅ #3 — *Agentic AI* (Andrew Ng)
`https://www.deeplearning.ai/courses/agentic-ai` · full Course · raw Python, vendor-neutral, no framework

- **Closes:** gap #3, at the design-pattern level. Reflection, tool use, planning, multi-agent. Plus evaluation-driven development, which is your spine anyway.
- **Why raw Python matters:** you interview as an architect. "I used LangGraph" is weak. "I chose a planner/executor over an autonomous loop because latency and approval gates" is the answer, and this course teaches the second one.
- **Doubles as** your Tuesday "Python reading (agent src)" stretch. Kill two blocks with one.
- **Budget:** spread over 3–4 weeks of stretch.

### ⚠️ #4 — *Retrieval Augmented Generation (RAG)* — **partial only**
`https://www.deeplearning.ai/courses/retrieval-augmented-generation` · Course · Intermediate · **26h3m** · 5 modules · uses Weaviate + Phoenix

26 hours is more than your entire month of stretch time. **You shipped Ask AI. Do not sit through a RAG course.** Cherry-pick:

| Module | Verdict | Why |
|---|---|---|
| 1 — RAG Overview | **Skip** | You built this in production |
| 2 — Information Retrieval & Search Foundations | **Do** | BM25, Reciprocal Rank Fusion. RRF is the standard hybrid-fusion answer you currently can't name against your custom re-ranker |
| 3 — IR with Vector Databases | **Do** | ANN internals + Weaviate. This is literally the `vector-databases` topic that's next in `interviews/ROADMAP.md`. Gets you off Couchbase-only — gap #2 |
| 4 — LLMs and Text Generation | **Skip** | Known |
| 5 — RAG Systems in Production | **Skim** | Compare against Ask AI, note only the deltas |

- **Artifact:** the pgvector/Weaviate vs Pinecone vs Couchbase FTS trade-off write-up with real latency + recall numbers — session `04`.
- **Budget:** ~8h, not 26.

### ⬜ Optional / later
- *Improving Accuracy of LLM Applications* — `https://www.deeplearning.ai/short-courses/improving-accuracy-of-llm-applications/`. Eval framework + scoring. Heavy overlap with what you know. Only if #1 leaves you wanting more.
- *Advanced Retrieval for AI with Chroma* — `https://www.deeplearning.ai/courses/advanced-retrieval-for-ai`. Cross-encoder reranking. Useful ablation reference for your custom re-ranker.
- *Building and Evaluating Data Agents* (Snowflake) — `https://www.deeplearning.ai/short-courses/building-and-evaluating-data-agents/`. Skip; redundant with #1.

**Note on cost:** short courses list as free during the platform beta; certificates need PRO. The full RAG and Agentic AI courses are also on Coursera. Verify current pricing — this changes.

---

## 2. Where DeepLearning.AI gives you nothing

Your read is correct. DLAI teaches AI *concepts in notebooks*. It does not teach you to run a system. These are unserved:

| Need | DLAI coverage | Why you need it |
|---|---|---|
| Docker / Compose | none | Capstone is Go + Next.js + Couchbase + eval CI. That's a Compose file |
| Ollama / local inference | none | Free, offline eval iteration. Judge calls cost real money at matrix scale |
| AWS SAA (VPC, IAM, Bedrock) | none | Thursday block; capstone deploy target |
| Kubernetes | none | Deferred — see below |
| Go backend depth | none | Capstone backend |
| React / Next.js / frontend SD | none | **Your spike.** DLAI is irrelevant here |

---

## 3. Udemy — only where it fills a real hole

> Udemy ratings, run-times and prices move constantly. Figures below were what the listings showed on 2026-08-25 — confirm on the page. Never pay list price; these sit at ~$10–15 on sale almost permanently.

### ✅ Docker — *Docker Mastery: with Kubernetes + Swarm from a Docker Captain* (Bret Fisher)
`https://www.udemy.com/course/docker-mastery/` · ~23h, 225 lectures

**Do not do 23 hours.** Take the container + image + Compose sections, stop there. Target ~6h. Skip Swarm entirely (dead for your purposes) and skip the K8s tail (see below).

- **Artifact:** `docker-compose.yml` bringing up Go backend + Next.js console + Couchbase + the promptfoo eval runner with one command.
- **Why it pays off immediately:** a reproducible eval environment is what makes the CI regression gate in session `06` possible at all.

### ✅ AWS SAA — *Ultimate AWS Certified Solutions Architect Associate 2026* (Stéphane Maarek)
`https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/` · SAA-C03

- Already your Thursday block. This is the standard, uncontroversial pick.
- Pair with his practice exams: `https://www.udemy.com/course/practice-exams-aws-certified-solutions-architect-associate/`
- **Honesty rule holds** (`career-roadmap.md`): "working knowledge, in progress" on the résumé until you actually pass.
- **Prioritise these sections for the capstone:** IAM → VPC → Lambda → ECS. Do them out of order if needed; you need the deploy path before you need the exam.

### ⚠️ Ollama — **don't buy a course**
Options exist (`https://www.udemy.com/course/running-open-llms-locally-practical-guide/`, `https://www.udemy.com/course/local-llms-with-ollama/`, `https://www.udemy.com/course/ollama-starttech/`), but Ollama is a ~2-hour read of `ollama.com/docs` plus `ollama pull`, `ollama run`, `ollama serve`, and the OpenAI-compatible endpoint at `localhost:11434/v1`.

**Buying a course for this is procrastination wearing a productive hat.** Spend the 2 hours pointing promptfoo's provider at a local Llama or Qwen instead — that makes your golden-set iteration free, which is the actual win.

Only reconsider if you want structured coverage of quantization (GGUF, Q4_K_M) and VRAM sizing — and even then, one afternoon of docs beats a course.

### ⏸️ Kubernetes — **defer, deliberately**
`https://www.udemy.com/course/kubernetesmastery/` (Bret Fisher + Jérôme Petazzoni) is the right course when you need it. **You don't yet.** Your capstone deploys to Bedrock + Lambda/ECS in a VPC. K8s is 20+ hours that ships nothing for the spike, and the spike sets the offer. Revisit after the capstone deploys.

### ⏸️ Go microservices — **defer**
You write Go at Couchbase. Courses like `https://www.udemy.com/course/working-with-microservices-in-go/` teach you what you can already read. This is the Java-deep pivot loop wearing a Go hat — operating rule #4 says don't re-pick the target.

### ❌ "AI Engineer Core Track / LLM Engineering, RAG, QLoRA, Agents"
`https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/` — broad, popular, and ~90% overlap with what you already know. QLoRA fine-tuning is not on your path. Skip.

---

## 4. The sequence (drops into the existing weekly rhythm)

Stretch slots only. Core 90 stays as-is.

| Weeks | Tue/Sun AI stretch | Thu cloud stretch | Ships |
|---|---|---|---|
| **1–2** | Finish *Evaluating AI Agents* from Lab 1 | Docker: images + Compose (~6h total) | Phoenix traces on your Go SSE endpoint · `docker-compose.yml` |
| **3–4** | *MCP with Anthropic*, full | AWS SAA: IAM → VPC | 1 MCP tool + approval gate in the console |
| **5–6** | RAG course Modules 2 + 3 only | AWS SAA: Lambda → ECS → Bedrock | vector-DB trade-off write-up w/ real numbers |
| **7+** | *Agentic AI* (Ng), spread out | AWS SAA remainder + practice exams | agent loop w/ planner/executor + reflection |

**Hard cap: 2 course-hours per week.** Beyond that the courses have eaten the build time, and passive video is what the operating rules exist to prevent.

---

## 5. Two self-driven habits that outperform any course

1. **Read the source, not the course.** promptfoo, Phoenix and the Anthropic MCP SDK are all open source and readable. Your Tuesday "Python reading (agent src)" block already says this. One hour in `promptfoo/src/assertions` teaches more about assertion design than any lecture on assertions.
2. **Course → capstone, same night.** A lesson that doesn't produce a commit against Agent Console within 24h is entertainment. Enforce it: the course is the stretch, the port to the capstone is the core.

---

## 6. Skipped on purpose (write it down so you stop reconsidering)

- Kubernetes — after capstone deploy, not before.
- Go/Java microservices courses — you have the job for this.
- Fine-tuning / QLoRA — not on the Staff frontend + AI spike path.
- Anything teaching "what is an eval" — `conducive-sentences.md` is already better than the lecture.
- Frontend courses — GFE stays your frontend source; DLAI and Udemy add nothing to the spike.

---

## Cross-links

[`../../RAMPUP.md`](../../RAMPUP.md) · [`README.md`](README.md) · [`../../interviews/ROADMAP.md`](../../interviews/ROADMAP.md) · [`career-roadmap.md`](career-roadmap.md)
