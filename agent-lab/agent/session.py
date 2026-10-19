from __future__ import annotations

from mcp.client.stdio import StdioServerParameters
from mcp.server import MCPServer

from agent.approval import Approver, ApprovalGate, deny_all
from agent.audit import AuditLog
from agent.executor import ToolExecutor
from agent.llm import LLM
from agent.loop import SYSTEM_PROMPT, RunResult, run_agent
from agent.mcp_backend import connect_mcp


async def run_session(
    prompt: str,
    llm: LLM,
    server: StdioServerParameters | MCPServer,
    audit: AuditLog,
    approver: Approver = deny_all,
    max_steps: int = 8,
    system_prompt: str = SYSTEM_PROMPT,
) -> RunResult:
    async with connect_mcp(server) as backend:
        tools = await backend.list_tools()
        executor = ToolExecutor(backend, tools, ApprovalGate(approver))
        return await run_agent(prompt, llm, executor, tools, audit, max_steps, system_prompt)
