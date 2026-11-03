# Influence without authority: aligning several teams on a frontend platform change
**Round:** 15 · Leadership & Behavioral · **Level:** Principal · **Time:** 12 min · **Tags:** behavioral · influence · stakeholders
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

Scenario: you want ten teams (none report to you) to adopt new build tooling, a design system and lint rules.

## What they're really testing
Whether you can make a change in other teams' interest, lower adoption cost to near zero, and make the decision durable through org mechanisms, while giving credit away.

## Core answer (key points)
- You can't order adoption, so **make it in their interest.**
- **Playbook:**
  1. **Listen first:** interview teams about pain; write the problem statement in their words.
  2. **Evidence:** incidents, metrics, survey data showing the cost of the status quo.
  3. **Prototype** in a real product area; a working slice beats a deck.
  4. **Early adopter:** one respected team, with your hands-on help; publish before/after.
  5. **Make it cheap:** codemods, templates, docs, office hours, migration pairing.
  6. **Formalize:** RFC/ADR, platform roadmap and team OKRs, deprecation timeline for the old way.
  7. **Measure and report honestly:** adoption %, outcomes; thank teams publicly.
- **Resistance:** find the real constraint (deadline, risk, missing feature), address it or schedule them in a later wave; escalate only through the agreed process and with data.
- **Champions** inside each team spread it faster than you can.

## Mental model / flow
```
interviews -> evidence -> prototype -> pilot team succeeds -> public results + champions
  -> RFC/ADR + roadmap/OKRs -> tooling makes it cheap -> waves of adoption -> honest metrics
```

## STAR skeleton
- **Situation:** How many teams, what inconsistency or pain (duplicate requests, inconsistent states, build times)? Why did nobody own it?
- **Task:** What you set out to change, and the fact you had no authority over the teams.
- **Action:**
  - Who you interviewed and the pain you heard.
  - The data you gathered.
  - The prototype/package you built and the pilot team you chose (why them).
  - How you made adoption cheap (codemod, generated hooks, pairing).
  - How you formalized it (RFC, guild, OKRs) and handled the most resistant team.
- **Result:** Adoption % over time, outcome metric on adopted surfaces (bugs, duplicate requests, build time), credit given to whom.
- **Learning:** e.g. start with interviews, not a solution; pilot success is the best argument.

## Trade-offs & pitfalls
- Leading with your solution before understanding their pain.
- Mandate via a VP too early: compliance without buy-in, quiet forks later.
- Adoption cost left on the teams ("here's the docs, migrate yourselves").
- Vanity adoption metrics (installed but unused).
- Taking credit instead of spotlighting the pilot team.

## Likely follow-ups
- **"What if a key team refuses?"** Understand the blocker, offer help or a later wave, document the exception and its cost.
- **"How did you pick the pilot team?"** Respected, motivated, real use case, low-risk surface.
- **"How did you measure success?"** Adoption by static import analysis plus outcome metrics on adopted areas.
- **"When would you escalate?"** When the cost of inconsistency is proven and a decision deadline is missed; through the agreed process.

## Say it in 60 seconds
Without authority, I make the change in each team's interest. I start by interviewing teams so the problem statement is in their words, gather data on what the status quo costs, and build a working prototype in a real product area. Then I get one respected team to adopt it with my hands-on help and publish their before-and-after. I make adoption nearly free with codemods, templates, docs and pairing, and make the decision durable through an RFC, the platform roadmap and team OKRs, with a deprecation timeline for the old way. Resistant teams get their real constraint addressed or a later wave. I report adoption honestly and give the credit to the teams that adopted.
