"""
Benchmark scenarios for validating Grounded Agency.

Each scenario compares baseline (naive) implementations against
Grounded Agency implementations to measure improvement.
"""

from .base import BenchmarkScenario
from .capability_gap import CapabilityGapScenario
from .conflicting_sources import ConflictingSourcesScenario
from .decision_audit import DecisionAuditScenario
from .mutation_recovery import MutationRecoveryScenario
from .workflow_type_error import WorkflowTypeErrorScenario

SCENARIOS = {
    "conflicting_sources": ConflictingSourcesScenario,
    "mutation_recovery": MutationRecoveryScenario,
    "decision_audit": DecisionAuditScenario,
    "workflow_type_error": WorkflowTypeErrorScenario,
    "capability_gap": CapabilityGapScenario,
}

__all__ = [
    "BenchmarkScenario",
    "ConflictingSourcesScenario",
    "MutationRecoveryScenario",
    "DecisionAuditScenario",
    "WorkflowTypeErrorScenario",
    "CapabilityGapScenario",
    "SCENARIOS",
]
