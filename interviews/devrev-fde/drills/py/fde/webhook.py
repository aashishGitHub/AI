import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Literal

type VerifyFailure = Literal[
    "missing_timestamp",
    "missing_signature",
    "malformed_timestamp",
    "stale_timestamp",
    "future_timestamp",
    "bad_signature",
]

DEFAULT_TOLERANCE_MS = 5 * 60 * 1000


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: VerifyFailure | None = None


def _fail(reason: VerifyFailure) -> VerifyResult:
    return VerifyResult(ok=False, reason=reason)


def sign_webhook(secret: str, timestamp: str, raw_body: bytes) -> str:
    message = timestamp.encode() + b"." + raw_body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_webhook(
    *,
    secret: str,
    raw_body: bytes,
    timestamp: str | None,
    signature: str | None,
    now_ms: float,
    tolerance_ms: float = DEFAULT_TOLERANCE_MS,
) -> VerifyResult:
    if timestamp is None:
        return _fail("missing_timestamp")
    if signature is None:
        return _fail("missing_signature")
    if not re.fullmatch(r"[0-9]{1,12}", timestamp):
        return _fail("malformed_timestamp")

    age_ms = now_ms - int(timestamp) * 1000
    if age_ms > tolerance_ms:
        return _fail("stale_timestamp")
    if age_ms < -tolerance_ms:
        return _fail("future_timestamp")

    expected = sign_webhook(secret, timestamp, raw_body)
    if hmac.compare_digest(expected.encode(), signature.lower().encode()):
        return VerifyResult(ok=True)
    return _fail("bad_signature")
