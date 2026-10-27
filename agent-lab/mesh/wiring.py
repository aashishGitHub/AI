from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TextIO

import httpx2
import uvicorn
from starlette.applications import Starlette

from agent.llm import LLM, ScriptedLLM, turns_from_dicts
from agent.mcp_backend import connect_mcp
from agent.ollama import OllamaLLM
from mesh.card import AgentCard, Registry
from mesh.client import MeshClient
from mesh.delegate import AgentToolBackend, CallContext, HttpTransport, agent_tool_spec
from mesh.scripts import INVESTIGATOR_SCRIPT, TRIAGE_SCRIPT
from mesh.service import AgentService, LLMFactory, build_app
from mesh.tasks import TaskStore
from orchestrator.roles import AgentRole

READ_TOOLS = frozenset({"get_live_metrics", "list_active_alerts", "explain_alert"})
INVESTIGATOR_CARD = AgentCard("investigator", "1", "Reads alerts and metrics for one tenant.", "", ("read-alerts",))
TRIAGE_CARD = AgentCard("triage", "1", "Triages a tenant by asking the investigator.", "", ("triage",))


def llm_factory(kind: str, script: list[dict[str, Any]], model: str = "", ollama_url: str = "") -> LLMFactory:
    if kind == "ollama":
        return lambda role, env: OllamaLLM(model, base_url=ollama_url)
    return lambda role, env: ScriptedLLM(turns_from_dicts(script))


@asynccontextmanager
async def investigator_app(mcp_url: str, secret: bytes, db: Path | str, audit: TextIO, base_url: str,
                           llm: LLMFactory | None = None) -> AsyncIterator[Starlette]:
    up = {"mcp": False}
    async with connect_mcp(mcp_url) as backend:
        tools = await backend.list_tools()
        up["mcp"] = True
        card = AgentCard(**{**INVESTIGATOR_CARD.to_dict(), "endpoint": base_url, "skills": INVESTIGATOR_CARD.skills})
        service = AgentService(card, AgentRole("investigator", READ_TOOLS, max_steps=3), tools, lambda env: backend,
                               llm or llm_factory("scripted", INVESTIGATOR_SCRIPT), secret, TaskStore(db), audit)
        yield build_app(service, ready=lambda: up["mcp"])


@asynccontextmanager
async def triage_app(investigator_url: str, secret: bytes, db: Path | str, audit: TextIO, base_url: str,
                     llm: LLMFactory | None = None) -> AsyncIterator[Starlette]:
    card = AgentCard(**{**TRIAGE_CARD.to_dict(), "endpoint": base_url, "skills": TRIAGE_CARD.skills})
    peer = AgentCard(**{**INVESTIGATOR_CARD.to_dict(), "endpoint": investigator_url, "skills": INVESTIGATOR_CARD.skills})
    ask_tool = agent_tool_spec(peer)
    transport = HttpTransport(MeshClient(httpx2.AsyncClient(), secret, "triage"))

    def backend_for(env: Any) -> AgentToolBackend:
        return AgentToolBackend(Registry((peer,)), transport, CallContext(env.correlation_id, env.hop_count, env.deadline))

    service = AgentService(card, AgentRole("triage", frozenset({ask_tool.name}), max_steps=3), [ask_tool], backend_for,
                           llm or llm_factory("scripted", TRIAGE_SCRIPT), secret, TaskStore(db), audit)
    yield build_app(service)


class Served:
    def __init__(self, server: uvicorn.Server, task: "asyncio.Task[None]") -> None:
        self._server = server
        self._task = task

    async def stop(self) -> None:
        self._server.should_exit = True
        await self._task


async def serve(app: Starlette, host: str, port: int) -> Served:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            task.result()
        await asyncio.sleep(0.02)
    return Served(server, task)


def deadline_in(seconds: float, clock: Callable[[], float] = time.time) -> float:
    return clock() + seconds
