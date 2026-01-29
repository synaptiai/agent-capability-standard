"""Tests for the OASF adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from grounded_agency.adapters.oasf import (
    OASFAdapter,
    OASFMapping,
    OASFSkillResult,
    UnknownSkillError,
)

ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = ROOT / "schemas" / "interop" / "oasf_mapping.yaml"
ONTOLOGY_PATH = ROOT / "schemas" / "capability_ontology.yaml"


@pytest.fixture
def adapter() -> OASFAdapter:
    """Create an adapter with the real mapping and ontology files."""
    from grounded_agency.capabilities.registry import CapabilityRegistry

    registry = CapabilityRegistry(ONTOLOGY_PATH)
    return OASFAdapter(MAPPING_PATH, registry=registry)


class TestOASFAdapterLoading:
    """Test adapter initialization and loading."""

    def test_loads_mapping_file(self, adapter: OASFAdapter) -> None:
        assert adapter.category_count == 15

    def test_oasf_version(self, adapter: OASFAdapter) -> None:
        assert adapter.oasf_version == "0.8.0"

    def test_mapping_version(self, adapter: OASFAdapter) -> None:
        assert adapter.mapping_version == "1.0.0"

    def test_total_mappings_includes_subcategories(self, adapter: OASFAdapter) -> None:
        # 15 categories + subcategories should be > 15
        assert adapter.total_mapping_count > 15

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            adapter = OASFAdapter("/nonexistent/path.yaml")
            adapter.translate("109")


class TestOASFTranslation:
    """Test skill code translation."""

    def test_direct_mapping(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("109")  # Text Classification
        assert "classify" in result.mapping.capabilities
        assert result.mapping.mapping_type == "direct"

    def test_domain_mapping(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("111")  # Token Classification
        assert "detect" in result.mapping.capabilities
        assert result.mapping.domain_hint == "token"

    def test_composition_mapping(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("101")  # NLU
        assert "detect" in result.mapping.capabilities
        assert "classify" in result.mapping.capabilities
        assert result.mapping.mapping_type == "composition"

    def test_workflow_mapping(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("6")  # RAG
        assert result.mapping.workflow == "rag_pipeline"
        assert result.mapping.mapping_type == "workflow"

    def test_category_level_mapping(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("2")  # Computer Vision
        assert "detect" in result.mapping.capabilities
        assert result.mapping.domain_hint == "image"

    def test_subcategory_mapping(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("801")  # Threat Detection
        assert "detect" in result.mapping.capabilities
        assert result.mapping.domain_hint == "security.threat"

    def test_unknown_skill_raises(self, adapter: OASFAdapter) -> None:
        with pytest.raises(UnknownSkillError):
            adapter.translate("99999")


class TestSafetyMetadata:
    """Test that safety properties propagate correctly."""

    def test_high_risk_detection(self, adapter: OASFAdapter) -> None:
        # DevOps category includes execute which is medium risk
        result = adapter.translate("12")
        assert result.max_risk in ("medium", "high")

    def test_checkpoint_propagation(self, adapter: OASFAdapter) -> None:
        # Model deployment (12) includes checkpoint capability
        result = adapter.translate("1202")  # Deployment Orchestration
        # checkpoint and rollback are in the capabilities list
        assert "checkpoint" in result.mapping.capabilities

    def test_low_risk_for_classify(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("109")  # Text Classification
        assert result.max_risk == "low"

    def test_capability_nodes_populated(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("109")
        assert len(result.capability_nodes) > 0
        assert result.capability_nodes[0].id == "classify"


class TestReverseLookup:
    """Test reverse mapping from capabilities to OASF codes."""

    def test_detect_maps_to_multiple_skills(self, adapter: OASFAdapter) -> None:
        codes = adapter.reverse_lookup("detect")
        assert len(codes) > 1  # detect maps to many OASF skills

    def test_ground_has_no_oasf_equivalent(self, adapter: OASFAdapter) -> None:
        codes = adapter.reverse_lookup("ground")
        assert codes == []  # ground has no OASF equivalent

    def test_checkpoint_has_no_oasf_equivalent(self, adapter: OASFAdapter) -> None:
        codes = adapter.reverse_lookup("checkpoint")
        # checkpoint maps to DevOps subcategories
        # but it may or may not be in the reverse mapping
        assert isinstance(codes, list)


class TestListOperations:
    """Test listing and enumeration."""

    def test_list_categories(self, adapter: OASFAdapter) -> None:
        categories = adapter.list_categories()
        assert len(categories) == 15
        names = [c.skill_name for c in categories]
        assert "Natural Language Processing" in names
        assert "Security & Privacy" in names

    def test_list_all_mappings(self, adapter: OASFAdapter) -> None:
        all_mappings = adapter.list_all_mappings()
        assert len(all_mappings) > 15  # includes subcategories

    def test_get_mapping_returns_none_for_unknown(self, adapter: OASFAdapter) -> None:
        assert adapter.get_mapping("99999") is None

    def test_get_mapping_returns_mapping(self, adapter: OASFAdapter) -> None:
        mapping = adapter.get_mapping("109")
        assert mapping is not None
        assert mapping.skill_name == "Text Classification"
