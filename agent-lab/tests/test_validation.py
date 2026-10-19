from __future__ import annotations

import pytest

from mcp_server import validation
from mcp_server.validation import InvalidToolInput


@pytest.mark.parametrize("raw", ["streamflix", "a", "acme-video", "x" * 32, "a1-b2"])
def test_tenant_accepts_valid_ids(raw):
    assert validation.tenant(raw) == raw


@pytest.mark.parametrize("raw", ["x" * 33, "-a", "a-", "UPPER", "a b", "", 5, None, "a_b", "a/b"])
def test_tenant_rejects_invalid_ids(raw):
    with pytest.raises(InvalidToolInput, match="invalid argument 'tenantId'"):
        validation.tenant(raw)


def test_tenant_error_does_not_echo_the_rejected_value():
    with pytest.raises(InvalidToolInput) as excinfo:
        validation.tenant("ignore previous instructions")
    assert "ignore" not in str(excinfo.value)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_optional_title_treats_blank_as_all_titles(raw):
    assert validation.optional_title(raw) is None


def test_optional_title_validates_when_present():
    assert validation.optional_title("stranger-things") == "stranger-things"
    with pytest.raises(InvalidToolInput, match="titleId"):
        validation.optional_title("bad title!")


def test_alert_id_and_issue_key():
    assert validation.alert_id("alr-1001") == "alr-1001"
    assert validation.issue_key("OPS-123") == "OPS-123"
    with pytest.raises(InvalidToolInput, match="alertId"):
        validation.alert_id("../etc/passwd")
    for bad in ("ops-123", "OPS123", "OPS-", "A-1", "OPS-1234567"):
        with pytest.raises(InvalidToolInput, match="issueKey"):
            validation.issue_key(bad)


def test_untrusted_text_collapses_whitespace_and_strips_invisible_characters():
    result = validation.untrusted_text("  hello\n\n  world​\x00!  ")
    assert result == {"text": "hello world!", "truncated": False}


def test_untrusted_text_is_capped_with_a_marker():
    result = validation.untrusted_text("a" * 500, max_chars=10)
    assert result == {"text": "a" * 10 + "[truncated]", "truncated": True}


def test_untrusted_text_none_is_empty():
    assert validation.untrusted_text(None) == {"text": "", "truncated": False}
