"""
Shared pytest fixtures for grounded_agency tests.

Provides reusable fixtures for ontology_path, adapter, and
related adapter variants.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
    """Pre-configured adapter with tmp checkpoint dir."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
        )
    )


@pytest.fixture
def strict_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with strict_mode=True."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=True,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
        )
    )


@pytest.fixture
def lenient_adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    """Adapter with strict_mode=False."""
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=ontology_path,
            strict_mode=False,
            checkpoint_dir=str(tmp_path / ".checkpoints"),
        )
    )
