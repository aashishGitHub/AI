from __future__ import annotations

import socket

import pytest

from agent.ollama import OllamaLLM
from agent.types import LLMError, Message, ToolCall, ToolSpec
from tests.fake_ollama import FakeOllama, serve, text_response, tool_response
from tests.helpers import run

TOOL = ToolSpec("get_thing", "reads a thing", {"type": "object", "properties": {"tenantId": {"type": "string"}}}, True)
HISTORY = [
    Message("system", "be brief"),
    Message("user", "hi"),
    Message("assistant", "", tool_calls=(ToolCall("call-1", "get_thing", {"tenantId": "t"}),)),
    Message("tool", '{"ok": 1}', tool_call_id="call-1", tool_name="get_thing"),
]


def test_request_matches_the_documented_chat_tools_shape():
    fake = FakeOllama([text_response("hello")])
    with serve(fake) as url:
        run(OllamaLLM("some-model", url).complete(HISTORY, [TOOL]))
    assert fake.paths == ["/api/chat"]
    body = fake.requests[0]
    assert body["model"] == "some-model"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.0}
    assert body["tools"] == [
        {"type": "function", "function": {"name": "get_thing", "description": "reads a thing",
                                           "parameters": TOOL.input_schema}}
    ]
    assert body["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "get_thing", "arguments": {"tenantId": "t"}}}]},
        {"role": "tool", "tool_name": "get_thing", "content": '{"ok": 1}'},
    ]


def test_text_reply_is_parsed_with_token_usage():
    with serve(FakeOllama([text_response("hello")])) as url:
        reply = run(OllamaLLM("m", url).complete(HISTORY[:2], [TOOL]))
    assert (reply.role, reply.content, reply.tool_calls) == ("assistant", "hello", ())
    assert reply.usage == {"prompt_tokens": 11, "completion_tokens": 7}


def test_tool_call_reply_is_parsed_into_tool_calls_with_dict_arguments():
    with serve(FakeOllama([tool_response("get_thing", tenantId="streamflix")])) as url:
        reply = run(OllamaLLM("m", url).complete(HISTORY[:2], [TOOL]))
    assert reply.content == ""
    assert [(c.name, c.arguments) for c in reply.tool_calls] == [("get_thing", {"tenantId": "streamflix"})]


def test_model_not_found_surfaces_ollamas_own_error_text():
    with serve(FakeOllama([(404, {"error": "model 'nope' not found"})])) as url:
        with pytest.raises(LLMError, match="HTTP 404: model 'nope' not found"):
            run(OllamaLLM("nope", url).complete(HISTORY[:2], [TOOL]))


def test_unreachable_server_is_an_llm_error_not_a_crash():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(LLMError, match="could not reach ollama"):
        run(OllamaLLM("m", f"http://127.0.0.1:{port}", timeout_s=2).complete(HISTORY[:2], [TOOL]))


def test_slow_server_times_out_as_an_llm_error():
    with serve(FakeOllama([text_response("late")], delay_s=1.0)) as url:
        with pytest.raises(LLMError, match="could not reach ollama"):
            run(OllamaLLM("m", url, timeout_s=0.2).complete(HISTORY[:2], [TOOL]))


@pytest.mark.parametrize(
    "response, message",
    [
        ((200, b"not json"), "not JSON"),
        ((200, {"nothing": 1}), "no 'message'"),
        ((200, {"error": "boom"}), "ollama error: boom"),
        ((200, {"message": {"content": "", "tool_calls": [{"function": {"name": "x", "arguments": "{}"}}]}}),
         "not a JSON object"),
        ((200, {"message": {"content": "", "tool_calls": [{"function": {"arguments": {}}}]}}), "missing a name"),
    ],
)
def test_malformed_replies_are_llm_errors(response, message):
    with serve(FakeOllama([response])) as url:
        with pytest.raises(LLMError, match=message):
            run(OllamaLLM("m", url).complete(HISTORY[:2], [TOOL]))
