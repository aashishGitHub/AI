# How do you mentor engineers and raise the bar of a team?
**Round:** 15 · Leadership & Behavioral · **Level:** Lead / Staff · **Time:** 10 min · **Tags:** behavioral · mentoring · leadership
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

Answer with specific examples, not a philosophy.

## What they're really testing
Two layers: individual mentoring tailored to the person, and systemic mechanisms that raise quality without you being the bottleneck.

## Core answer (key points)
- **Individual:** learn their goals and gaps; give stretch work with a safety net (weekly check-ins); specific, timely feedback; let them present the result.
- **Systemic (raise the bar):**
  - Code review as teaching: labeled comments (`nit:`, `suggestion:`, `blocking:`), explain why, praise good calls, turn repeated comments into docs or lint rules.
  - Design reviews/RFCs for non-trivial changes so people learn to write and defend decisions.
  - Pairing/mobbing on unfamiliar areas (profiling, tricky migrations).
  - Blameless incident reviews.
  - Quality made visible in CI: tests, perf budgets, a11y checks.
  - Learning in public: short internal talks, tool demos.
  - Career conversations: map their next level and find work that demonstrates it. (Mentoring vs sponsoring: sponsoring means putting their name forward for opportunities.)
- **Measure success by what others can do without you.**
- **Underperformance:** clear expectations, specific examples, a plan with checkpoints, early involvement of their manager.

## Mental model / flow
```
person: goals + gaps -> stretch assignment -> pairing on first hard bit -> ownership -> they teach others
team:   repeated review comment -> doc/lint rule -> CI check -> nobody needs to say it again
```

## STAR skeleton
- **Situation:** Who (level, anonymized), what gap or goal, and how it affected the team?
- **Task:** Why you were mentoring them (assigned, self-initiated)? What growth was the goal?
- **Action:**
  - How you learned what they needed.
  - The stretch assignment and the safety net.
  - The specific teaching moment (pairing session, review approach).
  - How you stepped back so they owned it.
  - The systemic change that came out of it (guide, lint rule, process).
- **Result:** What they could do afterwards (led X, wrote Y, promoted), team-level metric (flake rate, review turnaround, defects).
- **Learning:** e.g. turn repeat feedback into a mechanism; sponsor, don't just advise.

## Trade-offs & pitfalls
- All philosophy, no story.
- Hero mentoring: you remain the bottleneck for every review and decision.
- Nitpick-heavy reviews that teach style, not judgment.
- Taking credit for the mentee's result.

## Likely follow-ups
- **"How do you mentor someone more senior than you in one area?"** Peer exchange; you learn from them elsewhere.
- **"How do you handle someone not improving?"** Expectations, examples, plan, checkpoints, manager involvement.
- **"How do you scale mentoring across a large team?"** Mechanisms (docs, RFC culture, guilds), and mentoring mentors.
- **"How do you know it worked?"** Their independent outcomes and promotions; fewer repeated review comments.

## Say it in 60 seconds
Mentoring is tailored: I learn what someone wants and where they struggle, give them a stretch assignment slightly beyond them with weekly check-ins, pair on the first hard part, then step back and let them own and present it. Raising the bar is systemic: reviews that explain the why with labeled comments, repeated comments turned into docs or lint rules, RFCs and design reviews, blameless incident reviews, and quality checks visible in CI. A concrete example is the best proof: someone who avoided flaky tests, I paired on two failures, they owned a flake-reduction project, wrote our guide, and later led CI optimization. I measure success by what people can do without me.
