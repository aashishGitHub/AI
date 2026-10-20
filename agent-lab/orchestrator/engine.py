from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from agent.approval import ApprovalGate
from agent.audit import AuditLog
from agent.executor import ToolExecutor
from agent.grounding import IDENTIFIER_ARGS
from agent.llm import LLM
from agent.loop import run_agent
from agent.mcp_backend import ToolBackend
from agent.types import ToolSpec
from orchestrator.crash import AFTER_STEP_COMMIT, BEFORE_STEP, STEP_STARTED, CrashHook, no_crash
from orchestrator.errors import BudgetExceeded, RunPaused, RunStopped, StepFailed, WorkflowError
from orchestrator.guards import HandoffGuard, Limits, Uniform, full_jitter_delay
from orchestrator.journal import JournalingBackend, StoreApprover
from orchestrator.roles import AgentRole, PromptProvider, check_roles
from orchestrator.store import (
    CANCELLED, FAILED, RUNNING, SUCCEEDED, TERMINAL, WAITING_APPROVAL, InvalidTransition, RunRow, WorkflowStore, utc_now,
)

Workflow = Callable[["RunContext"], Awaitable[str]]
LLMFactory = Callable[[AgentRole, str, int], LLM]
Validate = Callable[[str], object]


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    output: str | None
    error: str | None


@dataclass(frozen=True)
class _Done:
    text: str


@dataclass(frozen=True)
class _Retry:
    reason: str


@dataclass(frozen=True)
class _Fatal:
    reason: str


@dataclass(frozen=True)
class _Pause:
    call: str


class _Discard:
    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None


class Orchestrator:
    def __init__(
        self,
        store: WorkflowStore,
        backend: ToolBackend,
        tools: Sequence[ToolSpec],
        roles: Sequence[AgentRole],
        workflows: Mapping[str, Workflow],
        llm_factory: LLMFactory,
        *,
        limits: Limits = Limits(),
        prompt_provider: PromptProvider | None = None,
        audit_stream=None,
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Uniform | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
        crash: CrashHook = no_crash,
        grounded_args: Collection[str] = IDENTIFIER_ARGS,
    ) -> None:
        check_roles(roles, tools)
        self.store = store
        self.backend = backend
        self.tools = list(tools)
        self.roles = {r.name: r for r in roles}
        self.workflows = dict(workflows)
        self.llm_factory = llm_factory
        self.limits = limits
        self.prompt_provider = prompt_provider
        self.audit_stream = audit_stream or _Discard()
        self.clock = clock
        self.sleeper = sleeper
        self.rng = rng or random.Random()
        self.new_id = new_id
        self.crash = crash
        self.grounded_args = frozenset(grounded_args)

    async def run(self, workflow: str, input_: str, run_id: str | None = None) -> RunSummary:
        if workflow not in self.workflows:
            raise KeyError(f"unknown workflow {workflow}")
        run = self.store.create_run(run_id or self.new_id(), workflow, input_)
        self.store.set_run_status(run.run_id, RUNNING, event="run_started")
        return await self._drive(run.run_id)

    async def resume(self, run_id: str) -> RunSummary:
        run = self.store.get_run(run_id)
        if run.status in TERMINAL:
            return _summary(run)
        if run.status == WAITING_APPROVAL and not self._approval_granted(run_id):
            return _summary(run)
        self.store.set_run_status(run_id, RUNNING, event="run_resumed")
        return await self._drive(run_id)

    def _approval_granted(self, run_id: str) -> bool:
        return any(s.status == WAITING_APPROVAL and s.approval == "granted" for s in self.store.steps(run_id))

    async def _drive(self, run_id: str) -> RunSummary:
        run = self.store.get_run(run_id)
        try:
            output = await self.workflows[run.workflow](RunContext(self, run))
        except (RunPaused, RunStopped):
            pass
        except WorkflowError as exc:
            self.store.set_run_status(run_id, FAILED, error=str(exc))
        except InvalidTransition:
            if self.store.get_run(run_id).status != CANCELLED:
                raise
        else:
            self.store.set_run_status(run_id, SUCCEEDED, output=output)
        return _summary(self.store.get_run(run_id))

    def system_prompt(self, role: AgentRole) -> str:
        return self.prompt_provider(role.name) if self.prompt_provider else role.system_prompt


class RunContext:
    def __init__(self, orchestrator: Orchestrator, run: RunRow) -> None:
        self._o = orchestrator
        self.run_id = run.run_id
        self.input = run.input
        self._guard = HandoffGuard(orchestrator.limits.max_handoffs)
        self._started = orchestrator.clock()

    async def step(self, step_id: str, role: str, prompt: str, validate: Validate | None = None) -> str:
        self._guard.begin(role)
        return await self._run_step(step_id, self._role(role), prompt, validate)

    async def handoff(self, step_id: str, to_role: str, prompt: str, validate: Validate | None = None) -> str:
        current = self._guard.current
        self._guard.hand_off(to_role, self._role(current).handoff_to)
        if self._o.store.get_step(self.run_id, step_id) is None:
            self._o.store.append_event(self.run_id, "handoff", step=step_id, **{"from": current, "to": to_role})
        return await self._run_step(step_id, self._role(to_role), prompt, validate)

    def _role(self, name: str) -> AgentRole:
        if name not in self._o.roles:
            raise WorkflowError(f"unknown role {name}")
        return self._o.roles[name]

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
            if isinstance(outcome, _Done):
                if validate is not None:
                    try:
                        validate(outcome.text)
                    except WorkflowError as exc:
                        store.fail_step(self.run_id, step_id, str(exc))
                        raise
                store.succeed_step(self.run_id, step_id, outcome.text)
                o.crash(AFTER_STEP_COMMIT, step_id)
                return outcome.text
            if isinstance(outcome, _Pause):
                store.pause_for_approval(self.run_id, step_id, outcome.call)
                raise RunPaused()
            if isinstance(outcome, _Fatal):
                store.fail_step(self.run_id, step_id, outcome.reason)
                raise StepFailed(outcome.reason)
            if row.attempt >= limits.max_attempts:
                reason = f"step {step_id} gave up after {row.attempt} attempts: {outcome.reason}"
                store.fail_step(self.run_id, step_id, reason)
                raise StepFailed(reason)
            delay = full_jitter_delay(row.attempt, limits.backoff_base_s, limits.backoff_cap_s, o.rng)
            store.schedule_retry(self.run_id, step_id, outcome.reason, delay)
            await o.sleeper(delay)

    def _check_may_start(self) -> None:
        o = self._o
        if o.store.get_run(self.run_id).status == CANCELLED:
            raise RunStopped()
        if o.clock() - self._started > timedelta(seconds=o.limits.wall_budget_s):
            raise BudgetExceeded(f"wall-clock budget of {o.limits.wall_budget_s:g} s exceeded")
        if o.store.attempts_started(self.run_id) >= o.limits.global_max_steps:
            raise BudgetExceeded(f"global step limit of {o.limits.global_max_steps} reached")

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


def _summary(run: RunRow) -> RunSummary:
    return RunSummary(run.run_id, run.status, run.output, run.error)
