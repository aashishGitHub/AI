# Write and drive a technical strategy or RFC across teams
**Round:** 15 · Leadership & Behavioral · **Level:** Principal · **Time:** 15 min · **Tags:** behavioral · rfc · technical strategy
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

Scenario: write an RFC for a company-wide frontend platform change (shared design system + framework upgrade) touching ten teams.

## What they're really testing
Written reasoning (evidence, options, honest trade-offs), consensus building before the meeting, explicit decisions, and follow-through on adoption and metrics.

## Core answer (key points)
- **RFC structure:**
  1. Context and problem, with evidence (incidents, metrics, developer survey).
  2. Goals and non-goals.
  3. Proposal (architecture, APIs, examples).
  4. Alternatives considered and why not.
  5. Trade-offs and risks: what gets worse, mitigations.
  6. Rollout and migration: phases, codemods, deprecation timeline, owners.
  7. Success metrics and when you'll check them.
  8. Open questions.
- **Driving it:**
  - Pre-wire: share drafts 1:1 with the most affected and most skeptical people; fold in their feedback before any review meeting.
  - Decide explicitly: named decider, deadline; record in an ADR (architecture decision record) including dissent.
  - Make the right path easy: templates, generators, codemods, lint rules, copy-paste docs.
  - Pilot with one team, publish results, then expand.
  - Revisit metrics; change course if assumptions were wrong.
- **Strategy vs RFC:** strategy is a level up: diagnose the situation, set guiding policies, then a coherent set of actions over quarters (this framing is commonly attributed to Richard Rumelt's "good strategy" kernel; verify if you cite it).

## Mental model / flow
```
evidence -> draft -> 1:1 pre-wire (skeptics first) -> revise -> review -> decision + ADR
  -> pilot team -> results published -> tooling + timeline -> org rollout -> metrics review
```

## STAR skeleton
- **Situation:** What cross-team problem, backed by which evidence? How many teams affected? Why now?
- **Task:** Were you asked or did you initiate? Who was the decision owner? What was in scope (and not)?
- **Action:**
  - Evidence you gathered and how.
  - Alternatives you seriously considered and why you rejected them.
  - Who you pre-wired, the toughest objection, and what you changed because of it.
  - How the decision was made and recorded.
  - How you made adoption cheap (codemods, templates, pilot).
- **Result:** Adoption numbers over time, outcome metric (consistency, defects, build time, perf), what happened to dissenters' concerns.
- **Learning:** e.g. pre-wire skeptics first; non-goals prevent scope creep.

## Trade-offs & pitfalls
- Recommendation without alternatives reads as advocacy, not analysis.
- Surprising stakeholders in the review meeting.
- "Approved" with no owner or rollout plan; nothing happens.
- No success metric, so you can't tell if it worked.
- Hiding what gets worse; reviewers find it and trust drops.

## Likely follow-ups
- **"How do you handle a team that refuses?"** Understand their constraint, offer support or a later wave, escalate via the agreed decision process only if needed.
- **"How long should an RFC be?"** As short as the decision allows; summary first.
- **"RFC vs ADR?"** RFC proposes and gathers input; ADR records the decision and context.
- **"What makes a strategy bad?"** Goals dressed as strategy, no diagnosis, actions that don't cohere.

## Say it in 60 seconds
A good RFC starts with the problem and evidence, states goals and non-goals, gives options with honest trade-offs including what gets worse, then a recommendation, rollout and migration plan with owners and deprecation timeline, and success metrics. Driving it matters as much as writing it: I share drafts one on one with the most affected and most skeptical people first, so the review has no surprises, then a named owner decides by a date and we record it in an ADR with dissent noted. Adoption comes from making it cheap: a pilot team, published results, codemods, templates and lint rules. And we check the metrics later and change course if assumptions were wrong.
