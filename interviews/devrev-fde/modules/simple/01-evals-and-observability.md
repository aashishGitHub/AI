# Module 01 in plain English: Evals and observability

> **Read this first**
> - **What it is for:** learning how to prove an AI feature works, keep it working, and report honestly when it does not.
> - **Who it is for:** a beginner. No repo knowledge needed. Every term is explained the first time it appears.
> - **Full version:** [01-evals-and-observability.md](../01-evals-and-observability.md) (the senior-level module with code and exact numbers).

Lanes used in this file:
- **[P]** shipped at Couchbase (the Ask AI system).
- **[L]** my own lab build on local models. Never shipped to customers.
- **[K]** knowledge only. I have read about it but not built it.

Almost everything measured here is **[L]**. The Couchbase **[P]** part is small: a manually run scoring script, a thumbs up/down store, tiered rate limits and a troubleshooting runbook. Say it like this out loud: "in production we did X, in my own build I went further and did Y."

Code lives in these places:
- [evals/promptfooconfig.yaml](../../../../evals/promptfooconfig.yaml) (the promptfoo test suite)
- [agent-lab/evals/](../../../../agent-lab/evals/) (the agent test harness)
- [fe-hands-on/server/stream.go](../../../../fe-hands-on/server/stream.go) (the server prompt and request logging)

---

## Phase 1 — Define quality and the golden dataset

**Analogy: a school exam.** A teacher does not judge a student on the three questions the student felt good about. The teacher sets a fixed exam, with answers, and uses the same exam every term. A golden dataset is that exam for your AI feature.

### Beginner points

**What is a golden dataset, and why have one before changing a prompt?**
- A golden dataset (a fixed list of test inputs, each with an expectation a machine can check) is rerun on every change.
- Without it, "it looks good" really means "it worked on the ten prompts I happened to try."
- In my promptfoo suite (a tool that runs prompts against checks), each row has a question, a context document, one or more assertions (checks), and tags.
- That suite has exactly two rows today: a happy path and an unanswerable question.
- So I call it a seed, not a benchmark.

**How do I define "quality" for a documentation assistant?**
- I split it into things I can name and check.
- Grounded means the answer only uses the context I supplied.
- If the context lacks the answer, the right behaviour is to decline, not to invent syntax.
- The answer should be actionable.
- In the shipped server prompt, the answer should cite sources by number.
- I pick checks from failures I have really seen. A quality definition nobody can test is just an opinion.

### Intermediate points

**What does one golden row look like, and what makes it good?**
- A good row has a realistic input, a pinned (fixed) context, and checks ordered cheapest first.
- My happy-path row asks how to create a primary index in Capella (Couchbase's cloud database).
- It points at a fixed context file. Its first check is a plain "contains this string" test.
- The second row asks about vector indexes, but the context only covers primary indexes.
- That row is deliberately unanswerable. A suite of only happy paths can never fail for the right reason.
- Rows have tags such as `grounding` and `negative`, so I can slice results later.
- The context is a file in the repo, so the row is reproducible and reviewable in a pull request (a proposed code change).

### Senior points

**How do I stop a golden set from giving false confidence?**
- Three problems: it does not match real traffic, it gets tuned against until it is contaminated, and it rots as the product changes.
- Fix one: seed it from real queries and every production incident.
- Fix two: keep held-out cases (tests you write before measuring any fix, and never tune against).
- Fix three: version the set like code, with an owner.
- The agent harness has 17 cases: 13 golden and 4 held-out. The held-out ones were written before the fixes were measured.
- The weakness: I wrote all 2 promptfoo rows and 17 agent cases myself. None came from real user logs.
- I have not measured how well either set matches real traffic.
- The held-out case file has a description saying it was written before any fix was measured. That is what lets me later tell a real fix from overfitting (fitting one phrasing, not the general problem).

**How many cases do I need?**
- I do not have a verified number. Anyone quoting one without knowing the effect size is guessing.
- My interview notes have planning ratios: roughly 40% happy path, 25% edge, 20% adversarial, 15% regression, starting at 30 to 50 cases.
- Those are planning figures I wrote. I did not measure them.
- Small samples tell you little. With a Wilson 95% interval (a way to show the uncertainty around a pass rate) that I computed:
  - 5 passes out of 5 is still consistent with a true pass rate as low as about 57%.
  - 0 failures out of 10 is consistent with a true failure rate up to about 28%.
- So I size the set by the decision it gates, and I report the interval, not just the pass count.
- The formula is my own helper, not from the repo. Verify it in a statistics reference before using it in a report.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Golden dataset | Fixed test inputs with machine-checkable expectations, rerun on every change. |
| Assertion | One automatic check on an output. |
| Grounded | The answer uses only the context given. |
| Held-out case | A test written before measuring a fix, kept away from tuning. |
| Overfitting | Fixing one phrasing, not the real problem. |
| Seed | A small starter set, not a benchmark. |
| Wilson interval | A range showing how uncertain a pass rate is on a small sample. |

**Say it in one breath:** A golden dataset is a fixed exam with checkable answers, and mine is only a small self-written seed, so I report the uncertainty and not just the pass count.

---

## Phase 2 — Deterministic checks first

**Analogy: a spell-checker before an editor.** A spell-checker is free, fast and always agrees with itself. You run it first. You only pay a human editor for what the spell-checker cannot see.

### Beginner points

**What is a deterministic check, and why run it before an LLM judge?**
- A deterministic check (a rule with no model inside, giving the same answer every time) is cheap.
- Examples: "the answer contains this string", "this parses as JSON", "this forbidden text is absent".
- It costs nothing and cannot be fooled by fluent prose.
- In my first measured run, the judge used about 901 grading tokens. The answer it judged was 278 tokens. That is roughly 3.2 times the generation cost.
- That was one case with one judge, so it is an order of magnitude, not a benchmark.
- It is why a cheap rule goes first.

### Intermediate points

**What rules are in my suite, and why does each exist?**
- Rule one: a required string, `CREATE PRIMARY INDEX`, because the happy path must contain it.
- Rule two: a `not-contains` guard for a wildcard form that appears nowhere in the context.
  - I wrote it because the 1B model really produced that form, and the judge scored it faithful.
  - A cheap string rule caught the bug the expensive judge missed.
  - That is what a regression guard is: a cheap rule pinned to a failure I actually observed.
- Rule three: on the unanswerable row, assert that a refusal is present, using a closed list of decline phrases.
- I did not use "bad string is absent" there. My first attempt did, and it passed while the model invented different wording.
- Why a list? There are few ways to decline and infinite ways to hallucinate (make things up). So I match the small set.

### Senior points

**What do deterministic checks miss?**
- Rules are exact but brittle.
- A refusal phrased outside my eight listed phrases would be a false failure.
- A rule can never judge "is this faithful?"

**How did I avoid grading the agent's words and not what happened?**
- The failure mode for agents is different. A model can say "done, alert acknowledged" without calling the tool.
- So in the agent harness, the outcome is read from the server's state file, not from the model's claim.
- Safety is derived from the tool records.
- The scorer takes `state` as a separate input from `run`. The text checks are the last lines of the function.
- I have a test where the model claims an action that never happened. It fails on both the missing tool call and the state check.
- The boundary: this proves the scorer is not fooled by words. It says nothing about how often a real model makes that claim.

**Why a list of decline phrases, not one exact string?**
- Both the shipped and eval prompts tell the model to reply with one exact sentence. An exact match would be the tightest rule.
- I used a tolerant list because a 1B model (a very small model, one billion parameters) may paraphrase.
- I would rather accept a legitimate decline than fail correct behaviour.
- The cost is a slightly weaker check. Any of the eight phrases could also appear inside a fabricated answer.
- I did not measure how often `llama3.2:1b` emits the exact string versus a paraphrase.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Deterministic check | A rule with no model; same input gives same result. |
| Regression guard | A cheap rule pinned to a failure that really happened. |
| Hallucination | The model invents facts that are not in the context. |
| State check | Reading the real system to see what changed, not trusting the model's words. |
| Brittle | Breaks easily when the wording changes slightly. |
| Token | A small chunk of text a model reads or writes; used for counting cost. |

**Say it in one breath:** Run free rules first and check what really changed in the system, because words can lie and a judge costs about three times the answer.

---

## Phase 3 — LLM-as-judge and calibrating the judge

**Analogy: a referee in a match.** A referee must not be on one of the teams, and must apply the same rules every game. If the referee is biased or moody, the scores mean nothing. You must test the referee, not just the players.

### Beginner points

**What is LLM-as-judge, and what is the first rule?**
- LLM-as-judge means a second model grades an output against a rubric (a written scoring guide).
- It lets me score things like faithfulness that no regex (a text pattern) can express.
- Rule one: use a different model, ideally a different family, from the one under test. A model tends to rate its own style generously.
- Rule two: pin the judge, with temperature 0 (no randomness) and a fixed model. Then a score does not move for reasons unrelated to my product.
- In my suite the system under test is `llama3.2:1b` and the judge is `qwen2.5:3b`.

### Intermediate points

**How is the judge configured, and how is a rubric phrased?**
- The judge is set once in `defaultTest`, so every assertion shares it. It uses temperature 0 and forced JSON output.
- A comment in the config records why the model was swapped.
- The rubric is the part people get wrong.
- promptfoo's grader asks whether the rubric statement is true of the output.
- So I write the rubric as a claim about the output, not as an instruction to the judge.
- I use `llm-rubric` and not `g-eval`. My reading of promptfoo source is that g-eval extracts the judge's JSON with a pattern that fails on multi-line JSON, which Ollama's JSON mode emits.
- Verify that g-eval versus llm-rubric difference in current docs before saying it in an interview.

### Senior points

**Did I calibrate the judge?**
- No. I isolated it. I say the difference out loud.
- Isolation means holding the input fixed and changing only the judge.
- Failure one, a false pass: an instruction-style rubric made both `qwen2.5:1.5b` and `3b` score a fabricated answer as correct 0 of 5 times (meaning they wrongly judged it).
- The same claim rewritten as an assertion about the output got 5 of 5 on both. So model size was not the cause.
- Failure two, a false fail on 2026-09-07: graded against a fixed correct refusal, at temperature 0, 3 runs.
  - The 1.5b judge said "fail" every time, while its own reason agreed there was no SQL statement.
  - The 3b judge said "pass" 3 of 3. So I swapped to 3b.
- Real calibration (checking the judge against humans) means a hand-labelled batch plus a judge-versus-human agreement score. I have not done that.
- The honest status is "no disagreements yet on 2 cases", not "the judge is trustworthy."
- Cohen's kappa (agreement beyond chance) is what the missing step would use. My sketch is not run on my data.

**What does it tell me that the judge passed fabrications, then failed a correct refusal?**
- Two cases were never enough.
- My reading: the first set let the judge be wrong in only one direction. The 1B model was fabricating, so there was no correct refusal to grade.
- The inversion stayed hidden until a prompt fix made the model refuse.
- I read that ordering from commit dates and notes. Verify it in git history before relying on it.
- The fix I would make: a labelled set with both polarities per rubric (correct declines and fabrications).
- Also a rule: every judge or rubric change reruns the fixed-input isolation test.
- I pin the judge by model tag, `qwen2.5:3b`. I have not verified a tag is immutable. For anything that gates a release, I would pin by digest (a content hash).

### Words you'll hear

| Term | One-line meaning |
|---|---|
| LLM-as-judge | A second model that grades an output against a rubric. |
| Rubric | The written scoring guide the judge uses. |
| Self-preference bias | A model rating its own style too kindly. |
| Temperature 0 | Settings that remove randomness from output. |
| Isolation test | Hold the input fixed, vary one thing, see if the result changes. |
| Calibration | Proving the judge agrees with human labels. |
| Polarity | Both directions: correct answers and wrong answers. |

**Say it in one breath:** I checked my judge by holding the input still and swapping the judge, but I never compared it to human labels, so I call it isolated and not calibrated.

---

## Phase 4 — The CI regression gate

**Analogy: a security checkpoint at an airport.** There is a quick metal detector for everyone, then a slower bag scan only for those who pass the first. Nothing reaches the plane without passing. The cheap check runs first so the slow one is not wasted.

### Beginner points

**What is a CI regression gate for an LLM feature?**
- CI (continuous integration) is a robot that runs checks on every code change.
- A regression gate is an automated check on every pull request touching the prompt or the eval. It turns a regression (something getting worse) into a red build, not a production surprise.
- Prompt changes are non-deterministic behaviour changes. Without a gate, every prompt tweak is an unreviewed deploy.
- I run two tiers, because they cost different amounts:
  - Tier one: a free parity check with no model.
  - Tier two: the golden set against local Ollama models (Ollama runs models on your own machine).

### Intermediate points

**What is the parity tier?**
- Parity asks: "is my eval grading the prompt the server actually ships?"
- The script uses a regular expression to pull the bullet rules out of the Go `groundedSystemPrompt` constant.
- It asserts each rule appears in the eval prompt, after normalising case and whitespace.
- If someone adds a rule to the server and forgets the eval, CI fails in seconds, with no model and no network.
- One rule, citing by `[n]`, is on an explicit exemption list with a written reason. The eval contexts are one unnumbered document, so there is no `[n]` to cite.
- The server prompt is the source of truth. The eval derives from it.
- The workflow says `needs: parity`, so the expensive tier runs only when the cheap one is green.
- When I ran the script on 2026-10-20, it reported 4 server rules, 1 exempted, and parity OK.

### Senior points

**What are the gate's weaknesses?**
- Trade-off: cost against signal. Parity is cheap and exact. The model tier is slow and can be red for a real, expected reason.
- The model tier uses absolute assertions and no baseline. The negative case is red whenever the 1B model fabricates. My notes put that at 5 of 6 runs.
- A gate that is always red teaches people to ignore red. The workflow comment says a red run is not automatically a merge blocker. That is the weakness.
- Hardening plan:
  - Make the deterministic tier block merges.
  - Make the judge tier only warn until it is calibrated.
  - Compare to a baseline, with a tolerance.
- Supply-chain gaps (risk from unpinned outside tools): the workflow installs Ollama with `curl | sh`, runs `promptfoo@latest`, and pulls models by tag.
- The exemption list is a hole in the parity guarantee that I wrote down on purpose.
- promptfoo exits with code 100 on a failed assertion. I verified that locally on 2026-09-07, not on a runner.
- As of the notes dated 2026-09-07, the workflow had passed locally but had not run on a real GitHub Actions runner. Verify before claiming otherwise.

**How would I make the gate regression-relative, not absolute?**
- Store per-case pass rates from the last green main run.
- Run each case several times.
- Fail only when a case drops below its baseline by more than a tolerance, set from observed variance.
- Keep a small set of absolute must-pass rules (the deterministic ones). A baseline can ratchet down silently.
- A missing case counts as zero, so deleting a test cannot hide a regression.
- With n of 5 or 10 per case, the tolerance must be wide. So the gate catches big regressions, not small ones.
- This is my sketch. I have not wired it into the repo.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| CI | A robot that runs checks on every code change. |
| Gate | A check that must pass before a change can merge. |
| Parity | The eval and the shipped prompt carry the same rules. |
| Baseline | The last known-good result to compare against. |
| Tolerance | How much worse is allowed before failing. |
| Supply-chain risk | Trouble from unpinned outside tools or downloads. |
| Exit code 100 | promptfoo's signal for "an assertion failed". |

**Say it in one breath:** I run a free parity check then a model eval on every prompt change, but my gate has no baseline and has never run on a real CI runner.

---

## Phase 5 — Agent and trajectory evals

**Analogy: judging a driving test.** You do not only ask whether the driver arrived. You watch the route, the signals, the mirror checks and the speed. A trajectory is the route. The outcome is where the car actually ended up.

### Beginner points

**How is evaluating an agent different from evaluating one answer?**
- An agent is a model that can call tools in a loop.
- With one answer, I grade one piece of text against its context.
- With an agent, I grade the path: which tools, which arguments, what order, how many steps.
- Then I grade the effect: what actually changed in the system.
- The final text can look fine while the process was wrong. For example, it guessed a tenant id (a customer account id) or called a write tool it should not have.
- I score selection, arguments, safety, outcome and step budget as separate checks. One pass/fail bit would hide which one broke.

### Intermediate points

**What does a trajectory case look like, and how is it scored?**
- A case is a YAML file (a plain-text config file). It holds a prompt, the expected tool sequence with argument matchers, forbidden tools, final-text expectations, and a scripted trajectory for the deterministic mode.
- One example: no tenant is named, so the right move is to call no tool and ask.
- The scorer returns a `CaseScore` with selection, args, safety, outcome and budget checks. A case succeeds only if none is false.
- Case files load strictly. A typo in a key raises an error at load time, not a silently dropped check.
- `args` is `Check(None)` when a case has no argument expectations. So "not checked" is different from "passed".
- Efficiency is a separate number from success.

### Senior points

**How do I know the harness is not green by construction?**
- A checker that has never failed proves nothing.
- So I feed deliberately wrong trajectories through the real loop, the real MCP server and the real scorer. I pin the exact failure string.
- MCP (Model Context Protocol) is a standard way for models to call tools on a server.
- My notes list 18 wrong trajectories plus a control. The test file has 21 test functions, as I counted on the day I wrote the module.
- I also did a manual mutation check in a scratch copy. With the approval gate removed, the deterministic suite went to 13 runs, 85% task success and 2 safety failures.
- On 2026-10-20 I reran the deterministic suite: 17 of 17 passing, 0 safety failures.
- An invented tenant id never reaches the server (a guard blocks it), yet the case still fails the eval by design.
- The boundary: the scripted model replays fixed turns and does not react to tool results. So deterministic mode proves plumbing, guardrails and scoring. It does not prove a real model chooses well.

**Why does the deterministic suite gate a merge and the live suite only report?**
- Deterministic answers "is the plumbing right?" That is binary.
- Live answers "how does this model behave?" That is a distribution, and would make CI flaky.
- The workflow file runs pytest plus the deterministic suite. The live (Ollama) mode is report-only and not run in CI.

**Pass@k or pass-rate for an agent?**
- Pass-rate is successes divided by runs.
- Pass@k is the chance at least one of k samples succeeds. It answers "can it ever do this?"
- My code uses the unbiased estimator I recall from Chen et al. 2021 (the Codex paper). That citation is from memory. Confirm before quoting.
- For agents that take actions, consistency matters. I would report the chance all k samples succeed.
- The tau-bench paper (arXiv 2406.12045, verified 2026-10-20) calls this pass^k.
- Example: a case at 4 of 5 with k of 3. Pass@3 is 1.0. The all-succeed figure is 0.4.
- With n of 5, any of these is a tiny sample.
- My all-k-succeed sketch is not from the repo. Check its definition in the paper before presenting it.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Agent | A model that calls tools in a loop to finish a task. |
| Trajectory | The path: which tools, args and order the agent used. |
| Outcome | What actually changed in the system. |
| Scripted LLM | A fake model that replays fixed turns, for deterministic tests. |
| Mutation check | Break the code on purpose to see if a test notices. |
| Pass@k | Chance at least one of k tries succeeds. |
| Pass^k | Chance all k tries succeed. |

**Say it in one breath:** For agents I score the route and the real effect separately, and I proved the scorer can fail, but a scripted model cannot prove a real model chooses well.

---

## Phase 6 — Online evaluation, observability, drift, cost and latency

**Analogy: a restaurant after opening day.** Tasting the menu in the kitchen (offline) is not the same as watching real diners, reading comments and counting wasted plates (online). You need both.

### Beginner points

**Offline versus online evaluation?**
- Offline runs a fixed golden set before deploy. It answers "should this change ship?"
- Online looks at sampled real traffic after deploy. It answers "is what shipped still good?"
- Offline is bounded by what I imagined. It cannot see:
  - query distribution shift (users asking different things over time),
  - corpus or provider changes,
  - long-tail inputs (rare odd inputs),
  - real user dissatisfaction.
- I need both. My local rig only has the offline half plus structured logs.

### Intermediate points

**What does the Agent Console log per request?**
- The Go server logs structured JSON (log lines a machine can parse).
- Fields: question length, number of turns, chunks retrieved, retrieval time in milliseconds.
- At the end: prompt tokens, completion tokens and total latency.
- It logs a distinct line when the client disconnects or generation fails.
- Retrieval failure is loud. It does not fall back to an ungrounded answer.
- The health endpoint reports dependency health. With the Ollama provider, a server that cannot reach its model returns 503 and `degraded`, not "ok".

**What does the agent harness record?**
- A JSONL audit file per run (one JSON object per line).
- It has a run id, a sequence number, and one event per model turn and tool call. It includes latency and error kind.
- This is structured logging, not distributed tracing (following one request across many services).
- I have not wired OpenTelemetry or Phoenix.
- A per-run audit file is how I read why a live case failed, instead of trusting the badge.
- These log fields are the raw material for cost, latency and quality questions.

### Senior points

**How would I design the online half for a production RAG assistant?**
- RAG (retrieval-augmented generation) means fetching documents and giving them to the model as context.
- Model each request as a trace with spans (timed steps) for retrieval and generation.
- Carry token counts, latency, time to first token, and prompt and model versions as attributes. Then I can tie a complaint to a cause.
- Mine free implicit signals on all traffic: thumbs, retries, abandons.
- Send only a small sample to an asynchronous judge. Judging costs tokens, and I measured it at about 3.2 times generation on one case.
- Sample by hashing the request id, so the same request is always in or out and I can replay it. The 5% figure is a planning number I would tune to the judge budget.
- Cheap deterministic guards run inline: schema, secret patterns, token caps. Anything model-graded runs asynchronously.
- Watch three drifts separately: input distribution, sampled quality, and cost per request. Each is compared to a rolling baseline.
- My local numbers are one sample each, on a CPU-only container:
  - A grounded answer took 4.94 s to first token, with 128 completion tokens.
  - A refusal took 0.90 s with 9 completion tokens. That is about 14 times cheaper.
- Token counts are exact because the server reports them. Wall times are not repeatable. None of it transfers to a GPU or multi-tenant setup.
- **[P]** The Couchbase Ask AI design adds tiered limits (per tenant, per user, tokens per month), a feedback store and a runbook. Verify those figures in the design document before quoting.

**It is 2 AM and answer quality dropped silently. What do I do?**
- First detect it with a quality proxy: thumbs-down rate or sampled judge score breaching a rolling baseline. Nothing throws an exception when answers merely get worse.
- Then triage cheap causes:
  - Did the provider model version change?
  - Did the re-embed job fail?
  - Did latency or retrieval counts change?
- Next, trace a few bad requests. Was retrieval empty, or was generation unfaithful?
- Then roll back to a pinned prompt or model version.
- The shipped **[P]** Ask AI runbook localises a failure by plane: source pages, then collections, then returned chunks. That comes from the design document.
- I have not run this runbook against a real incident. My lab has no alerting at all.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Online eval | Judging sampled real traffic after deploy. |
| Drift | A slow change in inputs, quality or cost over time. |
| Trace / span | One request's full path / one timed step inside it. |
| Structured log | A log line a machine can parse, as JSON. |
| Time to first token | Delay before the first word of the answer appears. |
| Implicit signal | Free feedback like retries or abandons. |
| Runbook | Step-by-step guide for handling a known problem. |

**Say it in one breath:** Offline tests cover what I imagined, so I log structured data, sample real traffic for a judge and watch drift, but my lab only has the logs.

---

## Phase 7 — Debugging failures and honest reporting

**Analogy: a doctor reading the test result.** A red flag on a lab report is not a diagnosis. The doctor reads why it is red, rules out a faulty machine, then treats one cause at a time.

### Beginner points

**An eval case goes red. What do I do first?**
- Read why it failed. Do not trust the badge.
- For promptfoo, write results to JSON, because the table truncates output and hides the per-assertion reason.
- For the agent harness, open the per-run audit log to see the real tool calls.
- A red result can be a real model failure, a bad rule, a bad rubric, or a broken judge. The fix differs for each.
- I decide which it is before I change anything.

### Intermediate points

**What bug did my eval find?**
- On 2026-09-07, the "must decline" case failed on the eval path. The server answered the same question correctly with the same model.
- The cause was two different prompts. The eval prompt said "use only the context" but gave no permitted alternative.
- The server prompt supplies an exact refusal sentence. So the server could decline and the eval could only invent.
- The fix was one sentence of prompt, plus the parity check so they cannot drift again. It was not a bigger model.
- The quote I use: "A prohibition without a permitted alternative is not a constraint, it is a trap."
- Then the judge still marked the correct refusal as a fail. I isolated that separately by fixing the output and varying only the judge.
- I call these Bug 1 and Bug 2 so I never blur them.
- After both fixes, the 1B model complied about 1 time in 5 across 6 runs. That is order of magnitude only.

### Senior points

**Two live agent cases failed. What did I try, learn and report?**
- Setup: `qwen2.5:3b` on CPU, 5 runs of 12 cases. That is 60 runs in about 13 minutes.
- Results: 82% task success, 92% tool selection, 90% argument accuracy, 0 safety failures.
- Two cases scored 0 of 5:
  - The model invented a tenant id instead of asking.
  - It explained the suppressed alert (a symptom) instead of the firing root cause.
- I changed one thing at a time. I measured the target case plus held-out cases at n of 10.
- Failure one (invented tenant): nothing fixed it.
  - One prompt example scored 10 of 10 on one held-out case and 0 of 10 on its sibling.
  - That is the signature of overfitting to a phrasing. So I did not claim it.
- Failure two (wrong alert): adding a `startHere` list to the tool result raised one held-out phrasing from 1 of 10 to 10 of 10.
  - But the target stayed 0 of 10 with a changed failure. A second held-out case stayed 0 of 10.
  - That change also deviates from the Java server contract.
- The honest report: "not fixed, one model, n of 10, no final regression run."
- A grounded-argument guard (the executor refuses an id not seen in the prompt or an earlier tool result) is a safety control, not a quality fix. An invented id never reaches the server, but the model still fails the eval by design.
- `injection_resisted` scored 5 of 5. That is the model resisting. In all 5 audit logs no write was attempted. So the approval gate was never exercised live.

**Why not ship the change that scored 10 of 10 on a held-out case?**
- One held-out win next to a sibling stuck at zero is evidence of fitting a phrasing, not of a general fix.
- A held-out set only works if I look at all of it and do not keep the cases that agree with me.
- The target case did not move. It was one model, n of 10. I never ran the final regression over all cases, so I cannot say it broke nothing else.
- A negative result stated clearly is useful to a customer. It shows where the model needs a human or a different design.
- I would offer exactly that sentence, plus the table, in a customer review.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Negative result | An honest report that a fix did not work. |
| Prompt injection | Text in the input that tries to give the model new orders. |
| Approval gate | A step that needs human approval before a write action. |
| Regression run | Rerunning all cases to see nothing else broke. |
| n=10 | Ten runs per case; a small sample. |
| Audit log | A record of every model turn and tool call. |

**Say it in one breath:** When a case fails I read the reason, change one thing at a time, and report a fix that did not work as "not fixed" with the sample size.

---

## Mix-ups to avoid

- **Isolated is not calibrated.** Isolation holds the input fixed. Calibration compares the judge to human labels. I only did the first.
- **Offline is not online.** A golden set before deploy does not watch real traffic after deploy.
- **Words are not outcomes.** An agent saying "done" is not proof the state changed. Check the state.
- **Deterministic suite is not a model test.** A scripted model proves plumbing and scoring, not that a real model chooses well.
- **A held-out win is not a fix.** One lucky case beside a stuck sibling is overfitting.
- **Logging is not tracing.** I have structured logs, not OpenTelemetry or Phoenix.

---

## What I built vs what I only know

**Built, my own lab [L] (never shipped to customers):**
- A promptfoo suite with 2 golden cases, a parity gate and an agent harness with 17 cases. All self-written, all seeds, not benchmarks.
- The judge is isolated, not calibrated. There is no hand-labelled batch and no agreement score. Both local judges are small models.
- Every model result is one model family and size: `llama3.2:1b` as system under test, `qwen2.5:3b` as judge and as live agent. Samples are n of 5 or 10 per case.
- Local latency and token numbers are single samples on a CPU-only container. The 1-in-5 compliance rate is 6 runs.
- The deterministic agent suite uses a scripted model. The approval gate was never exercised live.
- The `startHere` change for the chain case is not a fix and deviates from the Java server contract.
- Do not say "CI eval gates in production". As of the 2026-09-07 notes, the gate had passed locally and had not run on a real GitHub Actions runner.

**Shipped at Couchbase [P]:**
- The Ask AI system's eval is a manually triggered script. It scores answers with cosine similarity plus a GPT-4 classifier in a Google Sheet.
- It also has a thumbs up/down feedback store, tiered rate limits and a troubleshooting runbook. These come from the Ask AI design document. Verify figures before quoting, and do not claim authorship of what the docs do not mark as mine.

**Knowledge only [K]:**
- No tracing, alerting, online judge or drift monitoring exists in the lab. Phoenix was not wired, and its port and instrumentation are unverified.
- The pass@k citation (Chen et al. 2021) is from memory. Confirm before quoting. The tau-bench pass^k attribution was verified against arXiv 2406.12045.
- The g-eval versus llm-rubric difference is from my reading of promptfoo source. Verify in current docs.
