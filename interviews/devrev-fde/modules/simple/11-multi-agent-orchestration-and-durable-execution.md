# Module 11 (simple) — Multi-agent orchestration and durable execution

> **Read this first**
> - **What it is for:** running several role-limited agents as steps, saving every state change, and resuming after a crash without repeating a write.
> - **Who it is for:** a beginner. Each term is explained the first time it appears.
> - **Full version:** [11-multi-agent-orchestration-and-durable-execution.md](../11-multi-agent-orchestration-and-durable-execution.md) has the real code snippets and harder follow-ups.

Lane tags: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only.

- Everything built here is **[L]**. The orchestrator lives in [agent-lab/orchestrator](../../../../agent-lab/orchestrator/). Tests are in `agent-lab/tests/test_orchestrator*.py`.
- It uses only Python's `sqlite3`. It uses a scripted model and an in-process MCP server. No network. No real model.
- It is a **single-process, teaching-scale** engine. It is not Temporal, not LangGraph, and not a distributed system.
- The OrbitronAI role advertises "a runtime and orchestration engine" and "native agent lifecycle management" for its Galaxy platform. Those are advertised phrases only. I have not seen how Galaxy works inside.
- Anything I say about Temporal, LangGraph or Step Functions is **[K]**: verify in current docs.
- It builds on the single agent from module 03: [03-agents-and-mcp.md](../03-agents-and-mcp.md).

---

## Phase 1 — Single agent versus multi-agent, and when each is right

**Analogy: one chef versus a kitchen brigade.** One chef does everything in order. A brigade splits the work: one chops, one grills, one plates. Each has their own station. But a brigade needs a head chef, and more people means more ways for a plate to go wrong.

### Single versus multi-agent
- A **single agent** is one model loop. One system prompt. One tool list.
- It asks the model, runs the tool calls the model requests, feeds the results back, and stops on a text answer.
- A **multi-agent** system splits the work across several such loops. Each has its own prompt, tools and step limit.
- Some code, or some model, decides which one runs next.
- I stay with one agent until one prompt or one tool list is clearly too broad.
- Every extra agent costs latency and tokens, and adds a new place to fail.
- In agent-lab, [agent/loop.py](../../../../agent-lab/agent/loop.py) is the single-agent case. I did not change it. The orchestrator calls it once per step.

### Why wrap the agent instead of making it multi-agent
- I wanted a hard boundary.
- `run_agent` stays the small loop I can already defend line by line. The orchestrator owns everything that must survive a crash.
- A **step** is exactly one `run_agent` call. It uses the role's prompt, the role's filtered tool list, and the role's turn cap.
- The agent code knows nothing about SQLite, retries or resume. So I test them separately.
- Cost: the orchestrator cannot see inside a model turn. That matters in Phase 4, because only tool calls are journaled.
- Inside one step, the whole thing runs under `asyncio.wait_for`, a timer that cancels it if too slow. The step ends in only a few ways: success, retry, fatal error, or pause for approval.
- File: [engine.py](../../../../agent-lab/orchestrator/engine.py).

### What multi-agent bought me, and did I measure it (senior)
- What it bought me is structural, not a measured quality gain.
- **Least privilege per role.** A separate step that needs approval. A unit of work that can be checkpointed and retried on its own.
- I did not measure answer quality against a single agent. The demo model is a scripted fake. Claiming several agents answer better would be invented.
- The cost I can name: more model calls. The triage workflow runs five steps. That is at least five model-loop runs, plus one re-run of the responder after approval. One agent might need two or three turns.
- A failure mode: a bad plan from the planner. I contain it with a schema and a limit of five subtasks. I do not trust the model.
- My claim is limited. This proves the orchestration plumbing works. It does not prove multi-agent beats single-agent on any task.

### One agent or several, on a real task (senior)
- Run the same golden cases through both shapes. Compare task success, cost and latency. Use the harness from modules 01 and 03.
- Keep the split only if it wins on something I can count.
- First try a sharper prompt or a narrower tool list on the single agent. That is cheaper than a second agent.
- I have not run this comparison. I can describe the method. I have no result to quote.

### Words you'll hear
| Term | Meaning |
|---|---|
| Agent | A model loop that can call tools until it has an answer |
| Orchestrator | Code that runs several agent steps in order |
| Step | One bounded agent run inside a workflow |
| Role | A named setup: prompt, tools, turn cap |
| Turn cap | The max number of model turns one step may use |
| Least privilege | Give each part only the access it needs |
| Checkpoint | A saved point you can resume from |
| Golden case | A fixed test case with a known good outcome |

**Say it in one breath:** I keep one agent until one prompt is too broad, and my orchestrator treats each step as one bounded agent run, which gives me least privilege and retries but no proven quality gain.

---

## Phase 2 — Roles and least-privilege tool allowlists

**Analogy: staff badges in an office.** The receptionist's badge opens the front door only. The accountant's badge opens the finance room. A badge cannot open a door it was never coded for.

### What a role is
- A role has: a name, a system prompt, a turn limit, the set of tools it may use, and the set of roles it may hand off to.
- In `orchestrator/triage.py` there are four roles.
  - The planner and the aggregator have no tools.
  - The investigator has the three read tools.
  - The responder has `explain_alert` and `acknowledge_alert`.
- The role decides what the model is shown. A role that cannot see a tool cannot name it in a successful call.
- **Least privilege** here: each step gets the smallest tool list that lets it do its job.
- Files: [roles.py](../../../../agent-lab/orchestrator/roles.py), [triage.py](../../../../agent-lab/orchestrator/triage.py).

### How the allowlist is enforced
- The role filters the full tool list with `visible_tools`.
- The orchestrator builds a `ToolExecutor` from only that filtered list. Any other name comes back as an `unknown_tool` error. The backend is never called.
- I wrote no second check. I reuse the executor's unknown-tool path from module 03.
- A test makes the investigator's model ask for `acknowledge_alert`. It asserts the audit log shows `unknown_tool` with `executed` false, and the fake world's write count at zero.
- The assertion checks the refusal, the `executed` flag and the world count together. So a refusal that still ran the tool would fail.
- At startup, `check_roles` rejects a role that allows a tool the server does not list. So a typo fails loudly instead of silently granting nothing.
- Test file: [test_orchestrator_engine.py](../../../../agent-lab/tests/test_orchestrator_engine.py).

### Where least privilege stops protecting you (senior)
- The allowlist is by tool **name** only. It does not restrict arguments.
- An investigator that may call `explain_alert` can pass any tenant id the grounding guard accepts.
- Roles are trusted configuration in code. Nothing stops a deployer from handing the planner a write tool. The guarantee is only as good as the review of that file.
- A failure I cannot rule out: an allowed tool that is simply too powerful for its role.
- What I measured: the refusal test and the startup check pass.
- I did not measure how a real model behaves when shown fewer tools.
- Boundary: this is a per-step capability filter. It is not a sandbox.

### Allowlist vs approval gate (senior)
- They answer different questions. Both are code, not prompt text.
- The allowlist decides whether a role can see and call a tool at all.
- The gate decides whether a visible write tool may run right now.
- The responder can see `acknowledge_alert` because of its allowlist. Yet every call is denied until a human approves that exact call. That is Phase 6.

### Words you'll hear
| Term | Meaning |
|---|---|
| Allowlist | A list of the only things permitted |
| `visible_tools` | The role's filter over the full tool list |
| `unknown_tool` | Error for a tool name not in the role's list |
| Grounding guard | Check that arguments match what the user actually asked about |
| Audit log | Record of each tool call and its result |
| Write tool | A tool that changes real state |
| Sandbox | A strict wall that contains whatever runs inside |

**Say it in one breath:** Each role sees only its own tools, anything else returns `unknown_tool` and never reaches the server, but the filter is by name only, so it does not limit arguments.

---

## Phase 3 — Orchestration patterns (supervisor, plan-and-execute fan-out, handoff) and loop guards

**Analogy: a project manager with a checklist.** The manager writes a plan, sends each task to a specialist, gathers the results, then passes the final action to the one person allowed to sign. A rule says no task may bounce around forever.

### The three patterns
- **Supervisor:** a controller decides at run time which worker runs next.
- **Plan-and-execute:** a planner produces a list of subtasks. Workers run them. An aggregator merges the results.
- **Handoff:** control passes from one role to another, often to one with more authority.
- I built plan, fan-out and aggregate, plus a handoff to a write-capable responder.
- Plain Python in the `triage` function drives both. No model decides the route.
- I did not build a model-routed supervisor.

### How plan, fan-out and handoff work
- The planner step must return JSON. `parse_plan` checks it against a JSON schema.
  - One to five subtasks.
  - Each has a lowercase id and a task string.
  - No extra keys. Unique ids.
- The planner cannot choose a role. The workflow always runs subtasks with the investigator. The schema rejects a `role` key. So a bad plan cannot give itself more authority.
- **Fan-out** (one task split into several) is a plain sequential loop. There is **no concurrency** in this engine.
- The handoff to the responder goes through `ctx.handoff`. It checks the guard before the step is created.
- `validate=parse_plan` runs on the first step. The plan is validated before the step commits. So a stored plan is valid by construction. A malformed one fails the step with no retry.
- Files: [plan.py](../../../../agent-lab/orchestrator/plan.py), [triage.py](../../../../agent-lab/orchestrator/triage.py).

### What stops a runaway run, and what gaps remain (senior)
- Five bounds:
  - a global cap on step attempts per run (20 by default);
  - a per-step attempt cap (3);
  - a handoff guard: refuses cycles, undeclared targets, and more than two handoffs in a chain;
  - a per-step timeout;
  - a wall-clock budget from an injected clock.
- Unit tests assert the cycle message `handoff cycle: a -> b -> a`. An engine test shows the third step is never created.
- The wall budget is per run or per resume call. Time spent waiting for a human must not count.
- So a run resumed again and again can outlast it. The global attempt cap is the backstop, because it counts across resumes.
- Handoffs are chosen by my code, not a model. So the cycle guard mostly protects against my own workflow bugs. A model-chosen handoff would need the same guard.
- The default numbers are my choices. I did not tune them.
- File: [guards.py](../../../../agent-lab/orchestrator/guards.py).

### Why not let a model route, as a supervisor does (senior)
- Routing in code keeps the crash matrix finite and the audit log readable. It keeps the route reproducible on resume.
- Price: flexibility. The workflow cannot change shape based on what the model finds.
- A model-routed supervisor would make each routing decision a non-deterministic step.
- I would store the decision as a step output, the same way I store the plan. Replay would then reuse it.
- I have not built that.

### Words you'll hear
| Term | Meaning |
|---|---|
| Supervisor | A controller that picks the next worker at run time |
| Plan-and-execute | Plan first, then run each subtask |
| Fan-out | Split into several parallel-style tasks |
| Aggregator | A step that merges several results |
| Handoff | Passing control to another role |
| JSON schema | A formal description of valid JSON |
| Cycle | A loop of handoffs: a to b to a |
| Wall-clock budget | A real-time limit on the whole run |
| Deterministic | Same input always follows the same path |

**Say it in one breath:** My workflow is plain Python that plans, fans out sequentially, aggregates and hands off, and five caps stop a runaway, but no model routes and nothing runs in parallel.

---

## Phase 4 — Durable execution: checkpointing, journaling and resume

**Analogy: a video game with save points, plus a receipt book.** Save points let you restart a level without redoing finished levels. The receipt book records every payment made, so after a crash you never pay twice.

### What durable execution means
- It means a run's progress is stored outside the process. If the process dies, a new one finishes the run instead of starting over.
- I persist four things:
  - runs;
  - steps, with a status and an attempt count;
  - an append-only **event log** (a list that only grows);
  - a **journal** of tool calls, keyed by run, step and call index.
- Every state change is one SQLite transaction in **WAL mode** (SQLite's write-ahead-log journaling mode).
- On `resume(run_id)`, the workflow function runs again from the top. Every step that already succeeded returns its stored output without running.
- File: [store.py](../../../../agent-lab/orchestrator/store.py).

### How resume works
- The workflow is an ordinary async function calling `ctx.step` with deterministic step ids.
- `_run_step` first calls `ensure_step`. If the row says succeeded, it returns the stored output. A finished step never runs twice.
- A step that was `running` at the crash is started again with `begin_attempt`, which raises its attempt count by one.
- Consequence: the workflow function must be **deterministic**. It may build prompts and step ids only from the input and stored outputs. Never from the clock or a random number.
- `resume` itself: a finished run just returns. A run waiting for approval stays paused unless approval was granted. Otherwise it re-drives.
- My engine is a toy "done dictionary" plus a database, a status machine and the journal. The toy's dictionary is the `steps` table.

### How the journal stops a write running twice
- Every tool call inside a step gets a **call index**.
- Before the real call I write a `started` row. After it returns I write the result.
- On a re-run, the same index returns the stored result instead of calling the tool.
- A `started` row with no result for a **write** means I cannot know whether it ran. So I refuse to repeat it and fail the step with that reason.
- For a **read**, I just run it again.
- If the model's call at an index differs from the journal: a read is re-executed and replaced. A journaled write fails the step as diverged.
- There are two crash hooks inside the journal. The gap between them is the one window where a write has happened and the journal does not know.
- File: [journal.py](../../../../agent-lab/orchestrator/journal.py).

### What durability guarantees, and where it stops (senior)
- Steps are **at-least-once** (may run more than once, never zero times).
- A tool call whose result reached the journal is replayed. So a journaled write executes once.
- The gap: between a write executing and its journal row. There I refuse to repeat and fail the run.
- That is **at-most-once** for that window, with a human to clean up. It is **not** exactly-once.
- Model turns inside a step are re-run on resume. Only tool calls are journaled. So a non-deterministic model may ask for different calls the second time.
- What I measured: nine crash points plus the unknown-window case, all ending with a write count of one.
- A mutation that disables the journal lookup turns five tests red.
- Boundary: single process, one SQLite file. Two processes resuming the same run would both execute it. I built no **lease** (a time-limited claim that one worker owns the run).

### Comparison with Temporal or LangGraph (senior)
- I did not use either here. I will not claim their guarantees from memory. Verify in current docs. **[K]**
- The shape looks similar in spirit: record outcomes, re-drive code from that record.
- Mine is a few hundred lines. No distribution, no worker fleet, no versioning of workflow code.
- Workflow-code versioning is what I would ask about first. My engine has no answer when the workflow function changes between a crash and a resume.

### Words you'll hear
| Term | Meaning |
|---|---|
| Durable execution | Progress is saved so a dead process can be resumed |
| Journal | A log of each tool call and its result |
| Replay | Return the saved result instead of calling again |
| Transaction | A group of database changes that succeed or fail together |
| WAL | SQLite's write-ahead log mode |
| At-least-once | May run more than once, never zero |
| At-most-once | May run zero times, never twice |
| Exactly-once | Runs once. Hard to promise in practice |
| Lease | A time-limited claim that one worker owns a task |
| Divergence | The replay no longer matches the journal |

**Say it in one breath:** I save every step and tool call in SQLite, so after a crash finished steps return their stored output and a write that might have run is never repeated, which is at-least-once for steps and not exactly-once.

---

## Phase 5 — Idempotency, retries, timeouts and budgets

**Analogy: pressing a lift button twice.** The lift still comes once. That is idempotent. A bank transfer is not: pressing twice would move money twice, unless you add a receipt number.

### What idempotency is
- An operation is **idempotent** if doing it twice has the same effect as doing it once.
- It matters because a crash and resume can run a step again, and a retry can repeat a call.
- My two write tools in the lab are declared idempotent. Acknowledging an already acknowledged alert does nothing the second time.
- I do not rely on that. The journal stops the second call before it reaches the tool.

### How retries and backoff work
- Only two outcomes are retried:
  - an `LLMError`, which `run_agent` reports as the stop reason `llm_error`;
  - a step timeout.
- The delay is **full jitter**: a random number between zero and the smaller of the cap and (base times two to the power of attempt minus one).
- The random source and the sleeper are injected. So tests assert the exact delays.
- After the maximum attempts, the step fails and the run fails with the last reason.
- Never retried: a schema rejection, a handoff refusal, an approval denial, and an agent's turn limit.
- `schedule_retry` comes before the sleep. The retry and its reason are committed to the event log before the process waits. So a crash during the wait still leaves the run resumable.
- Files: [guards.py](../../../../agent-lab/orchestrator/guards.py), [engine.py](../../../../agent-lab/orchestrator/engine.py).

### A step times out while a write is in flight (senior)
- `wait_for` cancels the step. By my reading of the code, the write's journal row stays `started`.
- On the retry, the journal refuses to repeat the write and fails the run as outcome unknown.
- That is deliberate. I prefer a stopped run a human can inspect over a duplicated write.
- The cost: a slow tool with a tight timeout fails runs that a retry might have completed.
- I did not test that exact case end to end. I tested the unknown window by crash injection, which leaves the same journal state. I tested a step timeout with a hanging model, but not a hanging write.
- Cancelling a call in flight does not prove the server stopped it. Module 03 already lists that as unverified.
- Default timeouts are 30 s per step and 10 s per tool. I did not tune them.

### Getting a real exactly-once effect (senior)
- Pass an **idempotency key** built from run id, step id and call index to the tool. The server deduplicates on it. Then the unknown window becomes safe to retry.
- My MCP tools have no such argument and I did not change the server. This is a design, not something I built.
- A small sketch I ran once printed `True 1`: the retry returned the same result with one effect.
- The server must store the key durably. Otherwise a restart loses the deduplication and the problem returns.

### Words you'll hear
| Term | Meaning |
|---|---|
| Idempotent | Doing it twice equals doing it once |
| Retry | Try again after a failure |
| Backoff | Wait longer between each retry |
| Full jitter | Random wait between zero and a growing cap |
| Idempotency key | A unique id the server uses to spot a repeat |
| Timeout | Give up after a time limit |
| Budget | A cap on attempts, time or steps |
| Injected sleeper / rng | Fake wait and random source so tests are exact |

**Say it in one breath:** I retry only model errors and timeouts with jittered backoff, and for a write whose outcome is unknown I stop the run rather than risk a duplicate, because real exactly-once would need an idempotency key I did not build.

---

## Phase 6 — Human-in-the-loop pauses and approvals

**Analogy: a cheque that needs a second signature.** The clerk prepares the cheque and puts it in a tray. Nothing is paid until the manager signs that exact cheque. If the clerk changes the amount, the manager must sign again.

### Why pause for a human
- Some actions, like acknowledging an alert, change real state. They should not happen unless a person says yes.
- When the responder asks for a write, both the step and the run move to `waiting_approval`.
- The process can exit. Nothing holds a thread or a connection.
- A person then runs `approve` or `deny` for that step. `resume` continues or ends the run.
- The default is deny. With no recorded approval, the write never runs.

### How the pause is built on the existing gate
- I reuse `ApprovalGate` from module 03 unchanged. I give it a new approver, `StoreApprover`.
- The approver returns true only when the step has a granted approval recorded for the **exact tool and arguments**. Otherwise it returns false and remembers the call.
- After the agent finishes, a remembered call pauses the step with that call stored. Whatever the model said after the denial is discarded.
- `deny` moves the step and the run to failed in one transaction.
- Resuming after an approval does not count as a new attempt.
- The human approved one specific call. So a model that changes an argument after approval triggers a new pause. It cannot ride the old approval.
- Files: [approval.py](../../../../agent-lab/agent/approval.py), [journal.py](../../../../agent-lab/orchestrator/journal.py), [store.py](../../../../agent-lab/orchestrator/store.py).

### Weaknesses of this design (senior)
- Pausing mid-step wastes work. The responder's first model turn is re-run after approval. Only the tool calls before it are replayed from the journal.
- Binding approval to exact arguments is safer. A test shows a changed argument pausing again with zero writes. But it is annoying with a non-deterministic model.
- The approval also covers any identical repeat of that call inside the step. I accepted that, because the journal replays the first one anyway.
- The biggest gap is **identity**. `approve` records no approver, no expiry and no authentication. Anyone who can write to the database can approve.
- I measured only that the pause, approve, deny and changed-argument tests pass. I measured nothing about how long a real human takes.

### What if nobody ever approves (senior)
- The run stays in `waiting_approval` forever. I built no timeout and no escalation.
- `cancel` exists. It moves the run and its open steps to cancelled in one transaction. So an operator can end it.
- I would add an expiry event that fails the run after a deadline. I would also record who approved. Neither is built.

### Words you'll hear
| Term | Meaning |
|---|---|
| Human-in-the-loop | A person must decide before the run continues |
| `waiting_approval` | Status of a paused step or run |
| Approver | The code or person that says yes or no |
| Default-deny | Block unless approved |
| Pending call | The exact tool call waiting for a decision |
| Escalation | Alerting someone when a decision is overdue |
| Authentication | Proving who a person is |

**Say it in one breath:** A write pauses the run in `waiting_approval`, only a recorded approval of that exact call lets it run, and today the approval has no identity or expiry.

---

## Phase 7 — Observability and testing an orchestrator (the crash matrix)

**Analogy: a flight recorder and a crash-test lab.** The recorder logs everything that happened. The lab smashes the car at nine different speeds and angles, and checks the passenger always walks away.

### Seeing what a run did
- Every state change appends an event in the same transaction as the change itself.
- `describe` prints each step with its status and attempt, followed by the event timeline.
- Tool calls inside a step also go to the existing JSONL audit log, tagged with run, step and attempt.
- The CLI `status` command prints that timeline.
- So I can answer "what happened to this run" from the database without a debugger.
- Files: [control.py](../../../../agent-lab/orchestrator/control.py), [cli.py](../../../../agent-lab/orchestrator/cli.py).

### Testing that a process can die at any boundary
- I put named **crash hooks** at five boundaries.
- A `SimulatedCrash` derives from `BaseException`. So none of the engine's `except Exception` blocks can turn a dead process into a failed step.
- The harness boots a fresh orchestrator on the same SQLite file for each simulated process. It approves when asked. It resumes until the run is terminal.
- Then it compares the final output with an uninterrupted run. It counts real write executions in a fake world that survives the restarts.
- The matrix has nine crash points. Every case must match the uninterrupted output and show exactly one real write.
- Nothing in memory survives between boots except the database file and the fake world. That is what a real restart gives me.
- Files: [crash.py](../../../../agent-lab/orchestrator/crash.py), [test_orchestrator_crash.py](../../../../agent-lab/tests/test_orchestrator_crash.py), [orchestrator_helpers.py](../../../../agent-lab/tests/orchestrator_helpers.py).

### Would the crash test catch a broken journal, and what is missing (senior)
- I ran a mutation check in a scratch copy: replace the journal lookup with `entry = None`. It still writes the journal but never reads it.
- Five tests went red: crash after the write is journaled, attempt-plus-one, replay, the unknown window, and a CLI crash test.
- In a second scratch copy I disabled the "step already succeeded" shortcut. Six tests failed and ten errored.
- Neither bypass is in the repo.
- The matrix does not cover: a real process kill (the crash is an in-process exception), torn disk writes, power loss, two concurrent resumers, or a real model's non-determinism.
- Timing on this laptop: orchestrator tests run in about two seconds. One committed SQLite transaction with `synchronous=FULL` took about 0.11 to 0.14 ms in two runs of 1000. So the matrix is cheap to run on every change.

### What to add next (senior)
- A test that starts the CLI as a subprocess and kills it with SIGKILL at random moments in a loop. Then resume and check the same invariants. That tests a real process death.
- A lease, so two resumers cannot run the same run.
- I did not verify whether `synchronous=FULL` survives power loss on macOS. Verify in the SQLite and macOS docs before claiming durability beyond a process crash.
- None of these is built.

### Words you'll hear
| Term | Meaning |
|---|---|
| Observability | Being able to see what a system did |
| Event log | Append-only list of every state change |
| Crash matrix | A table of crash points, each tested |
| `BaseException` | A Python error type that ordinary `except Exception` does not catch |
| Mutation check | Break the code on purpose to see a test fail |
| SIGKILL | Operating-system signal that kills a process instantly |
| Terminal state | A final status: succeeded, failed or cancelled |
| Torn write | A disk write cut off halfway |

**Say it in one breath:** Every transition is an event, and a nine-point crash matrix proves each crash gives the same answer and exactly one real write, though the crash is an in-process exception and not a real kill.

---

## Mix-ups to avoid

- **Replay vs re-run.** On resume, finished steps and journaled tool calls are replayed from storage. Model turns inside a step are re-run.
- **At-least-once vs exactly-once.** Steps are at-least-once. A write in the unknown window is at-most-once. I do not claim exactly-once.
- **Allowlist vs approval gate.** The allowlist says what a role may see. The gate says whether a visible write may run now.
- **Retry vs resume.** A retry is a new attempt after a failure. A resume restarts a dead process's run from saved state.
- **Fan-out vs concurrency.** My fan-out is a sequential loop. Nothing runs in parallel.
- **Planner vs router.** The planner makes a list of subtasks. It does not choose roles or routes. Plain Python routes.

## What I built vs what I only know

**Built ([L], my own, in `agent-lab/orchestrator`):**
- A small workflow engine on SQLite: role-scoped agent steps, a plan then fan-out then aggregate then handoff workflow, a tool-call journal, resume, retries with jitter, caps, human approval pauses, an event log, and a nine-point crash matrix.
- Tested with a scripted model and an in-process MCP server.
- Mutation checks were done by hand in scratch copies. The bypasses are not in the repo.

**Not claimed:**
- Not a distributed workflow engine. One process, one SQLite file, no lease. Two resumers of one run would both execute it.
- No comparison with Temporal, LangGraph or AWS Step Functions from memory. I did not use them here. **[K]**: verify in current docs.
- No exactly-once. Steps are at-least-once. The window between a write and its journal row is handled as at-most-once with a failed run.
- The whole step is not replayed from the journal. Model turns inside a step are re-run, and only tool calls are journaled. A non-deterministic model can diverge.
- No concurrency. I did not build or test parallel workers.
- No model routes between agents. The route is plain Python in `triage`.
- Multi-agent was not shown to improve answers. The demo model is scripted. No comparison with a single agent was run.
- The crash matrix does not prove survival of a real kill, a torn write or a power loss. I did not verify macOS fsync behaviour.
- Approvals are not authenticated. `approve` records no identity or expiry, and nothing escalates a pause nobody answers.
- Nothing about how OrbitronAI's Galaxy platform works. I only know the phrases it advertises.
- The mutation checks are not automated.
