from __future__ import annotations

import argparse
from pathlib import Path

from mcp_server.server import build_server
from mcp_server.store import FixtureStore


def main() -> None:
    parser = argparse.ArgumentParser(description="StreamPulse MCP server (Python, fixture data) over stdio")
    parser.add_argument("--state-file", type=Path, help="write acknowledgements and issue links here as JSON")
    args = parser.parse_args()
    build_server(FixtureStore(state_path=args.state_file)).run("stdio")


if __name__ == "__main__":
    main()
