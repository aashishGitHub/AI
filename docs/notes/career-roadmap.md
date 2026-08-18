# Senior / Architect Readiness Roadmap — Aashish Kumar
**Goal:** Senior/Staff frontend-led architect with real AI depth — employable today (MNC India + FDE-style roles), relevant for the next 5 years.
**Resources on hand:** GreatFrontEnd (GFE), DesignGuru (DG), Udemy library.
**Source of truth / practice home:** `/Users/aashishkumar/Documents/GitHub/AI/`

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
- [ ] **Author for real:** reproduce a dual-React invalid-hook crash in your capstone MF setup, then fix it. Now it's your story, fully owned.

### B. Perf initiative — deepen the win you authored
- [ ] Reproduce the **10-route audit** locally (`PERF_ROUTES=/route npm run perf:audit`); read LCP/FCP/TBT/CLS/TTI/unused-JS output fluently.
- [ ] Diagnose **why LCP is still 6–7s** (bundle size + CSS loading) and propose the sub-3s path.
- [ ] Ship the **CI perf-budget gate** (fail PR on LCP/bundle regression) — author it end-to-end.
- [ ] Turn into a **STAR story**: 22s → 6–7s, method, what's left, one diagnosed failure.

### C. Close the roadmap's #1 gap (evals) — still the differentiator
- [ ] Build the capstone eval harness (golden set, LLM-as-judge + rule checks, CI regression) — see Tier 2 #1.

### D. Overdue anchor
- [ ] Submit the **3 rewritten Couchbase resume bullets** (deployment-oriented language). Week 1 item, still open.

---

| # | Topic | Why it matters | Resource | Done when… |
|---|-------|---------------|----------|------------|
| 1 | **Frontend system design** — news feed, chat app, autocomplete, infinite scroll, collaborative editor, video player | The #1 senior frontend interview round; also your architect signal | GFE System Design course (do ALL questions) | You can whiteboard any of the 6 classics in 35 min with trade-offs |
| 1b | **Complex UI systems** — canvas editors (Figma/Excalidraw-style rendering + hit-testing), workflow/graph builders (React Flow-style DAG editors), whiteboards (infinite pan/zoom canvas), timelines/Gantt views, real-time collaboration (OT vs CRDT), offline sync (IndexedDB + conflict resolution), large-document/list performance (virtualization, incremental rendering, windowing) | A distinct FE-architect skill set beyond "generic" system design — this is what separates Figma/Linear/Notion/Miro-caliber engineers from CRUD frontend engineers, and product-heavy senior/staff loops increasingly probe it; currently a gap, not covered by GFE's 6 classics | Read source: Excalidraw or tldraw (canvas + whiteboard rendering), React Flow docs (graph/workflow builders); study Yjs or Automerge docs (CRDTs) + Linear's/Figma's public eng blogs (real-time sync at scale); GFE's virtualization questions + "Collaborative Editor" | You can whiteboard the render pipeline (canvas vs SVG vs DOM trade-off, dirty-rect redraw, hit-testing), argue OT vs CRDT with a concrete example, and explain windowing a 10k-row timeline/list without jank |
| 2 | **React 19 / Next.js App Router** — Server Components, Server Actions, streaming SSR, Suspense boundaries, caching layers | The current edge; most 12-yr candidates are stuck in pre-RSC mental models | Udemy (pick a 2025+ Next.js 15 course) + build | You can explain when RSC hurts, not just helps |
| 3 | **Advanced TypeScript** — generics, discriminated unions, type-safe SDK/API design | Architect-level TS = designing types others consume | GFE TS drills + your own SDK in the capstone | Your project exposes a typed client SDK |
| 4 | **Web performance** — Core Web Vitals (esp. INP), profiling, bundle strategy, edge rendering | You have wins at NetApp; refresh to 2026 metrics | GFE quizzes + web.dev | You can run a live perf audit in an interview |
| 5 | **Design systems at scale** — tokens, versioning/governance, a11y (WCAG), Storybook | You've done this at Couchbase/JustAnswer — systematize the story | Your own experience → write-up | One blog-style write-up of your Svelte→React migration |
| 6 | **Micro-frontends / module federation** — and when NOT to use them | Architect judgment questions love this | 1 Udemy module + articles | You can argue both sides with real constraints |
| 6b | **MF × webpack chunking internals** (from your Capella codebase) — `splitChunks` cache groups vs MF `singleton` shared scope; dual-React instance → invalid hook call (module-instance identity); `chunks:'async'` sync-import duplication; `runtimeChunk:'single'` + `scriptLoading:'defer'` single-point-of-failure; V3_ONLY guarding; 1.6 MB wasted MF download; bundle-size CI regression gate | Elite FDE frontend-depth signal; you have a live real-world case | Study the Capella PR + transcript; re-derive each race yourself | You can whiteboard why two Reacts crash and give the V3_ONLY fix from memory |
| 7 | **AI-native UI patterns** — streaming token UIs, human-in-the-loop approvals, generative UI, optimistic updates for agent actions | Emerging, almost no competition; merges your two strengths | Build it (capstone) | Your agent console demos all four patterns |
| 8 | **UI coding drills** — vanilla JS + React component builds | Screens still happen; speed matters | GFE UI coding questions (3/week) | 45-min component builds feel routine |

## TIER 2 — AI ENGINEERING (the qualifying bar for every 2026 senior role)

| # | Topic | Why | Resource | Done when… |
|---|-------|-----|----------|------------|
| 1 | **Evals & evaluation harnesses** ← YOUR #1 GAP | Cited across the market as the 2026 differentiator; the FDE interview kill-question is "how do you know your AI system works?" | promptfoo / Braintrust docs + build | Your capstone has a regression suite catching hallucination + grounding failures in CI |
| 2 | **RAG beyond Couchbase** — chunking strategies, hybrid search, reranking, pgvector vs. managed vector DBs | You know one stack deeply; interviews test the trade-off space | Docs + small comparisons in capstone | You can defend pgvector vs. Pinecone vs. Couchbase FTS live |
| 3 | **Agents & tool use** — MCP, orchestration (LangGraph-style), memory, guardrails | The market has moved from RAG → agentic; MCP is becoming the integration standard | Udemy (2025+ agents course) + MCP spec + build | Your capstone agent calls 2+ MCP tools with approval gates |
| 4 | **Production LLM ops** — latency debugging across the stack, token-cost management, caching, rate limiting, retries, drift monitoring | Real FDE/senior interview material ("diagnose high latency in an inference pipeline") | Build + observability dashboard | Dashboard shows latency, cost, drift per request |
| 5 | **AI on AWS** — Bedrock, Lambda streaming, VPC-contained deployments | Matches your cloud + the "deploy in customer's locked environment" story | AWS docs + capstone deploy | Capstone runs on Bedrock inside a VPC |
| 6 | **Structured outputs & prompt architecture** — function calling, JSON schemas, system-prompt design, guardrails | Baseline literacy every AI interview assumes | Anthropic/OpenAI docs | You design prompts as versioned, tested artifacts |
| 7 | **AI-assisted engineering** — Claude Code / Cursor fluency | Now a screening filter, not a bonus; you already use these — get deliberate | Daily use + narrate in interviews | You can pair-with-AI live in a coding round comfortably |

## TIER 3 — BACKEND & CLOUD (literacy, NOT specialization)

| # | Topic | Why | Resource | Done when… |
|---|-------|-----|----------|------------|
| 1 | **Distributed system design fundamentals** — caching, queues, consistency, rate limiter, notification system, URL shortener | Senior loops at MNCs always include one; architect vocabulary | DG Grokking System Design (1 case/week) | 12 classic designs covered |
| 2 | **Go concurrency patterns** — goroutines, channels, worker pools, context | You use it at work; sharpen to teach-level | Work + 1 Udemy refresher | You can review others' concurrent Go confidently |
| 3 | **Python reading fluency** | The AI ecosystem's lingua franca; FDE stacks lean Python | Read agent-framework source (weekly drill) | You can review a Python PR without friction |
| 4 | **AWS architecture (SAA-level knowledge, cert optional)** — IAM, VPC, SQS/SNS, DynamoDB vs RDS, cost basics | Architect conversations require it; cert only if employer pays | Udemy SAA course (audit it) | You can sketch a well-architected review |
| 5 | **Docker + K8s basics** | Part of the modern deployed stack | You have K8s from NetApp — refresh | Can deploy capstone via container |
| 6 | **Event-driven patterns** — CDC, SSE, pub/sub | Already yours (Couchbase) — turn into interview stories | Write-up | One STAR story on CDC/SSE at scale |

## TIER 4 — INTERVIEW & POSITIONING

| # | Topic | Resource | Cadence |
|---|-------|----------|---------|
| 1 | DSA patterns (senior-level: arrays, two pointers, sliding window, hashmaps, trees, graphs, heaps, intervals; DP-light) | DG Grokking Coding Interview Patterns | 3 problems/week, timed |
| 2 | Behavioral — STAR + Amazon LPs, ambiguity/ownership/customer stories | Mocks with Claude | 1/week |
| 3 | Decomposition case study (FDE-style: clarify → decompose → MVP → iterate) | Mocks with Claude | 1/week from Week 5 |
| 4 | Presentation round — problem → constraints → approach → **eval methodology** → results → trade-offs → one diagnosed failure | Rehearse capstone pitch | Weeks 9–12 |
| 5 | Resume + LinkedIn reframe (deployment language), portfolio write-ups | 3 bullets pending! | Week 1 |

---

## THE CAPSTONE (one project, all tiers)

**"Agent Console"** — an agentic RAG service with a production-grade UI:
- **Backend:** Go (or TS) service on AWS Bedrock, inside a VPC; MCP integrations for 2+ tools; SSE streaming to client
- **AI layer:** hybrid RAG (vector + keyword + reranking), versioned prompts, guardrails
- **Evals:** golden dataset, LLM-as-judge + rule checks, regression suite wired into CI
- **Frontend:** React/Next.js console — streaming tokens, human-in-the-loop tool approvals, generative UI blocks, plus an observability dashboard (latency, token cost, drift)
- **Deliverables:** repo + 2 write-ups ("How I eval my RAG" / "AI-native UI patterns") + a 15-min recorded demo pitch

This one artifact answers: frontend depth, AI depth, cloud deployment, evals, and gives you the presentation-round asset.

## 12-WEEK SEQUENCE

- **Weeks 1–4 (Foundations):** Evals fundamentals + MCP/agents study; GFE system design 2 questions/wk; DG DSA 3/wk; resume reframe. Capstone: skeleton + RAG + first eval suite.
- **Weeks 5–8 (Build + Depth):** Capstone agent + approvals UI + dashboard; decomposition mocks weekly; DG distributed design 1 case/wk; Python reading drills.
- **Weeks 9–12 (Ship + Apply):** Deploy on Bedrock/VPC; write-ups + demo pitch; presentation-round rehearsals; start targeted applications (Databricks/Salesforce/ServiceNow India + global-remote FDE + MNC senior frontend), referrals-first.

## WEEKLY CADENCE (maps to daily rotation)
- Mon: DSA (DG) · Tue: Frontend system design (GFE) · Wed: AI build (capstone) · Thu: Backend literacy (DG case / Go / Python reading) · Fri: Mock (behavioral ↔ decomposition, alternating) · Weekend: capstone deep work + 1 UI coding drill.

## GUARDRAILS
- Udemy rule: only courses updated 2025+; AI content stales in months.
- No new certs unless employer-funded (AWS SAA knowledge > AWS SAA paper).
- Every topic must end in an artifact (code, write-up, or scored mock) — no passive video-watching streaks.
- Don't invent metrics — capture real numbers from the capstone for your resume.
- **Authorship honesty rule:** "Author" is claimed only where you wrote the PR/code. Team work = "contributed to" / "led my part of." Deep analysis done by teammates (e.g. Pavel's MF webpack-analyzer work) is study material, not a résumé claim. A fabricated ownership story dies at the first "walk me through how you did it."
- **Cert honesty:** AWS SAA = "working knowledge" on résumé (in progress, not yet passed) — never listed as an earned certification until you pass.