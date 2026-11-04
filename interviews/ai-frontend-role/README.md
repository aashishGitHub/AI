# AI + Frontend role: the self-contained prep pack

Written 2026-11-04 so you can prepare **without Claude**. Everything you need to rehearse is here or linked from here.
Target role: Staff / Lead / Senior Frontend Engineer on AI products (chat, copilots, agent consoles, AI search).

## Files, in study order

| # | File | What it covers | Time |
|---|---|---|---|
| 0 | [00-HOW-TO-PREPARE.md](00-HOW-TO-PREPARE.md) | **Start here.** Your 14-day plan (4–17 Nov) mapped to these files, priorities, daily loop, what replaces Claude | 15 min |
| 1 | [01-llm-fundamentals.md](01-llm-fundamentals.md) | Tokens, context, sampling, embeddings, hallucination, model choice: what an FE lead must know | 2 h |
| 2 | [02-ai-frontend-engineering.md](02-ai-frontend-engineering.md) | Streaming (SSE / fetch streams), abort, Markdown, generative UI, tool calls, chat state, latency UX, security | 4 h |
| 3 | [03-rag-agents-evals.md](03-rag-agents-evals.md) | RAG pipeline, hybrid search, agents, MCP, human-in-the-loop, evals, observability, cost | 3 h |
| 4 | [04-frontend-core.md](04-frontend-core.md) | JS runtime, TypeScript, React 19 / Next.js, performance, a11y, security, testing, architecture | 4 h |
| 5 | [05-system-design.md](05-system-design.md) | Six full AI-FE design walkthroughs (chat app, copilot, AI search, agent console, ...) | 4 h |
| 6 | [06-coding-rounds.md](06-coding-rounds.md) | TypeScript solutions you should be able to write from a blank editor | 4 h |
| 7 | [07-behavioral-and-closing.md](07-behavioral-and-closing.md) | STAR stories, AI-specific behavioural questions, questions to ask them, red flags | 2 h |
| 8 | [08-rapid-fire.md](08-rapid-fire.md) | One-line answers for the last hour before an interview | 30 min |

## Where the deeper material already lives (do not re-read everything, use it when a QnA answer feels thin)

| Topic | Deep file |
|---|---|
| Streaming, Markdown, generative UI, RAG UX, latency, evals (FE view) | [`fe-hands-on/whetstone/14-ai-frontend/`](../../fe-hands-on/whetstone/14-ai-frontend/README.md) |
| JS, TS, React, perf, a11y, security, testing, FE system design | [`fe-hands-on/whetstone/01..13`](../../fe-hands-on/whetstone/README.md) |
| Your own build: Go SSE server + Next.js console | [`fe-hands-on/README.md`](../../fe-hands-on/README.md) |
| Frontend AI UI (1300 lines) | [`devrev-fde/modules/09-frontend-ai-ui.md`](../devrev-fde/modules/09-frontend-ai-ui.md) |
| Agents, MCP, memory, orchestration | [`devrev-fde/modules/03, 10, 11, 14`](../devrev-fde/modules/README.md), [`agent-engineer-screen/QNA.md`](../agent-engineer-screen/QNA.md) |
| RAG + hybrid search | [`rag-hybrid-search/`](../rag-hybrid-search/README.md) |
| Vector databases | [`vector-databases/`](../vector-databases/README.md) |
| Evals + observability | [`llm-eval-and-observability/`](../llm-eval-and-observability/README.md), [`../../evals/`](../../evals/README.md) |
| STAR stories, FE system-design template | [`career/03-interview-kit.md`](../../career/03-interview-kit.md) |
| Anchor case study (Ask AI) | [`docs/Ask AI design document.md`](../../docs/Ask%20AI%20design%20document.md) |

## How to practise without an AI tutor

1. **Cold attempt.** Read only the question. Answer **out loud**, record it on your phone (90 s for a concept, 3 min for a design question).
2. **Check.** Compare with the written answer. Mark each one: ✅ said the core idea · 🟡 said it, missed the trade-off · ❌ missed it.
3. **Redo the 🟡 and ❌ ones the next day.** Keep a list at the bottom of this README (the "weak list").
4. **Self-grade senior signal** with the rubric below. A senior answer has all four.
5. **Code from a blank file.** For `06-coding-rounds.md`, close the answer, set a 25-minute timer, write it in a plain `.ts` file, run it with `npx tsx file.ts`.
6. **Mock with a friend.** Hand them `05-system-design.md` and the rubric. They read the prompt and the follow-ups. You drive.

### Senior-answer rubric (use it on every answer)

| Signal | What it sounds like |
|---|---|
| **Answer first** | First sentence is the answer, not background. |
| **Mechanism** | You say *how* it works (control flow, data flow), not just the name. |
| **Trade-off** | "I'd pick X over Y because Z; the cost is W." |
| **Failure mode + measurement** | "This breaks when ...; I'd know because metric M moves; I'd guard with ..." |

### The one-paragraph pitch (memorise this)

> "I'm a frontend architect with 10+ years, most recently at Couchbase on the Capella cloud console. For the last year
> I've focused on the frontend of AI products: I built a streaming, retrieval-grounded assistant (Go SSE server and a
> Next.js console that shows sources next to the answer), an eval harness with a golden set and a CI gate, and an MCP
> agent with an approval gate. I care about the parts of AI features that decide if users trust them: perceived latency,
> streaming that doesn't jank, citations, safe rendering of model output, and evals that catch regressions before users do."

Edit the pitch so every claim is one you can defend in a follow-up.

## Accuracy note

- Library APIs in AI tooling change every few months (Vercel AI SDK, MCP spec, model names, React minor versions).
  Where an answer names a specific API, the answer says "verify". Check the official docs the week of the interview.
- Numbers marked "approximately" are rules of thumb, not measurements. Do not quote them as fact.

## Weak list (fill as you practise)

| Date | File / Q# | What I missed |
|---|---|---|
| | | |
