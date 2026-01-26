"""
Scenario 5: Capability Gap Detection

Tests whether Grounded Agency's dependency graph detects
missing capabilities before workflow execution.

Setup:
- Workflows requiring various capabilities
- Agent manifest with subset of capabilities
- Baseline attempts execution and fails at runtime
- GA checks dependencies and blocks before execution

Metrics:
- Prevention rate: Workflows blocked before execution
- Resource savings: Compute not wasted on doomed workflows
- Gap identification: Correctly identifies missing capabilities
"""

from typing import Any

from .base import BenchmarkScenario


# Simplified capability dependencies from ontology
CAPABILITY_DEPS = {
    "retrieve": [],
    "search": [],
    "observe": [],
    "receive": [],
    "detect": ["observe"],
    "classify": ["detect"],
    "measure": ["observe"],
    "predict": ["measure"],
    "compare": [],
    "discover": ["search"],
    "plan": ["compare"],
    "decompose": [],
    "critique": ["compare"],
    "explain": [],
    "state": ["observe"],
    "transition": ["state"],
    "attribute": ["state"],
    "ground": [],
    "simulate": ["state", "transition"],
    "generate": [],
    "transform": [],
    "integrate": [],
    "execute": ["plan"],
    "mutate": ["checkpoint"],  # Hard dependency
    "send": [],
    "verify": [],
    "checkpoint": [],
    "rollback": ["checkpoint"],
    "constrain": [],
    "audit": [],
    "persist": [],
    "recall": [],
    "delegate": ["plan"],
    "synchronize": [],
    "invoke": [],
    "inquire": [],
}


class CapabilityGapScenario(BenchmarkScenario):
    """Benchmark for capability gap detection."""

    name = "capability_gap"
    description = "Tests pre-execution dependency checking vs runtime failures"

    def __init__(self, seed: int = 42, verbose: bool = False):
        super().__init__(seed, verbose)
        self.test_cases: list[dict] = []
        # Agent has limited capabilities
        self.agent_capabilities = {
            "retrieve",
            "search",
            "observe",
            "detect",
            "transform",
            "generate",
            "execute",
            "verify",
            "plan",
            "compare",
        }

    def setup(self) -> None:
        """Create test workflows with known capability requirements."""
        self.test_cases = [
            # Case 1: All capabilities available
            {
                "id": 1,
                "name": "fully_capable",
                "workflow": ["retrieve", "transform", "generate"],
                "has_gap": False,
                "missing": [],
            },
            # Case 2: Missing 'send' capability
            {
                "id": 2,
                "name": "missing_send",
                "workflow": ["retrieve", "transform", "generate", "send"],
                "has_gap": True,
                "missing": ["send"],
            },
            # Case 3: Missing 'mutate' and 'checkpoint' (dependency chain)
            {
                "id": 3,
                "name": "missing_mutation_chain",
                "workflow": ["retrieve", "plan", "execute", "mutate"],
                "has_gap": True,
                "missing": ["checkpoint", "mutate"],  # mutate requires checkpoint
            },
            # Case 4: Missing 'persist'
            {
                "id": 4,
                "name": "missing_persist",
                "workflow": ["observe", "detect", "persist"],
                "has_gap": True,
                "missing": ["persist"],
            },
            # Case 5: Available workflow with dependencies
            {
                "id": 5,
                "name": "with_deps_available",
                "workflow": ["observe", "detect", "verify"],
                "has_gap": False,
                "missing": [],
            },
            # Case 6: Missing 'delegate'
            {
                "id": 6,
                "name": "missing_delegate",
                "workflow": ["plan", "delegate", "synchronize"],
                "has_gap": True,
                "missing": ["delegate", "synchronize"],
            },
            # Case 7: Missing 'rollback' (requires checkpoint)
            {
                "id": 7,
                "name": "missing_rollback",
                "workflow": ["retrieve", "transform", "rollback"],
                "has_gap": True,
                "missing": ["checkpoint", "rollback"],
            },
            # Case 8: Simple available workflow
            {
                "id": 8,
                "name": "simple_available",
                "workflow": ["search", "transform"],
                "has_gap": False,
                "missing": [],
            },
            # Case 9: Missing 'simulate' (requires state, transition)
            {
                "id": 9,
                "name": "missing_simulate",
                "workflow": ["observe", "simulate"],
                "has_gap": True,
                "missing": ["state", "transition", "simulate"],
            },
            # Case 10: Missing 'audit'
            {
                "id": 10,
                "name": "missing_audit",
                "workflow": ["execute", "verify", "audit"],
                "has_gap": True,
                "missing": ["audit"],
            },
        ]

        self.log(f"Created {len(self.test_cases)} test cases")
        self.log(f"Agent capabilities: {len(self.agent_capabilities)}")

    def _get_all_required_capabilities(self, workflow: list[str]) -> set[str]:
        """Get all capabilities required including dependencies."""
        required = set(workflow)
        to_check = list(workflow)

        while to_check:
            cap = to_check.pop()
            deps = CAPABILITY_DEPS.get(cap, [])
            for dep in deps:
                if dep not in required:
                    required.add(dep)
                    to_check.append(dep)

        return required

    def _simulate_runtime_execution(self, workflow: list[str]) -> dict:
        """
        Simulate runtime execution that discovers gaps during execution.

        Returns result including steps completed before failure.
        """
        steps_completed = []
        compute_used = 0

        for cap in workflow:
            # Check if capability is available
            if cap not in self.agent_capabilities:
                return {
                    "success": False,
                    "failed_at": "runtime",
                    "missing_capability": cap,
                    "steps_completed": steps_completed,
                    "compute_wasted": compute_used,
                }

            # Simulate compute cost per step
            compute_used += 100
            steps_completed.append(cap)

        return {
            "success": True,
            "failed_at": None,
            "missing_capability": None,
            "steps_completed": steps_completed,
            "compute_wasted": 0,  # None wasted if successful
        }

    def _validate_capabilities(self, workflow: list[str]) -> dict:
        """
        Validate workflow capabilities before execution.

        Returns gaps found and prevents execution if gaps exist.
        """
        required = self._get_all_required_capabilities(workflow)
        available = self.agent_capabilities

        missing = required - available

        if missing:
            return {
                "success": False,
                "failed_at": "design_time",
                "missing_capabilities": sorted(missing),
                "required_capabilities": sorted(required),
                "blocked": True,
                "compute_saved": len(workflow) * 100,
            }

        return {
            "success": True,
            "failed_at": None,
            "missing_capabilities": [],
            "required_capabilities": sorted(required),
            "blocked": False,
            "compute_saved": 0,
        }

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: Attempt execution without pre-validation.

        Discovers missing capabilities at runtime, wasting compute.
        """
        results = []
        total_compute_wasted = 0
        gaps_detected = 0
        false_negatives = 0  # Has gap but wasn't detected

        for case in self.test_cases:
            result = self._simulate_runtime_execution(case["workflow"])

            detected_gap = not result["success"]
            if detected_gap:
                gaps_detected += 1
                total_compute_wasted += result["compute_wasted"]

            # Check for false negatives (should have gap but didn't detect all)
            if case["has_gap"] and result["success"]:
                false_negatives += 1

            results.append(
                {
                    "case_id": case["id"],
                    "has_gap": case["has_gap"],
                    "detected": detected_gap,
                    "detected_at": result.get("failed_at"),
                    "compute_wasted": result.get("compute_wasted", 0),
                    "steps_before_failure": len(result.get("steps_completed", [])),
                }
            )

        gap_cases = [c for c in self.test_cases if c["has_gap"]]
        detection_rate = gaps_detected / len(gap_cases) if gap_cases else 1.0

        self.log(f"Baseline gap detection rate: {detection_rate:.0%}")
        self.log(f"Baseline compute wasted: {total_compute_wasted}")
        self.log(f"Baseline design-time detections: 0%")

        return {
            "detection_rate": detection_rate,
            "design_time_detection_rate": 0.0,
            "compute_wasted": total_compute_wasted,
            "compute_saved": 0,
            "false_negatives": false_negatives,
            "results": results,
        }

    def run_ga(self) -> dict[str, Any]:
        """
        Grounded Agency: Pre-execution capability validation.

        Checks dependency graph and blocks workflows with gaps.
        """
        results = []
        total_compute_saved = 0
        gaps_detected = 0
        correct_gap_identification = 0

        for case in self.test_cases:
            result = self._validate_capabilities(case["workflow"])

            detected_gap = not result["success"]
            if detected_gap:
                gaps_detected += 1
                total_compute_saved += result["compute_saved"]

            # Check if gap identification is correct
            if case["has_gap"]:
                expected_missing = set(case["missing"])
                actual_missing = set(result.get("missing_capabilities", []))
                # Check if we found at least the expected gaps
                if expected_missing <= actual_missing:
                    correct_gap_identification += 1

            results.append(
                {
                    "case_id": case["id"],
                    "has_gap": case["has_gap"],
                    "detected": detected_gap,
                    "detected_at": result.get("failed_at"),
                    "missing_capabilities": result.get("missing_capabilities", []),
                    "compute_saved": result.get("compute_saved", 0),
                }
            )

        gap_cases = [c for c in self.test_cases if c["has_gap"]]
        detection_rate = gaps_detected / len(gap_cases) if gap_cases else 1.0
        identification_accuracy = (
            correct_gap_identification / len(gap_cases) if gap_cases else 1.0
        )

        self.log(f"GA gap detection rate: {detection_rate:.0%}")
        self.log(f"GA compute saved: {total_compute_saved}")
        self.log(f"GA identification accuracy: {identification_accuracy:.0%}")

        return {
            "detection_rate": detection_rate,
            "design_time_detection_rate": detection_rate,
            "compute_wasted": 0,
            "compute_saved": total_compute_saved,
            "identification_accuracy": identification_accuracy,
            "results": results,
        }

    def compare(
        self, baseline_result: dict[str, Any], ga_result: dict[str, Any]
    ) -> dict[str, float]:
        """Compare detection rates and resource savings."""
        detection_improvement = (
            ga_result["detection_rate"] - baseline_result["detection_rate"]
        )
        compute_savings = (
            baseline_result["compute_wasted"] + ga_result["compute_saved"]
        )

        comparison = {
            "detection_improvement": detection_improvement,
            "design_time_detection_improvement": ga_result["design_time_detection_rate"],
            "compute_savings": compute_savings,
            "identification_accuracy": ga_result["identification_accuracy"],
        }

        self.log(f"Detection improvement: +{detection_improvement:.0%}")
        self.log(f"Compute savings: {compute_savings}")
        self.log(f"Gap identification accuracy: {ga_result['identification_accuracy']:.0%}")

        return comparison
