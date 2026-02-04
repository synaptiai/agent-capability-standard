"""
Automated Capability Discovery

Detects capabilities from natural language task descriptions and
synthesizes valid workflows automatically.

Usage:
    from grounded_agency.discovery import DiscoveryPipeline
    from grounded_agency import CapabilityRegistry, WorkflowEngine

    registry = CapabilityRegistry("schemas/capability_ontology.yaml")
    engine = WorkflowEngine("schemas/capability_ontology.yaml")
    pipeline = DiscoveryPipeline(registry, engine)

    result = await pipeline.discover("Analyze CSV for anomalies and send report")
"""

from .gap_detector import GapDetector
from .pipeline import DiscoveryPipeline
from .synthesizer import WorkflowSynthesizer
from .types import (
    CapabilityGap,
    CapabilityMatch,
    DiscoveryResult,
    LLMFunction,
    ProposedCapability,
    SynthesizedWorkflow,
    TaskRequirement,
)

__all__ = [
    "DiscoveryPipeline",
    "GapDetector",
    "WorkflowSynthesizer",
    # Types
    "CapabilityGap",
    "CapabilityMatch",
    "DiscoveryResult",
    "LLMFunction",
    "ProposedCapability",
    "SynthesizedWorkflow",
    "TaskRequirement",
]
