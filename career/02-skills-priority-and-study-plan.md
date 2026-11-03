# Skills by priority + study plan (Udemy · DesignGurus · free Claude/Gemini)

Resources you said you have: **Udemy**, **DesignGurus**, **free Claude**, **free Gemini**.
⚠ Course names below are from memory, not checked against your accounts. Search the exact name in your Udemy/DesignGurus dashboard. Udemy rule from your own roadmap: **only courses updated 2025 or later** (AI content goes stale in months).
⚠ Free-tier limits on Claude/Gemini change often. Plan for a few long sessions a day, not unlimited use.

## Priority rule
Priority = (how often target loops test it) × (how big your gap is). Each skill ends in an **artifact** (code, write-up or scored mock), never only video hours.

| P | Skill | Why (which round tests it) | Your gap | Resource | "Done" when |
|---|---|---|---|---|---|
| **P0** | DSA patterns: arrays/hashing, two pointers, sliding window, stack, binary search, BFS/DFS, heap, intervals, light DP | Amazon / Google / Databricks reject on this alone, even for frontend | Rusty | **DesignGurus "Grokking the Coding Interview: Patterns for Coding Questions"** + LeetCode free (NeetCode 150 list) | 2/day, 25-min cap, ~28 in 14 days; mediums solved out loud |
| **P0** | Frontend system design (control-plane console, news feed, autocomplete, chat, data grid, collab editor) | Atlassian / Microsoft / Google frontend loops; your home turf | Structure + timing | Template in `03-interview-kit.md` §2; **free Claude/Gemini as interviewer** (prompt P3) | Any of the 6 whiteboarded in 35–45 min with trade-offs |
| **P0** | Frontend machine coding: autocomplete (debounce, cache, keyboard), virtualised table, nested comments, modal/toast with a11y | Atlassian / Microsoft / Uber UI rounds | Speed | Build in plain React + TS, timed 60 min | 4 builds done under time |
| **P0** | Behavioural STAR + Amazon Leadership Principles | Every loop; Amazon weights it heavily | Stories not written | `03-interview-kit.md` §1 (8 stories drafted) + **DesignGurus "Grokking the Behavioral Interview"** (verify the name) | 8 stories said aloud in 2 min each |
| **P1** | React 19 / Next.js 15+: RSC boundaries, Server Actions, `useActionState`, `useOptimistic`, `use()`, Suspense streaming, React Compiler, `<Activity>`, hydration errors | Interviewers test "post-RSC mental models" | Refresh | **react.dev + nextjs.org docs (primary)**; one Udemy Next.js 15 course updated 2025+ | You can say when RSC *hurts* |
| **P1** | Core Web Vitals depth: LCP sub-parts, INP, CLS, waterfall reading | Your #1 story; they will drill into it | Make it waterfall-level | web.dev (free), your own PR #51879 notes | Explain 22s→6–7s request by request, plus what's left for sub-3s |
| **P1** | LLM evals: golden sets, recall@k, faithfulness, LLM-as-judge, CI gates | AI-product loops: "how do you know it works?" | **Partly closed** — your AI repo has promptfoo + CI gate | Your repo + promptfoo docs; add recall@k (plan, 7 Nov) | Public write-up (600 words) linked on LinkedIn by 14 Nov |
| **P1** | Distributed system design (architect-literate): rate limiter, notification service, URL shortener, cache, queue, chat | Senior loops at MNCs always include one | Literacy | **DesignGurus "Grokking the System Design Interview"** (you own Vol II) + "Grokking the Advanced System Design Interview" | 1 design/week, 12 total; use AWS primitives |
| **P2** | AI-native UI patterns: streaming tokens, tool-call / approval UIs, optimistic agent actions, generative UI | Differentiator for "frontend for AI" roles | Partly built (Agent Console) | Your own repo | Demo all 4 patterns in the Agent Console |
| **P2** | RAG trade-offs: chunking, hybrid search, re-ranking, pgvector vs managed vector DB vs Couchbase FTS | AI teams probe the trade-off space | Know one stack deeply | Docs + free Claude/Gemini deep-dive (prompt P4) | Defend each option in 5 min |
| **P2** | MCP + agents: tools, approval gates, memory, guardrails | Market moving from RAG to agents | Have PoC experience | MCP spec (modelcontextprotocol.io); Udemy agents course updated 2025+ | Agent calls 2+ MCP tools behind approval gates |
| **P2** | Advanced TypeScript: generics, discriminated unions, typed SDK design | Architect signal | Refresh | TS handbook (free) | A typed client SDK in your project |
| **P3** | AWS architecture at SAA level: IAM, VPC, S3, Lambda, SQS/SNS, DynamoDB vs RDS | Architecture conversations | Working knowledge | Udemy SAA-C03 prep course (2025+ update); cert optional | Sketch a well-architected design unaided |
| **P3** | Go concurrency at teaching level | Fullstack screens | Have it | Your own code | Review others' concurrent Go confidently |
| **P3** | Python reading fluency | AI / FDE stacks lean Python | Reading only | Read agent-framework source weekly | Review a Python PR without friction |
| **Drop** | Angular, .NET, Manhattan SCALE, new certifications | Off-lane (plan Q8) | — | — | — |

## Weekly rhythm (while employed — from the plan)
- **Before work (~1.5h):** DSA (DesignGurus pattern of the day + 2 LeetCode problems)
- **Lunch (~1h):** outreach (referrals, recruiter replies) — see `04-outreach-and-negotiation.md`
- **Evening (~2h):** rotate Mon frontend system design · Tue React 19 / Next · Wed AI build (evals) · Thu distributed design (DesignGurus) · Fri mock (free Claude/Gemini) 
- **Weekend:** 1 full mock loop + 1 machine-coding build + eval-harness work

## 14-day calendar (4–17 Nov 2026, from your plan)
| Date | Prep block |
|---|---|
| Wed 4 Nov | Resume final check (this folder). DSA ×2 (arrays/hashing) |
| Thu 5 Nov | LinkedIn rewrite (`04-outreach-and-negotiation.md` §5). DSA ×2 |
| Fri 6 Nov | Machine coding: autocomplete, 60 min timed |
| Sat 7 Nov | Eval harness: 30–50 Q/A golden set + recall@k + faithfulness judge (extends your existing `AI/evals`) |
| Sun 8 Nov | Frontend system design mock: "design a cloud control-plane console" |
| Mon 9 Nov | React 19 / Next.js 15 refresh (list above) |
| Tue 10 Nov | DSA trees/graphs ×2. Say the 8 STAR stories aloud |
| Wed 11 Nov | Machine coding: nested comments or virtualised table |
| Thu 12 Nov | Core Web Vitals / INP deep dive; rehearse LCP waterfall story |
| Fri 13 Nov | Eval CI regression gate: fail when faithfulness/recall drop > X% |
| Sat 14 Nov | Publish eval write-up; full mock loop (DSA + FE design + behavioural) |
| Sun 15 Nov | Distributed design: rate limiter or notification service on AWS |
| Mon 16 Nov | DSA sliding window / two pointers, heaps |
| Tue 17 Nov | Retro: shift DSA vs design weight based on screen feedback |

## Weeks 3–6
- DSA: graphs, light DP, intervals. 2 mock loops a week (free Claude/Gemini or a peer).
- DesignGurus: 1 distributed design a week.
- Staff-level "scope and influence" stories: perf programme, micro-frontend work, SSE unblock.

## How to use free Claude / Gemini well
- One topic per chat. Paste the relevant section of this kit first so it has your context.
- Use them as **interviewer and critic**, never to write facts about you. Your facts live in the master resume.
- Prompts are in `06-free-ai-prompts.md`.
