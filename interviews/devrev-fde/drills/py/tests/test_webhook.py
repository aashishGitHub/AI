import json

import pytest

from fde.webhook import DEFAULT_TOLERANCE_MS, VerifyFailure, VerifyResult, sign_webhook, verify_webhook

SECRET = "whsec_test"
NOW_S = 1_700_000_000
NOW_MS = NOW_S * 1000
BODY = b'{"id":"t-1","status":"open"}'
OK = VerifyResult(ok=True)


def fail(reason: VerifyFailure) -> VerifyResult:
    return VerifyResult(ok=False, reason=reason)


def signed(body: bytes = BODY, timestamp_s: int = NOW_S, secret: str = SECRET) -> dict:
    timestamp = str(timestamp_s)
    return {
        "secret": SECRET,
        "raw_body": body,
        "timestamp": timestamp,
        "signature": sign_webhook(secret, timestamp, body),
        "now_ms": NOW_MS,
    }


def test_accepts_an_untouched_delivery() -> None:
    assert verify_webhook(**signed()) == OK


def test_matches_an_hmac_sha256_vector_computed_independently_with_openssl() -> None:
    assert sign_webhook("key", "1", b"x") == "fc4913c41a7bf793267e2a384f3261c9436ec2cd097bd745e7b0d99113f510ec"


def test_rejects_a_tampered_body() -> None:
    delivery = signed() | {"raw_body": b'{"id":"t-1","status":"closed"}'}
    assert verify_webhook(**delivery) == fail("bad_signature")


def test_rejects_a_signature_made_with_the_wrong_secret() -> None:
    assert verify_webhook(**signed(secret="whsec_other")) == fail("bad_signature")


def test_rejects_a_stale_timestamp_even_when_the_signature_is_genuine() -> None:
    assert verify_webhook(**signed(timestamp_s=NOW_S - 301)) == fail("stale_timestamp")


def test_rejects_a_timestamp_too_far_in_the_future() -> None:
    assert verify_webhook(**signed(timestamp_s=NOW_S + 301)) == fail("future_timestamp")


def test_accepts_exactly_the_tolerance_on_both_sides_and_rejects_one_second_beyond() -> None:
    edge = int(DEFAULT_TOLERANCE_MS / 1000)
    assert verify_webhook(**signed(timestamp_s=NOW_S - edge)) == OK
    assert verify_webhook(**signed(timestamp_s=NOW_S + edge)) == OK
    assert verify_webhook(**signed(timestamp_s=NOW_S - edge - 1)) == fail("stale_timestamp")
    assert verify_webhook(**signed(timestamp_s=NOW_S + edge + 1)) == fail("future_timestamp")


def test_binds_the_timestamp_into_the_mac_so_replaying_under_a_fresh_one_fails() -> None:
    old = signed(timestamp_s=NOW_S - 10)
    assert verify_webhook(**(old | {"timestamp": str(NOW_S)})) == fail("bad_signature")


def test_reports_missing_headers() -> None:
    assert verify_webhook(**(signed() | {"signature": None})) == fail("missing_signature")
    assert verify_webhook(**(signed() | {"timestamp": None})) == fail("missing_timestamp")


@pytest.mark.parametrize("timestamp", ["abc", "12.5", "-1", "", " 1700000000", "9" * 400, "١٧٠٠٠٠٠٠٠٠"])
def test_rejects_malformed_timestamps(timestamp: str) -> None:
    assert verify_webhook(**(signed() | {"timestamp": timestamp})) == fail("malformed_timestamp")


@pytest.mark.parametrize("signature", ["", "zz", "deadbeef", "é" * 64])
def test_rejects_malformed_signatures_without_raising(signature: str) -> None:
    assert verify_webhook(**(signed() | {"signature": signature})) == fail("bad_signature")


def test_accepts_an_upper_case_hex_signature() -> None:
    delivery = signed()
    assert verify_webhook(**(delivery | {"signature": delivery["signature"].upper()})) == OK


def test_fails_on_reserialised_json_same_data_different_bytes() -> None:
    original = b'{"id": "t-1",  "status": "open"}'
    delivery = signed(original)
    reserialised = json.dumps(json.loads(original), separators=(",", ":")).encode()

    assert json.loads(reserialised) == json.loads(original)
    assert verify_webhook(**(delivery | {"raw_body": reserialised})) == fail("bad_signature")
    assert verify_webhook(**delivery) == OK


def test_is_binary_safe_for_bytes_that_are_not_valid_utf8() -> None:
    assert verify_webhook(**signed(bytes([0xFF, 0xFE, 0x00, 0x80, 0xC3]))) == OK
