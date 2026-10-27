from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass, replace
from typing import Any


class EnvelopeError(Exception):
    pass


class BadSignature(EnvelopeError):
    pass


class Expired(EnvelopeError):
    pass


class TooManyHops(EnvelopeError):
    pass


@dataclass(frozen=True)
class Envelope:
    message_id: str
    correlation_id: str
    sender: str
    recipient: str
    deadline: float
    hop_count: int
    payload: dict[str, Any]
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Envelope:
        try:
            return Envelope(
                message_id=str(raw["message_id"]), correlation_id=str(raw["correlation_id"]),
                sender=str(raw["sender"]), recipient=str(raw["recipient"]),
                deadline=float(raw["deadline"]), hop_count=int(raw["hop_count"]),
                payload=dict(raw["payload"]), signature=str(raw.get("signature", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EnvelopeError(f"malformed envelope: {type(exc).__name__}: {exc}") from exc


def _mac(secret: bytes, data: bytes) -> str:
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


# Signs canonical JSON of the parsed fields, not the raw request bytes, so re-serialising in transit is safe.
def _canonical(env: Envelope) -> bytes:
    body = env.to_dict()
    del body["signature"]
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def sign(env: Envelope, secret: bytes) -> Envelope:
    return replace(env, signature=_mac(secret, _canonical(env)))


def verify(env: Envelope, secret: bytes, now: float, max_hops: int) -> None:
    if not hmac.compare_digest(env.signature, _mac(secret, _canonical(env))):
        raise BadSignature("signature does not match")
    if now >= env.deadline:
        raise Expired(f"deadline passed {now - env.deadline:.3f} s ago")
    if env.hop_count > max_hops:
        raise TooManyHops(f"hop_count {env.hop_count} exceeds {max_hops}")


# Task reads carry no body to sign, so the token binds the secret to the message id being read.
def read_token(secret: bytes, message_id: str) -> str:
    return _mac(secret, f"read:{message_id}".encode())


def check_read_token(secret: bytes, message_id: str, token: str) -> bool:
    return hmac.compare_digest(token, read_token(secret, message_id))
