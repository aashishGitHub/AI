# Evaluation in the time of LLMs

## Two Layers of Evaluation

- **LLM model evaluation** — how good is the raw model (benchmarks like MMLU, HumanEval).
- **LLM system/application evaluation** — how good is the whole app (prompts + tools + memory + routing), not just the model.
- System eval datasets come from: manual creation, automatic generation, or real-world synthetic data.

## Traditional Software Testing vs LLM Systems

- Traditional software = **deterministic**. Like a train on a track — fixed start/end, easy pass/fail checks.
- LLM systems = **non-deterministic**. Like driving a car in city traffic — variable environment, unpredictable behavior.
- Same prompt → different outputs each time.
- Metrics are often **qualitative** (relevance, coherence), not strict pass/fail.

## Common LLM Evaluation Types

- **Hallucination** — is it making things up vs. using given context?
- **Retrieval relevance** — are retrieved docs actually relevant?
- **Question answering accuracy** — does the answer match ground truth?
- **Toxicity** — harmful/undesirable language?
- **Overall performance** — is it hitting its goal?

## What Is an Agent?

- A software system that takes actions on a user's behalf using reasoning.
- Agent = LLM + ability to act (tools, APIs, capabilities). More complex than a plain LLM app.

### 3 Core Components of an Agent

1. **Reasoning** — powered by the LLM.
2. **Routing** — deciding which tool/skill to use.
3. **Action** — executing the tool call / API call / code.

### Example Agent Use Cases

- Personal assistant (notes, transcription)
- Desktop/browser automation
- Data scraping + summarization
- Research/search agents

## Worked Example: "Book a Trip to San Francisco"

1. Agent picks the right tool/API.
2. Calls search API, may ask follow-up questions, refines the request.
3. Returns a friendly, accurate response.

### How to Evaluate Each Step

- Did it pick the right tool?
- Did it call the function with correct parameters?
- Did it use context correctly (dates, preferences, location)?
- Is the final response correct tone + factually accurate?

## Things That Can Go Wrong

- Wrong tool selection (e.g., San Diego instead of San Francisco).
- Misusing context.
- Bad tone (snarky/inappropriate).
- Jailbreak attempts by users causing unexpected outputs.
- **Lesson**: must evaluate the *decision process*, not just the final LLM output.

## How to Evaluate Agent Behavior

- Human feedback / human-in-the-loop.
- LLM-as-a-judge (LLM evaluates the agent's output).

## Important Warning

- Small prompt/code changes can cause ripple effects.
- Example: adding "respond politely" may fix one case but break others (regression).
- **Solution**: keep a representative test set/dataset of critical use cases, rerun evals after every change.

## Iterative Testing Approach

- Agents are non-deterministic → can't rely only on deterministic checks.
- Need consistent test sets run on every change.
- Loop real production data (real user queries) back into development to refine prompts/tools.
- This catches regressions + expands test coverage over time.

## Tools Covered in the Course

- **Trace instrumentation** — see what's happening under the hood.
- **Eval runner** — includes LLM-as-a-judge.
- **Datasets** — for rerunning experiments.
- **Human feedback** — capture human annotations in production.
- **Prompt playground** — iterate on prompts/data.

## Lesson Takeaway

- Model eval ≠ system eval.
- LLM apps need different testing than traditional deterministic software.
- Agents add complexity: reasoning + routing + action.
- Common pitfalls: wrong tool choice, bad context usage.
- Iterative testing (same tools, dev → production) is key to keeping agents reliable.
