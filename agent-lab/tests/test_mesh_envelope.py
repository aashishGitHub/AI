from __future__ import annotations

from dataclasses import replace

import pytest

from mesh.card import AgentCard, Registry, UnknownAgent
from mesh.envelope import (
    BadSignature, Envelope, EnvelopeError, Expired, TooManyHops, check_read_token, read_token, sign, verify,
)

SECRET = b"s3cret"


def env(**overrides: object) -> Envelope:
    base = Envelope("m1", "c1", "triage", "investigator", 100.0, 1, {"prompt": "hi"})
    return sign(replace(base, **overrides), SECRET)  # type: ignore[arg-type]


def test_a_signed_envelope_verifies() -> None:
    verify(env(), SECRET, now=50.0, max_hops=3)


def test_a_changed_payload_fails_the_signature() -> None:
    tampered = replace(env(), payload={"prompt": "ack everything"})
    with pytest.raises(BadSignature):
        verify(tampered, SECRET, now=50.0, max_hops=3)


def test_a_changed_recipient_fails_the_signature() -> None:
    with pytest.raises(BadSignature):
        verify(replace(env(), recipient="responder"), SECRET, now=50.0, max_hops=3)


def test_a_different_secret_fails_the_signature() -> None:
    with pytest.raises(BadSignature):
        verify(env(), b"other", now=50.0, max_hops=3)


def test_an_envelope_at_its_deadline_is_expired() -> None:
    with pytest.raises(Expired):
        verify(env(), SECRET, now=100.0, max_hops=3)


def test_hop_count_above_the_limit_is_refused() -> None:
    with pytest.raises(TooManyHops):
        verify(env(hop_count=4), SECRET, now=50.0, max_hops=3)


def test_hop_count_at_the_limit_is_allowed() -> None:
    verify(env(hop_count=3), SECRET, now=50.0, max_hops=3)


def test_a_dict_round_trip_keeps_the_signature_valid() -> None:
    verify(Envelope.from_dict(env().to_dict()), SECRET, now=50.0, max_hops=3)


def test_a_missing_field_is_a_malformed_envelope() -> None:
    raw = env().to_dict()
    del raw["recipient"]
    with pytest.raises(EnvelopeError, match="malformed"):
        Envelope.from_dict(raw)


def test_a_read_token_only_opens_its_own_message() -> None:
    token = read_token(SECRET, "m1")
    assert check_read_token(SECRET, "m1", token)
    assert not check_read_token(SECRET, "m2", token)
    assert not check_read_token(b"other", "m1", token)


def test_registry_finds_cards_by_name_and_skill() -> None:
    card = AgentCard("investigator", "1", "d", "http://i", ("read-alerts",))
    registry = Registry((card,))
    assert registry.get("investigator") == card
    assert registry.find_by_skill("read-alerts") == [card]
    with pytest.raises(UnknownAgent):
        registry.get("nobody")
