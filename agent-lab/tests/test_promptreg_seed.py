from __future__ import annotations

from agent.loop import SYSTEM_PROMPT
from promptreg.cli import PROMPTS_DIR
from promptreg.registry import PromptRegistry
from promptreg.store import PromptStore


def test_v1_of_the_seeded_system_prompt_is_byte_identical_to_the_one_in_loop_py():
    assert (PROMPTS_DIR / "system" / "v1.md").read_bytes() == SYSTEM_PROMPT.encode("utf-8")


def test_the_seeded_store_verifies_clean_and_production_is_the_baseline():
    registry = PromptRegistry(PromptStore(PROMPTS_DIR))
    ref = registry.resolve("system", "any-run")
    assert (ref.version, ref.text) == (1, SYSTEM_PROMPT)
    assert registry.resolve("system", "any-run", version=2).text.startswith(SYSTEM_PROMPT)


def test_v2_is_labelled_unmeasured_in_its_changelog_and_is_not_production():
    index = PromptStore(PROMPTS_DIR).load_index("system")
    assert "UNMEASURED" in index.versions[2].changelog
    assert index.production == 1
