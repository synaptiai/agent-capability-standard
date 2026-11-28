"""
Benchmark scenarios for validating Grounded Agency.

Each scenario compares baseline (naive) implementations against
Grounded Agency implementations to measure improvement.
"""

from .base import BenchmarkScenario
from .capability_gap import CapabilityGapScenario
from .conflicting_sources import ConflictingSourcesScenario
from .decision_audit import DecisionAuditScenario
from .explanation_faithfulness import ExplanationFaithfulnessScenario
from .mutation_recovery import MutationRecoveryScenario
from .prompt_injection import PromptInjectionScenario
from .safety_layer import (
    CheckpointGateScenario,
    DestinationPolicyScenario,
    GroundingGateScenario,
    SecretRedactionScenario,
)
from .workflow_type_error import WorkflowTypeErrorScenario

SCENARIOS = {
    "conflicting_sources": ConflictingSourcesScenario,
    "mutation_recovery": MutationRecoveryScenario,
    "decision_audit": DecisionAuditScenario,
    "workflow_type_error": WorkflowTypeErrorScenario,
    "capability_gap": CapabilityGapScenario,
    "explanation_faithfulness": ExplanationFaithfulnessScenario,
    "destination_policy": DestinationPolicyScenario,
    "secret_redaction": SecretRedactionScenario,
    "checkpoint_gate": CheckpointGateScenario,
    "grounding_gate": GroundingGateScenario,
    "prompt_injection": PromptInjectionScenario,
}

__all__ = [
    "BenchmarkScenario",
    "ConflictingSourcesScenario",
    "MutationRecoveryScenario",
    "DecisionAuditScenario",
    "WorkflowTypeErrorScenario",
    "CapabilityGapScenario",
    "ExplanationFaithfulnessScenario",
    "DestinationPolicyScenario",
    "SecretRedactionScenario",
    "CheckpointGateScenario",
    "GroundingGateScenario",
    "PromptInjectionScenario",
    "SCENARIOS",
]
