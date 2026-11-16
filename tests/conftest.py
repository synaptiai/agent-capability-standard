"""
Shared pytest fixtures for grounded_agency tests.

Provides reusable fixtures for ontology_path, adapter, and
related adapter variants.

``adapter``, ``strict_adapter`` and ``lenient_adapter`` set
``approval="off"``: the tests that use them are about the rate limit and the
checkpoint rule, and a call that passes those is then allowed outright. The
approval rule (the default, ``approval="ask"``) is tested with
``asking_adapter`` in ``tests/test_tool_call_approval.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure grounded_agency is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

# =============================================================================
# Shared fixtures
# =============================================================================


@pytest.fixture
def ontology_path() -> str:
    """Path to the capability ontology YAML file."""
    return str(Path(__file__).parent.parent / "schemas/capability_ontology.yaml")


@pytest.fixture
def adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Pre-configured adapter with tmp checkpoint dir; asks for no approval."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


@pytest.fixture
def strict_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with strict_mode=True; asks for no approval."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=True,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


@pytest.fixture
def lenient_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with strict_mode=False; asks for no approval."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=False,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
            approval="off",
        )
    )


@pytest.fixture
def asking_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with the defaults: strict mode, and approval="ask"."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
        )
    )


class FakeClock:
    """A clock a test advances: pass it as ``clock=`` to a
    ``CheckpointTracker`` or a ``GroundedAgentAdapter``."""

    def __init__(self) -> None:
        from datetime import UTC, datetime

        self.now = datetime.now(UTC)

    def __call__(self) -> Any:
        return self.now

    def advance(self, **delta: float) -> None:
        from datetime import timedelta

        self.now += timedelta(**delta)


@pytest.fixture
def fake_clock() -> FakeClock:
    """A clock that stands still until the test advances it."""
    return FakeClock()
