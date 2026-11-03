# "Tell me about a large migration you led"
**Round:** 15 · Leadership & Behavioral · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** behavioral · migration · leadership
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

The interviewer will probe your decisions, risks managed and results.

## What they're really testing
Business judgment (why it was worth it), an incremental strategy without a feature freeze, bringing people along, and finishing.

## Core answer (key points)
- **Business case,** not "old tech": EOL/security risk, slower feature lead time on affected areas, hiring/onboarding cost, two component stacks. Say what you chose *not* to do.
- **Strategy:** incremental (strangler fig) with a bridge so old and new coexist; route-level cutover; shared design tokens for visual consistency.
- **Prioritization:** value x change frequency (most-touched, highest-traffic screens first), bundled with planned feature work.
- **Guardrails:** no new code in legacy; per-screen definition of done (parity, analytics, a11y, E2E ported, perf budget).
- **Bringing people along:** patterns doc, reference screen, reviews, pairing, division of work across teams.
- **Visibility:** dashboard of screens remaining and legacy bundle size.
- **Finish:** remove the legacy runtime; explicitly budget the long tail.
- **One real setback** (cross-stack state bug, perf regression, stalled screen) and how you handled it.

## Mental model / flow
```
why now -> bridge + guardrail -> prioritize by value x churn -> DoD per screen
  -> visible progress -> setback handled -> legacy removed -> numbers -> learning
```

## STAR skeleton
- **Situation:** Which stack to which? How big (screens, LOC, teams)? What concrete pain (lead time, EOL, defects, hiring)? Why could the roadmap not pause?
- **Task:** Your exact remit (frontend lead? whole program?). Who were the stakeholders? What did "done" mean?
- **Action:**
  - Bridge you chose (embed new in old / route split / shell) and the alternative you rejected (big-bang rewrite, micro-frontends) and why.
  - How you prioritized and how you tied migration to feature work.
  - Guardrails and per-screen definition of done.
  - How you scaled it across people: docs, reference implementation, reviews.
  - The hard moment: what went wrong, what you did.
- **Result:** Screens migrated over what period, legacy bundle removed (bytes), feature lead time or defect rate before/after, features shipped in parallel.
- **Learning:** e.g. budget the last 10% explicitly; start the guardrail on day one.

## Trade-offs & pitfalls
- Telling the tech, skipping the people and business parts.
- Claiming it finished cleanly with no setbacks (not credible).
- No numbers, or only vanity numbers ("migrated 200 files").
- Not knowing why you didn't choose the alternative approach.

## Likely follow-ups
- **"How did you decide what to migrate first?"** Value x change frequency, risk, dependency order.
- **"What went wrong?"** One real setback with root cause and fix.
- **"How did you convince leadership?"** Velocity on affected areas, EOL/security risk, hiring, user-facing quality.
- **"Micro-frontends next time?"** Depends on team count and independence needs; justify either way.

## Say it in 60 seconds
Frame: part of the product was on an end-of-life framework, so every feature there was slower and new hires couldn't work in it. I led moving it to React without pausing the roadmap. I set up a bridge so new components ran inside old pages and migrated routes went to the new app, shared design tokens so both looked the same, prioritized by how often a screen changed and how much traffic it had, and bundled migrations with planned features. Each screen had a definition of done covering parity, analytics, accessibility, tests and a perf budget, there was a no-new-legacy-code rule, and progress was on a dashboard. Then a real setback, the measured results, and the learning: plan the last 10% because that's where migrations stall.
