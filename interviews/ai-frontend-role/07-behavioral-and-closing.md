# 07 · Behavioural, AI-specific stories, and closing the interview

Full STAR table with leadership-principle mapping: [`career/03-interview-kit.md` §1](../../career/03-interview-kit.md).
Leadership question notes: [whetstone/15](../../fe-hands-on/whetstone/15-leadership-behavioral/README.md).

**Rules from your plan:** proof-point numbers are only **LCP 22s+ → 6–7s · ~25% CS cost cut · ~$100K/month saved · handling time 2 min → 40 s**. No other numbers.
Say "I built" only for what you built. Fill every `[bracket]` from memory before the first screen.

Format, 2 minutes each: **S**ituation 15 s · **T**ask 15 s · **A**ction 60 s (what *you* did, "I" not "we") · **R**esult 20 s · **L**earning 10 s.

---

## A. Your story bank: which story answers which question

| Question they ask | Story | One-line hook |
|---|---|---|
| Biggest technical impact / performance | **LCP 22s+ → 6–7s** (Capella console) | "Built a 10-route audit, found [top 2 bottlenecks], fixed [how]; ~3x LCP. Sub-3 s isn't done yet: here's the plan." |
| Unblocked the team / invented a simpler path | **SSE event bus** | "Real-time was blocked 6+ months on infra; I proposed SSE, co-designed it with a backend engineer, demoed a PoC, mentored 2 engineers." |
| Owned something outside your lane | **Home Page Recents backend in Go** | "FE engineer, wrote the API spec, built it in Go with compare-and-swap + backoff and 2-layer RBAC; caught spec drift in design review." |
| Failure / quality miss | **March quality miss** | "QE caught edge cases I missed. I owned it and changed how I work: QE-agreed test plan before code. Quality held from April." |
| Customer obsession / escalation | **Customer escalation fixed overnight** | "Fixed by the next morning, then changed proxy error handling so that class of ticket stops." |
| Disagree and commit / push back | **v1 UI investment question** | "Fixed the UI side, routed root cause to backend, asked PM whether to keep investing in a UI being retired." |
| Business impact / cost | **JustAnswer self-resolution** | "~25% CS cost cut, ~$100K/month, handling time 2 min → 40 s. [State your exact part.]" |
| How do you know AI works / dive deep | **Eval harness + prompt drift** | "promptfoo golden set, cross-family judge, CI gate; caught server prompt and eval prompt drifting; added a zero-model parity check." |
| Mentoring | SSE work, two engineers | "[what they could do after that they couldn't before]" |
| Large migration | Svelte → React at JustAnswer (you led it) | "[scope, how you kept shipping during it, how you measured done]" |

---

## B. AI-specific behavioural questions (with answer spines)

### B1. "Tell me about an AI feature you built end to end."
Spine: the user problem → why AI (and why not a simpler non-AI fix) → architecture in one sentence (retrieval + streaming + citations) → the hardest FE problem (streaming render / safe Markdown / trust UX) → **how you measured quality** (golden set, CI gate) → what you'd do next.
Use: the Agent Console + Go SSE server + evals in this repo; the Couchbase RAG/MCP work only to the extent you did it.

### B2. "Users say the AI gives wrong answers. What do you do?"
Spine: don't argue with anecdotes, get traces → split retrieval vs generation failure → add the failing cases to the golden set → fix the biggest bucket → ship behind a flag with an eval gate → add UX that makes wrongness checkable (citations, "I don't know", feedback). Tell the prompt-drift story as proof you've done this.

### B3. "A PM wants to ship an AI feature next week without evals. What do you say?"
Spine: disagree with data, not opinion. Propose the smallest eval that de-risks it (30 real questions, 1 day of work), ship to a small cohort behind a flag, define the rollback trigger. Then commit to the date. That's "have backbone, disagree and commit".

### B4. "When would you *not* use an LLM?"
Spine: when the task is deterministic (validation, formatting, routing by rules), when latency budget is tiny and a classic index works (autocomplete), when wrong answers are costly and unverifiable, when the volume makes cost absurd. "The best AI feature I can ship is sometimes a better search box."

### B5. "How do you use AI tools in your own engineering work?"
Spine: honest and specific. Coding assistants for scaffolding, test generation, reading unfamiliar code, reviewing diffs; you own correctness: you run the tests, you read every line, you don't paste secrets or customer data into them, you follow the company's policy. Mention you wrote rules files / prompts to keep an assistant aligned with team conventions if that's true.
Never use AI tools in an interview round unless the round provides one (your plan's rule).

### B6. "How do you stay current in a field that changes monthly?"
Spine: primary sources over threads (provider changelogs, spec repos like MCP, react.dev / nextjs.org release notes), build small things to test claims (your `agent-lab`, `evals/`), keep an eval set so you can judge a new model on *your* task in an hour instead of trusting benchmarks.

### B7. "Tell me about a time you balanced speed and safety."
Spine: approval gates for agent write tools, or the AI panel isolated behind an error boundary + feature flag; you shipped fast *because* the blast radius was bounded.

### B8. "How do you lead frontend architecture across teams?" (Staff signal)
Spine: write the RFC, prototype the risky part, get one team to adopt it, measure, then make it the paved road (shared package / design-system pattern), deprecate the old path with codemods. Influence without authority: make the right way the easy way.

---

## C. Questions to ask them (pick 3; ask the ones you actually want answered)

**About the AI product**
1. How do you measure whether the AI feature is good today? Is there an eval set, and who owns it?
2. What's the split between FE and ML/platform engineers on AI features — who owns prompts, retrieval, and the streaming API?
3. What's the hardest UX problem you haven't solved yet (trust, latency, cost, agent actions)?
4. How do prompt or model changes get rolled out — flags, canaries, eval gates?

**About the role and team**
5. What would make someone in this role clearly successful at 6 months?
6. What does the FE architecture look like today, and what do you want to change?
7. How are big technical decisions made — RFCs, architecture review, the tech lead?
8. What level is this role mapped to, and how is the interview loop structured? (Ask the recruiter early.)

**About the company and AI direction**
9. Is the AI roadmap build-on-providers or in-house models, and why?
10. What's your policy on AI tools in day-to-day engineering?

---

## D. Red flags to listen for (theirs)

- "We don't really evaluate it, we look at it and it seems fine." → quality debt you'll inherit.
- FE is expected to call the model provider straight from the browser with a key → security debt.
- No owner for prompts → regressions with no rollback path.
- "AI will replace the frontend" → misaligned role.
- The role's level isn't decided yet → push for it before onsite.

---

## E. Openers and closers (memorise)

**"Tell me about yourself" (60–90 s):** use the pitch in [README](README.md#the-one-paragraph-pitch-memorise-this), then: "…which is why this role caught my eye: [one specific thing about their AI product]."

**"Why are you leaving?":** "I want staff-level scope on frontend architecture for AI products, and [company] is where that work is happening." Never mention layoffs or the current company's health.

**"What's your expected compensation?":** don't give current CTC first. See [`career/04-outreach-and-negotiation.md`](../../career/04-outreach-and-negotiation.md).

**Close:** "Is there anything in my background that makes you hesitate about my fit? I'd like to address it now." Then thank them and name one thing from the conversation you'd enjoy working on.
