# Prompts for free Claude / Gemini

Always paste your context first: your master resume (kept in your personal Google Drive, not in this repo) or the variant you're editing.
Hard rule in every prompt: **"Do not invent facts, numbers, titles or tools. Use only what's in the resume. Mark anything you'd add as [ASK ME]."**

## P1 — Tailor a resume to a JD
```
You are a senior tech recruiter for Staff/Senior frontend roles in Bengaluru.
Here is my resume (source of truth) and a job description.
1. List the JD's top 10 requirements in order of weight.
2. For each one: do I have evidence in the resume? (yes / partial / no — quote the line)
3. Rewrite ONLY my header line, summary (max 70 words) and the order of my first 3 Couchbase bullets to match.
4. List the JD keywords I can honestly add to Skills.
Do not invent facts, numbers, titles or tools. Mark anything new as [ASK ME].
RESUME: <paste>
JD: <paste>
```

## P2 — Behavioural mock (Amazon LP style)
```
Act as an Amazon bar raiser for an SDE III frontend role. Ask me one Leadership Principle question at a time.
After each answer: score 1-4, say what was missing (scope? metric? my own actions vs the team's?), then ask one follow-up probe.
Do 5 questions. Don't be polite; be precise.
```

## P3 — Frontend system design interviewer
```
You are a staff frontend engineer at [Atlassian/Microsoft/Google] interviewing me for a senior frontend role.
Question: "Design [a cloud control-plane console / an AI chat UI with streaming and tool-call approvals / a data grid with 100k rows]".
Run it as a real 45-minute interview: let me drive, interrupt with realistic probes on rendering strategy, state, performance (LCP/INP), a11y and failure modes.
At the end, score me on: requirements, architecture, data/API, performance, trade-offs. Give the 3 things a strong hire would have said that I didn't.
```

## P4 — RAG / evals deep dive
```
Quiz me like an AI-product interviewer on: chunking, hybrid search, re-ranking, recall@k, faithfulness, LLM-as-judge bias, CI eval gates, hallucination debugging, streaming latency.
One question at a time, harder each time. Correct me with specifics. If you're not sure about a tool's API, say so.
```

## P5 — DSA coach (practice only — never in a real interview)
```
Give me one medium LeetCode-style problem on [sliding window]. Don't give hints unless I say "hint".
When I paste my solution: check correctness, edge cases, complexity, then show a cleaner version and name the pattern.
```

## P6 — Offer comparison
```
Compare these offers on year-1 cash, 4-year total, vesting schedule, level, and risk. Ask me for any missing numbers instead of assuming.
<paste offers>
```

## P7 — Referral message
```
Rewrite this referral ask for [Name], who I worked with at [Company] in [year]. Keep it under 90 words, warm and specific, with the req ID and link. Don't add facts.
<paste template from 04_OUTREACH_and_NEGOTIATION.md §1>
```
