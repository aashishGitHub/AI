from __future__ import annotations

import json
from hashlib import sha256

import pytest

from promptreg.errors import PromptRegError, TamperError, UnknownPrompt, VersionExists
from tests.promptreg_helpers import new_registry


def test_a_version_is_written_with_its_hash_author_changelog_and_injected_timestamp(tmp_path):
    registry, store = new_registry(tmp_path)
    registry.add_version("system", "hello", "aashish", "first")
    meta = store.load_index("system").versions[1]
    assert meta.sha256 == sha256(b"hello").hexdigest()
    assert (meta.author, meta.changelog, meta.created_at) == ("aashish", "first", "2026-01-01T00:00:00+00:00")
    assert (tmp_path / "system" / "v1.md").read_bytes() == b"hello"


def test_version_numbers_count_up_and_the_first_one_becomes_production(tmp_path):
    registry, store = new_registry(tmp_path)
    assert registry.add_version("system", "a", "x", "c") == 1
    assert registry.add_version("system", "b", "x", "c") == 2
    assert store.load_index("system").production == 1
    assert store.read_history("system") == [{"event": "bootstrap", "name": "system", "to": 1, "ts": "2026-01-01T00:00:01+00:00"}]


def test_an_existing_version_is_refused_and_its_file_is_untouched(tmp_path):
    registry, store = new_registry(tmp_path)
    registry.add_version("system", "original", "x", "c")
    with pytest.raises(VersionExists):
        registry.add_version("system", "overwrite", "x", "c", version=1)
    assert (tmp_path / "system" / "v1.md").read_text() == "original"
    assert store.read_version("system", 1)[0] == "original"


def test_a_file_that_exists_on_disk_but_not_in_the_index_is_still_refused(tmp_path):
    registry, _ = new_registry(tmp_path)
    registry.add_version("system", "a", "x", "c")
    (tmp_path / "system" / "v2.md").write_text("orphan")
    with pytest.raises(VersionExists):
        registry.add_version("system", "b", "x", "c")
    assert (tmp_path / "system" / "v2.md").read_text() == "orphan"


def test_reading_a_version_whose_file_changed_raises_tamper_error(tmp_path):
    registry, store = new_registry(tmp_path)
    registry.add_version("system", "original", "x", "c")
    (tmp_path / "system" / "v1.md").write_text("original, quietly edited")
    with pytest.raises(TamperError, match="v1 was modified"):
        store.read_version("system", 1)
    with pytest.raises(TamperError):
        registry.resolve("system", "any-run")


def test_unknown_names_and_versions_raise(tmp_path):
    registry, store = new_registry(tmp_path)
    with pytest.raises(UnknownPrompt):
        store.load_index("nope")
    registry.add_version("system", "a", "x", "c")
    with pytest.raises(UnknownPrompt):
        store.read_version("system", 9)


@pytest.mark.parametrize("name", ["../escape", "a/b", "", "Upper", ".hidden", "x" * 65])
def test_names_that_could_leave_the_store_directory_are_refused(tmp_path, name):
    registry, _ = new_registry(tmp_path)
    with pytest.raises(PromptRegError):
        registry.add_version(name, "a", "x", "c")


def test_index_json_is_plain_json_a_human_can_read(tmp_path):
    registry, _ = new_registry(tmp_path)
    registry.add_version("system", "a", "x", "c")
    raw = json.loads((tmp_path / "system" / "index.json").read_text())
    assert raw["aliases"] == {"production": 1, "canary": None}
    assert raw["canary_percent"] == 0
    assert raw["pin"] is None


def test_names_lists_only_directories_with_an_index(tmp_path):
    registry, store = new_registry(tmp_path)
    registry.add_version("beta", "a", "x", "c")
    registry.add_version("alpha", "a", "x", "c")
    (tmp_path / "stray").mkdir()
    assert store.names() == ["alpha", "beta"]
