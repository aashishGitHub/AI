# Module 11 — Multi-agent orchestration & durable execution

> This module is the orchestrator I built in `agent-lab/orchestrator` on top of the single agent from module 03: a small Python workflow engine that runs several role-scoped agents as steps, persists every state change in SQLite, and can be killed at any point and resumed. I wrote it because the OrbitronAI role advertises "a runtime and orchestration engine for reasoning and collaboration" and "native agent lifecycle management" for its Galaxy platform; those are the advertised phrases only, and I have not seen how Galaxy works inside, so nothing here is a claim about their product. Everything is lane [L], my own build, stdlib `sqlite3` only, with a scripted model and an in-process MCP server, so no network and no real model is involved. It is a single-process teaching-scale engine, not Temporal, not LangGraph and not a distributed system, and every statement about those tools below is marked "verify in current docs". The code lives in `AI/agent-lab/orchestrator/` and the tests in `AI/agent-lab/tests/test_orchestrator*.py`.

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. Single agent versus multi-agent | Keep one agent until a split pays for itself, and treat each step as one bounded agent run. | `agent/loop.py`, `orchestrator/engine.py` |
| 2. Roles and least-privilege allowlists | A role is a prompt, a step cap and the only tools its model can see or call. | `orchestrator/roles.py`, `orchestrator/triage.py` |
| 3. Orchestration patterns and loop guards | Plan, fan out, aggregate and hand off in plain code, with caps that stop a runaway run. | `orchestrator/triage.py`, `orchestrator/plan.py`, `orchestrator/guards.py` |
| 4. Durable execution | Persist runs, steps, events and a tool-call journal so a dead process can be resumed without repeating a write. | `orchestrator/store.py`, `orchestrator/journal.py`, `orchestrator/engine.py` |
| 5. Idempotency, retries, timeouts and budgets | Retry only what is safe, with jittered backoff, and bound every run by attempts, time and steps. | `orchestrator/guards.py`, `orchestrator/engine.py` |
| 6. Human-in-the-loop pauses | A write pauses the run in `waiting_approval`, and only a recorded approval of that exact call lets it run. | `orchestrator/journal.py`, `orchestrator/store.py`, `agent/approval.py` |
| 7. Observability and testing | Every transition is an event, and a crash matrix proves the same answer and one real write at each boundary. | `orchestrator/control.py`, `orchestrator/crash.py`, `tests/test_orchestrator_crash.py` |

## Phase 1 — Single agent versus multi-agent, and when each is right

### 🟢 Beginner

**Q:** What is the difference between a single agent and a multi-agent system, and when do you stay with one agent?

**A:** A single agent is one model loop with one system prompt and one tool list: it asks the model, runs the tool calls the model requests, feeds the results back and stops on a text answer. A multi-agent system splits the work across several such loops, each with its own prompt, tools and step limit, and some code or some model decides which one runs next. I stay with one agent until one prompt or one tool list is clearly too broad, because every extra agent costs latency and tokens and adds a new place to fail. In agent-lab the loop in `agent/loop.py` is the single-agent case, I did not change it, and the orchestrator calls it once per step.

### 🟡 Intermediate

**Q:** Why did you wrap the existing agent in an orchestrator instead of making the agent itself multi-agent?

**A:** I wanted a hard boundary: `run_agent` stays the small loop I can already defend line by line, and the orchestrator owns everything that has to survive a crash. A step is exactly one `run_agent` call with the role's prompt, the role's filtered tool list and the role's turn cap. The agent code knows nothing about SQLite, retries or resume, so I can test it and the orchestrator separately. The cost is that the orchestrator cannot see inside a model turn, which matters in phase 4 because only tool calls are journaled.

**Source:** `AI/agent-lab/orchestrator/engine.py:220-242`

```python
    async def _attempt(self, role: AgentRole, step_id: str, attempt: int, prompt: str) -> _Done | _Retry | _Fatal | _Pause:
        o = self._o
        tools = role.visible_tools(o.tools)
        journal = JournalingBackend(o.backend, o.store, self.run_id, step_id, {t.name: t for t in tools}, o.crash)
        approver = StoreApprover(o.store, self.run_id, step_id)
        executor = ToolExecutor(journal, tools, ApprovalGate(approver), default_timeout_s=o.limits.tool_timeout_s,
                                grounded_args=o.grounded_args)
        audit = AuditLog(o.audit_stream, run_id=f"{self.run_id}/{step_id}#{attempt}", clock=o.clock)
        agent = run_agent(prompt, o.llm_factory(role, step_id, attempt), executor, tools, audit, role.max_steps,
                          o.system_prompt(role))
        try:
            result = await asyncio.wait_for(agent, o.limits.step_timeout_s)
        except TimeoutError:
            return _Retry(f"step timed out after {o.limits.step_timeout_s:g} s")
        if journal.fatal:
            return _Fatal(journal.fatal)
        if approver.requested:
            return _Pause(approver.requested)
        if result.stop_reason == "llm_error":
            return _Retry(f"llm error: {result.error}")
        if result.stop_reason == "max_steps":
            return _Fatal(f"agent used all {role.max_steps} turns without answering")
        return _Done(result.final_text)
```

I would point at `run_agent(...)` inside `asyncio.wait_for`: the whole step is one bounded agent run, and the three early returns after it are the only ways a step ends other than success.

### 🔴 Senior

**Q:** What did the multi-agent structure buy you, and did you measure that it improves answers?

**A:** What it bought me is structural and not a measured quality gain: least privilege per role, a separate step that needs approval, and a unit of work that can be checkpointed and retried on its own. I did not measure answer quality against a single agent, because the demo model is a scripted fake, so any claim that several agents answer better would be invented. The cost I can name is more model calls: the triage workflow runs five steps, so it makes at least five model-loop runs plus one re-run of the responder after approval, where one agent might need two or three turns. A failure mode is a bad plan from the planner, which I contain with a schema and a limit of five subtasks instead of trusting the model. The boundary of the claim is that this proves the orchestration plumbing works, not that multi-agent beats single-agent on any task.

**Follow-up they will ask:** How would you decide, on a real task, between one agent and several?

**A:** I would run the same golden cases through both shapes and compare task success, cost and latency with the harness from modules 01 and 03, and I would keep the split only if it wins on something I can count. I would first try a sharper prompt or a narrower tool list on the single agent, because that is cheaper than a second agent. I have not run this comparison, so I can describe the method but I have no result to quote.

## Phase 2 — Roles and least-privilege tool allowlists

### 🟢 Beginner

**Q:** What is a role in your orchestrator?

**A:** A role is a name, a system prompt, a turn limit, the set of tools it may use and the set of roles it may hand off to. In `orchestrator/triage.py` there are four: the planner and the aggregator have no tools, the investigator has the three read tools, and the responder has `explain_alert` and `acknowledge_alert`. The role decides what the model is shown, so a role that cannot see a tool has no way to name it in a successful call. Least privilege here means each step gets the smallest tool list that lets it do its job.

### 🟡 Intermediate

**Q:** How is the allowlist enforced, and what stops a model from calling a tool outside it?

**A:** The role filters the full tool list with `visible_tools`, and the orchestrator builds a `ToolExecutor` from only that filtered list, so any other name comes back as an `unknown_tool` error and the backend is never called. I did not write a second check; I reuse the executor's existing unknown-tool path from module 03. A test makes the investigator's model ask for `acknowledge_alert` and asserts that the audit log shows `unknown_tool` with `executed` false and the fake world's write count at zero. At startup `check_roles` rejects a role that allows a tool the server does not list, so a typo in an allowlist fails loudly instead of silently granting nothing.

**Source:** `AI/agent-lab/orchestrator/roles.py:11-20`

```python
@dataclass(frozen=True)
class AgentRole:
    name: str
    allowed_tools: frozenset[str] = frozenset()
    max_steps: int = 4
    handoff_to: frozenset[str] = frozenset()
    system_prompt: str = ""

    def visible_tools(self, tools: Sequence[ToolSpec]) -> list[ToolSpec]:
        return [t for t in tools if t.name in self.allowed_tools]
```

**Source:** `AI/agent-lab/tests/test_orchestrator_engine.py:99-111`

```python
def test_a_role_cannot_call_a_tool_outside_its_allowlist(tmp_path, world):
    audit = new_audit()

    def factory(role, step_id, attempt):
        if step_id == "work-alerts":
            return CallThenEcho("acknowledge_alert", {"tenantId": "streamflix", "alertId": "alr-1001"})
        return reactive_llm(role, step_id, attempt)

    start(tmp_path, world, llm_factory=factory, audit=audit)
    events = [json.loads(line) for line in audit.getvalue().splitlines()]
    refused = [e for e in events if e["event"] == "tool_call" and e["run_id"].startswith(f"{RUN_ID}/work-alerts")]
    assert [(e["tool"], e["error_kind"], e["executed"]) for e in refused] == [("acknowledge_alert", "unknown_tool", False)]
    assert world.count("acknowledge_alert") == 0
```

I would point at the assertion tuple: it checks the refusal, the `executed` flag and the world count together, so a refusal that still ran the tool would fail.

### 🔴 Senior

**Q:** Where does this least-privilege model stop protecting you?

**A:** The allowlist is by tool name only, so it does not restrict arguments: an investigator that may call `explain_alert` can pass any tenant id the grounding guard accepts. Roles are trusted configuration in code, so nothing stops a deployer from handing the planner a write tool, and the guarantee is only as good as the review of that file. A failure mode I cannot rule out is an allowed tool that is simply too powerful for its role. What I measured is that the refusal test and the startup check pass, and I did not measure how a real model behaves when it is shown fewer tools. The boundary is that this is a per-step capability filter and not a sandbox.

**Follow-up they will ask:** How is the allowlist different from the approval gate?

**A:** They answer different questions and both are code, not prompt text. The allowlist decides whether a role can see and call a tool at all, and the gate decides whether a visible write tool may run right now. The responder can see `acknowledge_alert` because of its allowlist, yet every call is still denied until a human approves that exact call, which is phase 6.

## Phase 3 — Orchestration patterns (supervisor, plan-and-execute fan-out, handoff) and loop guards

### 🟢 Beginner

**Q:** What are the three orchestration patterns, and which did you build?

**A:** A supervisor is a controller that decides at run time which worker runs next, plan-and-execute has a planner produce a list of subtasks that workers run and an aggregator merges, and a handoff passes control from one role to another, often to one with more authority. I built plan, fan-out and aggregate, and a handoff to a write-capable responder. Both are driven by ordinary Python in the `triage` function, and no model decides the route. I did not build a model-routed supervisor.

### 🟡 Intermediate

**Q:** How do the plan, the fan-out and the handoff work in your code, and how is the plan validated?

**A:** The planner step must return JSON, and `parse_plan` checks it against a JSON schema: one to five subtasks, each with a lowercase id and a task string, no extra keys, and unique ids. The planner cannot choose a role, because the workflow always runs subtasks with the investigator and the schema rejects a `role` key, so a bad plan cannot grant itself more authority. The fan-out is a plain sequential loop over the subtasks, so there is no concurrency in this engine. The handoff to the responder goes through `ctx.handoff`, which checks the guard before the step is created.

**Source:** `AI/agent-lab/orchestrator/plan.py:43-55`

```python
def parse_plan(text: str) -> tuple[Subtask, ...]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"plan is not valid JSON: {exc.msg}") from exc
    errors = sorted(_VALIDATOR.iter_errors(data), key=lambda e: e.json_path)
    if errors:
        raise PlanError(f"plan rejected: {errors[0].json_path}: {errors[0].message}")
    subtasks = tuple(Subtask(item["id"], item["task"]) for item in data["subtasks"])
    ids = [s.id for s in subtasks]
    if len(set(ids)) != len(ids):
        raise PlanError("plan rejected: duplicate subtask ids")
    return subtasks
```

**Source:** `AI/agent-lab/orchestrator/triage.py:59-69`

```python
async def triage(ctx: RunContext) -> str:
    plan = await ctx.step("plan", "planner", ctx.input, validate=parse_plan)
    findings = [
        await ctx.step(f"work-{sub.id}", "investigator", f"{sub.task}\nRequest: {ctx.input}")
        for sub in parse_plan(plan)
    ]
    summary = await ctx.step("aggregate", "aggregator", "Merge these findings:\n" + "\n".join(findings))
    action = await ctx.handoff(
        "respond", "responder",
        f"{ctx.input}\nFindings: {summary}\nAcknowledge the root-cause alert named in the findings.")
    return f"{summary}\n{action}"
```

I would point at `validate=parse_plan` on the first step: the plan is validated before the step commits, so a stored plan is valid by construction and a malformed one fails the step without a retry.

### 🔴 Senior

**Q:** What stops a runaway orchestration, and what gaps remain?

**A:** There are five bounds: a global cap on step attempts per run (20 by default), a per-step attempt cap (3), a handoff guard that refuses cycles, undeclared targets and more than two handoffs in a chain, a per-step timeout, and a wall-clock budget read from an injected clock. Unit tests assert the cycle message `handoff cycle: a -> b -> a`, and an engine test shows the third step is never created. The wall budget is per run or resume call, because time spent waiting for a human must not count, so a run resumed again and again can outlast it, and the global attempt cap is the backstop because it counts across resumes. Handoffs are chosen by my code and not by a model, so the cycle guard mostly protects against my own workflow bugs, and a model-chosen handoff would need the same guard. The default numbers are my choices and I did not tune them.

**Source:** `AI/agent-lab/orchestrator/guards.py:38-48`

```python
    def begin(self, role: str) -> None:
        self._chain = [role]

    def hand_off(self, to_role: str, allowed_targets: frozenset[str]) -> None:
        if to_role not in allowed_targets:
            raise HandoffRefused(f"{self.current} may not hand off to {to_role}")
        if to_role in self._chain:
            raise HandoffRefused(f"handoff cycle: {' -> '.join([*self._chain, to_role])}")
        if len(self._chain) - 1 >= self._max:
            raise HandoffRefused(f"max handoffs ({self._max}) reached at {' -> '.join(self._chain)}")
        self._chain.append(to_role)
```

**Source:** `AI/agent-lab/orchestrator/engine.py:211-218`

```python
    def _check_may_start(self) -> None:
        o = self._o
        if o.store.get_run(self.run_id).status == CANCELLED:
            raise RunStopped()
        if o.clock() - self._started > timedelta(seconds=o.limits.wall_budget_s):
            raise BudgetExceeded(f"wall-clock budget of {o.limits.wall_budget_s:g} s exceeded")
        if o.store.attempts_started(self.run_id) >= o.limits.global_max_steps:
            raise BudgetExceeded(f"global step limit of {o.limits.global_max_steps} reached")
```

**Follow-up they will ask:** Why not let a model route between workers, as a supervisor does?

**A:** Routing in code keeps the crash matrix finite and the audit log readable, and it keeps the route reproducible on resume. The price is flexibility: the workflow cannot adapt its shape to what the model finds. A model-routed supervisor would make each routing decision a non-deterministic step, so I would store the decision as a step output the same way I store the plan, and replay would then reuse it. I have not built that.

## Phase 4 — Durable execution: checkpointing, journaling and resume

### 🟢 Beginner

**Q:** What does durable execution mean, and what do you persist?

**A:** It means a run's progress is stored outside the process, so if the process dies a new one can finish the run instead of starting over. I persist runs, steps with a status and an attempt count, an append-only event log, and a journal of tool calls keyed by run, step and call index. Every state change is one SQLite transaction in WAL mode, which is SQLite's write-ahead-log journaling mode. On `resume(run_id)` the workflow function runs again from the top, and every step that already succeeded returns its stored output without running.

### 🟡 Intermediate

**Q:** How does resume work in the code?

**A:** The workflow is an ordinary async function that calls `ctx.step` with deterministic step ids. `_run_step` first calls `ensure_step`, and if the row already says succeeded it returns the stored output, so a completed step is never run twice. A step that was `running` at the crash is started again with `begin_attempt`, which raises its attempt count by one. The consequence is that the workflow function must be deterministic: it may build prompts and step ids only from the input and from stored outputs, never from the clock or a random number.

**Source:** `AI/agent-lab/orchestrator/engine.py:112-119`

```python
    async def resume(self, run_id: str) -> RunSummary:
        run = self.store.get_run(run_id)
        if run.status in TERMINAL:
            return _summary(run)
        if run.status == WAITING_APPROVAL and not self._approval_granted(run_id):
            return _summary(run)
        self.store.set_run_status(run_id, RUNNING, event="run_resumed")
        return await self._drive(run_id)
```

**Source:** `AI/agent-lab/orchestrator/engine.py:167-186`

```python
    async def _run_step(self, step_id: str, role: AgentRole, prompt: str, validate: Validate | None) -> str:
        o, store, limits = self._o, self._o.store, self._o.limits
        o.crash(BEFORE_STEP, step_id)
        row = store.ensure_step(self.run_id, step_id, role.name)
        if row.status == SUCCEEDED:
            return row.output or ""
        if row.status == CANCELLED:
            raise RunStopped()
        if row.status == FAILED:
            raise StepFailed(row.error or f"step {step_id} failed")
        while True:
            self._check_may_start()
            row = store.get_step(self.run_id, step_id)
            if row.status != WAITING_APPROVAL and row.attempt >= limits.max_attempts:
                reason = f"step {step_id} used all {limits.max_attempts} attempts (crashed or failed)"
                store.fail_step(self.run_id, step_id, reason)
                raise StepFailed(reason)
            row = store.begin_attempt(self.run_id, step_id)
            o.crash(STEP_STARTED, step_id)
            outcome = await self._attempt(role, step_id, row.attempt, prompt)
```

**Illustrative (not from the repo):** the whole replay idea in a dozen lines, run once; it printed `AB ['a', 'b']`, so step "a" had its effect once even though the first attempt died after it.

```python
done = {}
effects = []


def step(step_id, fn):
    if step_id not in done:
        done[step_id] = fn()
    return done[step_id]


def workflow(crash_after=None):
    a = step("a", lambda: effects.append("a") or "A")
    if crash_after == "a":
        raise RuntimeError("process died")
    return step("b", lambda: effects.append("b") or a + "B")


try:
    workflow(crash_after="a")
except RuntimeError:
    pass
print(workflow(), effects)
```

I would say that my engine is this toy plus a database, a status machine and the journal below, and that the toy's `done` dictionary is the `steps` table.

**Q:** How does the journal stop a write tool from running twice?

**A:** Every tool call inside a step gets a call index. Before the real call I write a `started` row, after it returns I write the result, and on a re-run the same index returns the stored result instead of calling the tool. A `started` row with no result for a write means I cannot know whether it ran, so I refuse to repeat it and fail the step with that reason. For a read I simply run it again. If the model's call at an index differs from the journal, a read is re-executed and replaced, and a journaled write fails the step as diverged.

**Source:** `AI/agent-lab/orchestrator/journal.py:27-49`

```python
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput:
        index = self._next_index
        self._next_index += 1
        arguments_json = json.dumps(arguments, sort_keys=True)
        read_only = name in self._tools and self._tools[name].read_only
        entry = self._store.journal_get(self._run_id, self._step_id, index)
        if entry is not None and (entry.tool, entry.arguments) == (name, arguments_json):
            if entry.status == "done":
                self._store.append_event(self._run_id, "tool_replayed", step=self._step_id, index=index, tool=name)
                return ToolOutput(entry.content or "", entry.is_error)
            if not entry.read_only:
                self.fatal = f"{name} (call {index}) may already have run before a crash; not repeating a write"
                return ToolOutput(f"error: {name} outcome unknown; not repeated", True)
        elif entry is not None and not entry.read_only:
            self.fatal = f"replay diverged at write call {index}: journal has {entry.tool}, the model asked for {name}"
            return ToolOutput(f"error: {name} not run; replay diverged from the journal", True)
        self._store.journal_start(self._run_id, self._step_id, index, name, arguments_json, read_only)
        output = await self._inner.call_tool(name, arguments)
        self._crash(TOOL_EXECUTED, self._step_id)
        self._store.journal_finish(self._run_id, self._step_id, index, output.content, output.is_error)
        self._store.append_event(self._run_id, "tool_journaled", step=self._step_id, index=index, tool=name)
        self._crash(TOOL_JOURNALED, self._step_id)
        return output
```

I would point at the two `self._crash(...)` calls: they are the only seams the tests need, and the gap between them is the one window where a write has happened and the journal does not know.

### 🔴 Senior

**Q:** What exactly does your durability guarantee, and where does it stop?

**A:** Steps are at-least-once, and a tool call whose result reached the journal is replayed, so a write that was journaled executes once. The gap is the window between a write executing and its journal row: there I refuse to repeat the write and fail the run, which is at-most-once for that window with a human to clean up, and it is not exactly-once. The model turns inside a step are re-run on resume and only tool calls are journaled, so a non-deterministic model may ask for different calls the second time. I measured nine crash points plus the unknown-window case, all ending with a write count of one, and a mutation that disables the journal lookup turns five tests red. The boundary is a single process on one SQLite file: two processes resuming the same run would both execute it, because I built no lease.

**Follow-up they will ask:** How does this compare with Temporal or LangGraph checkpointing?

**A:** I did not use either in this module, so I will not claim their guarantees from memory; verify them in the current docs before comparing. What I can say is that the shape looks similar in spirit, recording outcomes and re-driving code from that record, and that mine is a few hundred lines with no distribution, no worker fleet and no versioning of workflow code. Workflow-code versioning is the thing I would ask about first, since my engine has no answer when the workflow function changes between a crash and a resume.

## Phase 5 — Idempotency, retries, timeouts and budgets

### 🟢 Beginner

**Q:** What is idempotency, and why does it matter for an orchestrator?

**A:** An operation is idempotent if doing it twice has the same effect as doing it once. It matters because a crash and resume can run a step again and a retry can repeat a call, so a write that is not idempotent can happen twice. My two write tools in the lab are declared idempotent, and acknowledging an already acknowledged alert does nothing the second time. I do not rely on that, because the journal stops the second call before it reaches the tool.

### 🟡 Intermediate

**Q:** How do retries and backoff work, and what is not retried?

**A:** Only two outcomes are retried: an `LLMError`, which `run_agent` reports as the stop reason `llm_error`, and a step timeout. The delay is full jitter: a random number between zero and the smaller of the cap and the base times two to the power of the attempt minus one. The random source and the sleeper are injected, so the tests assert the exact delays. After the maximum attempts the step fails and the run fails with the last reason. A schema rejection, a handoff refusal, an approval denial and the turn limit of an agent are never retried.

**Source:** `AI/agent-lab/orchestrator/guards.py:25-26`

```python
def full_jitter_delay(attempt: int, base_s: float, cap_s: float, rng: Uniform) -> float:
    return rng.uniform(0.0, min(cap_s, base_s * 2 ** (attempt - 1)))
```

**Source:** `AI/agent-lab/orchestrator/engine.py:203-209`

```python
            if row.attempt >= limits.max_attempts:
                reason = f"step {step_id} gave up after {row.attempt} attempts: {outcome.reason}"
                store.fail_step(self.run_id, step_id, reason)
                raise StepFailed(reason)
            delay = full_jitter_delay(row.attempt, limits.backoff_base_s, limits.backoff_cap_s, o.rng)
            store.schedule_retry(self.run_id, step_id, outcome.reason, delay)
            await o.sleeper(delay)
```

I would point at `schedule_retry` before `sleeper`: the retry and its reason are committed to the event log before the process waits, so a crash during the wait still leaves the run resumable.

### 🔴 Senior

**Q:** A step times out while a write tool is in flight. What happens, and what is the trade-off?

**A:** `wait_for` cancels the step, so by my reading of the code the write's journal row stays `started`, and on the retry the journal refuses to repeat the write and fails the run as outcome unknown. That is deliberate: I prefer a stopped run that a human can inspect over a duplicated write, but it means a slow tool with a tight timeout fails runs that a retry might have completed. I did not test that exact case end to end; I tested the unknown window by crash injection, which leaves the same journal state, and I tested a step timeout with a hanging model, but not with a hanging write. Cancelling a call in flight does not prove the server stopped it, and module 03 already lists that as unverified. The default timeouts are 30 s per step and 10 s per tool and I did not tune them.

**Follow-up they will ask:** How would you get a real exactly-once effect for the write?

**A:** I would pass an idempotency key derived from the run id, the step id and the call index to the tool and have the server deduplicate on it, so the unknown window becomes safe to retry. My MCP tools have no such argument and I did not change the server, so this is a design and not something I built. The sketch below shows the shape and I ran it once; it printed `True 1`, meaning the retry returned the same result with one effect.

**Illustrative (not from the repo):** a write that deduplicates on a key built from the run, step and call index.

```python
effects = []
seen = {}


def acknowledge(idempotency_key, alert_id):
    if idempotency_key not in seen:
        effects.append(alert_id)
        seen[idempotency_key] = f"acknowledged {alert_id}"
    return seen[idempotency_key]


key = "run-1/respond/0"
first = acknowledge(key, "alr-1001")
retry_after_unknown_outcome = acknowledge(key, "alr-1001")
print(first == retry_after_unknown_outcome, len(effects))
```

I would add that the key must be stored by the server durably, otherwise a server restart loses the deduplication and the problem returns.

## Phase 6 — Human-in-the-loop pauses and approvals

### 🟢 Beginner

**Q:** Why pause for a human, and what does the run look like while it is paused?

**A:** Some actions, such as acknowledging an alert, change real state and should not happen unless a person says yes. When the responder asks for a write, both the step and the run move to `waiting_approval`, the process can exit, and nothing holds a thread or a connection. A person then runs `approve` or `deny` for that step, and `resume` continues or ends the run. The default is deny, so with no recorded approval the write never runs.

### 🟡 Intermediate

**Q:** How is the pause built on the approval gate you already had?

**A:** I reuse `ApprovalGate` from module 03 unchanged and give it a new approver, `StoreApprover`. The approver returns true only when the step has a granted approval recorded for the exact tool and arguments, and otherwise it returns false and remembers the call. After the agent finishes, a remembered call pauses the step with that call stored, and whatever the model said after the denial is discarded. `deny` moves the step and the run to failed in one transaction, and resuming after an approval does not count as a new attempt.

**Source:** `AI/agent-lab/agent/approval.py:34-47`

```python
class ApprovalGate:
    """Trusts read_only because this client owns the server; for a third-party server use an allowlist."""

    def __init__(self, approver: Approver = deny_all) -> None:
        self._approver = approver

    def decide(self, call: ToolCall, tool: ToolSpec) -> Decision:
        if tool.read_only:
            return Decision(True, "read-only tool")
        try:
            approved = self._approver(call, tool)
        except Exception:
            return Decision(False, "approver failed; denied")
        return Decision(approved, "approved by approver" if approved else "denied by approver")
```

**Source:** `AI/agent-lab/orchestrator/journal.py:61-68`

```python
    def __call__(self, call: ToolCall, tool: ToolSpec) -> bool:
        wanted = json.dumps({"tool": call.name, "arguments": call.arguments}, sort_keys=True)
        step = self._store.get_step(self._run_id, self._step_id)
        if step is not None and step.approval == "granted" and step.pending_call == wanted:
            return True
        if self.requested is None:
            self.requested = wanted
        return False
```

**Source:** `AI/agent-lab/orchestrator/store.py:229-234`

```python
    def pause_for_approval(self, run_id: str, step_id: str, pending_call: str) -> None:
        with self._tx() as db:
            self._move_step(db, run_id, step_id, WAITING_APPROVAL, None, pending_call=pending_call,
                            call=json.loads(pending_call))
            db.execute("UPDATE steps SET approval = NULL WHERE run_id = ? AND step_id = ?", (run_id, step_id))
            self._move_run(db, run_id, WAITING_APPROVAL, None, None, None, step=step_id)
```

I would point at `step.pending_call == wanted`: the human approved one specific call, so a model that changes an argument after approval triggers a new pause instead of riding the old approval.

### 🔴 Senior

**Q:** What are the weaknesses of this approval design?

**A:** Pausing in the middle of a step wastes work, because the responder's first model turn is re-run after approval and only the tool calls before it are replayed from the journal. Binding approval to the exact arguments is safer, and a test shows a changed argument pausing again with zero writes, but it is annoying with a non-deterministic model. The approval also covers any identical repeat of that call inside the step, which I accepted because the journal replays the first one anyway. The biggest gap is identity: `approve` records no approver, no expiry and no authentication, so anyone who can write to the database can approve. I measured only that the pause, approve, deny and changed-argument tests pass, and I measured nothing about how long a real human takes.

**Follow-up they will ask:** What happens if nobody ever approves?

**A:** The run stays in `waiting_approval` forever, because I built no timeout and no escalation. `cancel` exists and moves the run and its open steps to cancelled in one transaction, so an operator can end it. I would add an expiry event that fails the run after a deadline, and I would record who approved, but neither is built.

## Phase 7 — Observability and testing an orchestrator (the crash matrix)

### 🟢 Beginner

**Q:** How can you see what an orchestrated run did?

**A:** Every state change appends an event in the same transaction as the change itself, and `describe` prints each step with its status and attempt followed by the event timeline. The tool calls inside a step also go to the existing JSONL audit log, tagged with the run, the step and the attempt. The `status` command of the CLI prints that timeline. So I can answer "what happened to this run" from the database without a debugger.

### 🟡 Intermediate

**Q:** How do you test that a process can die at any boundary?

**A:** I put named crash hooks at five boundaries and a `SimulatedCrash` that derives from `BaseException`, so none of the engine's `except Exception` blocks can turn a dead process into a failed step. The test harness boots a fresh orchestrator on the same SQLite file for each simulated process, approves when asked, and resumes until the run is terminal. It then compares the final output with an uninterrupted run and counts real write executions in a fake world that survives the restarts. The matrix has nine crash points and every case must give the same output as the uninterrupted run and exactly one real write.

**Source:** `AI/agent-lab/orchestrator/crash.py:15-16`

```python
class SimulatedCrash(BaseException):
    """BaseException on purpose: no `except Exception` in the engine may turn a dead process into a failed step."""
```

**Source:** `AI/agent-lab/tests/test_orchestrator_crash.py:8-18`

```python
CRASH_MATRIX = [
    pytest.param(BEFORE_STEP, "plan", id="before-first-step"),
    pytest.param(BEFORE_STEP, "respond", id="before-write-step"),
    pytest.param(STEP_STARTED, "respond", id="write-step-running-at-crash"),
    pytest.param(TOOL_JOURNALED, "respond", id="after-write-journaled-before-commit"),
    pytest.param(AFTER_STEP_COMMIT, "respond", id="after-write-step-commit"),
    pytest.param(AFTER_STEP_COMMIT, "work-alerts", id="mid-fan-out-after-first-worker"),
    pytest.param(BEFORE_STEP, "work-metrics", id="mid-fan-out-before-second-worker"),
    pytest.param(TOOL_JOURNALED, "work-metrics", id="mid-fan-out-read-journaled-before-commit"),
    pytest.param(TOOL_EXECUTED, "work-metrics", id="mid-fan-out-read-executed-not-journaled"),
]
```

**Source:** `AI/agent-lab/tests/orchestrator_helpers.py:152-179`

```python
def drive(tmp_path: Path, point: str | None = None, step_id: str | None = None, max_boots: int = 8) -> Outcome:
    """Boot a fresh orchestrator per 'process', approve when asked, until the run is terminal."""
    db, world, hook = tmp_path / "o.db", World(), OneShotCrash(point, step_id)
    llm_created: list[tuple[str, int]] = []

    def factory(role: AgentRole, step: str, attempt: int) -> LLM:
        llm_created.append((step, attempt))
        return reactive_llm(role, step, attempt)

    crashes, summary = 0, None
    for boot in range(max_boots):
        orchestrator, store = make_orchestrator(db, world, llm_factory=factory, crash=hook)
        try:
            if boot == 0:
                summary = run(orchestrator.run("triage", INPUT, RUN_ID))
            else:
                if store.get_run(RUN_ID).status == WAITING_APPROVAL:
                    RunControl(store).approve(RUN_ID, "respond")
                summary = run(orchestrator.resume(RUN_ID))
        except SimulatedCrash:
            crashes += 1
            summary = None
        steps = {s.step_id: (s.status, s.attempt) for s in store.steps(RUN_ID)}
        event_types = [e.type for e in store.events(RUN_ID)]
        store.close()
        if summary is not None and summary.status in TERMINAL:
            return Outcome(summary, world, crashes, steps, event_types, llm_created)
    raise AssertionError("run did not reach a terminal state")
```

I would point at the fresh `make_orchestrator` per loop turn: nothing in memory survives between boots except the database file and the fake world, which is what a real restart gives me.

### 🔴 Senior

**Q:** How do you know the crash test would catch a broken journal, and what does it not cover?

**A:** I ran a mutation check in a scratch copy: I replaced the journal lookup with `entry = None`, which keeps writing the journal but never reads it, and five tests went red, namely the crash after the write is journaled, the attempt-plus-one test, the replay test, the unknown-window test and a CLI crash test. In a second scratch copy I disabled the "step already succeeded" shortcut and six tests failed and ten errored. Neither bypass is in the repo. The matrix does not cover a real process kill, because the crash is an in-process exception, nor torn disk writes, power loss, two concurrent resumers or a real model's non-determinism. On this laptop the orchestrator tests run in about two seconds and one committed SQLite transaction with `synchronous=FULL` took about 0.11 to 0.14 ms in two runs of 1000, so the matrix is cheap enough to run on every change.

**Follow-up they will ask:** What would you add next to trust this further?

**A:** I would add a test that starts the CLI as a subprocess and kills it with SIGKILL at random moments in a loop, then resumes and checks the same invariants, because that exercises a real process death and not an exception. I would add a lease so two resumers cannot run the same run. I also did not verify whether `synchronous=FULL` is enough to survive power loss on macOS, so verify that in the SQLite and macOS documentation before claiming durability beyond a process crash. None of these is built.

**Illustrative (not from the repo):** the exact one-line mutation I applied to a scratch copy of `journal.py`, shown as a diff.

```diff
-        entry = self._store.journal_get(self._run_id, self._step_id, index)
+        entry = None
```

## Code reference index

| path:lines | what it shows |
|---|---|
| `AI/agent-lab/orchestrator/engine.py:220-242` | One step is one bounded agent run; how a step outcome is classified. |
| `AI/agent-lab/orchestrator/engine.py:211-218` | Cancel, wall-clock budget and global step limit checked before each attempt. |
| `AI/agent-lab/orchestrator/engine.py:112-119` | `resume`: terminal runs return, unapproved pauses stay paused, otherwise re-drive. |
| `AI/agent-lab/orchestrator/engine.py:167-186` | `_run_step`: reuse a succeeded step, crash-loop cap, `begin_attempt`. |
| `AI/agent-lab/orchestrator/engine.py:203-209` | Give up after max attempts, otherwise schedule a retry and sleep. |
| `AI/agent-lab/orchestrator/roles.py:11-20` | `AgentRole` and `visible_tools`, the allowlist. |
| `AI/agent-lab/orchestrator/plan.py:43-55` | Plan validation against a JSON schema. |
| `AI/agent-lab/orchestrator/triage.py:59-69` | The example workflow: plan, fan-out, aggregate, handoff. |
| `AI/agent-lab/orchestrator/guards.py:38-48` | Handoff guard: cycle, undeclared target, max handoffs. |
| `AI/agent-lab/orchestrator/guards.py:25-26` | Full-jitter backoff. |
| `AI/agent-lab/orchestrator/journal.py:27-49` | The tool-call journal and replay. |
| `AI/agent-lab/orchestrator/journal.py:61-68` | `StoreApprover`: approve only the exact granted call. |
| `AI/agent-lab/orchestrator/store.py:229-234` | Pause a step and its run for approval in one transaction. |
| `AI/agent-lab/orchestrator/crash.py:15-16` | `SimulatedCrash` as a `BaseException`. |
| `AI/agent-lab/agent/approval.py:34-47` | The default-deny `ApprovalGate` the orchestrator reuses. |
| `AI/agent-lab/tests/test_orchestrator_crash.py:8-18` | The nine crash points of the matrix. |
| `AI/agent-lab/tests/orchestrator_helpers.py:152-179` | The crash harness: fresh boot per simulated process. |
| `AI/agent-lab/tests/test_orchestrator_engine.py:99-111` | A call outside the allowlist is refused and never executed. |
| `AI/agent-lab/tests/test_orchestrator_engine.py:220-237` | A handoff cycle fails the run before the second handoff. |
| `AI/agent-lab/orchestrator/store.py` | Schema, status tables, append-only events, one transaction per transition. |
| `AI/agent-lab/orchestrator/cli.py` | `run`, `resume`, `status`, `approve`, `deny`, `cancel` and `--crash-at` for a live demo. |
| `AI/agent-lab/NOTES.md` | The single-agent design this module builds on. |

## Self-check

1. **What does a step contain in this orchestrator?** One `run_agent` call with the role's prompt, the role's filtered tool list and the role's turn cap, whose output is stored when the step commits.
2. **Why is `SimulatedCrash` a `BaseException`?** So that no `except Exception` in the engine can turn a simulated dead process into a failed step.
3. **A write tool executed and then the process died before the journal row was written; what does resume do?** It refuses to repeat the write and fails the run as outcome unknown, so the write ran once and a human decides what to do next.
4. **Which parts of a step are re-run on resume and which are replayed?** The model turns are re-run, and journaled tool calls are replayed from their stored results.
5. **Why does approval bind to the exact tool and arguments?** So that a model which changes an argument after a human approved cannot ride the old approval, and the run pauses again.

## What not to claim

- Do not say this is a distributed workflow engine: it is one process on one SQLite file, with no lease, so two resumers of one run would both execute it.
- Do not compare it with Temporal, LangGraph or AWS Step Functions from memory; I did not use them here, and their exact guarantees should be verified in the current docs.
- Do not say it gives exactly-once execution: steps are at-least-once, and the window between a write and its journal row is handled as at-most-once with a failed run.
- Do not say the whole step is replayed from the journal: the model turns inside a step are re-run on resume and only tool calls are journaled, so a non-deterministic model can diverge.
- Do not claim concurrency: the fan-out is a sequential loop, and I did not build or test parallel workers.
- Do not claim a model routes between agents: the route is plain Python in `triage`, and no model-routed supervisor was built.
- Do not claim multi-agent improved answers: the demo model is scripted, and no comparison against a single agent was run.
- Do not claim the crash matrix proves survival of a real kill, a torn write or a power loss: the crash is an in-process exception and I did not verify macOS fsync behaviour.
- Do not claim approvals are authenticated: `approve` records no identity, no expiry and no authentication, and nothing escalates a pause nobody answers.
- Do not claim anything about how OrbitronAI's Galaxy platform works: I only know the phrases it advertises, and I have not seen its internals.
- Do not claim the mutation checks are automated: I did them by hand in scratch copies and the bypasses are not in the repo.
