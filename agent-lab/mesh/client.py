from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2

from mesh.envelope import Envelope, read_token, sign
from orchestrator.guards import Uniform, full_jitter_delay

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class MeshError(Exception):
    pass


class DeadlineExceeded(MeshError):
    pass


class Rejected(MeshError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"rejected with {status}: {body}")
        self.status = status


class Unavailable(MeshError):
    pass


class MeshClient:
    def __init__(
        self,
        http: httpx2.AsyncClient,
        secret: bytes,
        sender: str,
        max_attempts: int = 3,
        backoff_base_s: float = 0.5,
        backoff_cap_s: float = 8.0,
        poll_interval_s: float = 0.2,
        attempt_timeout_s: float = 30.0,
        rng: Uniform = random,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._http = http
        self._secret = secret
        self._sender = sender
        self._max_attempts = max_attempts
        self._backoff = (backoff_base_s, backoff_cap_s)
        self._poll_interval_s = poll_interval_s
        self._attempt_timeout_s = attempt_timeout_s
        self._rng = rng
        self._sleep = sleep
        self._clock = clock

    def make_envelope(self, recipient: str, prompt: str, correlation_id: str, deadline: float, hop_count: int = 0) -> Envelope:
        env = Envelope(uuid.uuid4().hex, correlation_id, self._sender, recipient, deadline, hop_count, {"prompt": prompt})
        return sign(env, self._secret)

    async def send(self, endpoint: str, env: Envelope) -> dict[str, Any]:
        """The same envelope, so the same message_id, goes out on every attempt: the receiver dedupes the retry."""
        last: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            remaining = env.deadline - self._clock()
            if remaining <= 0:
                raise DeadlineExceeded(f"deadline passed before attempt {attempt}")
            try:
                response = await self._http.post(f"{endpoint}/tasks", json=env.to_dict(),
                                                 timeout=min(remaining, self._attempt_timeout_s))
            except httpx2.TransportError as exc:
                last = Unavailable(f"{type(exc).__name__}")
            else:
                if response.status_code in (200, 202):
                    body = response.json()
                    return body if body["state"] != "working" else await self._poll(endpoint, env)
                if response.status_code not in RETRYABLE_STATUS:
                    raise Rejected(response.status_code, response.text)
                last = Unavailable(f"status {response.status_code}")
            if attempt < self._max_attempts:
                await self._sleep(full_jitter_delay(attempt, *self._backoff, self._rng))
        raise Unavailable(f"gave up after {self._max_attempts} attempts: {last}")

    async def _poll(self, endpoint: str, env: Envelope) -> dict[str, Any]:
        headers = {"x-mesh-token": read_token(self._secret, env.message_id)}
        while self._clock() < env.deadline:
            response = await self._http.get(f"{endpoint}/tasks/{env.message_id}", headers=headers,
                                            timeout=min(env.deadline - self._clock(), self._attempt_timeout_s))
            if response.status_code != 200:
                raise Rejected(response.status_code, response.text)
            body = response.json()
            if body["state"] != "working":
                return body
            await self._sleep(self._poll_interval_s)
        raise DeadlineExceeded("task still working at the deadline")
