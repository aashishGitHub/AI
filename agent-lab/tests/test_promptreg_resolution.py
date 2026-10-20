from __future__ import annotations

from hashlib import sha256

import pytest

from promptreg.bucketing import bucket
from promptreg.errors import PromptRegError
from tests.promptreg_helpers import new_registry

TOLERANCE_POINTS = 1.5


def registry_with_two_versions(tmp_path):
    registry, store = new_registry(tmp_path)
    registry.add_version("system", "stable text", "x", "c")
    registry.add_version("system", "candidate text", "x", "c")
    return registry, store


def test_bucket_is_the_first_eight_hex_digits_of_sha256_mod_100():
    assert bucket("system", "run-1") == int(sha256(b"system:run-1").hexdigest()[:8], 16) % 100


def test_the_same_run_key_always_gets_the_same_version(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 50)
    first = {key: registry.resolve("system", key).version for key in map(str, range(200))}
    again = {key: registry.resolve("system", key).version for key in map(str, range(200))}
    assert first == again
    assert set(first.values()) == {1, 2}


@pytest.mark.parametrize("percent", [5, 10, 50])
def test_canary_share_over_10k_keys_is_within_1_5_points_of_the_percentage(tmp_path, percent):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, percent)
    canary = sum(registry.resolve("system", f"user-{i}").version == 2 for i in range(10_000))
    assert abs(canary / 100 - percent) <= TOLERANCE_POINTS


def test_zero_percent_and_no_canary_both_send_everyone_to_production(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    assert {registry.resolve("system", str(i)).version for i in range(100)} == {1}
    registry.set_canary("system", 2, 0)
    assert {registry.resolve("system", str(i)).version for i in range(100)} == {1}


def test_hundred_percent_sends_everyone_to_the_canary(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 100)
    assert {registry.resolve("system", str(i)).version for i in range(100)} == {2}


def test_the_reason_names_the_bucket_and_the_threshold(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 50)
    ref = registry.resolve("system", "run-7")
    slot = bucket("system", "run-7")
    expected = f"canary: bucket {slot} < 50" if slot < 50 else f"production: bucket {slot} >= 50"
    assert ref.reason == expected


def test_an_explicit_version_beats_a_pin_and_a_canary(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 100)
    registry.pin("system", 2)
    ref = registry.resolve("system", "run", version=1)
    assert (ref.version, ref.reason, ref.text) == (1, "explicit version 1", "stable text")


def test_a_pin_beats_canary_bucketing_until_it_is_cleared(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 100)
    registry.pin("system", 1)
    assert {registry.resolve("system", str(i)).version for i in range(50)} == {1}
    registry.unpin("system")
    assert {registry.resolve("system", str(i)).version for i in range(50)} == {2}


def test_the_ref_carries_the_text_and_the_hash_of_what_will_run(tmp_path):
    registry, store = registry_with_two_versions(tmp_path)
    ref = registry.resolve("system", "run")
    assert ref.text == "stable text"
    assert ref.sha256 == store.load_index("system").versions[1].sha256


def test_shadow_mode_returns_production_as_primary_and_the_canary_as_shadow(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 100)
    pair = registry.resolve_shadow("system", "run")
    assert (pair.primary.version, pair.primary.text) == (1, "stable text")
    assert (pair.shadow.version, pair.shadow.text) == (2, "candidate text")


def test_shadow_primary_is_the_same_for_every_run_key_whatever_the_percentage(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 50)
    assert {registry.resolve_shadow("system", str(i)).primary.version for i in range(100)} == {1}


def test_shadow_is_absent_without_a_canary_or_when_the_canary_is_the_primary(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    assert registry.resolve_shadow("system", "run").shadow is None
    registry.set_canary("system", 2, 10)
    registry.pin("system", 2)
    assert registry.resolve_shadow("system", "run").shadow is None


def test_canary_percent_outside_0_to_100_is_refused(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    with pytest.raises(PromptRegError):
        registry.set_canary("system", 2, 101)


def test_the_boundary_bucket_equal_to_the_percentage_stays_on_production(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 10)
    key_at = {bucket("system", f"k{i}"): f"k{i}" for i in range(2000)}
    assert registry.resolve("system", key_at[9]).version == 2
    assert registry.resolve("system", key_at[10]).version == 1


def test_ramping_the_percentage_up_only_adds_keys_to_the_canary(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    keys = [f"user-{i}" for i in range(2000)]
    registry.set_canary("system", 2, 10)
    at_ten = {k for k in keys if registry.resolve("system", k).version == 2}
    registry.set_canary("system", 2, 25)
    at_twenty_five = {k for k in keys if registry.resolve("system", k).version == 2}
    assert at_ten < at_twenty_five
