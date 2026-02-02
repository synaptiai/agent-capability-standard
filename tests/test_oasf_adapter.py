"""Tests for the OASF adapter."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from grounded_agency.adapters.oasf import (
    OASFAdapter,
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
        assert adapter.mapping_version == "1.1.0"

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

    def test_translate_category_with_aggregate_capabilities(
        self, adapter: OASFAdapter
    ) -> None:
        """Category '1' (NLP) aggregates capabilities from subcategories."""
        result = adapter.translate("1")
        assert len(result.mapping.capabilities) > 0
        assert "classify" in result.mapping.capabilities
        assert result.mapping.domain_hint == "text"

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

    def test_checkpoint_required_for_mutation_capabilities(
        self, adapter: OASFAdapter
    ) -> None:
        # OASF code "1204" (Model Versioning) maps to mutate, which requires checkpoint
        result = adapter.translate("1204")
        assert result.requires_checkpoint is True

    def test_low_risk_for_classify(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("109")  # Text Classification
        assert result.max_risk == "low"

    def test_capability_nodes_populated(self, adapter: OASFAdapter) -> None:
        result = adapter.translate("109")
        assert len(result.capability_nodes) > 0
        assert result.capability_nodes[0].id == "classify"

    def test_warning_logged_for_missing_capability(
        self, adapter: OASFAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A warning is logged when a mapped capability is not found in the registry."""
        with patch.object(adapter._registry, "get_capability", return_value=None):
            with caplog.at_level(
                logging.WARNING, logger="grounded_agency.adapters.oasf"
            ):
                result = adapter.translate("109")  # classify -> patched to None
        assert "not found in registry" in caplog.text
        assert result.capability_nodes == []


class TestReverseLookup:
    """Test reverse mapping from capabilities to OASF codes."""

    def test_detect_maps_to_multiple_skills(self, adapter: OASFAdapter) -> None:
        codes = adapter.reverse_lookup("detect")
        assert len(codes) > 1  # detect maps to many OASF skills

    def test_ground_has_partial_oasf_mapping(self, adapter: OASFAdapter) -> None:
        """ground maps partially to OASF codes 103 (Information Retrieval) and 6 (RAG)."""
        codes = adapter.reverse_lookup("ground")
        assert "103" in codes
        assert "6" in codes

    def test_checkpoint_has_partial_oasf_mapping(self, adapter: OASFAdapter) -> None:
        """checkpoint maps partially to OASF codes 1201, 1202, 1204."""
        codes = adapter.reverse_lookup("checkpoint")
        assert len(codes) >= 3
        assert "1201" in codes
        assert "1202" in codes
        assert "1204" in codes

    def test_computed_reverse_mapping_covers_all_forward_entries(
        self, adapter: OASFAdapter
    ) -> None:
        """Every capability in the forward mapping should appear in the reverse mapping."""
        for mapping in adapter.list_all_mappings():
            for cap in mapping.capabilities:
                codes = adapter.reverse_lookup(cap)
                assert mapping.skill_code in codes, (
                    f"Code {mapping.skill_code} missing from reverse lookup for {cap}"
                )


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


class TestGAExtensions:
    """Test GA extension codes for unmapped capabilities."""

    @pytest.mark.parametrize(
        "ga_code, expected_capability",
        [
            ("GA-001", "attribute"),
            ("GA-002", "integrate"),
            ("GA-003", "recall"),
            ("GA-004", "receive"),
            ("GA-005", "send"),
            ("GA-006", "transition"),
        ],
    )
    def test_each_ga_extension_translates(
        self, adapter: OASFAdapter, ga_code: str, expected_capability: str
    ) -> None:
        """Every GA extension code should translate to its expected capability."""
        result = adapter.translate(ga_code)
        assert result.mapping.capabilities == (expected_capability,)
        assert result.mapping.mapping_type == "ga_extension"

    def test_ga_send_is_high_risk(self, adapter: OASFAdapter) -> None:
        """GA-005 (send) should be high risk since send requires checkpoint."""
        result = adapter.translate("GA-005")
        assert result.max_risk == "high"
        assert result.requires_checkpoint is True

    def test_list_ga_extensions_count(self, adapter: OASFAdapter) -> None:
        extensions = adapter.list_ga_extensions()
        assert len(extensions) == 6

    def test_ga_extension_count_property(self, adapter: OASFAdapter) -> None:
        assert adapter.ga_extension_count == 6

    def test_ga_codes_excluded_from_list_categories(self, adapter: OASFAdapter) -> None:
        """GA codes should NOT appear in list_categories() — only OASF categories."""
        category_codes = {c.skill_code for c in adapter.list_categories()}
        ga_codes = {ext.skill_code for ext in adapter.list_ga_extensions()}
        assert category_codes.isdisjoint(ga_codes), (
            f"GA codes found in categories: {category_codes & ga_codes}"
        )

    def test_ga_extensions_included_in_list_all_mappings(
        self, adapter: OASFAdapter
    ) -> None:
        """GA extensions should appear in list_all_mappings()."""
        all_mappings = adapter.list_all_mappings()
        ga_entries = [m for m in all_mappings if m.mapping_type == "ga_extension"]
        assert len(ga_entries) == 6

    def test_reverse_lookup_includes_ga_codes(self, adapter: OASFAdapter) -> None:
        """Reverse lookup for 'attribute' should include GA-001."""
        codes = adapter.reverse_lookup("attribute")
        assert "GA-001" in codes

    def test_unknown_ga_code_raises(self, adapter: OASFAdapter) -> None:
        """An invalid GA-prefixed code should raise UnknownSkillError."""
        with pytest.raises(UnknownSkillError):
            adapter.translate("GA-999")

    def test_all_unmapped_have_ga_extension(self, adapter: OASFAdapter) -> None:
        """Every unmapped capability should have a GA extension entry."""
        unmapped = adapter.unmapped_capabilities()
        extensions = adapter.list_ga_extensions()
        extension_caps = {cap for ext in extensions for cap in ext.capabilities}
        for cap_id in unmapped:
            assert cap_id in extension_caps, (
                f"Unmapped capability '{cap_id}' has no GA extension"
            )


class TestCoverageReport:
    """Test coverage introspection methods."""

    def test_unmapped_list_matches_expected_set(self, adapter: OASFAdapter) -> None:
        unmapped = adapter.unmapped_capabilities()
        assert len(unmapped) == 6
        expected = {"attribute", "integrate", "recall", "receive", "send", "transition"}
        assert set(unmapped) == expected

    def test_partial_dict_has_expected_entries(self, adapter: OASFAdapter) -> None:
        partial = adapter.partial_capabilities()
        assert len(partial) == 7
        expected = {
            "checkpoint",
            "simulate",
            "inquire",
            "synchronize",
            "state",
            "ground",
            "rollback",
        }
        assert set(partial.keys()) == expected

    def test_partial_capabilities_have_valid_oasf_codes(
        self, adapter: OASFAdapter
    ) -> None:
        """Each partial capability must reference valid, non-empty OASF codes."""
        partial = adapter.partial_capabilities()
        for cap_id, oasf_codes in partial.items():
            assert len(oasf_codes) > 0, (
                f"Partial capability '{cap_id}' has empty oasf_codes"
            )
            for code in oasf_codes:
                mapping = adapter.get_mapping(code)
                assert mapping is not None, (
                    f"Partial capability '{cap_id}' references unknown OASF code '{code}'"
                )

    def test_coverage_report_totals(self, adapter: OASFAdapter) -> None:
        report = adapter.coverage_report()
        assert report["total_capabilities"] == 36
        assert report["unmapped_count"] == 6
        assert report["partial_count"] == 7
        assert report["fully_mapped"] == 23

    def test_total_capabilities_matches_registry(self, adapter: OASFAdapter) -> None:
        """The hardcoded total in coverage_report() must match the actual ontology."""
        report = adapter.coverage_report()
        actual_count = adapter._registry.capability_count
        assert report["total_capabilities"] == actual_count, (
            f"coverage_report() hardcodes {report['total_capabilities']} "
            f"but ontology has {actual_count} capabilities"
        )

    def test_coverage_report_includes_ga_extension_count(
        self, adapter: OASFAdapter
    ) -> None:
        report = adapter.coverage_report()
        assert "ga_extension_count" in report
        assert report["ga_extension_count"] == 6

    def test_coverage_report_includes_oasf_version(self, adapter: OASFAdapter) -> None:
        report = adapter.coverage_report()
        assert report["oasf_version"] == "0.8.0"
        assert report["mapping_version"] == "1.1.0"
