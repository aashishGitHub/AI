# Interview kit

## 1. Eight STAR stories (built from your real evidence; fill the [brackets] from memory)
Say each one aloud in about 2 minutes: Situation 15s · Task 15s · Action 60s · Result 20s · Learning 10s.

| # | Story | Amazon LPs it covers | S / T | A (what *you* did) | R |
|---|---|---|---|---|---|
| 1 | **LCP 22s+ → 6–7s** | Deliver Results, Dive Deep | The Capella console was slow for enterprise users | Built a 10-route audit (LCP/FCP/TBT/CLS/TTI/unused JS), found the bottlenecks [name the top 2: bundle? CSS? data waterfall?], fixed them [how] | ~3x LCP gain; sub-3s plan is [X]. Say honestly that it's not done yet. |
| 2 | **SSE unblock** | Invent & Simplify, Bias for Action | Real-time updates blocked on NATS/CDS infra, 6+ months away | Proposed an SSE event-bus alternative, co-designed it with a backend engineer, demoed the PoC | Work moving; mentored 2 engineers. Learning: if a dependency is >1 quarter away, start the alternative now |
| 3 | **Home Page Recents backend** | Ownership, Are Right A Lot | Frontend engineer taking a backend feature end to end | Wrote the API spec, built it in Go; compare-and-swap with exponential backoff; 2-layer RBAC | Shipped; caught spec drift + unbuilt dismiss/backfill in design review |
| 4 | **Quality miss in March** (failure story) | Earn Trust, Insist on Highest Standards | QE caught basic edge cases you missed | Owned it; for the next feature, wrote the test plan with Sync Gateway *before* coding, modelled on customer testing | Quality held from April; new habit: QE-agreed test plan before code |
| 5 | **Customer escalation** | Customer Obsession | A customer escalation arrived | Fixed by next morning; also changed proxy error handling so that class of ticket stops | No repeat tickets of that class [verify] |
| 6 | **Pushing back on product** | Have Backbone; Disagree & Commit | Escalation in v1 UI that is being retired | Fixed the UI side, routed the root cause to backend, asked PM whether to keep investing in v1 | [outcome] |
| 7 | **JustAnswer automation** | Customer Obsession, Frugality | Support costs high, agents slow | Built "Chat First" + email self-resolution [your part] | ~25% CS cost cut, ~$100K/month, AHT 2 min → 40 s |
| 8 | **Eval harness / prompt drift** | Learn & Be Curious, Dive Deep | How do you know your RAG works? | Built a promptfoo golden set + cross-family judge + CI gate; found that the server prompt and the eval prompt had drifted, added a zero-model parity check | A real bug caught by CI |

Extra stories to draft: mentoring (two engineers on the SSE work), Svelte → React migration, NetApp CLI → GUI.

**"Why are you leaving?"** — "I want staff-level scope on frontend architecture for AI products, and [company] is where that work is happening." Never mention layoffs or the company's health.

## 2. Frontend system design — 45-minute template
1. **Requirements (5 min):** users, core flows, scale (users, data size), devices, offline needs, a11y, i18n. Agree what is out of scope.
2. **Architecture (8 min):** rendering strategy (CSR/SSR/SSG/ISR/RSC), routing, micro-frontends or not (with reasons), BFF.
3. **Data model + API (7 min):** entities, REST/GraphQL/SSE/WebSocket, pagination (cursor), caching (HTTP, SWR / React Query, normalised store).
4. **Component tree + state (8 min):** server state vs UI state, URL state, optimistic updates.
5. **Performance (7 min):** LCP/INP/CLS budgets, code splitting, virtualisation, image strategy, prefetch, edge caching — **tell your 22s → 6–7s story here.**
6. **Reliability & security (5 min):** error boundaries, retries with backoff, XSS/CSP, auth token storage, RBAC in UI.
7. **Observability & rollout (5 min):** RUM, error tracking, feature flags, canary.

Practice prompts: cloud control-plane console · news feed · autocomplete · chat app · data grid with 100k rows · Google-Docs-style collaborative editor · **AI chat UI with streaming + tool approvals** (your edge).

## 3. React 19 / Next.js 15+ — what's asked (verify details on react.dev / nextjs.org)
- **RSC vs client boundary:** what runs where, bundle cost, why `"use client"` spreads down the tree.
- **Server Actions** + `useActionState`, `useFormStatus`, `useOptimistic`.
- **`use()`** with promises and context; Suspense streaming; error boundaries.
- **Hydration mismatches:** causes (dates, random values, browser-only APIs) and fixes.
- **React Compiler:** automatic memoisation. Is `useMemo`/`useCallback` obsolete? "Mostly, but know when not."
- **`<Activity>`** (React 19.2): keeps hidden UI state alive.
- **Rendering strategies:** SSR / SSG / ISR / PPR trade-offs.
- **INP** replaced FID as a Core Web Vital (March 2024).

## 4. AI-product questions + answer skeletons
- **"How do you know your AI feature works?"** → golden dataset (30–50+ real questions), retrieval metric (recall@k), answer faithfulness judged by a *different* model family, deterministic checks first (cheap), CI gate on regression, production sampling + thumbs feedback.
- **"Hallucination in production — what do you do?"** → check retrieval first (was the right chunk retrieved?), then the grounding prompt, then refusal behaviour; add the case to the golden set; gate it.
- **"Latency of a streaming RAG UI"** → time to first token vs total; retrieval vs generation split; stream sources first; cache embeddings; smaller re-ranker.
- **"Vector vs keyword vs hybrid"** → keyword wins on exact IDs / rare terms, vector on paraphrase; hybrid + re-rank is the production default.
- **"MCP — why?"** → a standard tool interface; scoped auth per tool, rate limits, approval gates for writes.

## 5. DSA — pattern checklist (tick as done)
- [ ] Arrays / hashing ×4 · [ ] Two pointers ×3 · [ ] Sliding window ×3 · [ ] Stack ×3 · [ ] Binary search ×3
- [ ] Trees BFS/DFS ×4 · [ ] Graphs BFS/DFS ×3 · [ ] Heap / top-K ×3 · [ ] Intervals ×2 · [ ] Light DP ×2
Rules: 25-min cap, talk out loud, state complexity, write tests for edge cases. **No AI tools in real rounds unless the round gives you one** (detection is serious — plan Q6).

## 6. Mock loop (Saturdays)
1 DSA (45 min) + 1 frontend system design (45 min) + 1 behavioural (30 min). Score yourself 1–4 on: problem solving, communication, code quality, trade-offs.
