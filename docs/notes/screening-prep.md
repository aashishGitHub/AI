# Screening Template — Prep Sheet (generic frontend/AI-native architect framing)

Source: screening template pasted 2026-08-18. Cross-checked against [career-roadmap.md](career-roadmap.md) (authorship-honesty rule, real evidence log) and [positioning.md](positioning.md) (keyword/framing conventions). Not tailored to a specific company — generic senior/staff frontend + AI-native positioning.

**How to use this:** for each row — a spoken-form answer (what to actually say) and the 2–3 follow-ups most likely to land, with the angle to take. Where your notes and the roadmap disagree on authorship, I flagged it rather than smoothing it over — say "contributed to" / "studying to author" where that's the honest framing; a fabricated ownership story is the fastest way to fail the very next question.

---

## Technical Expertise

**React depth**
> "12 years, most recently as React lead on Couchbase Capella's console. I led a Svelte-to-React migration, work daily with hooks and modern patterns, and I'm ramping on React Server Components for the next architecture push."
- *Follow-up: "Walk me through the Svelte→React migration decision."* → Have the trigger (why leave Svelte), the risk you managed (parity during rollout), and one thing you'd do differently.
- *Follow-up: "What's your RSC experience concretely — shipped, or studied?"* → Be precise: if it's study-track per your roadmap, say "studying it now, haven't shipped an RSC feature yet" rather than implying production use.

**TypeScript mastery**
> "Expert level — I design generics and typed SDKs that other engineers consume, and I set the strict-mode standards on my team."
- *Follow-up: "Give a concrete example of a generic/typed SDK you designed."* → Have one real example ready (even a small internal client) with the actual type signature, not a hypothetical.
- *Follow-up: "How do you decide when strictness is worth the friction?"* → Boundary-vs-internal-code framing: strict at public APIs/SDKs, pragmatic internally.

**Frontend Architecture**
> "I own the frontend architecture for Capella's console — design system, micro-frontend structure, module federation setup."
- *Follow-up: "Where has MF caused you pain, and how did you handle it?"* → This is your strongest depth story (dual-React invalid-hook crash, singleton vs splitChunks races) — see roadmap item 6b. Don't undersell it; it's genuinely rare depth.
- *Follow-up: "When would you NOT use micro-frontends?"* → Have the counter-case ready: team-topology mismatch, shared-dependency bundle cost, singleton footguns.

**Backend TypeScript/Node**
> "Good, not deep — I've built a Node BFF layer, and at work I also touch Go services, so I can read/review backend code across both."
- *Follow-up: "What does the BFF do and why was it needed?"* → Have the actual reason (aggregation, auth boundary, etc.) ready — vague answers here read as padding.

**State Management**
> "Redux Toolkit is my daily driver; I know Zustand and can speak to the trade-offs."
- *Follow-up: "When would you pick Zustand over Redux Toolkit?"* → Small/local state, less boilerplate, no need for middleware/devtools ecosystem — vs. RTK for larger apps needing normalized state, time-travel debugging, team conventions.

**Performance Optimization**
> "This is my strongest story: I cut Capella's LCP from 22+ seconds to 6–7 seconds — roughly 3x — through bundle and CSS work, and I authored the 10-route perf audit system behind it. Sub-3s is the next target, not yet hit."
- *Follow-up: "Walk me through the diagnosis, not just the fix."* → Lead with measurement first (the audit tooling), not the fix — this is explicitly your roadmap's lesson-learned. Have the bundle/CSS specifics ready.
- *Follow-up: "What's left to get to sub-3s, and why haven't you gotten there yet?"* → Answer honestly: this is an open, in-progress target per your own notes — don't imply it's solved.
- *Follow-up: "Is the CI perf-budget gate yours?"* → **Careful here.** Per your roadmap, the bundle-size CI gate is a teammate's (Anand's) build that you're studying/tracking, not something you authored. Say "in progress on the team, I'm studying it to build my own version" — not "I'm building it."

**Canvas/WebGL/Rendering**
> "Light — not my main area. I've integrated a canvas editor library into a product but haven't built rendering/hit-testing internals myself."
- *Follow-up: "Which library, and what did integrating it involve?"* → Have the specific library name and what you configured (not built) ready — this keeps the "integrated, not built" line credible.
- *Follow-up (if role needs canvas depth): "Would you be comfortable owning canvas rendering work?"* → Honest answer: willing to ramp, not currently deep — don't overclaim into a role that needs Figma/Excalidraw-caliber rendering skill.

**Testing Strategy**
> "TDD as default. React Testing Library and Cypress for unit/integration, Playwright for e2e, and I use AI to help generate and review test coverage."
- *Follow-up: "How do you use AI in test generation without it giving you false confidence?"* → Have a concrete guardrail: AI drafts, you review for actual behavior coverage vs. tautological tests, coverage numbers checked in CI.

**CI/CD**
> "Yes — I use CI/CD in my daily workflow, and I'm currently studying and partnering on perf-budget regression gates for the team."
- *Follow-up: "Did you build the perf-budget gate?"* → Same flag as above — be precise about contributed-to vs. authored. This will come up again if it came up in the perf-optimization row; keep the answer consistent both times.

**Code Review Leadership**
> "I lead reviews on my team, set the coding standards, and mentor juniors — including on React and increasingly on RAG/vector-DB patterns."
- *Follow-up: "Give an example of a standard you introduced and why."* → Have one concrete standard (e.g. a strict-TS rule, a component API convention) with the problem it solved.

---

## Complex Product Experience

**Most complex product built**
> "Capella's console — a React UI over a Go backend and an AWS-hosted search platform. It's the customer-facing surface for a distributed database product, so correctness and perf both matter under real production load."
- *Follow-up: "What made it complex — scale, domain, or architecture?"* → Architecture: MF, design system, perf constraints, plus the domain complexity of a database console (not just CRUD).

**Scale**
> "At JustAnswer, prior role, 10M+ users across US/EU/APAC."
- *Follow-up: "What broke at that scale that wouldn't at smaller scale?"* → Have a concrete story — i18n/timezone edge cases, or infra/perf issues surfaced only under real geographic spread.

**Architecture ownership**
> "I own frontend architecture on Capella and authored the perf initiative end-to-end — PR #51879."
- *Follow-up: "What's a decision you made that you'd defend even if someone pushed back?"* → Have one real trade-off call ready (e.g. an MF vs. splitChunks decision) with the reasoning, not just the outcome.

**Team size**
> "I've mostly worked in small teams — led a module of 5 at Eurofins."
- *Follow-up: "What was the hardest part of leading that team?"* → Have a specific people/scope story, not just "coordination was hard."

**Cross-functional collaboration**
> "Daily — PM, design, backend, DevOps. It's constant, not occasional."
- *Follow-up: "Tell me about a disagreement with PM or design you had to resolve."* → Have a real example with the resolution mechanism (data, prototype, compromise) — screeners probe for how you handle friction, not whether you collaborate.

**Business impact**
> "At JustAnswer: cut support cost by roughly 25%, saved around $100K a month through email self-resolution, and cut agent handling time from 2 minutes to 40 seconds."
- *Follow-up: "How did you or your team measure that $100K figure?"* → Know the measurement methodology (what was tracked, over what period) — a confident number with no measurement story invites doubt. If you're not 100% certain of the figure's precision, say "approximately" and describe how it was derived, per your own accuracy standard.

---

## Design-to-Code

**Figma/Sketch**
> "Yes — Figma to React, daily."
- *Follow-up: none likely beyond a quick example — have one recent Figma→component instance ready anyway.*

**Design Systems**
> "Built design systems at both Couchbase and JustAnswer."
- *Follow-up: "What's in the system — just components, or tokens/governance too?"* → Have the actual scope ready: token layer, versioning approach, who consumes it.

**Component Libraries**
> "Yes, Storybook-based component libraries."
- *Follow-up: "How do you handle breaking changes to a shared component?"* → Versioning/deprecation strategy, consumer communication.

**Figma to Production workflow**
> "Figma → design tokens → React components → ship."
- *Follow-up: "Where does that pipeline break down in practice?"* → Have one real friction point (token drift, designer/dev handoff gaps) — a frictionless answer sounds rehearsed, not real.

**Designer collaboration**
> "Close — I sit with designers and we agree on component APIs together, not just visuals."
- *Follow-up: "Give an example of pushing back on a design for technical reasons."* → Concrete example of a compromise you negotiated.

**Accessibility**
> "WCAG-aware — I build accessible components and follow secure UI patterns."
- *Follow-up: "What WCAG level, and how do you verify it — audit tools, manual, both?"* → Be specific: AA vs AAA, axe/Lighthouse usage, manual screen-reader checks if you do them. Vague "WCAG-aware" invites a specificity probe.

---

## AI Native Engineering

**Uses Claude/Cursor/Copilot**
> "Daily — Claude Code, Cursor, Copilot, across the actual work, not just experimentation."
- *Follow-up: "What's a task you'd never hand to AI, and one where it clearly outperforms you?"* → Have both — over-claiming AI usefulness reads as naive; under-claiming reads as not actually using it.

**AI code review process**
> "I use AI to draft and review PRs, and to catch regressions before they hit CI."
- *Follow-up: "Give an example of AI catching something a human reviewer missed — or getting it wrong."* → A failure example is more credible than a clean success story; have one of each if you can.

**Voice prompting experience**
> "Yes."
- *Flag: this is a one-word answer with nothing to hang a follow-up on — expect "tell me more" immediately.* Have a concrete scenario ready (what tool, what task, why voice vs. typing mattered) before this comes up, or it'll sound like you said yes reflexively.

**Prompt engineering**
> "Yes — I design prompts as versioned, tested artifacts, not throwaway strings."
- *Follow-up: "How do you version and test a prompt — what does the test check?"* → This connects directly to your roadmap's #1 gap (evals). If you don't yet have a regression suite for prompts, say so honestly rather than implying a mature eval harness exists — "versioned in git, testing is the piece I'm actively building out" is a defensible, honest answer.

**AI-first product exposure**
> "Yes — RAG and vector search on Couchbase FTS."
- *Follow-up: "What does your RAG pipeline actually do — chunking, hybrid search, reranking?"* → Per your roadmap, RAG beyond Couchbase (pgvector, Pinecone trade-offs) is a named gap. Speak confidently about the Couchbase FTS stack specifically; if pushed on alternatives, say you know one stack deeply and are studying the broader trade-off space rather than bluffing breadth you don't have.

---

## Complex UI

**Canvas editors**
> "Yes — I've integrated a canvas editor library into a product, though I haven't built the rendering/hit-testing engine myself."
- *Follow-up: "Which library, what did you configure vs. what came out of the box?"* → Keep this consistent with the "Light" answer on raw Canvas/WebGL — same honest boundary (integrated, not built).

**Workflow builders**
> "Currently building an agent console with a workflow-style UI — in progress, not yet shipped."
- *Follow-up: "How far along is it — what's built vs. planned?"* → Match this to your actual capstone status; don't let "building" imply "shipped."

**Whiteboards**
> "No direct experience."
- *Follow-up: unlikely to probe further on a stated "no" — if it does come up, pivot to adjacent experience (canvas integration, real-time collab) rather than overclaiming.*

**Timelines**
> "No direct experience."
- *Same as above — a clean "no" is fine and credible; don't pad it.*

**Real-time collaboration**
> "Yes — I've built with an SSE event bus, handling live updates under real load."
- *Follow-up: "SSE vs. WebSockets — why SSE here, and what breaks under load?"* → Have the actual reason (simplicity, one-directional need, infra fit) and one real failure mode you hit.

**Offline sync**
> "Light exposure only."
- *Follow-up: unlikely to go deep given the honest "light" framing — if asked, name the specific limited case rather than generalizing.*

**Large document performance**
> "Yes — data-heavy console pages on Capella, perf-tuned."
- *Follow-up: "What technique — virtualization, windowing, incremental rendering?"* → This ties directly back to your perf-optimization story; have the specific technique(s) named, not just "we tuned it."

---

## Ownership & Agency

**End-to-end ownership**
> "Yes — I own features from design through deploy."
- *Follow-up: "Walk me through one, start to finish."* → Use the Capella perf initiative — you have the receipts (PR #51879).

**Initiative**
> "High — I started the perf-monitoring initiative myself."
- *Follow-up: "What made you start it — was there a trigger, or self-directed?"* → Have the actual origin story; "I noticed X was bad and nobody owned it" is more credible than a vague "I'm proactive."

**Decision making**
> "I make architecture calls — weigh trade-offs, pick a direction, defend it."
- *Follow-up: "Tell me about a call that turned out wrong, and what you did."* → This is a near-certain follow-up at senior/staff level. Have a real one — a wrong call you caught and corrected reads as more senior than a spotless record.

**Mentoring**
> "Yes — I mentor juniors on React, RAG, and vector DBs."
- *Follow-up: "What's a concrete thing a mentee of yours can now do that they couldn't before?"* → Have a specific, attributable outcome, not "I help people grow."

**Architecture reviews**
> "I join and run them, and I set the coding standards."
- *Follow-up: "What's a standard you set that people initially pushed back on?"* → Real friction example beats a frictionless one.

**RFC writing**
> "Yes — and I use AI to help draft and structure RFCs."
- *Flag: "AI guides" is vague as written.* Be ready to say precisely what the AI does (drafting structure, prior-art search, alternatives section) vs. what decision-making stays yours — otherwise this can read as "AI writes my RFCs," which undercuts the ownership story you're telling everywhere else.

---

## Problem Solving

**Biggest challenge solved (last year)**
> "Cutting Capella's LCP from 22+ seconds to 6–7 seconds through bundle and CSS work."
- *Follow-up: "What was the hardest part — not the fix, the diagnosis?"* → Emphasize "measure first" (your own stated lesson learned) — this is the strongest, most defensible story you have; lean on it across multiple rows rather than trying to manufacture variety.

**Optimization example**
> "Same perf initiative, plus module-federation/webpack chunking fixes."
- *Follow-up: "Describe one of the chunking races you found."* → This is where the dual-React invalid-hook crash story belongs — but per your roadmap, be precise about what you authored vs. studied from a teammate's analysis (Pavel's work) if this specific example comes up. "I mastered and can now derive this myself" is honest; "I found this" is only honest if you actually found it.

**Trade-offs considered**
> "MF singleton sharing vs. splitChunks — weighing dual-React risk against bundle cost."
- *Follow-up: "Which did you choose, and why?"* → Have the actual decision and its concrete failure mode (the ones in your roadmap: singleton race, async-chunk duplication, runtimeChunk SPOF) ready to name specifically.

**Metrics improved**
> "LCP roughly 3x better. At JustAnswer, agent handling time went from 2 minutes to 40 seconds."
- *Follow-up: "How confident are you in these numbers — measured or estimated?"* → State your actual confidence level; "approximately" is fine and more credible than false precision.

**Lessons learned**
> "Measure first. Ship small, guarded routes. Guard against regressions before declaring a win."
- *Follow-up: "What's a time you didn't measure first and regretted it?"* → Concrete miss > abstract lesson.

---

## Culture & Motivation

**Why leave current company**
> "I want a role with more scope in AI + frontend — more reach than my current position gives me."
- *Follow-up: "What does 'more scope' look like concretely — bigger team, bigger architecture surface, more AI ownership?"* → Be specific; vague "growth" answers read as generic to experienced screeners.

**Interest in AI**
> "High — I'm building RAG, evals, and agents, and working with MCP."
- *Follow-up: "Where are you on evals specifically?"* → Per your own roadmap this is your named #1 gap — honest framing: "actively closing this, it's the piece I'm most deliberately building out right now," not "done."

**Interest in startup**
> "Open to it — I like ownership and 0-to-1 work."
- *Follow-up: "What's the biggest 0-to-1 thing you've actually built?"* → Have a real example, even at small scope, rather than a values statement with no evidence.

**5-day office readiness**
> "Yes."
- *Follow-up: unlikely — this is logistics, not substance.*

**Long-term goals**
> "Becoming a frontend-led architect with real AI depth."
- *Follow-up: "What does 'real AI depth' mean to you specifically — not buzzwords?"* → Point to evals, agents, MCP, RAG trade-off fluency — the concrete Tier 2 items in your own roadmap, not the phrase itself.

---

## Compensation

Blank in the template you shared — flag for you: decide before the call whether you want a number, a range, or "let's discuss after we confirm mutual fit," and whether you want it tied to India bands or global-remote. [positioning.md](positioning.md) has directional comp bands (senior frontend India ~₹34–45L avg per 6figr/Glassdoor 2026 samples, small self-reported n — verify, don't quote as fact) if you want a reference point, but the actual number is your call, not something I should fill in for you.

---

## Cross-cutting notes

- **Recurring theme across follow-ups:** almost every technical/perf row traces back to the same one story (Capella LCP 22s→6–7s, PR #51879). That's fine — it's your strongest, most verifiable evidence. Just vary the *angle* (diagnosis vs. trade-off vs. lesson-learned vs. metric) depending on which row prompted it, rather than repeating the same sentence.
- **Three rows need your own precision before the call, not mine:** the CI perf-budget gate (yours vs. Anand's), "voice prompting experience" (currently a bare "yes" with no story behind it), and React Server Components (per roadmap Tier 1 #2 — you understand hooks-era React deeply but haven't shipped a production RSC/Server Actions feature; say "studying it now, haven't shipped it yet" rather than implying production RSC experience).
- **Your own accuracy rule applies to yourself here too:** any number you state (25%, $100K/mo, 2min→40s, 22s→6-7s) should carry "approximately" if you're not fully certain of the precise figure — confident precision you can't back up is exactly the failure mode a good screener will probe for.
