from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path

import httpx2

from mcp_server.server import build_server
from mcp_server.store import FixtureStore
from mesh.client import MeshClient
from mesh.scripts import INVESTIGATOR_SCRIPT, TRIAGE_SCRIPT
from mesh.wiring import deadline_in, investigator_app, llm_factory, serve, triage_app

HOST = "127.0.0.1"
MCP_PORT, INVESTIGATOR_PORT, TRIAGE_PORT = 8801, 8802, 8803


def _secret() -> bytes:
    value = os.environ.get("MESH_SECRET")
    if not value:
        sys.exit("MESH_SECRET is not set; it signs every envelope between agents")
    return value.encode()


async def _demo() -> None:
    secret = secrets.token_hex(16).encode()
    mcp_url = f"http://{HOST}:{MCP_PORT}/mcp"
    investigator_url = f"http://{HOST}:{INVESTIGATOR_PORT}"
    triage_url = f"http://{HOST}:{TRIAGE_PORT}"
    mcp = await serve(build_server(FixtureStore()).streamable_http_app(), HOST, MCP_PORT)
    try:
        async with (
            investigator_app(mcp_url, secret, ":memory:", sys.stdout, investigator_url) as investigator,
            triage_app(investigator_url, secret, ":memory:", sys.stdout, triage_url) as triage,
        ):
            servers = [await serve(investigator, HOST, INVESTIGATOR_PORT), await serve(triage, HOST, TRIAGE_PORT)]
            try:
                async with httpx2.AsyncClient() as http:
                    client = MeshClient(http, secret, "user")
                    env = client.make_envelope("triage", "Triage tenant streamflix.", "demo-1", deadline_in(30))
                    task = await client.send(triage_url, env)
                print(f"\nresult: {task['state']} -> {task['result']['final_text']}")
            finally:
                for served in servers:
                    await served.stop()
    finally:
        await mcp.stop()


async def _agent(args: argparse.Namespace) -> None:
    secret = _secret()
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    base_url = args.public_url or f"http://{args.host}:{args.port}"
    scripted = llm_factory(args.llm, TRIAGE_SCRIPT if args.name == "triage" else INVESTIGATOR_SCRIPT,
                           args.ollama_model, args.ollama_url)
    with audit_path.open("a") as audit:
        if args.name == "investigator":
            context = investigator_app(args.mcp_url, secret, args.db, audit, base_url, scripted)
        else:
            context = triage_app(args.investigator_url, secret, args.db, audit, base_url, scripted)
        async with context as app:
            served = await serve(app, args.host, args.port)
            try:
                await asyncio.Event().wait()
            finally:
                await served.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mesh")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="MCP over HTTP + investigator + triage on local ports, one delegated task")
    mcp = sub.add_parser("mcp", help="serve the fixture MCP server over streamable HTTP")
    mcp.add_argument("--host", default=HOST)
    mcp.add_argument("--port", type=int, default=MCP_PORT)
    agent = sub.add_parser("agent", help="serve one agent over HTTP (needs MESH_SECRET)")
    agent.add_argument("--name", choices=["investigator", "triage"], required=True)
    agent.add_argument("--host", default=HOST)
    agent.add_argument("--port", type=int, required=True)
    agent.add_argument("--public-url", help="endpoint other agents use to reach this one")
    agent.add_argument("--mcp-url", default=f"http://{HOST}:{MCP_PORT}/mcp")
    agent.add_argument("--investigator-url", default=f"http://{HOST}:{INVESTIGATOR_PORT}")
    agent.add_argument("--db", default="runs/mesh-tasks.db")
    agent.add_argument("--audit", default="runs/mesh-audit.jsonl")
    agent.add_argument("--llm", choices=["scripted", "ollama"], default="scripted")
    agent.add_argument("--ollama-model", default="")
    agent.add_argument("--ollama-url", default="http://localhost:11434")
    args = parser.parse_args(argv)
    if args.command == "demo":
        asyncio.run(_demo())
    elif args.command == "mcp":
        build_server(FixtureStore()).run("streamable-http", host=args.host, port=args.port)
    else:
        asyncio.run(_agent(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
