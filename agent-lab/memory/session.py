from __future__ import annotations

from mcp.client.stdio import StdioServerParameters
from mcp.server import MCPServer

from agent.approval import ApprovalGate, Approver, deny_all
from agent.audit import AuditLog
from agent.executor import ToolExecutor
from agent.grounding import IDENTIFIER_ARGS
from agent.llm import LLM
from agent.loop import SYSTEM_PROMPT, RunResult, run_agent
from agent.mcp_backend import connect_mcp
from memory.render import build_memory_context
from memory.retrieval import Retriever
from memory.store import MemoryStore
from memory.tools import MemoryToolBackend


async def run_memory_session(
    prompt: str,
    llm: LLM,
    server: StdioServerParameters | MCPServer,
    audit: AuditLog,
    store: MemoryStore,
    retriever: Retriever,
    tenant_id: str,
    run_id: str,
    approver: Approver = deny_all,
    max_steps: int = 8,
    system_prompt: str = SYSTEM_PROMPT,
) -> RunResult:
    context = build_memory_context(store, tenant_id, prompt, retriever=retriever)
    async with connect_mcp(server) as inner:
        backend = MemoryToolBackend(inner, store, retriever, tenant_id, run_id, audit=audit)
        tools = await backend.list_tools()
        executor = ToolExecutor(backend, tools, ApprovalGate(approver), grounded_args=IDENTIFIER_ARGS)
        return await run_agent(prompt, llm, executor, tools, audit, max_steps, system_prompt + context)
