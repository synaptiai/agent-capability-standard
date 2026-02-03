"""Shared fixtures for benchmark tests."""

from pathlib import Path

import pytest

from grounded_agency.capabilities.registry import CapabilityRegistry

_ONTOLOGY_PATH = (
    Path(__file__).parent.parent.parent / "schemas" / "capability_ontology.yaml"
)


@pytest.fixture
def registry() -> CapabilityRegistry:
    """Pre-loaded CapabilityRegistry instance."""
    return CapabilityRegistry(_ONTOLOGY_PATH)
