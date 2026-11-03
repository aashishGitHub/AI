# "Tell me about a time you disagreed with a technical decision"
**Round:** 15 · Leadership & Behavioral · **Level:** Senior · **Time:** 10 min · **Tags:** behavioral · conflict · disagreement
Source: https://whetstone-v1.vercel.app/#leadership-behavioral

They want judgment and collaboration, not a story where you were simply right.

## What they're really testing
Do you disagree with evidence and respect, seek the other side's constraints, propose a way to decide, and commit afterwards ("disagree and commit").

## Core answer (key points)
- **Separate decision from person;** start by understanding their reasoning and constraints you couldn't see.
- **Make the concern concrete:** performance, maintainability, consistency, timeline, not taste.
- **Escalation ladder:** 1:1 conversation first -> questions -> short written comparison with agreed criteria -> prototype/benchmark or time-boxed experiment -> decision owner decides.
- **Commit** once decided, even if it went against you, and help make it succeed.
- **Best endings:** a better combined outcome, or you visibly and graciously changing your mind on part of it.

## Mental model / flow
```
decision + stakes -> my concrete concern -> understand their need
  -> agree criteria -> evidence (doc / prototype) -> owner decides -> I commit -> outcome + learning
```

## STAR skeleton
- **Situation:** What was being decided, by whom, and what was at stake (perf, maintenance cost, deadline)?
- **Task:** Your role: reviewer, peer, lead? Why was it yours to raise?
- **Action:**
  - Your concern, stated concretely.
  - How you learned the other side's real need (the question you asked).
  - How you engaged: 1:1, comparison doc with criteria, prototype or benchmark.
  - How the decision was made and who owned it.
  - Where you were wrong or adjusted.
- **Result:** What was chosen, what happened after (bugs avoided, perf numbers, consistency), and the relationship afterwards.
- **Learning:** e.g. agree on criteria before debating options; ask "what do you need from X" before arguing about X.

Example outline to adapt (own paraphrase of a common pattern): a teammate wants all server data in a global store; you worry about re-implementing caching and invalidation; you ask what they need (shared access, devtools); you prototype the same screen with a query-cache library; criteria favor it; you concede a small client-only store for genuine workflow state.

## Trade-offs & pitfalls
- "I was right, they were wrong" stories read as low collaboration.
- Escalating to a manager before talking directly.
- Arguing in PR comments instead of a conversation.
- No commitment after the decision ("I still think...").
- Choosing a trivial disagreement (tabs vs spaces).

## Likely follow-ups
- **"What if they'd still disagreed?"** Decision owner decides with documented trade-offs; I commit and set a checkpoint to revisit with data.
- **"Have you ever been wrong in a disagreement?"** Have one ready.
- **"How do you disagree with someone more senior?"** Same process, more emphasis on evidence and their context.
- **"What did you learn about yourself?"**

## Say it in 60 seconds
I'd pick a disagreement with real stakes. I start by stating my concern concretely, then go 1:1 and ask what they actually need from their approach, because there's usually a constraint I haven't seen. Then I suggest how we decide: agreed criteria, a short comparison, and a small prototype or benchmark. The decision owner decides and I commit fully, even if it's not my option. My best example ended with a combined solution where I was right on the main point but wrong on one part, and I said so. The learning I carry: agree on criteria before debating options.
