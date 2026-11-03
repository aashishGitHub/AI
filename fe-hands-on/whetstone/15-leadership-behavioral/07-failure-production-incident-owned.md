# "Tell me about a failure or production incident you owned"
**Round:** 15 · Leadership & Behavioral · **Level:** Senior · **Time:** 10 min · **Tags:** behavioral · failure · incidents
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

They listen for ownership, calm under pressure, and what changed afterwards.

## What they're really testing
Accountability without excuses or blame, incident competence (detect, mitigate, communicate), root-cause depth (process gaps, not just "a typo"), and durable systemic fixes.

## Core answer (key points)
- **Pick a real failure with real impact.** No fake failures ("I work too hard").
- **Own your part** plainly in one sentence.
- **Spend most time on what you did next:**
  1. Impact: users affected, duration.
  2. Your role in causing or missing it.
  3. Mitigation: rollback or flag off, stakeholder communication.
  4. Root cause: usually a gap in tests, review or monitoring, not only the code line.
  5. Systemic fixes: tests, alerts, guardrails, runbooks.
  6. How you work differently now.
- **Blameless mindset:** systems and processes, not people.
- **Show you know the fixes worked** (e.g. alert caught a later regression; no recurrence).

## Mental model / flow
```
detect -> mitigate (rollback/flag) -> communicate -> root cause (5 whys) -> systemic fixes
  -> verify fixes -> personal habit change
```

## STAR skeleton
- **Situation:** What changed, what broke, who was affected and for how long? How was it detected (alert, customer, you)?
- **Task:** Your role: author, reviewer, on-call? What did you own during and after?
- **Action:**
  - First 15 minutes: how you mitigated and who you told.
  - How you found the root cause (and the process gap behind it).
  - The postmortem you wrote or ran.
  - Systemic fixes: test type added, lint rule, alert, rollout practice.
- **Result:** Time to mitigate, recurrence since, any later incident the new guardrail caught.
- **Learning:** The personal default you changed (e.g. flag every shared-component change, define a production check before shipping).

Example outline to adapt (own paraphrase): a memoization change to a shared table component passes tests but shows stale rows for one filter combination; you flag it off within the hour, post in the incident channel, find the memo comparison ignoring a nested prop, add interaction tests for filter combinations, a lint rule, and per-release error alerts.

## Trade-offs & pitfalls
- Blaming others or "the process" without owning your part.
- A trivial failure with no consequences.
- Long incident narration, rushed systemic fixes.
- Root cause = "I made a typo" with no process change.
- Getting defensive under follow-up questions.

## Likely follow-ups
- **"How did you communicate during it?"** Incident channel, regular status updates, single owner of comms.
- **"Why didn't tests catch it?"** Specific coverage gap and what you added.
- **"What would you do differently?"** Usually: rollout flag + targeted production check for shared code.
- **"How did your team/manager react?"** Show blameless culture, or how you helped create it.

## Say it in 60 seconds
I pick a real incident I caused or missed, state my part in one sentence, then spend most of the time on the response. I mitigated quickly, by flag or rollback, and posted updates in the incident channel. In the postmortem the root cause wasn't just the bug but the gap that let it ship, such as a missing test for a combination or no per-release alerting. So the fixes were systemic: new interaction tests, a lint rule, release-level error alerts. And I changed a personal default, for example every shared-component change now ships behind a flag with a specific production check. I close with evidence the fix worked.
