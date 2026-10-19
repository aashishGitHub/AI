from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server import MCPServer
from mcp.types import TextContent

from agent.types import ToolOutput, ToolSpec

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ToolBackend(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput: ...


class McpToolBackend:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def list_tools(self) -> list[ToolSpec]:
        listing = await self._client.list_tools()
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.input_schema,
                read_only=bool(tool.annotations and tool.annotations.read_only_hint is True),
            )
            for tool in listing.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutput:
        result = await self._client.call_tool(name, arguments)
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        return ToolOutput(content=text or "[no text content]", is_error=result.is_error)


def stdio_server_params(state_file: Path | None) -> StdioServerParameters:
    args = ["-m", "mcp_server"]
    if state_file is not None:
        args += ["--state-file", str(state_file)]
    return StdioServerParameters(command=sys.executable, args=args, cwd=PROJECT_ROOT)


@asynccontextmanager
async def connect_mcp(server: StdioServerParameters | MCPServer) -> AsyncIterator[McpToolBackend]:
    async with Client(server) as client:
        yield McpToolBackend(client)
