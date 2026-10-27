from __future__ import annotations

import json

import httpx2

from mesh.client import Rejected, Unavailable
from mesh.envelope import Envelope, read_token, sign
from orchestrator.roles import AgentRole
from tests.helpers import READ_TOOL, FakeBackend, final_turn, run, tool_turn
from tests.mesh_helpers import NOW, SECRET, PostTasksCounter, Sleeps, build_service, mesh_client

ROLE = AgentRole("investigator", frozenset({"get_thing"}), max_steps=3)
SCRIPT = [tool_turn("get_thing", tenantId="acme"), final_turn("acme is healthy")]


def investigator(**kwargs):
    return build_service("investigator", ROLE, [READ_TOOL], FakeBackend(), SCRIPT, **kwargs)


def envelope(client, recipient="investigator", prompt="check acme", hop_count=0):
    return client.make_envelope(recipient, prompt, "corr-1", NOW + 30, hop_count)


def test_a_round_trip_runs_the_agent_and_returns_its_answer() -> None:
    built = investigator()
    client = mesh_client(built.app)
    task = run(client.send("http://investigator", envelope(client)))
    assert task["state"] == "completed"
    assert task["result"]["final_text"] == "acme is healthy"
    assert task["result"]["tools_called"] == ["get_thing"]
    assert task["correlation_id"] == "corr-1"


def test_the_same_envelope_sent_twice_runs_the_agent_once() -> None:
    built = investigator()
    client = mesh_client(built.app)
    env = envelope(client)
    first = run(client.send("http://investigator", env))
    second = run(client.send("http://investigator", env))
    assert first == second
    assert len(built.llms) == 1


def test_a_lost_response_is_retried_with_the_same_message_id_and_processed_once() -> None:
    built = investigator()
    flaky = PostTasksCounter(built.app, lose_response=1)
    sleeps = Sleeps()
    client = mesh_client(flaky, sleeps)
    task = run(client.send("http://investigator", envelope(client)))
    assert task["state"] == "completed"
    assert flaky.posts == 2
    assert len(built.llms) == 1
    assert len(sleeps.calls) == 1


def test_a_503_is_retried_and_then_succeeds() -> None:
    built = investigator()
    flaky = PostTasksCounter(built.app, fail_before=2)
    client = mesh_client(flaky)
    assert run(client.send("http://investigator", envelope(client)))["state"] == "completed"
    assert flaky.posts == 3


def test_retries_stop_at_max_attempts() -> None:
    built = investigator()
    flaky = PostTasksCounter(built.app, fail_before=10)
    client = mesh_client(flaky, max_attempts=3)
    try:
        run(client.send("http://investigator", envelope(client)))
    except Unavailable:
        pass
    else:
        raise AssertionError("expected Unavailable")
    assert flaky.posts == 3
    assert built.llms == []


def test_a_4xx_is_not_retried() -> None:
    built = investigator()
    counted = PostTasksCounter(built.app)
    client = mesh_client(counted)
    try:
        run(client.send("http://investigator", envelope(client, recipient="someone-else")))
    except Rejected as exc:
        assert exc.status == 421
    else:
        raise AssertionError("expected Rejected")
    assert counted.posts == 1


def test_a_task_still_working_is_polled_until_it_finishes() -> None:
    built = investigator()
    client_for_env = mesh_client(built.app)
    env = envelope(client_for_env)
    built.store.begin(env.message_id, env.correlation_id)
    sleeps = Sleeps(on_sleep=lambda: built.store.finish(env.message_id, "completed", {"final_text": "done"}))
    client = mesh_client(built.app, sleeps)
    task = run(client.send("http://investigator", env))
    assert task["state"] == "completed" and task["result"] == {"final_text": "done"}
    assert built.llms == []


def raw_post(app, body: bytes) -> httpx2.Response:
    async def go() -> httpx2.Response:
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://agent") as http:
            return await http.post("/tasks", content=body)
    return run(go())


def test_the_service_maps_envelope_problems_to_status_codes() -> None:
    built = investigator()
    good = sign(Envelope("m1", "c1", "caller", "investigator", NOW + 30, 0, {"prompt": "check acme"}), SECRET)
    tampered = json.dumps({**good.to_dict(), "payload": {"prompt": "ack all"}}).encode()
    expired = sign(Envelope("m2", "c1", "caller", "investigator", NOW - 1, 0, {"prompt": "p"}), SECRET)
    too_deep = sign(Envelope("m3", "c1", "caller", "investigator", NOW + 30, 9, {"prompt": "p"}), SECRET)
    elsewhere = sign(Envelope("m4", "c1", "caller", "responder", NOW + 30, 0, {"prompt": "p"}), SECRET)
    assert raw_post(built.app, tampered).status_code == 401
    assert raw_post(built.app, json.dumps(expired.to_dict()).encode()).status_code == 408
    assert raw_post(built.app, json.dumps(too_deep.to_dict()).encode()).status_code == 422
    assert raw_post(built.app, json.dumps(elsewhere.to_dict()).encode()).status_code == 421
    assert raw_post(built.app, b"not json").status_code == 400
    assert raw_post(built.app, b"[1, 2]").status_code == 400
    assert built.llms == []


def test_reading_a_task_needs_the_read_token() -> None:
    built = investigator()
    client = mesh_client(built.app)
    env = envelope(client)
    run(client.send("http://investigator", env))

    async def get(headers: dict[str, str]) -> httpx2.Response:
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=built.app), base_url="http://agent") as http:
            return await http.get(f"/tasks/{env.message_id}", headers=headers)

    assert run(get({})).status_code == 401
    assert run(get({"x-mesh-token": "guess"})).status_code == 401
    assert run(get({"x-mesh-token": read_token(SECRET, env.message_id)})).status_code == 200


def test_health_readiness_and_card_endpoints() -> None:
    built = investigator()

    async def get(path: str) -> httpx2.Response:
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=built.app), base_url="http://agent") as http:
            return await http.get(path)

    assert run(get("/healthz")).json() == {"status": "ok"}
    assert run(get("/readyz")).status_code == 200
    assert run(get("/agent-card")).json()["name"] == "investigator"


def test_a_blank_prompt_fails_the_task_without_running_the_agent() -> None:
    built = investigator()
    client = mesh_client(built.app)
    task = run(client.send("http://investigator", client.make_envelope("investigator", "  ", "c", NOW + 30)))
    assert task["state"] == "failed"
    assert built.llms == []
