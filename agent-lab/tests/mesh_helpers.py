from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from starlette.responses import JSONResponse

from agent.approval import Approver, deny_all
from agent.llm import ScriptedLLM
from agent.mcp_backend import ToolBackend, connect_mcp
from agent.types import ToolSpec
from mcp_server.server import build_server
from mcp_server.store import FixtureStore
from mesh.card import AgentCard, Registry
from mesh.client import MeshClient
from mesh.delegate import AgentToolBackend, CallContext, HttpTransport, Transport, agent_tool_spec
from mesh.scripts import INVESTIGATOR_SCRIPT, TRIAGE_SCRIPT
from mesh.service import AgentService, build_app
from mesh.tasks import TaskStore
from orchestrator.roles import AgentRole
from tests.helpers import scripted

SECRET = b"test-secret"
NOW = 1_000.0


class ZeroJitter:
    def uniform(self, a: float, b: float) -> float:
        return 0.0


class Sleeps:
    def __init__(self, on_sleep: Callable[[], None] | None = None) -> None:
        self.calls: list[float] = []
        self._on_sleep = on_sleep

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self._on_sleep:
            self._on_sleep()


class Built:
    def __init__(self, service: AgentService, llms: list[ScriptedLLM], store: TaskStore, audit: io.StringIO) -> None:
        self.service = service
        self.llms = llms
        self.store = store
        self.audit = audit
        self.app = build_app(service)


def build_service(
    name: str,
    role: AgentRole,
    tools: list[ToolSpec],
    backend: ToolBackend,
    script: list[dict[str, Any]],
    approver: Approver = deny_all,
    max_hops: int = 3,
    store: TaskStore | None = None,
) -> Built:
    llms: list[ScriptedLLM] = []

    def llm_factory(_: AgentRole, __: Any) -> ScriptedLLM:
        llm = scripted(*script)
        llms.append(llm)
        return llm

    store = store or TaskStore()
    audit = io.StringIO()
    card = AgentCard(name, "1", f"{name} agent.", f"http://{name}", ("triage",))
    service = AgentService(card, role, tools, lambda env: backend, llm_factory, SECRET, store, audit,
                           approver=approver, max_hops=max_hops, clock=lambda: NOW)
    return Built(service, llms, store, audit)


def mesh_client(app: Any, sleeps: Sleeps | None = None, max_attempts: int = 3, sender: str = "caller") -> MeshClient:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://agent")
    return MeshClient(http, SECRET, sender, max_attempts=max_attempts, rng=ZeroJitter(),
                      sleep=sleeps or Sleeps(), clock=lambda: NOW)


class PostTasksCounter:
    """Counts POST /tasks and can fail the first N: before the app runs, or after it ran (response lost)."""

    def __init__(self, app: Any, fail_before: int = 0, lose_response: int = 0, status: int = 503) -> None:
        self._app = app
        self._fail_before = fail_before
        self._lose_response = lose_response
        self._status = status
        self.posts = 0

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"] == "/tasks" and scope["method"] == "POST":
            self.posts += 1
            if self._fail_before > 0:
                self._fail_before -= 1
                await JSONResponse({"error": "unavailable"}, status_code=self._status)(scope, receive, send)
                return
            if self._lose_response > 0:
                self._lose_response -= 1

                async def discard(_: Any) -> None:
                    return None

                await self._app(scope, receive, discard)
                await JSONResponse({"error": "gateway timeout"}, status_code=504)(scope, receive, send)
                return
        await self._app(scope, receive, send)


READ_TOOLS = frozenset({"get_live_metrics", "list_active_alerts", "explain_alert"})
INVESTIGATOR_CARD = AgentCard("investigator", "1", "Reads alerts and metrics for one tenant.",
                              "http://investigator", ("read-alerts",))
TRIAGE_CARD = AgentCard("triage", "1", "Triages a tenant by asking the investigator.", "http://triage", ("triage",))


class Rig:
    def __init__(self, investigator: AgentService, triage: AgentService, inv_audit: io.StringIO,
                 tri_audit: io.StringIO) -> None:
        self.investigator = investigator
        self.triage = triage
        self.inv_audit = inv_audit
        self.tri_audit = tri_audit
        self.entry = MeshClient(httpx2.AsyncClient(transport=httpx2.ASGITransport(app=build_app(triage)),
                                                   base_url="http://triage"),
                                SECRET, "user", rng=ZeroJitter(), sleep=Sleeps(), clock=lambda: NOW)

    async def triage_task(self, correlation_id: str, hop_count: int = 0) -> dict[str, Any]:
        env = self.entry.make_envelope("triage", "Triage tenant streamflix.", correlation_id, NOW + 30, hop_count)
        return await self.entry.send("http://triage", env)

    def inv_log(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.inv_audit.getvalue().splitlines()]

    def tri_log(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.tri_audit.getvalue().splitlines()]


@asynccontextmanager
async def rig(transport_for: Callable[[AgentService], Transport], investigator_max_hops: int = 3,
              triage_script: list[dict[str, Any]] | None = None) -> AsyncIterator[Rig]:
    async with connect_mcp(build_server(FixtureStore())) as mcp_backend:
        tools = await mcp_backend.list_tools()
        inv_audit, tri_audit = io.StringIO(), io.StringIO()
        investigator = AgentService(
            INVESTIGATOR_CARD, AgentRole("investigator", READ_TOOLS, max_steps=3), tools, lambda env: mcp_backend,
            lambda role, env: scripted(*INVESTIGATOR_SCRIPT), SECRET, TaskStore(), inv_audit,
            max_hops=investigator_max_hops, clock=lambda: NOW)
        ask_tool = agent_tool_spec(INVESTIGATOR_CARD)
        registry = Registry((INVESTIGATOR_CARD,))
        transport = transport_for(investigator)
        triage = AgentService(
            TRIAGE_CARD, AgentRole("triage", frozenset({ask_tool.name}), max_steps=3), [ask_tool],
            lambda env: AgentToolBackend(registry, transport, CallContext(env.correlation_id, env.hop_count, env.deadline)),
            lambda role, env: scripted(*(triage_script or TRIAGE_SCRIPT)), SECRET, TaskStore(), tri_audit,
            clock=lambda: NOW)
        yield Rig(investigator, triage, inv_audit, tri_audit)


def http_to(service: AgentService) -> HttpTransport:
    client = MeshClient(httpx2.AsyncClient(transport=httpx2.ASGITransport(app=build_app(service)),
                                           base_url="http://investigator"),
                        SECRET, "triage", rng=ZeroJitter(), sleep=Sleeps(), clock=lambda: NOW)
    return HttpTransport(client)
