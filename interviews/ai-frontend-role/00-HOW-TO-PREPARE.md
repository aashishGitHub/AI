# 00 · How to prepare (no Claude needed)

This is your plan from 3 Nov 2026, kept as it was, with each prep block pointed at the QnA file to use.
Original sources (same content; the Drive copies are your personal backup):
- [`career/00-source-plan-14-day.md`](../../career/00-source-plan-14-day.md): full 14-day plan with market research and sources
- [`career/02-skills-priority-and-study-plan.md`](../../career/02-skills-priority-and-study-plan.md): skills by priority, resources, "done when"
- [`career/03-interview-kit.md`](../../career/03-interview-kit.md): STAR stories, FE design template, React 19 list
- [`career/README.md`](../../career/README.md): the hub, pipeline + prep by date
- Drive backup: `course01000@gmail.com` → `My Drive/002_JobSearch_Nov2026/` (start with `00_START_HERE.md`)

---

## 1. The lane, in one line

**Senior/Staff Frontend Engineer for AI products.** Fullstack widens the funnel. FDE (forward-deployed engineer) gets 20–25% of the effort.
Proof points (only these numbers): LCP 22s+ → 6–7s · ~25% CS cost cut · ~$100K/month saved · handling time 2 min → 40 s.

## 2. Priorities (from the study plan)

| P | Skill | Use in this folder | Other material | Done when |
|---|---|---|---|---|
| **P0** | DSA patterns | — | DesignGurus "Grokking the Coding Interview" + NeetCode 150; [DSnAlgoUsingJS/PLAN.md](https://github.com/aashishGitHub/DSnAlgoUsingJS/blob/master/PLAN.md) | ~28 mediums solved aloud, 25-min cap |
| **P0** | Frontend system design | [05-system-design.md](05-system-design.md) | [whetstone/12](../../fe-hands-on/whetstone/12-frontend-system-design/README.md), [`career/03` §2](../../career/03-interview-kit.md) | Any of 6 designs whiteboarded in 35–45 min with trade-offs |
| **P0** | Machine coding | [06-coding-rounds.md](06-coding-rounds.md) | [whetstone/06](../../fe-hands-on/whetstone/06-machine-coding/README.md) | 4 builds under 60 min: autocomplete, virtual table, nested comments, modal/toast |
| **P0** | Behavioural | [07-behavioral-and-closing.md](07-behavioral-and-closing.md) | [`career/03` §1](../../career/03-interview-kit.md) | 8 stories aloud, 2 min each, brackets filled |
| **P1** | React 19 / Next.js + Web Vitals | [04-frontend-core.md](04-frontend-core.md) §C–E | react.dev, nextjs.org, web.dev | You can say when RSC *hurts*; LCP story request by request |
| **P1** | LLM evals | [03-rag-agents-evals.md](03-rag-agents-evals.md) §D | [`evals/`](../../evals/README.md) | Golden set + recall@k + faithfulness + CI gate; write-up published |
| **P1** | Distributed design | — | [SystemDesign-Backend/PLAN.md](https://github.com/aashishGitHub/SystemDesign-Backend/blob/main/PLAN.md) | 1 design a week |
| **P2** | AI-native UI | [02-ai-frontend-engineering.md](02-ai-frontend-engineering.md) | [`fe-hands-on/`](../../fe-hands-on/README.md) | Agent Console demos streaming, tool approval, optimistic action, generative UI |
| **P2** | RAG / vector DBs / MCP + agents | [03-rag-agents-evals.md](03-rag-agents-evals.md) §A–C | [`rag-hybrid-search/`](../rag-hybrid-search/README.md), [`vector-databases/`](../vector-databases/README.md), [`agent-lab/`](../../agent-lab/NOTES.md) | Defend each option in 5 min |
| **P2** | LLM basics for FE | [01-llm-fundamentals.md](01-llm-fundamentals.md) | — | Rapid-fire table in [08](08-rapid-fire.md) all green |

## 3. The 14 days (Wed 4 – Tue 17 Nov 2026) with files

| Date | Pipeline (from the plan) | Prep block (from the plan) | Use |
|---|---|---|---|
| Wed 4 Nov | List 40 reqs (req ID + level) | Resume final check · DSA ×2 | Read [01](01-llm-fundamentals.md) at night (1 pass) |
| Thu 5 Nov | 25 referral asks to a specific req ID | LinkedIn rewrite · DSA ×2 | [02](02-ai-frontend-engineering.md) §A–B |
| Fri 6 Nov | 10 hiring-manager notes | Machine coding: autocomplete, 60 min | [06](06-coding-rounds.md) C11, then C3 + C6 |
| Sat 7 Nov | Chase pending referrals | Evals: 30–50 Q/A golden set + recall@k + faithfulness | [03](03-rag-agents-evals.md) §D, Q21–Q23 |
| Sun 8 Nov | 10 direct applications | FE design mock: cloud control-plane console | [05](05-system-design.md) D2 (copilot in a console) + the checklist |
| Mon 9 Nov | Recruiter replies < 24h | React 19 / Next.js refresh | [04](04-frontend-core.md) §C–D |
| Tue 10 Nov | Second referral wave (15) | DSA trees/graphs ×2 · 8 STAR stories aloud | [07](07-behavioral-and-closing.md) §A |
| Wed 11 Nov | Book screens 13–17 Nov; ask level, loop, AI-tool policy | Machine coding: nested comments / virtual table | [06](06-coding-rounds.md) C12 list |
| Thu 12 Nov | FDE lane applications | Core Web Vitals / INP deep dive | [04](04-frontend-core.md) §E + [02](02-ai-frontend-engineering.md) Q22 |
| Fri 13 Nov | Follow up on 7–10-day-old applications | Eval CI regression gate | [03](03-rag-agents-evals.md) Q23, Q25 |
| Sat 14 Nov | Publish eval write-up, link on LinkedIn Featured | Full mock loop | [05](05-system-design.md) D1 + [06](06-coding-rounds.md) C1–C2 + [07](07-behavioral-and-closing.md) B1–B3 |
| Sun 15 Nov | Rest | Distributed design: rate limiter / notifications on AWS | SystemDesign-Backend repo |
| Mon 16 Nov | First screens: never give current CTC first | DSA sliding window, heaps | [08](08-rapid-fire.md) the hour before each screen |
| Tue 17 Nov | < 5 active processes → third outreach wave | Retro: shift DSA vs design weight | Update the weak list in [README](README.md#weak-list-fill-as-you-practise) |

**Weeks 3–6 (from the plan):** DSA graphs, light DP, intervals · 2 mock loops a week · 1 distributed design a week · staff-level "scope and influence" stories (perf programme, micro-frontends, SSE unblock). In this folder: cycle through [05](05-system-design.md) D1–D6 (one a week, twice), and redo [06](06-coding-rounds.md) C1, C2, C4, C11 from blank until each is under 20 minutes.

## 4. Daily loop (from your START_HERE)

Morning DSA (~1.5 h) → lunch outreach, log it in the tracker (~1 h) → evening prep block above (~2 h) → once a day, update the tracker's "Next action".
Weekend: 1 full mock loop + 1 machine-coding build + eval-harness work.
Every block ends in an **artifact**: code, a write-up, or a scored mock. Video hours alone don't count.

## 5. Replacing Claude in each part of the plan

| Plan used Claude for | Do this instead |
|---|---|
| Mock interviewer | Free Gemini with the prompts in [`career/06-free-ai-prompts.md`](../../career/06-free-ai-prompts.md) (free-tier limits change; plan a few long sessions a day), or a friend reading [05](05-system-design.md) prompts and follow-ups aloud |
| Grading your answers | The senior-answer rubric in [README](README.md#senior-answer-rubric-use-it-on-every-answer) + record yourself + compare with the written answer |
| Explaining a concept | The linked deep files (whetstone, devrev-fde modules), then primary docs: react.dev, nextjs.org, web.dev, MDN, modelcontextprotocol.io, the provider's API docs |
| Checking code | Run it. Every pure-TS snippet in [06](06-coding-rounds.md) passed strict `tsc` and runtime asserts on 2026-11-04. Write your own asserts the same way |
| Writing facts about you | Never AI. Your facts live in `01_Resumes/00_MASTER_RESUME_source_of_truth.md` on Drive |

## 6. Rules (from the plan; don't break them)

- AWS SA-Associate = "in preparation" until passed.
- No AI tools in real interview rounds unless the round provides one.
- Ask the recruiter for **level + loop structure + AI-tool policy** when booking.
- Plan for 4–8 weeks from application to offer. Day 30: 5–8 active processes · Day 60: 2+ offers · Day 90: join.
- Take-homes: never on Couchbase devices or with Couchbase code.
