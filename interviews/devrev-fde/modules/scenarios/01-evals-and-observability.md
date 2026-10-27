# Scenarios 01 — Evals and observability

Source module: [`../01-evals-and-observability.md`](../01-evals-and-observability.md). Six real-time situations an FDE meets, laddered 🟢 🟢 🟡 🟡 🔴 🔴.

How to use: read only the **Situation**, answer out loud, then compare. Every number in a Situation is an **example** to make the story concrete, not a measurement from my repo. Numbers that are real (from my lab) are marked "from my notes".

Lanes: **[P]** shipped at Couchbase · **[L]** my own lab build, never deployed to a customer · **[K]** knowledge only, not built.

| # | Level | Failure mode |
|---|---|---|
| 1 | 🟢 | The eval grades a different prompt than the server ships |
| 2 | 🟢 | The LLM judge passes an answer a regex would have caught |
| 3 | 🟡 | The judge itself is wrong (a correct refusal scores as a fail) |
| 4 | 🟡 | The agent says "done" and nothing changed |
| 5 | 🔴 | The customer review: small-n live results and a tempting "fix" |
| 6 | 🔴 | Silent quality drop in production at 2 AM |

---

## Scenario 1 🟢 The negative case is red in CI, but the server answers correctly

**Situation.** Tuesday 10:40, a docs-team pilot at a customer (example). The "must decline" row of the golden set fails on the eval path: the model invents a `CREATE VECTOR INDEX` statement. A teammate asks the same question against the running server with the same model and it replies "The provided documentation does not cover this." (example). Nobody changed the model.

**Level.** 🟢 Beginner.

**What's being tested.** Whether I know an eval is only evidence about the thing it grades. If the eval prompt is not the shipped prompt, a red or green result says nothing about production.

**Clarifying questions to ask first.**
1. Is the eval using the same prompt text as the server, or its own copy?
2. Did either prompt change recently, and who owns each?
3. Same model, same temperature, same context for both runs?
4. Is the failure reproducible, or one flaky run?

**Flow of control and data.**

```
golden row (question + context file)
   └─▶ promptfoo ──▶ evals/prompts/answer.txt ──▶ model ──▶ asserts ──▶ red/green
user question
   └─▶ /api/chat ──▶ groundedSystemPrompt (Go const) ──▶ model ──▶ answer
                      ▲ two different prompts: the eval can drift from the server
```

**Diagnosis steps.**
1. Write the promptfoo results to JSON and read the per-assertion reason. The table truncates it.
2. Diff the eval prompt against the server prompt rule by rule. Look for the refusal sentence.
3. Run the parity script. A failure line names the missing rule.
4. Re-run the negative row 5 or 6 times to separate "always fails" from "fails sometimes" (the 1B model is a distribution).
5. Only then touch the model or the judge.

**Fix now vs fix properly.**
- Now: add the exact refusal sentence and the no-invention rule to the eval prompt. A prohibition with no permitted alternative is a trap, so the model can only invent.
- Properly: make the server prompt the source of truth and fail CI when a rule is missing from the eval prompt, with a short, justified exemption list.

**How you'd test it.** The parity check is the test. Mutation check: delete one rule from `answer.txt` and confirm the script exits non-zero in seconds with no model and no network.

**Spoken answer (60-90 seconds).**
I would first ask whether the eval and the server use the same prompt, because the same model gave two different answers and that points at the inputs, not the model. I would write the promptfoo results to JSON and read the failing assertion's reason, then diff the eval prompt against the server's grounded prompt rule by rule. In my own build that was exactly the bug: the eval prompt said use only the context but gave no permitted alternative, while the server prompt supplied an exact refusal sentence. So a model that could not comply could only invent. I added one sentence to the eval prompt, and then I added a parity script that extracts the bullet rules from the Go constant and fails CI if one is missing from the eval prompt. It runs with no model, so it fails in seconds. The lesson I say to customers is that an eval that grades a prompt nobody ships cannot tell you whether production still works. After both fixes the small model still complied only about one run in five across six runs, so I report that as a model limitation, not as a harness bug.

**Follow-ups the interviewer will ask.**
- *Why not share one prompt file?* The server owns the prompt as a Go constant, so the eval derives from it. Parity keeps one source of truth without a build dependency.
- *What is on the exemption list and why?* One rule, citing by `[n]`, because eval contexts are one unnumbered document. Every exemption is a hole in the guarantee, so it is written down with the reason.
- *Does this run in a real CI runner?* Per my notes it passed locally and had not run on a GitHub runner as of 2026-09-07. Verify before claiming more.

**Tie to your code.** [L] [`evals/ci/check-parity.py`](../../../../evals/ci/check-parity.py), [`evals/prompts/answer.txt`](../../../../evals/prompts/answer.txt), [`.github/workflows/eval-gate.yml`](../../../../.github/workflows/eval-gate.yml), server prompt in [`fe-hands-on/server/stream.go`](../../../../fe-hands-on/server/stream.go).

---

## Scenario 2 🟢 The judge scored it "faithful" but the SQL is not in the docs

**Situation.** Wednesday 14:15, a customer SE pastes an answer into the shared channel: ``CREATE PRIMARY INDEX ON `bucket_name`.*``. The syntax appears nowhere in the supplied documentation. Your nightly eval had that row green, and the LLM judge scored it 1 out of 1 (example, shaped like a case that really happened in my lab).

**Level.** 🟢 Beginner.

**What's being tested.** Deterministic checks first, a judge second, and what a regression guard is: a cheap rule pinned to a failure that really occurred.

**Clarifying questions to ask first.**
1. Which assertions ran on this row, and in what order?
2. What does the judge rubric say, and is it phrased as a claim about the output?
3. Is the offending string anywhere in the pinned context file?
4. Is this row tagged so I can slice results (`grounding`, `negative`)?

**Flow of control and data.**

```
row ──▶ model output ──▶ [1 contains] ──▶ [2 not-contains] ──▶ [3 llm-rubric judge]
                              cheap, exact      cheap, exact        costly, can be fooled
```

**Diagnosis steps.**
1. Open the JSON results for this row and list each assertion with its pass/fail and reason.
2. Search the context file for the offending string to prove it is not in the source.
3. Read the judge's reason text. Does it describe the output correctly and still pass it?
4. Note the judge's token use against the answer's: in my one measured case the judge used about 901 grading tokens against 278 for the answer (about 3.2 times, one case, order of magnitude only).

**Fix now vs fix properly.**
- Now: add a `not-contains` rule for the exact wildcard form, so the bug is red in seconds.
- Properly: grow the set from real failures, keep deterministic rules as the blocking tier, treat the judge as advisory until it is calibrated.

**How you'd test it.** The rule is the test. Feed the known-bad output through the assertion once and confirm it fails, then feed a clean answer and confirm it passes. A regression test that has never failed proves nothing.

**Spoken answer (60-90 seconds).**
I would reproduce the row with the pinned context and read the per-assertion results, because a green badge hides which checks actually ran. In my own suite a 1B model once produced a wildcard form of the primary-index statement that appears nowhere in the context, and the judge marked it faithful. The expensive check missed what a string check catches for free, so I added a `not-contains` rule for that exact string and wrote down in the config why it exists: it pins an observed failure, not a hypothetical one. I order assertions cheapest first, so deterministic rules run before the judge, and the judge costs about three times the generation tokens in the one case I measured. For the customer I would say plainly that the judge is a second opinion, not the gate, and that I grow the golden set from every failure the customer reports.

**Follow-ups the interviewer will ask.**
- *Why not tighten the judge instead?* Judges drift and can be wrong in both directions (Scenario 3). A rule is exact and free.
- *What do rules miss?* They are brittle: a refusal phrased outside my eight listed phrases is a false failure, and no rule judges faithfulness.
- *How big should the golden set be?* No verified number. Size it by the decision it gates and report an interval, not only the pass count.

**Tie to your code.** [L] [`evals/promptfooconfig.yaml`](../../../../evals/promptfooconfig.yaml), the `not-contains` guard near line 44 and the happy-path row near line 36.

---

## Scenario 3 🟡 The judge fails a correct refusal, three runs out of three

**Situation.** Monday 09:30. After your prompt fix, the model now answers the unanswerable question with the exact sentence "The provided documentation does not cover this." The negative row is still red. The judge's reason text says there is no SQL statement in the output, then marks the rubric false anyway (example, shaped like my 2026-09-07 finding). Re-running does not change it.

**Level.** 🟡 Intermediate.

**What's being tested.** Isolating one variable, telling a judge bug from a model bug, and the difference between isolation and calibration.

**Clarifying questions to ask first.**
1. Is the rubric an assertion about the output, or an instruction to the judge?
2. Is the judge pinned (model, temperature 0, JSON mode)?
3. Did the judge model or the rubric change recently?
4. Does a human agree the output is a correct refusal?
5. Is the judge a different family from the model under test?

**Flow of control and data.**

```
fixed output ("The provided documentation does not cover this.")
      └─▶ judge model + rubric (temp 0, x3 runs) ──▶ pass/fail + reason
            vary ONE thing: judge size, then rubric wording
```

**Diagnosis steps.**
1. Take the model out of the loop: hold the output string constant, so there is no sampling variance from the system under test.
2. Run the judge at temperature 0, three times. Same result every time means deterministic, not noise.
3. Read the reason against the verdict. Reason says "true", verdict says false is an inversion.
4. Swap only the judge size and re-run on the identical input.
5. Reword the rubric as a claim about the output and re-run.

**Fix now vs fix properly.**
- Now: swap to the judge size that was right 3 of 3 on this exact input. In my lab the 1.5b judge failed all 3 and the 3b judge passed all 3.
- Properly: hand-label a batch with both polarities (correct declines and fabrications), score judge-versus-human agreement, pin the judge by digest, and re-run the fixed-input isolation on every judge or rubric change.

**How you'd test it.** A standing fixed-input check per rubric: one known-correct output and one known-bad output, each run 3 times at temperature 0, expected verdicts pinned. It fails when someone swaps the judge.

**Spoken answer (60-90 seconds).**
First I would stop looking at the model, because I have a fixed output and the only moving part is the judge. I hold the refusal sentence constant, run the judge three times at temperature 0, and read the reason against the verdict. In my lab the smaller judge agreed in its own words that there was no SQL statement and still marked the rubric false, three times out of three, so it was a reproducible inversion, not sampling noise. The larger judge passed the same input three out of three, so I swapped it. I want to be exact about what that is: isolation, not calibration. Real calibration is a hand-labelled batch with an agreement score, and I have not done that, so my honest status is "no disagreements yet on two cases". I also learned that a rubric written as an instruction can make a judge pass a fabrication, so I write it as a claim about the output.

**Follow-ups the interviewer will ask.**
- *Why did the judge pass fabrications earlier and fail a correct refusal now?* The first cases only let it be wrong in one direction. Need both polarities in the labelled set. (My reading from commit dates; verify in git history.)
- *Is a model tag a stable pin?* Not verified that a tag is immutable. Pin by digest for anything that gates.
- *What metric for agreement?* Cohen's kappa on a labelled batch (sketch in the module, not run on my data).

**Tie to your code.** [L] [`evals/promptfooconfig.yaml`](../../../../evals/promptfooconfig.yaml) judge block near lines 14-30 (the comment records the isolation test) and the `llm-rubric` near line 112.

---

## Scenario 4 🟡 The agent said "Done, alr-1001 is acknowledged" and the alert is still firing

**Situation.** Thursday 16:05. An on-call lead tells you the agent's final message claimed the acknowledgement, but the alert is still firing in the monitoring UI (example). The agent eval for that case has been green for a week.

**Level.** 🟡 Intermediate.

**What's being tested.** Trajectory evals: grade what happened in the system, not what the model said. The scorer must be independent of the model's claim.

**Clarifying questions to ask first.**
1. Does the eval check the final text only, or also the tool calls and the server state?
2. Is acknowledging a write tool behind an approval gate, and was it approved or denied?
3. Where did the state change get recorded, and who can read it?
4. Was this run live or scripted?

**Flow of control and data.**

```
user ─▶ run_agent ─▶ LLM ─▶ ToolCall ─▶ executor ─▶ approval gate ─▶ MCP server ─▶ state file
                       └▶ final text ("Done")        denied? never dispatched      ▲
scorer reads: tool records (selection/safety) + STATE FILE (outcome) ──────────────┘
```

**Diagnosis steps.**
1. Open the audit JSONL for the run and find `tool_call` events. Was `acknowledge_alert` called at all?
2. If called, read `approval`, `executed` and `error_kind`. A default-deny gate gives `denied`, `executed: false`.
3. Read the server state file's acknowledged set. That is ground truth.
4. Compare with the final text. If they disagree, the text is the bug.
5. Check whether the scorer reads `state` as a separate argument from `run`.

**Fix now vs fix properly.**
- Now: tell the on-call lead the truth (the action did not happen), and acknowledge the alert through the proper approval path.
- Properly: keep outcome scoring on server state; add a case where the model claims an action that never ran; consider a post-write read-back in the agent so it verifies before it claims (a design idea, not built).

**How you'd test it.** A scripted model that returns "Done. alr-1001 is acknowledged." with no tool call. Expect two failures: the required tool was never called, and the acknowledged set is empty. The test exists in my harness.

**Spoken answer (60-90 seconds).**
The agent's words are not evidence, so I go to the audit log and the server state. I look for a `tool_call` event for the write tool, and then at its approval decision, whether it executed, and its error kind. In my lab the gate denies writes by default, so the likely story is a denied call followed by a model that claimed success anyway. Then I read the state file the server wrote, which is the true outcome. I built my scorer that way on purpose: selection and safety come from the tool records, and the outcome comes from state, with the final-text checks last. I have a test where the model claims an acknowledgement with no tool call and it fails on both the missing call and the empty state. The boundary of that claim is that it shows the scorer cannot be fooled by words. It says nothing about how often a real model makes that claim.

**Follow-ups the interviewer will ask.**
- *Why separate selection, safety and outcome?* A blocked injection must read "system safe, model wrong", not one pass/fail bit.
- *What does the scripted suite not prove?* A scripted model replays turns and does not react to tool results, so it proves plumbing and scoring, not model quality.
- *What if the customer's system has no state file?* Read the system of record through its API after the run. Same principle, different adapter.

**Tie to your code.** [L] [`agent-lab/evals/scoring.py`](../../../../agent-lab/evals/scoring.py), [`agent-lab/tests/test_harness_catches_failures.py`](../../../../agent-lab/tests/test_harness_catches_failures.py), [`agent-lab/agent/audit.py`](../../../../agent-lab/agent/audit.py).

---

## Scenario 5 🔴 The customer review: "is the agent ready?" and a teammate wants to ship the 10 out of 10 change

**Situation.** Friday 11:00, a customer QBR (example). Your live run shows task success 82%, safety failures 0, and two cases at 0/5. A teammate found a change that took one held-out phrasing from 1/10 to 10/10 and wants to announce the fix. The customer's VP asks you for a yes or no on readiness.

**Level.** 🔴 Senior.

**What's being tested.** Honest reporting under pressure: small n, held-out cases, negative results, and the limits of what a run proves.

**Clarifying questions to ask first.**
1. How many runs per case, which model, and is anything on this run a scripted result?
2. Did the target case move, or only a sibling phrasing?
3. Were held-out cases written before the change, and did we look at all of them?
4. Did we run the full case set after the change?
5. What decision does the customer want to make with this number?

**Flow of control and data.**

```
live runs (n per case) ─▶ per-case pass counts ─▶ target + held-out siblings
        │                                              │
        └─▶ audit logs: real model failure or harness bug? ─▶ report: counts, interval, status
```

**Diagnosis steps.**
1. Read the audit logs of the failing runs to confirm they are real model behaviours, not harness bugs.
2. Put the target and every held-out sibling in one table, n=10 each. A win on one phrasing next to a 0/10 sibling is the signature of fitting a phrasing.
3. Check what changed in the failure: a target that "stops after the list" instead of "explains the wrong alert" has changed shape, not been fixed.
4. Compute an interval, not a bare percentage. From my notes' helper, 5 of 5 is still consistent with a true rate as low as about 57%, and 0 of 10 with a true rate up to about 28% (verify the formula before presenting).
5. Check whether the safety claim was exercised live. In my runs the injection case passed because the model resisted, so the approval gate was never tested live.

**Fix now vs fix properly.**
- Now: report "not fixed, one model, n of 10, no final regression run" with the table, and keep the experiment flagged, not shipped.
- Properly: larger n, a second model, the full case set after every change, report intervals, mark runs invalid when the model server dies, and grow cases from real traffic.

**How you'd test it.** Make held-out cases a rule: written before measuring, all reported, none dropped. Run the whole set after each change and compare per-case against the last baseline with a tolerance sized from observed variance.

**Spoken answer (60-90 seconds).**
My answer to the VP is "not yet, and here is exactly why", with the numbers. On one small local model I ran 60 live runs: 82% task success, no safety failures, two cases at zero out of five, where the model invented a tenant id and explained a suppressed alert instead of the firing one. I then tried fixes one at a time at n of 10. One change took a held-out phrasing from one out of ten to ten out of ten, but the target stayed at zero and a sibling stayed at zero, which looks like fitting one phrasing, so I did not claim it. I also never ran the final regression across all cases. I would give the customer the table, the interval, and the statement that this is one model and a seed set I wrote, not mined from their traffic. A clear negative result is useful to them, because it shows where the model needs a human step or a different design.

**Follow-ups the interviewer will ask.**
- *pass@k or pass-rate for an agent that acts?* Consistency matters, so report the chance all k runs succeed (tau-bench calls it pass^k, arXiv 2406.12045, verified 2026-10-20 per the module).
- *Why is the deterministic suite the gate and live report-only?* Deterministic is binary and proves plumbing; live is a distribution and would make CI flaky.
- *Would you ship the change as a flagged experiment?* Only with a Java-contract change, a contract test and a larger re-run. None of it is done.

**Tie to your code.** [L] [`agent-lab/NOTES.md`](../../../../agent-lab/NOTES.md) live-run table and the two attempt tables, [`agent-lab/evals/cases/16_heldout_chain_rephrased.yaml`](../../../../agent-lab/evals/cases/16_heldout_chain_rephrased.yaml), [`.github/workflows/agent-eval.yml`](../../../../.github/workflows/agent-eval.yml).

---

## Scenario 6 🔴 2 AM: answer quality dropped and nothing alerted

**Situation.** Wednesday 02:10 (example). A support lead pings you: the documentation assistant has been giving wrong answers since yesterday evening. No errors in the logs, latency flat, but thumbs-down rate went from about 6% to about 14% (example numbers). The offline golden set is still green.

**Level.** 🔴 Senior.

**What's being tested.** Online evaluation and observability design, the limit of an offline set, and incident triage for a failure that throws no exception.

**Clarifying questions to ask first.**
1. When did it start, and what shipped or changed near then (prompt, model version, corpus, re-embed job, provider)?
2. Is the drop across all tenants or one corpus slice?
3. Do we log retrieved chunk count, chunk ids, prompt version and model version per request?
4. Is there a pinned previous prompt or model version to roll back to?

**Flow of control and data.**

```
request ─▶ retrieval (chunks, ms) ─▶ generation (tokens, latency) ─▶ answer ─▶ thumbs / retry / abandon
   └──────────── trace + structured log ───────────────────────────┘
online: implicit signals on ALL traffic ─▶ small hashed sample ─▶ async judge ─▶ rolling baseline ─▶ alert
```

**Diagnosis steps.**
1. Confirm the signal: thumbs-down against a rolling baseline, split by tenant and time.
2. Cheap causes first: provider model version change, a failed re-embed job, changes in retrieved count or retrieval ms.
3. Pull a few bad requests and look at the stages: was retrieval empty or irrelevant, or was generation unfaithful?
4. Look at token counts. A refusal is much cheaper than a grounded answer (my one-sample local figures: 9 completion tokens against 128 to 162), so a shift in the token distribution is a cheap drift signal.
5. Roll back to the pinned prompt or model version and watch the signal.

**Fix now vs fix properly.**
- Now: roll back to the pinned version, then confirm the signal recovers.
- Properly: spans per stage carrying prompt and model version, implicit signals on everything, a small hash-sampled async judge, inline cheap guards (schema, secret patterns, token caps), three separate drift watches (input mix, sampled quality, cost per request), and every incident becomes a golden row.

**How you'd test it.** The offline set only covers what I imagined, so add each production failure as a labelled row. Add a synthetic canary query set run on a schedule against production, and replay hashed-sampled real requests through a candidate prompt before rollout.

**Spoken answer (60-90 seconds).**
Nothing throws when answers merely get worse, so I detect it through a proxy such as the thumbs-down rate breaching a rolling baseline, and I treat that as the incident. I triage cheap causes first: did the provider model version change, did the re-embed job fail, did retrieved counts or latency move. Then I trace a few bad requests to see whether retrieval was empty or generation was unfaithful, and I roll back to a pinned prompt or model version while I investigate. I have to be honest about my lab: my Go server logs structured fields per request, such as retrieved count, retrieval milliseconds, token counts and latency, but I have no tracing, no online judge and no alerting. So the online design is knowledge, not something I ran. The Ask AI system has a feedback store and a troubleshooting runbook per its design document, and I did not write those and have not run that runbook against a real incident.

**Follow-ups the interviewer will ask.**
- *How do you sample for the judge?* Hash the request id so the same request is always in or out and can be replayed. The percentage is a budget decision.
- *How is cost watched?* Tokens per request from the server's usage counts, against a rolling baseline.
- *What if the provider silently updated the model?* Pin by exact version where the provider allows it and keep a canary set to detect behaviour change. Verify what your provider guarantees.

**Tie to your code.** [L] request log fields in [`fe-hands-on/server/stream.go`](../../../../fe-hands-on/server/stream.go) (retrieval failure log, completion log with tokens and latency, degraded health check). [K] tracing, online judge, drift alerts. [P] Ask AI feedback store and runbook, described in [`docs/Ask AI design document.md`](../../../../docs/Ask%20AI%20design%20document.md), not my code.

---

## What not to claim in these scenarios

- No part of the eval gate, parity check or agent harness has served a customer. They are lab builds on local models.
- The CI gate had not run on a real GitHub runner as of the 2026-09-07 notes.
- The judge is isolated, not calibrated. No hand-labelled batch or agreement score exists.
- Every model number is one model family and size, with n of 5 or 10, on CPU.
- There is no tracing, alerting, online judge or drift monitoring in the lab.
