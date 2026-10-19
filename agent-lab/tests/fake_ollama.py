from __future__ import annotations

import json
import socketserver
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeOllama:
    def __init__(self, responses: list[tuple[int, Any]], delay_s: float = 0.0) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []
        self._delay_s = delay_s

    def handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                outer.paths.append(self.path)
                outer.requests.append(json.loads(self.rfile.read(length)))
                time.sleep(outer._delay_s)
                status, body = outer.responses.pop(0)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args: Any) -> None:
                pass

        return Handler


class QuickServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # HTTPServer.server_bind calls socket.getfqdn(), which blocked for 35 s on the author's machine.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@contextmanager
def serve(fake: FakeOllama) -> Iterator[str]:
    server = QuickServer(("127.0.0.1", 0), fake.handler())
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def text_response(content: str) -> tuple[int, dict[str, Any]]:
    return 200, {"model": "fake", "message": {"role": "assistant", "content": content}, "done": True,
                 "prompt_eval_count": 11, "eval_count": 7}


def tool_response(name: str, **arguments: Any) -> tuple[int, dict[str, Any]]:
    return 200, {"model": "fake", "message": {"role": "assistant", "content": "",
                 "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}, "done": True,
                 "prompt_eval_count": 20, "eval_count": 9}
