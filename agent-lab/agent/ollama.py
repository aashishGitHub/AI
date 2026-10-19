from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from agent.types import LLMError, Message, ToolCall, ToolSpec


def _wire_message(message: Message) -> dict[str, Any]:
    if message.role == "tool":
        return {"role": "tool", "tool_name": message.tool_name, "content": message.content}
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {"function": {"name": call.name, "arguments": call.arguments}} for call in message.tool_calls
        ]
    return wire


def _wire_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema},
    }


class OllamaLLM:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_s: float = 120.0,
        temperature: float = 0.0,
    ) -> None:
        self._model = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._timeout_s = timeout_s
        self._temperature = temperature

    async def complete(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Message:
        payload = {
            "model": self._model,
            "messages": [_wire_message(m) for m in messages],
            "tools": [_wire_tool(t) for t in tools],
            "stream": False,
            "options": {"temperature": self._temperature},
        }
        body = await asyncio.to_thread(self._post, payload)
        return self._parse(body)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise LLMError(f"ollama returned HTTP {exc.code}: {_error_text(exc)}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"could not reach ollama at {self._url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("ollama returned a body that is not JSON") from exc

    def _parse(self, body: dict[str, Any]) -> Message:
        if "error" in body:
            raise LLMError(f"ollama error: {body['error']}")
        message = body.get("message")
        if not isinstance(message, dict):
            raise LLMError("ollama response has no 'message' object")
        calls = tuple(self._parse_call(raw, n) for n, raw in enumerate(message.get("tool_calls") or [], start=1))
        usage = {
            "prompt_tokens": body.get("prompt_eval_count", 0),
            "completion_tokens": body.get("eval_count", 0),
        }
        return Message(role="assistant", content=message.get("content") or "", tool_calls=calls, usage=usage)

    @staticmethod
    def _parse_call(raw: dict[str, Any], position: int) -> ToolCall:
        function = raw.get("function") or {}
        arguments = function.get("arguments")
        if not isinstance(function.get("name"), str) or not isinstance(arguments, dict):
            raise LLMError("ollama tool call is missing a name or its arguments are not a JSON object")
        return ToolCall(id=f"call-{position}", name=function["name"], arguments=arguments)


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read()).get("error", exc.reason))
    except (json.JSONDecodeError, AttributeError, OSError):
        return str(exc.reason)
