# Scenarios 11 — Multi-agent orchestration and durable execution

Source module: [`../11-multi-agent-orchestration-and-durable-execution.md`](../11-multi-agent-orchestration-and-durable-execution.md). Six real-time situations an FDE meets, laddered 🟢 🟢 🟡 🟡 🔴 🔴. This is the file to know best: it is the deployment and orchestration story.

How to use: read only the **Situation**, answer out loud, then compare. Every number in a Situation is an **example** to make the story concrete, not a measurement from my repo. Numbers that come from my own code defaults or notes are marked "from my notes" or "derived from the code".

Lanes: **[P]** shipped at Couchbase · **[L]** my own lab build, never deployed to a customer · **[K]** knowledge only, not built.

The orchestrator in `agent-lab/orchestrator` is **[L]**: one process, one SQLite file in WAL mode, a scripted model, an in-process MCP server. It is not Temporal, not LangGraph, and not a distributed system. I never used those tools here, so any comparison is "verify in current docs". I do not know how any vendor's orchestration engine works inside.

One picture to hold in your head for every scenario:

```
run (pending → running → waiting_approval | succeeded | failed | cancelled)
 └─ workflow function (plain async Python, deterministic step ids)
     └─ ctx.step(step_id, role, prompt)  = ONE bounded run_agent call
          ├─ steps table: status + attempt count     ├─ events table: append-only, same transaction
          └─ journal: (run, step, call index) → tool call, result    ← replay source for tool calls
resume(run_id): re-run the workflow from the top; a succeeded step returns its stored output
```

| # | Level | Failure mode |
|---|---|---|
| 1 | 🟢 | The orchestrator process is killed mid-run and must resume without redoing the write |
| 2 | 🟢 | The planner returns output that is not the JSON the workflow needs |
| 3 | 🟡 | A handoff cycle between two roles |
| 4 | 🟡 | Retries after a timeout produce a double acknowledgement |
| 5 | 🔴 | A human approval sits for two days, then the run resumes |
| 6 | 🔴 | The wall-clock budget is exceeded during a provider slowdown |

---

## Scenario 1 🟢 The orchestrator pod is OOM-killed after the write; did it acknowledge twice or not at all?

**Situation.** Wednesday 02:10, a customer's on-call platform (example). The container hosting the orchestrator is killed for exceeding its memory limit (exit code 137, example) while a triage run for tenant `streamflix` is in flight. The supervisor restarts the container. The customer's SRE asks: "Did it acknowledge the alert twice, or never?" The run row says `running`, and no process owns it.

**Level.** 🟢 Beginner.

**What's being tested.** Durable execution basics: what is persisted, what resume replays, what is re-run, and the one window where the answer is "I cannot know".

**Clarifying questions to ask first.**
1. Which step was running, and had the write tool already executed? The status output and the event log say.
2. Is the run status `running`, `waiting_approval`, or already terminal?
3. Does anything automatically resume orphaned runs, or does a person run `resume`?
4. Is exactly one process allowed to resume this run, or could two start?
5. Can we look at the alert in the target system to see whether the acknowledgement landed?

**Flow of control and data.**

```
process dies at one of five named points:
  before_step │ step_started │ tool_executed │ tool_journaled │ after_step_commit
new process ─▶ resume(run_id) ─▶ status running ─▶ re-run workflow from the top
   succeeded step ─▶ return stored output (no model call)
   step that was "running" ─▶ begin_attempt: attempt + 1 ─▶ run_agent again
   tool call with a journal row "done" ─▶ replay stored result, do not call the tool
   write with a row "started" and no result ─▶ refuse to repeat: fail step, "may already have run"
```

**Diagnosis steps.**
1. Run `python -m orchestrator status <run_id>`. Read each step's status and attempt, then the event timeline.
2. Look for a `tool_journaled` event for `acknowledge_alert` on the `respond` step. If present, the write is journaled and resume will replay it (you will see `tool_replayed`), not run it again.
3. If the step is `running` with no `tool_journaled` for the write, the process died somewhere between starting the tool call and journaling it. That is the unknown window.
4. Check the target system for the alert's acknowledged state. For the unknown window this is the only way to find out what happened.
5. Confirm only one resumer is active. I built no lease.

**Fix now vs fix properly.**
- Now: if the write was journaled, run `resume <run_id>`. The run finishes and the write count stays at one. In the unknown window the run fails with `acknowledge_alert (call 0) may already have run before a crash; not repeating a write`. A person checks the alert and decides.
- Properly: a reconciler that finds orphaned `running` runs and resumes them under a lease, so two pods cannot run the same run. Idempotency keys at the tool server, so even the unknown window is safe to retry. Memory limits and a restart budget for the container. Workflow-code versioning, which my engine does not have.

**How you'd test it.** The crash matrix has nine crash points. Each case boots a fresh orchestrator on the same SQLite file, resumes until terminal, and asserts the same output as an uninterrupted run and exactly one real write. A separate test covers the unknown window. `SimulatedCrash` is a `BaseException`, so no `except Exception` in the engine can turn a dead process into a failed step. The honest limit is that this is an in-process exception, not a real `kill -9`, a torn write or a power loss.

**Spoken answer (60-90 seconds).**
I would say what is persisted first: every run, step, attempt count, event and tool call goes into SQLite in one transaction per state change, so a new process can rebuild where it was. On resume the workflow function runs again from the top. Steps that already succeeded return their stored output without a model call. A step that was running starts again with the attempt count raised by one. Tool calls are journaled by run, step and call index, so a write that reached the journal is replayed from its stored result and never executed twice. The one window I cannot close is a write that executed before its journal row was written. There I refuse to repeat it and fail the run as outcome unknown, so a human checks the alert. I tested that with nine crash points and the unknown window, all ending with exactly one write. I should be clear it is a single process on one SQLite file with no lease, and the crashes are simulated exceptions, not real kills.

**Follow-ups the interviewer will ask.**
- *What if two pods resume the same run?* Both execute it, because I built no lease. The fix is a lease or a database row lock on the run, which is **[K]**.
- *Why are model turns not replayed?* Only tool calls are journaled, so a non-deterministic model may ask for a different call on re-run. A different write fails the step as diverged; a different read is simply re-executed.
- *Why a `BaseException` for the simulated crash?* So the crash cannot be swallowed and recorded as an ordinary failure, which would hide exactly the bug the matrix looks for.

**Tie to your code.** [L] [`agent-lab/orchestrator/journal.py`](../../../../agent-lab/orchestrator/journal.py), [`agent-lab/orchestrator/engine.py`](../../../../agent-lab/orchestrator/engine.py) (`resume`, `_run_step`), [`agent-lab/tests/test_orchestrator_crash.py`](../../../../agent-lab/tests/test_orchestrator_crash.py), [`agent-lab/orchestrator/cli.py`](../../../../agent-lab/orchestrator/cli.py) (`--crash-at POINT:STEP` for a live demo). The reconciler and lease are **[K]**.

---

## Scenario 2 🟢 Triage runs fail in seconds because the planner output is not valid JSON

**Situation.** Monday 14:20, a customer pilot (example). Four of 30 triage runs (example) fail within seconds, always at the first step, with `plan is not valid JSON: Expecting value` or `plan rejected: $.subtasks: ...`. The planner prompt was edited on Friday (example). The run status is `failed`, only the `plan` step exists, it shows `attempt=1`, and nothing was retried.

**Level.** 🟢 Beginner.

**What's being tested.** Treating model output as untrusted input, validating before committing a step, why a schema failure is not retried, and the cost of that choice.

**Clarifying questions to ask first.**
1. What did the planner actually return? (Preface text, markdown fences, an empty list, extra keys?)
2. What changed since the last good run: the prompt, the model, or the input?
3. Is the failure rate the same across tenants and inputs?
4. Does the customer want a failed run retried automatically, or surfaced?
5. Is the raw rejected text stored anywhere I can read?

**Flow of control and data.**

```
ctx.step("plan", "planner", input, validate=parse_plan)
   └─▶ run_agent (planner: no tools, max 2 turns) ─▶ text
   └─▶ validate(text): json.loads ─▶ JSON-schema check (1..5 subtasks, lowercase ids, no extra keys)
         ok    ─▶ succeed_step(output)  (stored plan is valid by construction)
         fail  ─▶ fail_step(error) ─▶ raise ─▶ run FAILED, no retry, no sleep
triage then runs one investigator step per subtask; the planner cannot choose a role
```

**Diagnosis steps.**
1. `python -m orchestrator status <run_id>`: confirm one step, `failed`, attempt 1, and read the error text (the schema path and message).
2. Find the raw planner text. The engine fails the step with the validation message only and does not store the rejected output, so I would check the audit stream and my model-call logs. If neither holds it, that is a gap and the fix is to log a truncated copy of the rejected text.
3. Compare the prompt before and after Friday's edit. Read the role's system prompt that the engine used for that step.
4. Compute the failure rate by prompt version. If it jumps at the edit, the prompt is the cause.
5. Check whether the failures cluster on certain inputs, which would suggest a prompt that is brittle for long inputs.

**Fix now vs fix properly.**
- Now: roll the prompt back, or tighten it with an example of the exact JSON shape. Rerun the failed inputs as new runs.
- Properly: a golden set of planner inputs in the eval harness that must produce a valid plan, run before any prompt change ships. Use structured output at the provider if it offers it (verify in current docs). Consider a bounded repair retry that re-asks the planner with the validation error. That is safe to repeat because the planner has no tools and cannot write, and it should be bounded and counted. Alert on the plan rejection rate.

**How you'd test it.** `a malformed plan fails the run without a retry` asserts a failed run, a `plan rejected` error, no sleeps, one attempt, and that no later step was created. `a malformed plan is rejected` is parametrized over bad inputs, and `a valid plan parses into subtasks` covers the good path.

**Spoken answer (60-90 seconds).**
I treat model output like a form field: it is untrusted until validated. The planner step must return JSON, and I validate it against a schema inside the step, before the step is committed, so a stored plan is always valid. The schema allows one to five subtasks with lowercase ids and no extra keys, and it rejects a role key, so a bad plan cannot give itself more authority. A rejected plan fails the step and the run immediately, with no retry, because I decided a schema failure is not a transient error. Here that decision hurts, so I would first find the raw planner text, which my engine does not store on rejection, and compare the prompt before and after Friday's edit. The fix now is rolling back the prompt. The fix properly is a golden set of planner inputs that gates prompt changes, structured output if the provider supports it, and possibly a bounded repair retry, which is safe because the planner has no tools.

**Follow-ups the interviewer will ask.**
- *Why not retry on a schema failure?* The same prompt and input tend to fail the same way, and a retry costs tokens. A repair retry that includes the error is a different, bounded design that I have not built.
- *Why cap subtasks at five?* It bounds fan-out, cost and latency. The number is my choice, not tuned.
- *Where is the plan re-parsed?* `triage` calls `parse_plan` again on the stored text; it is cheap and deterministic.

**Tie to your code.** [L] [`agent-lab/orchestrator/plan.py`](../../../../agent-lab/orchestrator/plan.py), [`agent-lab/orchestrator/triage.py`](../../../../agent-lab/orchestrator/triage.py), [`agent-lab/tests/test_orchestrator_engine.py`](../../../../agent-lab/tests/test_orchestrator_engine.py), [`agent-lab/tests/test_orchestrator_guards.py`](../../../../agent-lab/tests/test_orchestrator_guards.py). Storing rejected text and the repair retry are **[K]**.

---

## Scenario 3 🟡 The customer adds a "final summary" handoff and every run now fails with a handoff cycle

**Situation.** Thursday 11:00, the customer's platform team extends the triage workflow (example). After the responder acknowledges, they want the aggregator to write a final summary, so they give `responder` permission to hand off to `aggregator` and add a handoff step. Every run now fails after the write with `handoff cycle: aggregator -> responder -> aggregator` (example). They ask you to disable the guard.

**Level.** 🟡 Intermediate.

**What's being tested.** What a handoff guard protects against, how it behaves, and the difference between a handoff and a plain step. Also resisting the request to remove a safety control.

**Clarifying questions to ask first.**
1. Did the role declarations and the workflow function both change, and in which release?
2. Is the handoff chosen by code or by a model? In my engine it is plain Python.
3. Did the write already happen before the failure? (Yes, here: the respond step completed.)
4. What does the team actually need: a new authority for the aggregator, or just one more summarising step?
5. Are other runs in flight that the changed workflow code will meet on resume?

**Flow of control and data.**

```
triage: step("aggregate", aggregator)       ─▶ guard.begin("aggregator"): chain = [aggregator]
        handoff("respond", responder)        ─▶ allowed: aggregator.handoff_to has responder ─▶ chain = [aggregator, responder]
        handoff("final-summary", aggregator) ─▶ "aggregator" already in chain ─▶ HandoffRefused("handoff cycle: ...")
                                              ─▶ step is never created ─▶ run FAILED
rules: target must be in handoff_to │ no role twice in a chain │ at most 2 handoffs per chain (default)
a plain ctx.step(...) starts a new chain
```

**Diagnosis steps.**
1. `python -m orchestrator status <run_id>`: the run error holds the exact chain. Read the events; exactly one `handoff` event was recorded and the refused step does not exist.
2. Check the role table: which role gained `handoff_to` and what targets.
3. Read the workflow diff for the new handoff step.
4. Remember the startup check: `check_roles` rejects a `handoff_to` that names an unknown role, but it does not reject cycles, since a cycle depends on the path taken.
5. Confirm the write step itself succeeded, so the failure is after the side effect and the run reports failed even though the action happened.

**Fix now vs fix properly.**
- Now: do not disable the guard. Model the final summary as a plain step (`ctx.step`) by the aggregator, which starts a new chain and needs no new `handoff_to` permission. Revert the responder's `handoff_to`.
- Properly: decide what the workflow is allowed to do after a write, and make the final summary a step with an explicit input from the stored outputs. A plain step bypasses the cycle check, so the global attempt cap (20 by default) is the backstop for a workflow that loops with plain steps. If handoffs ever become model-chosen, the guard matters much more, and each routing decision should be stored as a step output so replay reuses it. I have not built that. Workflow-code changes while runs are in flight are a versioning problem I have not solved.

**How you'd test it.** `a handoff cycle fails the run before the second handoff runs` asserts the failed run, the `a -> b -> a` message, no third step, and exactly one `handoff` event. Guard unit tests cover the cycle, the declared-targets rule, the maximum of two handoffs, and that a plain step starts a new chain.

**Spoken answer (60-90 seconds).**
I would not remove the guard. It enforces three rules: the target must be declared in the role's handoff list, no role may appear twice in a chain, and a chain has at most two handoffs. Here the aggregator is already in the chain, so handing back to it is a cycle, and the refused step is never created. In my engine the route is plain Python, so a cycle is my workflow's bug. If a model were choosing handoffs, the guard would be the thing stopping a ping-pong that burns tokens. What the team needs is not a new authority, it is one more summarising step, so I would make it a plain step by the aggregator, which starts a new chain and needs no new permission. I would also explain the backstop: a plain step bypasses the cycle check, so the global attempt cap of twenty stops a workflow that loops that way. I should say my defaults are untuned, and that changing workflow code under in-flight runs is something my engine has no versioning for.

**Follow-ups the interviewer will ask.**
- *Why not let a model route like a supervisor?* Routing in code keeps the crash matrix finite and the route reproducible on resume. The price is flexibility.
- *How is a handoff different from a plain step?* A handoff checks the guard and records a `handoff` event; a plain step begins a new chain.
- *What if the cycle is wanted (verify, fix, verify)?* Model it as an explicit loop with a counter in code and a hard limit, not as an open-ended handoff chain.

**Tie to your code.** [L] [`agent-lab/orchestrator/guards.py`](../../../../agent-lab/orchestrator/guards.py), [`agent-lab/orchestrator/engine.py`](../../../../agent-lab/orchestrator/engine.py) (`handoff`), [`agent-lab/orchestrator/triage.py`](../../../../agent-lab/orchestrator/triage.py) (roles), [`agent-lab/tests/test_orchestrator_engine.py`](../../../../agent-lab/tests/test_orchestrator_engine.py), [`agent-lab/tests/test_orchestrator_guards.py`](../../../../agent-lab/tests/test_orchestrator_guards.py). Model-routed handoffs and workflow versioning are **[K]**.

---

## Scenario 4 🟡 A slow acknowledge call times out and the customer fears a double acknowledgement

**Situation.** Friday 16:45 (example). The customer's previous in-house script retried on timeouts and once acknowledged the same alert twice, paging the on-call twice. In a staging trial of your orchestrator, `acknowledge_alert` was slow (example: 12 s against the 10 s tool timeout). The run ended `failed` with `acknowledge_alert (call 0) may already have run before a crash; not repeating a write`. The SRE asks why you did not simply retry, and whether it can ever double-acknowledge.

**Level.** 🟡 Intermediate.

**What's being tested.** The three different retry layers (model-driven, step-level, crash-resume), at-least-once versus at-most-once, idempotency keys, and the honesty to say where my own design has a hole.

**Clarifying questions to ask first.**
1. Did the write land on the server before the client gave up? Only the target system knows.
2. Is the tool idempotent on the server side, and does it accept an idempotency key?
3. Which timeout fired: the per-tool timeout (default 10 s) or the per-step timeout (default 30 s)?
4. Did the model call the tool again after seeing the timeout error, or did the engine retry the step?
5. What is worse for this customer: a duplicate acknowledgement or a stopped run?

**Flow of control and data.**

```
executor: wait_for(backend.call_tool, tool_timeout) ─▶ TimeoutError ─▶ record "timed out" (executed=True), tool call cancelled
JournalingBackend: index 0 row "started", cancelled before journal_finish ─▶ row stays "started", no result
path A (step retry / crash resume): same index 0 ─▶ write + "started" + no result ─▶ fatal, run fails (at-most-once)
path B (model-driven retry in the SAME attempt): the loop continues, the model calls the tool again
        ─▶ _next_index = 1 ─▶ no journal row for index 1 ─▶ the write was sent again (found, now closed: see below)
```

**Diagnosis steps.**
1. `python -m orchestrator status <run_id>`: the `respond` step, its attempt count, and the events. A retry event followed by a failure points to path A.
2. Read the audit log for the step: a `tool_call` with `error_kind` `timeout` and `executed` true, and whether a second `acknowledge_alert` call follows it. A second call in the same attempt is path B.
3. Ask the target system for the alert's acknowledgement history. Count acknowledgements.
4. Read the journal rows for the step: index 0 `started` without a result, and whether an index 1 row exists.
5. Compare the tool timeout and the step timeout against the target's real latency percentiles.

**Fix now vs fix properly.**
- Now: raise `tool_timeout_s` in `Limits` to fit the target's real latency, so the call is not cancelled while it succeeds. The executor also has a per-tool timeout mapping, but `_attempt` does not pass one through today, so a per-tool value needs a small change. Leave the stop-on-unknown behaviour in place.
- Properly: pass an idempotency key built from run id, step id and call index to the tool, and have the server deduplicate on it durably, so a retry after an unknown outcome returns the first result. That turns at-least-once plus an idempotent effect into one real effect. My MCP tools have no such argument, so it is a design and not built.
- Path B is closed in the engine. Before any new write the journal now checks whether this step already holds a write that was started and never finished, and if so fails the step with outcome unknown. I confirmed the bug first with a failing test (the fake world saw the write twice), then added the check. A backend exception on a write also leaves a started row, so a retry after a backend error now fails the step too: that is stricter than before, and it is deliberate.

**How you'd test it.** `a crash between a write and its journal entry is never repeated and fails the run cleanly` covers the unknown window with crash injection, and `a step that exceeds its timeout is retried then fails` covers a hanging model. Neither covered a hanging write followed by a model retry. I wrote that test with a fake world that counts writes and a tool that hangs once: before the fix the count was two, and with the fix it is one and the run fails with outcome unknown. A second test shows a read after the timed-out write still runs, so the check does not block reads.

**Spoken answer (60-90 seconds).**
There are three retry layers and they behave differently. If the step is retried or the process crashes and resumes, my journal sees a started write with no result and refuses to repeat it, so the run fails with outcome unknown. That is at-most-once for that window, and I chose it over a duplicate acknowledgement. I also found a gap in my own code by reading it. If the per-tool timeout fired and the model then called the tool again in the same attempt, the call got a new journal index, so the journal did not recognise it as a repeat. I wrote a failing test that saw the write sent twice, then fixed it: the journal now refuses a new write while an earlier write in the step has an unknown outcome. The real fix for both is an idempotency key derived from run, step and call index, deduplicated durably by the server, so retrying after an unknown outcome is safe. My tools do not have that argument yet. I also raise the tool timeout to match real latency, and the stop-on-unknown rule stays.

**Follow-ups the interviewer will ask.**
- *Is that exactly-once?* No. Steps are at-least-once; the write window is at-most-once with a human to clean up. Exactly-once needs a server that deduplicates.
- *Does cancelling the call stop the server?* No. A cancelled client call does not prove the server stopped, which is already listed as unverified in module 03.
- *Why are reads different?* A read can be run again, so the journal simply re-executes it.

**Tie to your code.** [L] [`agent-lab/orchestrator/journal.py`](../../../../agent-lab/orchestrator/journal.py), [`agent-lab/agent/executor.py`](../../../../agent-lab/agent/executor.py) (timeout branch), [`agent-lab/tests/test_orchestrator_crash.py`](../../../../agent-lab/tests/test_orchestrator_crash.py). The model-retry-after-timeout case is now tested in [`agent-lab/tests/test_orchestrator_write_retry.py`](../../../../agent-lab/tests/test_orchestrator_write_retry.py). Idempotency keys are still **[K]**: a design, not built.

---

## Scenario 5 🔴 A human approval sits for two days, then the run resumes

**Situation.** Monday 09:05 (example). A triage run paused at the acknowledge write on Friday 15:10 and the process exited. The approver clicked approve this morning, about 66 hours later (example), and a webhook called `resume`. The customer reports one of three outcomes (example): the acknowledgement was applied to an alert that had been resolved on Saturday; or the run paused again with a different pending call and the approver is confused; or two approvers clicked and two resumes started. They also ask "who approved this?"

**Level.** 🔴 Senior.

**What's being tested.** The full pause-and-resume mechanics, what a long pause invalidates (state, prompts, models), concurrency without a lease, and the gaps in identity and expiry.

**Clarifying questions to ask first.**
1. What changed during the pause: the alert state, the prompt version, the model, the workflow code?
2. Did the resumed run ask for the same call as the one approved? Compare the pending call JSON with the new one.
3. Did one or two `resume` calls run, and could they overlap?
4. How does the customer want stale approvals handled: expire, re-confirm, or auto-deny?
5. What identity and audit trail does the approval need?

**Flow of control and data.**

```
Friday:  respond step ─▶ acknowledge_alert requested ─▶ StoreApprover: not granted ─▶ records the call
         ─▶ pause_for_approval: step + run = waiting_approval, pending_call stored (one transaction) ─▶ process exits
Monday:  approve(run, step) ─▶ step.approval = granted
         resume ─▶ run RUNNING ─▶ workflow re-runs from the top; finished steps return stored output
         respond step re-enters (does not count as a new attempt) ─▶ run_agent re-runs the MODEL TURNS
           ─▶ model asks for a call ─▶ approver: granted AND pending_call == this exact call ?
                 yes ─▶ write executes through the journal        no ─▶ pause again (zero writes)
wall budget is measured from this resume call, so the two days do not count
```

**Diagnosis steps.**
1. `python -m orchestrator status <run_id>`: the `step_waiting_approval` event timestamps. Two such events mean the run paused again, because the arguments changed after approval.
2. Compare the pending call JSON before and after. A different argument (even a note field) means a different call and a new approval.
3. Compare the prompt or model in force at Friday's pause and Monday's resume. My engine can take the role prompt from a provider, so a prompt change between pause and resume changes what the model asks for.
4. Read the alert's current state in the target system. If it was resolved on Saturday, the approval was granted against a state that no longer exists.
5. Look for two `run_resumed` events close together. Without a lease, two concurrent resumes can both execute.
6. Look for who approved. My `approve` records the decision and the step, not an identity.

**Fix now vs fix properly.**
- Now: if the run paused again with a changed call, read the new pending call and approve it deliberately, or deny it so the run fails cleanly. If the alert is stale, deny or cancel the run. `cancel` moves the run and its open steps to cancelled in one transaction.
- Properly: an approval expiry that fails the run after a deadline and notifies the requester; record the approver's identity from authentication; a precondition read before a write that resumes after a long pause (is the alert still firing?); pin prompt, model and workflow version on the run so a resume uses the same ones; a lease per run so only one resumer drives it; escalation for pending approvals. None is built.

**How you'd test it.** The engine tests cover: the run pauses at the write with no write done; resume without an approval stays paused; approve then resume runs the write once; deny fails cleanly with no write; an approval is bound to the exact call, with a changed argument pausing again and zero writes; cancel while waiting stops everything. The wall budget is checked against an injected clock. A test that advances the clock by 48 hours across a pause and asserts the run completes and the budget is not tripped is **[K]**, and so are the lease and expiry tests.

**Spoken answer (60-90 seconds).**
I would first separate what the pause preserved from what it did not. The pause itself is cheap and safe: the step and run move to waiting for approval in one transaction, the process can exit, and nothing holds a thread. The wall budget is measured per resume call, so two days do not count against it. The approval is bound to the exact tool and arguments. But a resume re-runs the model turns inside the step, and only tool calls are replayed from the journal. If the prompt or model changed over the weekend, the model can ask for a different call, which pauses the run again with zero writes. That is safe and confusing. The bigger problems are about the world, not the engine: the alert may have been resolved, my approvals have no expiry, and my approve records no identity. And with no lease two resumes can both run. So my proper fix is expiry, authenticated approvers, a precondition read before the write, pinned versions and a lease. I have built none of those.

**Follow-ups the interviewer will ask.**
- *Why bind approval to the exact arguments?* So a model that changes an argument after a human approved cannot ride the old approval; the cost is more pauses with a non-deterministic model.
- *What if nobody approves?* The run stays in `waiting_approval` forever. `cancel` ends it, and an expiry event is the missing piece.
- *Why re-run the first model turn at all?* Because only tool calls are journaled, not model turns; storing the model's decision as a step output is the alternative, and I did not build it.

**Tie to your code.** [L] [`agent-lab/orchestrator/journal.py`](../../../../agent-lab/orchestrator/journal.py) (`StoreApprover`), [`agent-lab/orchestrator/store.py`](../../../../agent-lab/orchestrator/store.py) (`pause_for_approval`), [`agent-lab/orchestrator/engine.py`](../../../../agent-lab/orchestrator/engine.py) (`resume`), [`agent-lab/orchestrator/control.py`](../../../../agent-lab/orchestrator/control.py), [`agent-lab/tests/test_orchestrator_engine.py`](../../../../agent-lab/tests/test_orchestrator_engine.py). Expiry, approver identity, preconditions, version pinning and leases are **[K]**.

---

## Scenario 6 🔴 Six of 40 nightly runs fail with "wall-clock budget exceeded" and the customer wants the budget raised to an hour

**Situation.** Tuesday 03:00, a nightly batch of 40 triage runs (example). Six fail with `wall-clock budget of 300 s exceeded` while the other 34 finish in about 90 s (example). The model provider was slow from 02:50 (example). The customer's request: raise the budget to 3,600 s.

**Level.** 🔴 Senior.

**What's being tested.** How budgets, timeouts and attempts interact, where each is checked, what raising one limit costs, and designing a real deadline instead of a number.

**Clarifying questions to ask first.**
1. What did the provider's latency and error rate look like during the incident?
2. Which steps burned the time: how many attempts, and what were the retry reasons?
3. How many resumes did the failed runs go through? The budget is per run or resume call.
4. What is the cost of a retried model call, and the provider's rate limit?
5. May a failed run be re-run from the beginning, and is it safe to?

**Flow of control and data.**

```
before EVERY attempt: _check_may_start
   run cancelled? ─▶ stop │ now - this call's start > wall_budget_s (300) ─▶ BudgetExceeded │ attempts started >= global cap (20) ─▶ BudgetExceeded
attempt: wait_for(run_agent, step_timeout 30 s)
   timeout or llm_error ─▶ retry up to max_attempts 3, full-jitter backoff (base 0.5 s, cap 8 s) ─▶ then fail the step
the budget is NOT checked while an attempt is running or while sleeping: a step can overshoot by up to step_timeout
BudgetExceeded is a workflow error ─▶ run FAILED. A failed run is terminal: resume returns its summary
```

**Diagnosis steps.**
1. `python -m orchestrator status <run_id>` for each failed run: per-step attempt counts and the retry events with their reasons (`step timed out after 30 s` versus `llm error: ...`).
2. Do the arithmetic. If a slow provider makes a call hit the 30 s step timeout once before it succeeds, a step costs about 60 s plus a short backoff. The triage workflow has five steps, so about 300 s: exactly the limit (derived from the default limits, example).
3. Compare event timestamps from `run_started` to the failure for the six runs against the 34 that passed.
4. Check the global attempt count against the cap of 20. A run that hit the cap before the budget tells a different story.
5. Pull the provider-side latency and error metrics for 02:50 to 03:10 to confirm an upstream incident, not a bug in the engine.

**Fix now vs fix properly.**
- Now: do not set 3,600 blindly. A retry storm against a degraded provider costs money, burns rate limit and hides the incident. Re-submit the six failed inputs as new runs after the provider recovers. Raise the budget modestly if the normal worst case is near 300 s.
- Properly: make the budget a real deadline by passing the remaining budget into the step timeout, for example the smaller of the step timeout and the time left, so a run cannot overshoot. Propagate the deadline to the model and tool calls. Add a circuit breaker on the provider. Limit batch concurrency. Emit a distinct budget-exceeded event, not only a failed step. Support re-driving a failed run from its last good step, which my engine does not do (a failed run is terminal, so the six re-runs repeat the earlier steps).

**How you'd test it.** `the wall-clock budget is checked against the injected clock` and `the global step limit stops the run` exist. `an LLM error is retried with exponential backoff and then succeeds` and `a step that exceeds its timeout is retried then fails` cover the retry layers, and a guard test asserts the full-jitter delay range doubles per attempt and is capped. A deadline-aware step timeout and the overshoot case are **[K]**; I would drive them with the injected clock and sleeper so no test waits in real time.

**Spoken answer (60-90 seconds).**
I would not raise the budget to an hour first. I would ask why six runs ran long, because the likely answer is a provider incident and an hour of retries would hide it and cost money. My engine has several limits that interact. A wall budget of 300 seconds per run or resume call, a per-step timeout of 30 seconds, three attempts per step with jittered backoff, and a global cap of 20 attempts. The budget is only checked before each attempt, so a step already running can overshoot it by up to the step timeout, and it is not checked during backoff. With a slow provider, one timeout then a success costs about a minute per step, and my triage has five steps, which lands right at 300 seconds. So I would read the retry reasons per step to confirm that. The fix now is to rerun the failed inputs after recovery. The fix properly is a real deadline: pass the remaining budget into the step timeout, add a circuit breaker, and let a failed run restart from its last good step, which I have not built.

**Follow-ups the interviewer will ask.**
- *Why is the budget per call, not per run lifetime?* So time spent waiting for a human approval does not count; the global attempt cap counts across resumes and is the backstop.
- *Why full jitter?* So many clients retrying after the same incident do not return at the same instant. The delay is a random value between zero and the smaller of the cap and the base times two to the attempt minus one.
- *Which errors are never retried?* A schema rejection, a handoff refusal, an approval denial and an agent using all its turns.

**Tie to your code.** [L] [`agent-lab/orchestrator/engine.py`](../../../../agent-lab/orchestrator/engine.py) (`_check_may_start`, retry branch), [`agent-lab/orchestrator/guards.py`](../../../../agent-lab/orchestrator/guards.py) (`Limits`, `full_jitter_delay`), [`agent-lab/tests/test_orchestrator_engine.py`](../../../../agent-lab/tests/test_orchestrator_engine.py), [`agent-lab/tests/test_orchestrator_guards.py`](../../../../agent-lab/tests/test_orchestrator_guards.py). The deadline propagation, circuit breaker and re-drive of a failed run are **[K]**.
