"""Shared fixtures for discovery tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from grounded_agency.capabilities.registry import CapabilityRegistry
from grounded_agency.discovery.analyzer import TaskAnalyzer
from grounded_agency.discovery.classifier import CapabilityClassifier
from grounded_agency.discovery.gap_detector import GapDetector
from grounded_agency.discovery.pipeline import DiscoveryPipeline
from grounded_agency.discovery.synthesizer import WorkflowSynthesizer
from grounded_agency.discovery.types import LLMFunction
from grounded_agency.state.evidence_store import EvidenceStore
from grounded_agency.workflows.engine import WorkflowEngine


@pytest.fixture
def ontology_path() -> str:
    """Path to the real capability ontology."""
    return str(
        Path(__file__).parent.parent.parent / "schemas" / "capability_ontology.yaml"
    )


@pytest.fixture
def catalog_path() -> str:
    """Path to the real workflow catalog."""
    return str(
        Path(__file__).parent.parent.parent / "schemas" / "workflow_catalog.yaml"
    )


@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    """Real CapabilityRegistry loaded from ontology."""
    return CapabilityRegistry(ontology_path)


@pytest.fixture
def engine(ontology_path: str, catalog_path: str) -> WorkflowEngine:
    """Real WorkflowEngine loaded from catalog."""
    eng = WorkflowEngine(ontology_path=ontology_path)
    catalog = Path(catalog_path)
    if catalog.exists():
        eng.load_catalog(catalog_path)
    return eng


@pytest.fixture
def evidence_store() -> EvidenceStore:
    """Fresh EvidenceStore."""
    return EvidenceStore()


@pytest.fixture
def mock_llm_fn() -> LLMFunction:
    """Mock LLM function that returns pre-defined analysis results."""

    async def _llm(prompt: str, schema: dict[str, Any] | None) -> dict[str, Any]:
        """Return canned responses based on prompt content."""
        if "capability analyst" in prompt.lower():
            # Analysis + classification prompt
            return {
                "requirements": [
                    {
                        "action": "find",
                        "target": "files",
                        "constraints": [],
                        "domain_hint": None,
                    },
                    {
                        "action": "detect",
                        "target": "patterns",
                        "constraints": [],
                        "domain_hint": "pattern",
                    },
                ],
                "matches": [
                    {
                        "requirement_index": 0,
                        "capability_id": "search",
                        "confidence": 0.9,
                        "reasoning": "Finding files maps to search capability",
                        "domain": None,
                    },
                    {
                        "requirement_index": 1,
                        "capability_id": "detect",
                        "confidence": 0.85,
                        "reasoning": "Pattern detection maps to detect capability",
                        "domain": "pattern",
                    },
                ],
            }
        elif "ontology designer" in prompt.lower():
            # Gap proposal prompt
            return {
                "id": "negotiate",
                "layer": "COORDINATE",
                "description": "Negotiate terms with external parties",
                "risk": "medium",
                "mutation": False,
                "input_schema": {
                    "type": "object",
                    "properties": {"terms": {"type": "object"}},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"agreement": {"type": "object"}},
                },
                "suggested_edges": [
                    {"from": "negotiate", "to": "inquire", "type": "requires"}
                ],
                "reasoning": "Negotiation requires inquiry but is a distinct coordination action",
            }
        elif "workflow composer" in prompt.lower():
            # Binding generation prompt
            return {
                "steps": [
                    {
                        "capability": "search",
                        "store_as": "search_out",
                        "purpose": "Find matching files",
                        "input_bindings": {},
                    },
                    {
                        "capability": "detect",
                        "store_as": "detect_out",
                        "purpose": "Detect patterns in files",
                        "input_bindings": {"source": "${search_out}"},
                    },
                ],
            }
        # Default: return empty
        return {}

    return _llm


@pytest.fixture
def analyzer(registry: CapabilityRegistry) -> TaskAnalyzer:
    """TaskAnalyzer without LLM (keyword fallback)."""
    return TaskAnalyzer(registry)


@pytest.fixture
def analyzer_with_llm(
    registry: CapabilityRegistry, mock_llm_fn: LLMFunction
) -> TaskAnalyzer:
    """TaskAnalyzer with mock LLM."""
    return TaskAnalyzer(registry, llm_fn=mock_llm_fn)


@pytest.fixture
def classifier(registry: CapabilityRegistry) -> CapabilityClassifier:
    """CapabilityClassifier."""
    return CapabilityClassifier(registry)


@pytest.fixture
def gap_detector(registry: CapabilityRegistry) -> GapDetector:
    """GapDetector without LLM."""
    return GapDetector(registry)


@pytest.fixture
def gap_detector_with_llm(
    registry: CapabilityRegistry, mock_llm_fn: LLMFunction
) -> GapDetector:
    """GapDetector with mock LLM."""
    return GapDetector(registry, llm_fn=mock_llm_fn)


@pytest.fixture
def synthesizer(
    registry: CapabilityRegistry, engine: WorkflowEngine
) -> WorkflowSynthesizer:
    """WorkflowSynthesizer without LLM."""
    return WorkflowSynthesizer(registry, engine)


@pytest.fixture
def synthesizer_with_llm(
    registry: CapabilityRegistry, engine: WorkflowEngine, mock_llm_fn: LLMFunction
) -> WorkflowSynthesizer:
    """WorkflowSynthesizer with mock LLM."""
    return WorkflowSynthesizer(registry, engine, llm_fn=mock_llm_fn)


@pytest.fixture
def pipeline(registry: CapabilityRegistry, engine: WorkflowEngine) -> DiscoveryPipeline:
    """DiscoveryPipeline without LLM (keyword fallback)."""
    return DiscoveryPipeline(registry, engine)


@pytest.fixture
def pipeline_with_llm(
    registry: CapabilityRegistry, engine: WorkflowEngine, mock_llm_fn: LLMFunction
) -> DiscoveryPipeline:
    """DiscoveryPipeline with mock LLM."""
    return DiscoveryPipeline(registry, engine, llm_fn=mock_llm_fn)
