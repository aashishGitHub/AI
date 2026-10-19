from __future__ import annotations

from agent.grounding import IDENTIFIER_ARGS, ungrounded_args

IDS = {"tenantId", "alertId"}


def test_an_id_the_user_typed_is_grounded():
    assert ungrounded_args({"tenantId": "streamflix"}, IDS, ["Any alerts for tenant streamflix?"]) == []


def test_an_id_from_an_earlier_tool_result_is_grounded():
    evidence = ["What is wrong with tenant streamflix?", '{"firing": [{"alertId": "alr-1001"}]}']
    assert ungrounded_args({"tenantId": "streamflix", "alertId": "alr-1001"}, IDS, evidence) == []


def test_an_invented_id_is_reported_by_name():
    assert ungrounded_args({"tenantId": "streampulse"}, IDS, ["Are there any active alerts right now?"]) == ["tenantId"]


def test_every_ungrounded_id_is_reported_sorted():
    assert ungrounded_args({"tenantId": "x", "alertId": "y"}, IDS, ["nothing here"]) == ["alertId", "tenantId"]


def test_a_prefix_of_a_longer_id_is_not_grounded():
    evidence = ["tenant streamflix, alert alr-1001"]
    assert ungrounded_args({"tenantId": "stream", "alertId": "alr-100"}, IDS, evidence) == ["alertId", "tenantId"]


def test_punctuation_around_an_id_still_counts_as_a_match():
    assert ungrounded_args({"alertId": "alr-1001"}, IDS, ["Explain alr-1001."]) == []


def test_case_is_ignored():
    assert ungrounded_args({"tenantId": "streamflix"}, IDS, ["Is Streamflix healthy?"]) == []


def test_a_blank_id_is_never_grounded():
    assert ungrounded_args({"tenantId": " "}, IDS, ["a b c"]) == ["tenantId"]


def test_args_not_declared_as_identifiers_are_not_checked():
    assert ungrounded_args({"tenantId": "t1", "titleId": "invented"}, IDS, ["tenant t1"]) == []


def test_the_declared_identifiers_are_the_ones_a_guess_would_hurt():
    assert IDENTIFIER_ARGS == {"tenantId", "alertId", "issueKey"}
