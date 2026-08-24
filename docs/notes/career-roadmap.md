# Senior / Architect Readiness Roadmap — Aashish Kumar

## ✅ COMMITTED GOAL (locked — stop re-picking) ✅
**Staff/Principal IC — Frontend-heavy + AI + AWS, with system-design depth.**
- **Lead / spike:** React, Next.js, TypeScript, performance (the LCP win), design systems, AI-native UI.
- **Second strength:** AI engineering — RAG, vector/hybrid search, evals, MCP, agents.
- **Third:** AWS + system design — enough to architect and defend, not to specialize backend. **Tracked in a separate repo** (see below), not duplicated here.
- **Breadth (literacy only):** Java/Spring, Go, Node, Python-reading — to screen as fullstack.

**Not chasing:** pure Java fullstack, backend-systems/file-system roles, VP/EM. These fail the T-shape test — they ask me to lead with my weakest spike. A call is cheap; retilting the roadmap toward them is the pivot loop.

**Why this one:** it's the only target that uses my frontend depth as the *advantage* instead of burying it. "Feels far" = focus was split 5 ways, not a capability gap. One lane → distance shrinks.

**Goal (detail):** Staff/Principal IC — a **fullstack engineer who leads with a frontend + AI spike**. Apply broad (fullstack roles to match comp + experience), win on depth (frontend + AI is what sets the offer and salary). Employable today (MNC India + FDE-style + staff fullstack), relevant for the next 5 years.

**Positioning rule (the T-shape):** Breadth is the horizontal bar — it gets you *past the JD checklist*. The frontend + AI spike is the vertical — it gets you *the offer and the comp*. Widen the surface; never erase the spike. "Everyone knows everything" is not a strategy; a deep spike + broad literacy is.

**Resources on hand:** GreatFrontEnd (GFE), DesignGuru (DG), Udemy library.

---

## REPO MAP (where each track actually lives)

This file is the **strategic layer** — positioning, evidence, gaps, and the frontend + AI practice plan. It deliberately does NOT re-derive execution detail that already lives elsewhere; it links out instead, so there's one source of truth per track.

| Repo / path | Owns | Status |
|---|---|---|
| **`AI/` (this repo)** — [`RAMPUP.md`](../../RAMPUP.md), [`interviews/`](../../interviews/), [`docs/notes/`](.) | AI engineering knowledge track (Track A) + hands-on build track (Track B): evals, RAG/hybrid search, vector DBs, agents/MCP, the Agent Console capstone | Active — 2/6 knowledge topics built (`llm-eval-and-observability`, `rag-hybrid-search`); `vector-databases` next |
| **`AWS-Cloud-tech/`** — `AWS-Essentials/`, `Getting-Started-Terraform-4/` | AWS core services, IAM/VPC/Bedrock, Terraform hands-on, distributed-system-design classics (cache, queue, rate limiter, etc.), AWS interview Q&A | Active, separate cadence — **not duplicated in this file below the reference section** |
| **`career-roadmap.md` (here)** | Positioning, evidence log, frontend rampup + practice plan, cross-tier interview prep | This document |

**Rule going forward:** AWS/system-design detail changes happen in `AWS-Cloud-tech/`. Frontend and AI *execution* detail changes happen in `RAMPUP.md`/`interviews/` for AI, and in the Frontend Rampup Plan below for frontend (no equivalent frontend tracker existed before this update — it does now, in this file). This file stays the positioning + practice-cadence layer so it doesn't drift out of sync with three trackers.

---

## REAL EVIDENCE LOG (defensible — measured production work, no invented numbers)

These are true, screenshot/PR-backed artifacts. Use these before the capstone; they already prove parts of the FDE story.

| Artifact | What's real | Metric (defensible) | Interview use | Authorship — verify before claiming |
|---|---|---|---|---|
| **Capella-UI Core Web Vitals initiative** (PR #51879) | LCP cut, 10-route audit system, CI perf gates in progress | **LCP 22s+ → 6–7s (~3x)**; bundle + TTI improved (directional); target sub-3s | Perf STAR story; "run a live perf audit" | **Author** (PR #51879) |
| **MF × webpack chunking analysis** | splitChunks vs MF shared singletons; dual-React invalid-hook crash; runtimeChunk/defer failure modes; 1.6 MB wasted MF download | Qualitative architecture depth | Micro-frontend architect judgment story | **Author-track:** master until you can derive all 3 races unaided, then author the equivalent on your capstone for real. (Original Capella analyzer work: Pavel; bundle CI gate: Anand.) |

### Metrics captured (real)
- **LCP: 22s+ → 6–7s** on Capella console (perf initiative). Sub-3s is the next target, NOT yet achieved.
- JustAnswer (prior, real): ~25% CS cost cut, ~$100K/month email self-resolution, agent handling 2min → 40s.

> Full interview-ready phrasing for each of these (with likely follow-ups and the honest boundary to hold) lives in [`screening-prep.md`](screening-prep.md). Market/positioning claims (FDE growth, comp bands, 2026 hiring trends) live in [`positioning.md`](positioning.md) — verify dates/stats there before repeating them; several are self-reported or small-sample.

---

## ROLE-TARGETING MAP (which lane leads for which JD)

Same person, same resume base — you re-order the *lead* by JD type. Never rewrite from scratch; re-tilt.

| JD type | Example | Lead with (spike) | Support with (breadth) |
|---|---|---|---|
| **Frontend-heavy fullstack** | Databricks *Core Experiences* Staff | React/Next/TS depth, design systems, perf (LCP win), AI-native UI | Node/Go/Java, distributed systems, cloud |
| **AI Principal / architect** | DigitalT3 *AI Principal* | RAG, vector/hybrid search, agents, MCP, evals, LLM solution design | Frontend delivery, Go/Node, AWS/Bedrock |
| **General staff fullstack** | Most India product cos | Frontend + AI spike as differentiator | Full breadth bar below |
| **FDE** | Atlassian/Databricks FDE | Python/API/cloud + RAG/evals + customer-facing ownership | Frontend as the rare differentiator |
| **VP/EM (NOT current target)** | Clairvolex VP | — (leadership bet, different prep) | — |

Decision: **apply to fullstack + AI-principal + FDE lanes; win on the frontend + AI spike.** Comp comes from the spike, not the breadth.

---

## FULLSTACK BREADTH BAR (the horizontal of the T — screen as fullstack)

Purpose: pass the "fullstack / knows everything" filter that India staff/principal JDs (Databricks Core Experiences, DigitalT3, Clairvolex-style) apply. This is **literacy to keep warm, NOT new deep specialization.** Most of it you already have — the job is to keep it interview-ready, not to out-specialize a backend engineer.

| Area | You can already claim | Keep-warm drill (literacy only) | Screens you as |
|---|---|---|---|
| **Java / Spring Boot** | NetApp OTV microservice, Eurofins ordering module | Read Spring code; 1 REST CRUD refresher; explain DI, transactions | Fullstack (JVM) |
| **Go** | Couchbase CDC/SSE, goroutines, channels | Review concurrent Go at teach-level | Fullstack (modern backend) |
| **Node / BFF** | JustAnswer + Couchbase BFF layer | Keep an Express/Nest BFF in the capstone | Fullstack (JS backend) |
| **Python** | (gap — reading only) | Read agent-framework source weekly; review a PR unaided | AI-ecosystem literate |
| **Databases** | SQL (12 yrs), Couchbase (FTS/vector), Mongo/Redis exposure | Say SQL vs NoSQL trade-offs, data modeling, unstructured data | Data-literate |
| **Distributed systems** | CDC, SSE, pub/sub, cross-region replication | 1 classic design/week — **tracked in `AWS-Cloud-tech/`, not here** | Systems-literate |
| **Cloud (multi)** | AWS deep; Azure/GCP by concept | Map AWS knowledge → Azure/GCP equivalents — **tracked in `AWS-Cloud-tech/`, not here** | Cloud-native |
| **Agile / tooling** | Atlassian (Jira/Confluence), Git, CI/CD | Already daily | Delivery-ready |

**Rule:** breadth work = keep-warm reps (read, review, one refresher), never a new 3-month deep track. If a breadth item starts eating spike time, stop it. The spike is the paycheck.

---

## TIER 1 — FRONTEND (your moat: stay on the cutting edge)

| # | Topic | Why it matters | Resource | Done when… |
|---|-------|---------------|----------|------------|
| 1 | **Frontend system design** — news feed, chat app, autocomplete, infinite scroll, collaborative editor, video player | The #1 senior frontend interview round; also your architect signal | GFE System Design course (do ALL questions) | You can whiteboard any of the 6 classics in 35 min with trade-offs |
| 1b | **Complex UI systems** — canvas editors (Figma/Excalidraw-style rendering + hit-testing), workflow/graph builders (React Flow-style DAG editors), whiteboards (infinite pan/zoom canvas), timelines/Gantt views, real-time collaboration (OT vs CRDT), offline sync (IndexedDB + conflict resolution), large-document/list performance (virtualization, incremental rendering, windowing) | A distinct FE-architect skill set beyond "generic" system design — this is what separates Figma/Linear/Notion/Miro-caliber engineers from CRUD frontend engineers, and product-heavy senior/staff loops increasingly probe it; per [`screening-prep.md`](screening-prep.md) this is currently a **"light/integrated, not built"** honest boundary — the real gap | Read source: Excalidraw or tldraw (canvas + whiteboard rendering), React Flow docs (graph/workflow builders); study Yjs or Automerge docs (CRDTs) + Linear's/Figma's public eng blogs (real-time sync at scale); GFE's virtualization questions + "Collaborative Editor" | You can whiteboard the render pipeline (canvas vs SVG vs DOM trade-off, dirty-rect redraw, hit-testing), argue OT vs CRDT with a concrete example, and explain windowing a 10k-row timeline/list without jank |
| 2 | **React 19 / Next.js App Router** — Server Components, Server Actions, streaming SSR, Suspense boundaries, caching layers | The current edge; most 12-yr candidates are stuck in pre-RSC mental models. Per `screening-prep.md`, current honest line is "studying it now, haven't shipped it yet" | Udemy (pick a 2025+ Next.js 15 course) + build | You can explain when RSC hurts, not just helps, **and** point to a shipped RSC feature — not just studied |
| 3 | **Advanced TypeScript** — generics, discriminated unions, type-safe SDK/API design | Architect-level TS = designing types others consume | GFE TS drills + your own SDK in the capstone | Your project exposes a typed client SDK |
| 4 | **Web performance** — Core Web Vitals (esp. INP), profiling, bundle strategy, edge rendering | You have wins at NetApp/Capella; refresh to 2026 metrics | GFE quizzes + web.dev | You can run a live perf audit in an interview |
| 5 | **Design systems at scale** — tokens, versioning/governance, a11y (WCAG), Storybook | You've done this at Couchbase/JustAnswer — systematize the story | Your own experience → write-up | One blog-style write-up of your Svelte→React migration |
| 6 | **Micro-frontends / module federation** — and when NOT to use them | Architect judgment questions love this | 1 Udemy module + articles | You can argue both sides with real constraints |
| 6b | **MF × webpack chunking internals** (from your Capella codebase) — `splitChunks` cache groups vs MF `singleton` shared scope; dual-React instance → invalid hook call; `chunks:'async'` sync-import duplication; `runtimeChunk:'single'` + `scriptLoading:'defer'` SPOF; V3_ONLY guarding; 1.6 MB wasted MF download; bundle-size CI regression gate | Elite FDE frontend-depth signal; you have a live real-world case — see [TODO §A](#a-mf--webpack-internals--become-the-person-who-could-have-authored-the-analysis) below | Study the Capella PR + transcript; re-derive each race yourself | You can whiteboard why two Reacts crash and give the V3_ONLY fix from memory |
| 7 | **AI-native UI patterns** — streaming token UIs, human-in-the-loop approvals, generative UI, optimistic updates for agent actions | Emerging, almost no competition; merges your two strengths | Build it in the Agent Console capstone ([`RAMPUP.md`](../../RAMPUP.md)) | Your agent console demos all four patterns |
| 8 | **UI coding drills** — vanilla JS + React component builds | Screens still happen; speed matters | GFE UI coding questions (3/week) | 45-min component builds feel routine |

### FRONTEND RAMPUP & PRACTICE PLAN

No dedicated frontend tracker existed before this update (AI has `RAMPUP.md`; AWS has `AWS-Cloud-tech/`). This is that tracker. Same discipline as the AI track: **every session ends in an artifact** (a whiteboard recording, a shipped component, a written trade-off note) — no passive video streaks.

**Session log** (mirrors the format of [`docs/notes/README.md`](README.md) — add rows as sessions land):

| # | Focus | Artifact | Maps to Tier 1 # | Status |
|---|---|---|---|---|
| F1 | Frontend system design: news feed + autocomplete (GFE) | 2 whiteboard recordings, 35-min timed, trade-offs called out | 1 | 🚧 News feed written design + trade-offs done ([`interviews/frontend-system-design/news-feed.md`](../../interviews/frontend-system-design/news-feed.md), 2026-08-24) — autocomplete (Wk2) still open |
| F2 | Complex UI: read Excalidraw's canvas render loop + hit-testing | Written note: canvas vs SVG vs DOM trade-off, dirty-rect redraw | 1b | ⬜ |
| F3 | Complex UI: Yjs or Automerge docs, OT vs CRDT | Written note with one concrete conflict-resolution example | 1b | ⬜ |
| F4 | React 19 / Next.js App Router: ship one real RSC + Server Action feature (not a tutorial toy) — candidate: the capstone console itself | Shipped feature + PR/commit link | 2 | ⬜ |
| F5 | Advanced TypeScript: typed client SDK for the capstone's API | Working SDK with generics/discriminated unions, used by the console | 3 | ⬜ |
| F6 | Web perf: reproduce the 10-route audit locally, diagnose sub-3s path | Updated STAR notes in `screening-prep.md`; one diagnosed bottleneck | 4 | ⬜ |
| F7 | MF internals: whiteboard Races 1–3 + V3_ONLY fix from memory, unaided | Recorded whiteboard walkthrough | 6b | ⬜ |
| F8 | MF internals: reproduce a dual-React invalid-hook crash in a small repro repo, then fix it | Repro repo + fix — this is the one that converts "studied" into "authored" | 6b | ⬜ |
| F9 | AI-native UI: implement streaming tokens + human-in-the-loop approval UI in the capstone console | Working UI, demoed | 7 | 🚧 Started in [`fe-hands-on/app/agent-console-ui`](../../fe-hands-on/app/agent-console-ui) (SSE Go backend + Next.js console) — CORS + flusher bugs fixed, single-message render working (2026-08-24); token-by-token streaming + approval-gate UI in progress |
| F10 | AI-native UI: generative UI blocks + optimistic updates for agent actions | Working UI, demoed | 7 | ⬜ |
| F11 | UI coding drills, ongoing | 3 GFE component builds/week, timed | 8 | ⬜ ongoing |

**Weekly cadence (frontend lane):**
- **Tue:** Frontend system design or Complex UI session (F1–F3 rotation) — GFE.
- **Wed/Weekend:** Capstone frontend build (F4–F5, F9–F10) — this is the same capstone the AI track uses, so frontend and AI sessions compound on one artifact instead of splitting effort.
- **Ongoing (3×/week, ~45 min):** UI coding drill (F11) — speed practice, not depth practice.
- **Once/month:** Revisit the MF whiteboard (F7) until it's cold-recall fluent, then do F8 once and stop — it only needs to happen once to convert the claim.

**Done when (frontend lane, overall):** every Tier 1 row above has a "shipped/whiteboarded, not just studied" artifact, and `screening-prep.md`'s two open frontend flags (RSC production experience, canvas/whiteboard "light" boundary) are either closed with a real artifact or still honestly stated as open — never silently upgraded without one.

---

## TIER 2 — AI ENGINEERING (the qualifying bar for every 2026 senior role)

**Execution detail for this tier lives in [`RAMPUP.md`](../../RAMPUP.md) and [`interviews/ROADMAP.md`](../../interviews/ROADMAP.md) — this table is the positioning-level summary; update the session log in `docs/notes/README.md`, not this file, as sessions land.**

| # | Topic | Why | Resource | Status (per RAMPUP.md) |
|---|-------|-----|----------|------------|
| 1 | **Evals & evaluation harnesses** ← YOUR #1 GAP | Cited across the market as the 2026 differentiator; the FDE interview kill-question is "how do you know your AI system works?" | promptfoo / Ragas docs + build ([`01-promptfoo-golden-dataset-llm-judge.md`](01-promptfoo-golden-dataset-llm-judge.md)) | ✅ Knowledge topic [`llm-eval-and-observability`](../../interviews/llm-eval-and-observability/) built; CI regression gate (Wk4) still open |
| 2 | **RAG beyond Couchbase** — chunking strategies, hybrid search, reranking, pgvector vs. managed vector DBs | You know one stack deeply; interviews test the trade-off space | Docs + comparisons in capstone | ✅ [`rag-hybrid-search`](../../interviews/rag-hybrid-search/) built; ⬜ `vector-databases` (pgvector vs Pinecone vs Couchbase) is the next topic to build |
| 3 | **Agents & tool use** — MCP, orchestration, memory, guardrails | The market has moved from RAG → agentic; MCP is becoming the integration standard | Udemy (2025+ agents course) + MCP spec + build | ⬜ `agentic-rag-and-mcp` planned — capstone needs 2+ MCP tools with approval gates |
| 4 | **Production LLM ops** — latency debugging, token-cost management, caching, rate limiting, retries, drift monitoring | Real FDE/senior interview material ("diagnose high latency in an inference pipeline") | Build + observability dashboard | ⬜ `llm-serving-and-model-lifecycle` planned |
| 5 | **AI on AWS** — Bedrock, Lambda streaming, VPC-contained deployments | Matches the cloud + "deploy in customer's locked environment" story | AWS docs + capstone deploy | ⬜ Ship+Apply phase (Wk9–12 in `RAMPUP.md`); coordinate with `AWS-Cloud-tech/` for the underlying AWS mechanics |
| 6 | **Structured outputs & prompt architecture** — function calling, JSON schemas, system-prompt design, guardrails | Baseline literacy every AI interview assumes | Anthropic/OpenAI docs | Ongoing — versioned prompts are part of every capstone session |
| 7 | **AI-assisted engineering** — Claude Code / Cursor fluency | Now a screening filter, not a bonus; you already use these — get deliberate | Daily use + narrate in interviews | Ongoing |

**Honesty note carried from `RAMPUP.md`:** the shipped Couchbase Ask AI system uses a bespoke cosine-similarity + GPT-4-judge eval and is 100% Couchbase (no pgvector/Pinecone). promptfoo/Ragas/pgvector/Pinecone are **learning targets**, not descriptions of what's already shipped — keep that boundary honest in interviews (see `screening-prep.md`).

**Weekly cadence (AI lane):** Wed = AI build session against the `RAMPUP.md` session log; the exact session-by-session schedule is maintained there, not duplicated here, to avoid two files drifting out of sync.

---

## AWS + SYSTEM DESIGN — REFERENCE ONLY

**This workstream now lives entirely in `/Users/aashishkumar/Documents/GitHub/AWS-Cloud-tech` (separate repo, separate cadence). Nothing below is tracked or updated in this file.**

- **AWS core + AI-on-AWS** (IAM, VPC, S3, Lambda, Bedrock, DynamoDB vs RDS) — `AWS-Cloud-tech/AWS-Essentials/`.
- **Terraform / IaC hands-on** — `AWS-Cloud-tech/Getting-Started-Terraform-4/`.
- **Distributed system design classics** (cache, queue, rate limiter, notification system, URL shortener — DG Grokking, 1 case/week) — tracked there, not here.
- **AWS interview Q&A / transcripts** — `AWS-Cloud-tech/AWS-Essentials/senior-interview-questions.md`.

**What stays here instead:** *frontend* system design (Tier 1 #1/#1b above) is a distinct skill from generic distributed-system design and remains part of the frontend spike, not the AWS reference track. The capstone's Bedrock/VPC deployment (Tier 2 #5) is the one point where the two tracks touch — coordinate timing, don't duplicate content.

**Rule:** if AWS/system-design work starts pulling focus back into this file in more than a link, that's the pivot loop the goal section warns about — redirect it to `AWS-Cloud-tech/` instead.

---

## TODO — AUTHOR-TRACK MASTERY (earn every claim; check when you can do it unaided)

### A. MF × webpack internals — become the person who could have authored the analysis
- [ ] Explain **why two React instances crash** — module-instance identity + hooks resolving to the wrong React → invalid hook call. Whiteboard from memory.
- [ ] Explain **Race 1**: `splitChunks` `vendor-react` (`chunks:'all'`) vs MF `singleton` shared scope; who registers first wins; `singleton:true` only warns.
- [ ] Explain **Race 2**: `chunks:'async'` + synchronous `react-redux` import in `main.tsx` → Redux duplicated (inline in main.js + vendor-redux.js); ~50–80 KB dead download.
- [ ] Explain **Race 3**: `runtimeChunk:'single'` + `scriptLoading:'defer'` → single `runtime.js` SPOF; 5xx = `__webpack_require__ is not defined`, blank page, no error boundary.
- [ ] Explain the **1.6 MB wasted MF download** — host wins singleton, cp-ui-v3's `vendor-react.js` downloads but never executes.
- [ ] Write the **V3_ONLY guard fix** for the cache groups from memory.
- [ ] Design the **bundle-size CI regression gate** (the thing Anand is building) — your own version.
- [ ] **Author for real:** reproduce a dual-React invalid-hook crash in your capstone MF setup, then fix it (Frontend Rampup F8). Now it's your story, fully owned.

### B. Perf initiative — deepen the win you authored
- [ ] Reproduce the **10-route audit** locally (`PERF_ROUTES=/route npm run perf:audit`); read LCP/FCP/TBT/CLS/TTI/unused-JS output fluently (Frontend Rampup F6).
- [ ] Diagnose **why LCP is still 6–7s** (bundle size + CSS loading) and propose the sub-3s path.
- [ ] Ship the **CI perf-budget gate** (fail PR on LCP/bundle regression) — author it end-to-end.
- [ ] Turn into a **STAR story**: 22s → 6–7s, method, what's left, one diagnosed failure. (See `screening-prep.md` — this story is already interview-ready; keep it current as the sub-3s work progresses.)

### C. Close the AI roadmap's #1 gap (evals) — still the differentiator
- [ ] Build the capstone eval harness (golden set, LLM-as-judge + rule checks, CI regression) — tracked in [`RAMPUP.md`](../../RAMPUP.md) and [`01-promptfoo-golden-dataset-llm-judge.md`](01-promptfoo-golden-dataset-llm-judge.md).

### D. Overdue anchor
- [ ] Submit the **3 rewritten Couchbase resume bullets** (deployment-oriented language, per `positioning.md` §3). Week 1 item, still open.

---

## TIER 4 — INTERVIEW & POSITIONING

| # | Topic | Resource | Cadence |
|---|-------|----------|---------|
| 1 | DSA patterns (senior-level: arrays, two pointers, sliding window, hashmaps, trees, graphs, heaps, intervals; DP-light) | DG Grokking Coding Interview Patterns | 3 problems/week, timed |
| 2 | Behavioral — STAR + Amazon LPs, ambiguity/ownership/customer stories | Mocks with Claude; source material in [`screening-prep.md`](screening-prep.md) | 1/week |
| 3 | Decomposition case study (FDE-style: clarify → decompose → MVP → iterate) | Mocks with Claude | 1/week from Week 5 |
| 4 | Presentation round — problem → constraints → approach → **eval methodology** → results → trade-offs → one diagnosed failure | Rehearse capstone pitch | Weeks 9–12 |
| 5 | Resume + LinkedIn reframe (deployment language), portfolio write-ups | 3 bullets pending! (see TODO §D) | Week 1 |
| 6 | Distributed-system-design mocks | **Tracked in `AWS-Cloud-tech/`, not here** | Its own cadence, that repo |

---

## THE CAPSTONE (one project, all tiers)

**"Agent Console"** — an agentic RAG service with a production-grade UI. Full build detail, session log, and status live in [`RAMPUP.md`](../../RAMPUP.md) and [`docs/notes/README.md`](README.md); summarized here for positioning context:

- **Backend:** Go (or TS) service on AWS Bedrock, inside a VPC; MCP integrations for 2+ tools; SSE streaming to client
- **AI layer:** hybrid RAG (vector + keyword + reranking), versioned prompts, guardrails
- **Evals:** golden dataset, LLM-as-judge + rule checks, regression suite wired into CI
- **Frontend:** React/Next.js console — streaming tokens, human-in-the-loop tool approvals, generative UI blocks, plus an observability dashboard (latency, token cost, drift) — this is where Frontend Rampup F4, F5, F9, F10 land
- **Deliverables:** repo + 2 write-ups ("How I eval my RAG" / "AI-native UI patterns") + a 15-min recorded demo pitch

This one artifact answers: frontend depth, AI depth, cloud deployment, evals, and gives you the presentation-round asset. It is also the single point where the Frontend and AI rampup plans above compound instead of splitting effort — every capstone session should be checked off in *both* the Frontend session log (this file) and the `docs/notes/README.md` session log (AI track), whichever applies.

## 12-WEEK SEQUENCE (frontend + AI focus — AWS/system-design runs on its own cadence in `AWS-Cloud-tech/`)

- **Weeks 1–4 (Foundations):** AI — evals fundamentals + MCP/agents study (per `RAMPUP.md`). Frontend — GFE system design 2 questions/wk (F1), MF internals whiteboard mastery (F7). DSA 3/wk. Resume reframe (TODO §D). Capstone: skeleton + RAG + first eval suite.
- **Weeks 5–8 (Build + Depth):** Capstone agent + approvals UI + dashboard (F9, F10); RSC feature shipped in the capstone (F4); typed SDK (F5); decomposition mocks weekly; MF dual-React repro (F8).
- **Weeks 9–12 (Ship + Apply):** Deploy on Bedrock/VPC (coordinate with `AWS-Cloud-tech/` for the AWS mechanics); write-ups + demo pitch; presentation-round rehearsals; start targeted applications (Databricks/Salesforce/ServiceNow India + global-remote FDE + MNC senior frontend), referrals-first.

## WEEKLY CADENCE (maps to daily rotation)
- **Mon:** DSA (DG). **Tue:** Frontend system design / Complex UI (GFE — F1–F3). **Wed:** AI build (capstone, per `RAMPUP.md` session log). **Thu:** UI coding drill (F11) + Python reading fluency (breadth bar, keep-warm only). **Fri:** Mock (behavioral ↔ decomposition, alternating). **Weekend:** capstone deep work (frontend + AI sessions compounding on the same artifact).
- **Once/month:** revisit MF internals whiteboard (F7) until cold-recall fluent.
- **Separately, own cadence:** distributed-system-design + AWS deep-dives in `AWS-Cloud-tech/` — not part of this weekly rotation.

## GUARDRAILS
- Udemy rule: only courses updated 2025+; AI content stales in months.
- No new certs unless employer-funded (AWS SAA knowledge > AWS SAA paper).
- Every topic must end in an artifact (code, write-up, or scored mock) — no passive video-watching streaks.
- Don't invent metrics — capture real numbers from the capstone for your resume.
- **Authorship honesty rule:** "Author" is claimed only where you wrote the PR/code. Team work = "contributed to" / "led my part of." Deep analysis done by teammates (e.g. Pavel's MF webpack-analyzer work) is study material, not a résumé claim. A fabricated ownership story dies at the first "walk me through how you did it."
- **Cert honesty:** AWS SAA = "working knowledge" on résumé (in progress, not yet passed) — never listed as an earned certification until you pass.
- **Breadth-containment rule:** The Fullstack Breadth Bar is keep-warm literacy only. It does NOT count against the 3-active-goals-per-quarter limit *unless* it turns into deep study — at which point it does, and something else drops. Applying to "fullstack" roles is a positioning move, not a mandate to specialize in backend. If you feel the pull to go deep on Java/Spring again, re-read this line: that's the pivot loop, not a plan.
- **Anti-pivot check:** Target has moved multiple times (Java FS → FDE → AI+FE+Cloud → fullstack-breadth). The *committed* answer: Staff/Principal IC, frontend + AI spike, fullstack breadth as literacy. New external opinions tilt the positioning, they do NOT reset the spike.
- **No-drift rule (new):** AI execution detail lives in `RAMPUP.md` / `interviews/` / `docs/notes/README.md`. Frontend execution detail lives in the Frontend Rampup & Practice Plan above. AWS/system-design detail lives in `AWS-Cloud-tech/`. When updating progress, update the tracker that owns it — don't let this file silently duplicate and drift from any of the three.
