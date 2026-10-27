# Rubric — how a mock answer is scored

Used by [`MOCK-INTERVIEWER.md`](MOCK-INTERVIEWER.md). Also usable alone: record yourself, then score yourself strictly.

The thresholds below are **my own calibration**. DevRev has not published a scoring rubric for this loop (see the first lines of [`questions-answers.md`](questions-answers.md)). Do not quote them as DevRev's.

Lanes: **[P]** shipped at Couchbase · **[L]** your own build · **[K]** knowledge only. Ladder: 🟢 beginner · 🟡 intermediate · 🔴 senior ([`LEVELS.md`](LEVELS.md)).

## Scale

| Score | Meaning |
|---|---|
| 0 | Missing, wrong, or harmful. |
| 1 | Partial. Needs prompting. Vague. |
| 2 | Solid. Right without prompting. Some depth missing. |
| 3 | Senior. Unprompted depth, boundaries stated, tied to own evidence. |

Score each answer on six dimensions. Half points are not allowed. If torn between two scores, give the lower one.

## The six dimensions

### 1. Correctness

| Score | Anchor |
|---|---|
| 0 | Core claim is wrong, or a term is used with the wrong meaning (e.g. "exactly-once" as a guarantee you get for free). |
| 1 | Right idea, one real error or a missing key part. Terms used loosely. |
| 2 | Right. Terms used correctly. Misses one edge or detail. |
| 3 | Right and precise. Names the edge cases unprompted and gets them right. |

### 2. Flow of control and data

| Score | Anchor |
|---|---|
| 0 | Cannot say what calls what, or in which order. |
| 1 | Lists components. Order is fuzzy. Does not say where data is stored or copied. |
| 2 | Clear order of calls. Says what data moves at each step and where state lives. |
| 3 | Walks one request end to end. Names who owns the state, where it can be lost, and which step is replayed after a crash. |

### 3. Trade-offs and failure modes

| Score | Anchor |
|---|---|
| 0 | Gives one answer as if it has no cost. No failure named. |
| 1 | Names one failure only when asked. Gives a verdict, not a trade-off. |
| 2 | Names a failure unprompted and the cost of the choice. |
| 3 | Names several failures (duplicate, out of order, crash between two steps, timeout, overload). Gives the condition that would flip the choice. Says what the mitigation does not cover. |

### 4. Evidence from own code, with honest lane

| Score | Anchor |
|---|---|
| 0 | No example, or an example that is made up or not theirs. |
| 1 | Generic example, or names a file but cannot explain it. Lane missing or wrong. |
| 2 | Points at a real file or test, explains it without reading it line by line, and tags [P] / [L] / [K] correctly. |
| 3 | As 2, plus says how it is tested, quotes a measured number with its sample size, and says what the evidence does not prove. |

### 5. Honesty about limits

| Score | Anchor |
|---|---|
| 0 | Invents a number, a source, an API name, or claims lab work as production. |
| 1 | Over-claims by omission: no sample size, "I built" for something they only read or contributed to. |
| 2 | Says "I do not know" or "verify this" where true. No over-claims. |
| 3 | Volunteers the boundary before asked ("mock vendor", "n=5, one model", "never applied to AWS", "single process, no lease"). Separates built / contributed / read. |

### 6. Communication in plain spoken English

| Score | Anchor |
|---|---|
| 0 | Cannot be followed. Rambling, or only jargon. |
| 1 | Understandable but long, or jargon with no meaning given. Answer is buried. |
| 2 | Answer first, then reason. Defines a term the first time. Fits 60 to 90 seconds. |
| 3 | Answer first, one concrete example, trade-off in one sentence. A non-expert could follow it. Stops when done. |

## Level bars

What an answer must contain at each rung. The interviewer starts at the chosen rung and pushes down the ladder.

| Level | Rung | Must contain | Typical weak spot |
|---|---|---|---|
| Beginner | 🟢 | A plain definition with no undefined jargon. One everyday example. Says what problem it solves. | Jargon without meaning. |
| Mid | 🟡 | How it works in order. How **I** built it, with a real file. One failure mode. How it is tested. | Cannot explain own code without opening it. |
| Senior FDE | 🔴 | Clarifying questions first. Design under constraints. At least two failure modes and a trade-off with its flip condition. A measured number with its sample size. The boundary of the claim. A fix-now versus fix-properly split. | Gives a verdict, not a trade-off. No boundary. |

## Pass thresholds

Average = mean of the six scores, averaged over all scored answers in the session.

| Target | Pass when |
|---|---|
| Beginner pass | Average at least 1.5, and correctness is never 0 on a 🟢 question. |
| Mid pass | Average at least 2.0, no dimension below 1, and honesty at least 2 on average. |
| Senior pass | Average at least 2.3, no dimension below 2 on honesty, and no 🔴 answer scored under 2 on trade-offs and failure modes. |

"Broke at a rung" means two consecutive answers at that rung averaged below 1.5. The weakest rung per module is the highest rung where the user broke.

## Red flags that cap the score

A red flag overrides the average. One flag means the session cannot pass senior.

| Red flag | Cap |
|---|---|
| Invented number (a latency, a percentage, a count with no source) | Honesty 0 for that answer. Overall: no senior pass. |
| Lab work claimed as production ([L] said as [P]) | Honesty 0. Overall: no senior pass. |
| No failure mode named on a design answer | Trade-offs max 1. |
| Cannot explain how it is tested | Evidence max 1. Flow max 2. |
| Cannot say what the flow of control and data is | Flow max 1. |
| "I built" for code they only read or contributed to | Honesty max 1. |
| Invented API, library function, or spec detail stated as fact | Correctness 0 and honesty max 1. |
| Lane tag refused or dodged after being asked twice | Evidence max 1. |
| Claims "exactly-once", "100% safe", or "no data loss" with no condition | Correctness max 1. |

Check the repo's own "What not to claim" list at the end of each module (for example in [`modules/11-multi-agent-orchestration-and-durable-execution.md`](modules/11-multi-agent-orchestration-and-durable-execution.md)). Each line there is a ready-made red flag for that module.

## FDE-specific: customer-facing skills

The role is mostly customer work ([`README.md`](README.md) section 1). Score these in `scenario` and `customer role-play` modes. They are scored 0 to 3 like the other dimensions, and reported on the scorecard separately.

| Skill | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Clarifying questions first | Starts solving at once. | Asks one question after starting. | Asks 2 to 3 relevant questions before solving. | Asks about impact, scope, data, and "what does correct mean" before any fix, and states the assumption it chose when unanswered. |
| Explain to a non-expert | Jargon only. | Defines terms but too long. | Uses an analogy. Short. | Uses the customer's own words. Says what they can do next. No blame. |
| Scoping | Says yes to everything. | Lists tasks with no order. | Splits now / later and says what is out of scope. | Gives a thin first slice, the risk, how to measure success, and what will not be promised. |
| Handling the unknown | Guesses. | Hides it. | Says "I do not know yet". | Says what is unknown, how to find out, and by when. |
| Written follow-up | None. | Vague. | States cause, fix, owner. | States cause, fix, owner, next check, and what is still open. |

A senior FDE pass in role-play needs at least 2 on every row and 3 on "Clarifying questions first".

## Scorecard template

One row per answered question. Copy this table.

| # | Module | Rung | Q (short) | Correct | Flow | Trade-offs | Evidence + lane | Honesty | Plain English | Avg | Flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | 🟢 | | | | | | | | | |
| 2 | | 🟡 | | | | | | | | | |
| 3 | | 🔴 | | | | | | | | | |

Session summary:

| Module | Answers | Average | Rung where broke | Weakest dimension | Red flags |
|---|---|---|---|---|---|
| | | | | | |

| Customer skill (scenario / role-play) | Score 0-3 |
|---|---|
| Clarifying questions first | |
| Explain to a non-expert | |
| Scoping | |
| Handling the unknown | |
| Written follow-up | |

Verdict: beginner / mid / senior pass or not yet. Reason in one line. Re-read list: `modules/simple/NN-*.md` first for a basics gap, then the module phase, then `modules/scenarios/NN-*.md`.
