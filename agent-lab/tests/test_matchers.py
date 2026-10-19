from __future__ import annotations

import pytest

from evals.matchers import CaseError, describe, mismatch, validate_matcher


def test_plain_value_is_an_exact_match():
    assert mismatch("streamflix", True, "streamflix") is None
    assert mismatch("streamflix", True, "acme-video") == "expected exact 'streamflix' but got 'acme-video'"


def test_missing_argument_is_reported_as_missing_not_as_none():
    assert mismatch("streamflix", False, None) == "expected exact 'streamflix' but the argument was missing"


def test_regex_uses_search_and_requires_a_string():
    assert mismatch({"regex": "^alr-\\d+$"}, True, "alr-1001") is None
    assert mismatch({"regex": "^alr-\\d+$"}, True, "alr-x") == "expected regex '^alr-\\\\d+$' but got 'alr-x'"
    assert mismatch({"regex": "5"}, True, 5) is not None


def test_subset_on_dicts_and_lists():
    assert mismatch({"subset": {"a": 1}}, True, {"a": 1, "b": 2}) is None
    assert mismatch({"subset": {"a": 1}}, True, {"a": 2}) is not None
    assert mismatch({"subset": [1, 2]}, True, [3, 2, 1]) is None
    assert mismatch({"subset": [1, 9]}, True, [1, 2]) is not None
    assert mismatch({"subset": {"a": 1}}, True, "str") is not None


def test_absent_matcher():
    assert mismatch({"absent": True}, False, None) is None
    assert mismatch({"absent": True}, True, "x") == "expected the argument to be absent but got 'x'"


def test_describe():
    assert describe("x") == "exact 'x'"
    assert describe({"regex": "a"}) == "regex 'a'"


@pytest.mark.parametrize("bad", [{"exactly": 1}, {"exact": 1, "regex": "a"}, {}])
def test_validate_rejects_unknown_or_ambiguous_dict_matchers(bad):
    with pytest.raises(CaseError, match="exactly one key"):
        validate_matcher(bad, "where")


def test_validate_rejects_a_regex_that_does_not_compile():
    with pytest.raises(CaseError, match="bad regex"):
        validate_matcher({"regex": "("}, "where")
