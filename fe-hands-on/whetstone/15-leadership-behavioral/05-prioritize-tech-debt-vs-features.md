# How do you get tech debt prioritized against feature work?
**Round:** 15 · Leadership & Behavioral · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** behavioral · tech debt · prioritization
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

Scenario: product says no room for debt this quarter; you believe slow builds and brittle tests cost the team about a day a week.

## What they're really testing
Translating engineering pain into business language, negotiating with product as a partner, and having more than one mechanism.

## Core answer (key points)
- **Translate to business impact and quantify:**
  | Debt | Framing | Metric |
  |---|---|---|
  | Slow/flaky CI | engineer hours lost, slower releases | CI duration, re-run rate, PR lead time |
  | Legacy framework | feature lead time, hiring, EOL security | cycle time on that area |
  | No tests on revenue path | incident risk | regressions/incidents per quarter |
  | Bundle bloat | conversion/engagement | LCP/INP per route, bytes |
- **Attach to the roadmap,** don't compete with it ("building the new invoices flow; migrating that area adds ~20% and halves future change cost there").
- **Mix mechanisms:** boy-scout fixes in PRs that touch the code; standing capacity allocation (often quoted as 15-20%, treat as a negotiable starting point); dedicated projects with milestones for big debt.
- **Debt register:** owner, impact, effort, rough priority; reviewed with product each quarter.
- **Error budgets/SLOs:** when reliability drops below target, priority shifts automatically, no debate.
- **If still no:** do the smallest high-ROI slice within existing work, keep measuring, and come back with data next quarter. Report before/after so the next ask is easier.

## Mental model / flow
```
measure cost (hours/week, incidents) -> frame in product's goals -> propose options (bundle / % / project)
  -> agree target + checkpoint -> deliver -> report before/after -> credibility for next ask
```

## STAR skeleton
- **Situation:** What debt, and what visible symptom (CI ~X min, Y% flaky re-runs, Z incidents)? What was product prioritizing?
- **Task:** Your role in getting it addressed; what you needed (time, people, sponsorship).
- **Action:**
  - How you measured the cost (data source, rough team-wide hours).
  - How you framed it in product's terms.
  - Options you offered and the one agreed.
  - How you de-risked delivery (milestones, no feature freeze).
  - What you did when you met resistance.
- **Result:** Before/after metric, effect on delivery (PR throughput, release frequency), and what it unlocked later.
- **Learning:** e.g. report outcomes publicly; a debt register reviewed with product beats ad-hoc asks.

## Trade-offs & pitfalls
- Leading with "the code is ugly". Product hears preference, not cost.
- All-or-nothing rewrite proposals.
- Fixed allocation without a register becomes a slush fund nobody can explain.
- Unmeasured outcomes make the next ask harder.
- Doing debt work secretly erodes trust with product.

## Likely follow-ups
- **"How do you decide which debt first?"** Impact x frequency of pain / effort; prefer debt in areas on the roadmap.
- **"What if product still says no?"** Smallest slice inside feature work, keep the data, escalate only with clear numbers and a recommendation.
- **"Is all tech debt bad?"** No; deliberate, prudent debt is a valid trade-off if recorded and repaid.
- **"How do you prevent new debt?"** Lint/CI guardrails, definition of done, ADRs for deliberate shortcuts.

## Say it in 60 seconds
I translate debt into the product's language and put numbers on it: if flaky CI costs a day a week, that's hours across the team, slower releases and batching that creates risk. Then I attach the fix to the roadmap instead of competing with it, for example cleaning up the area we're about to build in, and offer options: boy-scout fixes as we go, a standing capacity slice, or a time-boxed project with a target. I keep a debt register with owners and impact that we review with product quarterly, and SLOs shift priority automatically when reliability slips. After delivery I report before and after, which makes the next request easy.
