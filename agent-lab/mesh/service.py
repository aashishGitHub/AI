from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from agent.approval import Approver, ApprovalGate, deny_all
from agent.audit import AuditLog
from agent.executor import ToolExecutor
from agent.grounding import IDENTIFIER_ARGS
from agent.llm import LLM
from agent.loop import SYSTEM_PROMPT, run_agent
from agent.mcp_backend import ToolBackend
from agent.types import ToolSpec
from mesh.card import AgentCard
from mesh.envelope import Envelope, EnvelopeError, check_read_token, verify
from mesh.tasks import TaskStore, TaskView
from orchestrator.roles import AgentRole

BackendFactory = Callable[[Envelope], ToolBackend]
LLMFactory = Callable[[AgentRole, Envelope], LLM]


class WrongRecipient(EnvelopeError):
    pass


class AgentService:
    """handle() is the only entry point; HTTP and the queue worker both call it, so dedupe and checks live once."""

    def __init__(
        self,
        card: AgentCard,
        role: AgentRole,
        tools: Sequence[ToolSpec],
        backend_factory: BackendFactory,
        llm_factory: LLMFactory,
        secret: bytes,
        store: TaskStore,
        audit_stream: TextIO,
        approver: Approver = deny_all,
        max_hops: int = 3,
        tool_timeout_s: float = 10.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.card = card
        self._role = role
        self._tools = role.visible_tools(tools)
        self._backend_factory = backend_factory
        self._llm_factory = llm_factory
        self._secret = secret
        self.store = store
        self._audit_stream = audit_stream
        self._approver = approver
        self._max_hops = max_hops
        self._tool_timeout_s = tool_timeout_s
        self._clock = clock

    def read(self, message_id: str) -> TaskView | None:
        return self.store.get(message_id)

    def check_read_token(self, message_id: str, token: str) -> bool:
        return check_read_token(self._secret, message_id, token)

    async def handle(self, env: Envelope) -> TaskView:
        verify(env, self._secret, self._clock(), self._max_hops)
        if env.recipient != self.card.name:
            raise WrongRecipient(f"envelope is for {env.recipient}, this is {self.card.name}")
        view, created = self.store.begin(env.message_id, env.correlation_id)
        if not created:
            return view
        audit = AuditLog(self._audit_stream, run_id=env.correlation_id)
        audit.record("task_received", agent=self.card.name, message_id=env.message_id,
                     sender=env.sender, hop_count=env.hop_count)
        state, result = await self._run(env, audit)
        audit.record("task_finished", agent=self.card.name, message_id=env.message_id, state=state)
        return self.store.finish(env.message_id, state, result)

    async def _run(self, env: Envelope, audit: AuditLog) -> tuple[Any, dict[str, Any]]:
        prompt = env.payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return "failed", {"error": "payload.prompt must be a non-empty string"}
        executor = ToolExecutor(self._backend_factory(env), self._tools, ApprovalGate(self._approver),
                                default_timeout_s=self._tool_timeout_s, grounded_args=IDENTIFIER_ARGS)
        try:
            run = await asyncio.wait_for(
                run_agent(prompt, self._llm_factory(self._role, env), executor, self._tools, audit,
                          max_steps=self._role.max_steps, system_prompt=self._role.system_prompt or SYSTEM_PROMPT),
                max(env.deadline - self._clock(), 0.0))
        except TimeoutError:
            return "failed", {"error": "deadline_exceeded"}
        except Exception as exc:
            audit.record("task_error", error=type(exc).__name__)
            return "failed", {"error": type(exc).__name__}
        denied = [{"tool": r.call.name, "arguments": r.call.arguments} for r in run.tool_records if r.error_kind == "denied"]
        result = {"final_text": run.final_text, "stop_reason": run.stop_reason, "steps": run.steps,
                  "tools_called": [r.call.name for r in run.tool_records if r.executed]}
        if denied:
            return "input-required", {**result, "needs_approval": denied}
        return ("completed" if run.stop_reason == "final" else "failed"), result


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def build_app(service: AgentService, ready: Callable[[], bool] = lambda: True) -> Starlette:
    async def post_task(request: Request) -> Response:
        try:
            env = Envelope.from_dict(json.loads(await request.body()))
        except (json.JSONDecodeError, EnvelopeError, AttributeError, TypeError):
            return _error(400, "malformed envelope")
        try:
            view = await service.handle(env)
        except WrongRecipient as exc:
            return _error(421, str(exc))
        except EnvelopeError as exc:
            return _error(_ENVELOPE_STATUS.get(type(exc).__name__, 400), str(exc))
        except Exception:
            return _error(500, "internal error")
        return JSONResponse(view.to_dict(), status_code=202 if view.state == "working" else 200)

    async def get_task(request: Request) -> Response:
        message_id = request.path_params["message_id"]
        if not service.check_read_token(message_id, request.headers.get("x-mesh-token", "")):
            return _error(401, "bad read token")
        view = service.read(message_id)
        return _error(404, "unknown task") if view is None else JSONResponse(view.to_dict())

    async def card(request: Request) -> Response:
        return JSONResponse(service.card.to_dict())

    async def healthz(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    async def readyz(request: Request) -> Response:
        ok = ready()
        return JSONResponse({"status": "ready" if ok else "not-ready"}, status_code=200 if ok else 503)

    return Starlette(routes=[
        Route("/tasks", post_task, methods=["POST"]),
        Route("/tasks/{message_id}", get_task, methods=["GET"]),
        Route("/agent-card", card, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/readyz", readyz, methods=["GET"]),
    ])


_ENVELOPE_STATUS = {"BadSignature": 401, "Expired": 408, "TooManyHops": 422}
