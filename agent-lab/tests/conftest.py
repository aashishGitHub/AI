from __future__ import annotations

import pytest

from evals.case import Case, load_cases
from evals.cli import CASES_DIR
from mcp_server.store import FixtureStore


@pytest.fixture
def store() -> FixtureStore:
    return FixtureStore()


@pytest.fixture(scope="session")
def golden() -> dict[str, Case]:
    return {c.id: c for c in load_cases(CASES_DIR)}
