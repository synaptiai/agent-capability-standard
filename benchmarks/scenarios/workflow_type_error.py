"""
Scenario 4: Workflow Type Error

Tests whether Grounded Agency's design-time type checking
catches errors before runtime.

Setup:
- Workflows with intentional type mismatches
- Baseline executes and fails at runtime
- GA validates and catches at design time

Metrics:
- Detection rate: Errors caught before runtime
- Time to detection: Design-time vs runtime
- Suggestion accuracy: Correct coercions suggested
"""

from pathlib import Path
from typing import Any

from grounded_agency.utils.safe_yaml import safe_yaml_load

from .base import BenchmarkScenario

# Path to the canonical coercion registry
_COERCION_REGISTRY_PATH = (
    Path(__file__).parent.parent.parent
    / "schemas"
    / "transforms"
    / "transform_coercion_registry.yaml"
)


def _load_coercions() -> dict[tuple[str, str], str]:
    """Load coercion mappings from the canonical transform_coercion_registry.yaml."""
    if not _COERCION_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Coercion registry not found: {_COERCION_REGISTRY_PATH}. "
            "Benchmark integrity requires this file."
        )

    data = safe_yaml_load(_COERCION_REGISTRY_PATH)
    coercions: dict[tuple[str, str], str] = {}
    for entry in data.get("coercions", []):
        from_type = entry["from"]
        to_type = entry["to"]
        mapping_ref = entry.get("mapping_ref", "")
        mapping_name = mapping_ref.rsplit("/", 1)[-1].replace(".yaml", "")
        coercions[(from_type, to_type)] = mapping_name
    return coercions


_TYPES = {
    "string": {"compatible_with": ["string"]},
    "number": {"compatible_with": ["number", "integer"]},
    "integer": {"compatible_with": ["integer"]},
    "boolean": {"compatible_with": ["boolean"]},
    "object": {"compatible_with": ["object"]},
    "array<string>": {"compatible_with": ["array<string>", "array<any>"]},
    "array<object>": {"compatible_with": ["array<object>", "array<any>"]},
    "array<any>": {"compatible_with": ["array<any>"]},
}

COERCIONS = _load_coercions()


class WorkflowTypeErrorScenario(BenchmarkScenario):
    """Benchmark for workflow type error detection."""

    name = "workflow_type_error"
    description = "Tests design-time type validation vs runtime errors"

    def __init__(self, seed: int = 42, verbose: bool = False):
        super().__init__(seed, verbose)
        self.test_workflows: list[dict] = []

    def setup(self) -> None:
        """Create test workflows with known type mismatches."""
        self.test_workflows = [
            # Workflow 1: array<string> -> expects object
            {
                "id": 1,
                "name": "array_to_object_mismatch",
                "steps": [
                    {
                        "capability": "retrieve",
                        "output_type": "array<string>",
                        "store_as": "documents",
                    },
                    {
                        "capability": "transform",
                        "input_binding": "${documents}",
                        "input_expects": "object",
                    },
                ],
                "has_error": True,
                "error_type": "type_mismatch",
                "coercion_exists": False,  # No direct array<string> -> object
            },
            # Workflow 2: string -> expects number (coercible)
            {
                "id": 2,
                "name": "string_to_number_coercible",
                "steps": [
                    {
                        "capability": "retrieve",
                        "output_type": "string",
                        "store_as": "raw_value",
                    },
                    {
                        "capability": "measure",
                        "input_binding": "${raw_value}",
                        "input_expects": "number",
                    },
                ],
                "has_error": True,
                "error_type": "type_mismatch",
                "coercion_exists": True,
                "coercion": "transform_mapping_coerce_string_to_number",
            },
            # Workflow 3: Valid workflow (no error)
            {
                "id": 3,
                "name": "valid_string_string",
                "steps": [
                    {
                        "capability": "retrieve",
                        "output_type": "string",
                        "store_as": "content",
                    },
                    {
                        "capability": "generate",
                        "input_binding": "${content}",
                        "input_expects": "string",
                    },
                ],
                "has_error": False,
                "error_type": None,
                "coercion_exists": False,
            },
            # Workflow 4: number -> expects string (coercible)
            {
                "id": 4,
                "name": "number_to_string_coercible",
                "steps": [
                    {
                        "capability": "measure",
                        "output_type": "number",
                        "store_as": "metric",
                    },
                    {
                        "capability": "generate",
                        "input_binding": "${metric}",
                        "input_expects": "string",
                    },
                ],
                "has_error": True,
                "error_type": "type_mismatch",
                "coercion_exists": True,
                "coercion": "transform_mapping_coerce_number_to_string",
            },
            # Workflow 5: Missing binding reference
            {
                "id": 5,
                "name": "missing_binding",
                "steps": [
                    {
                        "capability": "retrieve",
                        "output_type": "string",
                        "store_as": "data",
                    },
                    {
                        "capability": "transform",
                        "input_binding": "${nonexistent}",  # Bad reference
                        "input_expects": "string",
                    },
                ],
                "has_error": True,
                "error_type": "unresolved_reference",
                "coercion_exists": False,
            },
            # Workflow 6: object -> expects string (coercible via stringify)
            {
                "id": 6,
                "name": "object_to_string_coercible",
                "steps": [
                    {
                        "capability": "state",
                        "output_type": "object",
                        "store_as": "world_state",
                    },
                    {
                        "capability": "send",
                        "input_binding": "${world_state}",
                        "input_expects": "string",
                    },
                ],
                "has_error": True,
                "error_type": "type_mismatch",
                "coercion_exists": True,
                "coercion": "transform_mapping_stringify_object",
            },
            # Workflow 7: array<object> -> array<string> (coercible via project)
            {
                "id": 7,
                "name": "array_object_to_array_string",
                "steps": [
                    {
                        "capability": "search",
                        "output_type": "array<object>",
                        "store_as": "results",
                    },
                    {
                        "capability": "generate",
                        "input_binding": "${results}",
                        "input_expects": "array<string>",
                    },
                ],
                "has_error": True,
                "error_type": "type_mismatch",
                "coercion_exists": True,
                "coercion": "transform_mapping_project_array_object_to_array_string",
            },
            # Workflow 8: Valid array workflow
            {
                "id": 8,
                "name": "valid_array_array",
                "steps": [
                    {
                        "capability": "search",
                        "output_type": "array<string>",
                        "store_as": "items",
                    },
                    {
                        "capability": "integrate",
                        "input_binding": "${items}",
                        "input_expects": "array<string>",
                    },
                ],
                "has_error": False,
                "error_type": None,
                "coercion_exists": False,
            },
        ]

        self.log(f"Created {len(self.test_workflows)} test workflows")
        error_count = sum(1 for w in self.test_workflows if w["has_error"])
        self.log(f"Workflows with errors: {error_count}")

    def _simulate_runtime_execution(self, workflow: dict) -> dict:
        """
        Simulate runtime execution that only catches errors during execution.

        Returns error information if execution fails.
        """
        # Simulate executing steps
        stored_outputs = {}

        for step in workflow["steps"]:
            # Simulate storing output
            if "store_as" in step:
                stored_outputs[step["store_as"]] = {
                    "type": step.get("output_type", "any"),
                    "value": f"mock_value_{step['store_as']}",
                }

            # Check binding resolution
            if "input_binding" in step:
                ref_name = step["input_binding"].replace("${", "").replace("}", "")
                if ref_name not in stored_outputs:
                    return {
                        "success": False,
                        "error_at": "runtime",
                        "error_type": "unresolved_reference",
                        "message": f"Cannot resolve ${{{ref_name}}}",
                    }

                # Type check at runtime (simulated)
                actual_type = stored_outputs[ref_name]["type"]
                expected_type = step.get("input_expects", "any")

                if (
                    expected_type != "any"
                    and actual_type != expected_type
                    and expected_type
                    not in _TYPES.get(actual_type, {}).get("compatible_with", [])
                ):
                    return {
                        "success": False,
                        "error_at": "runtime",
                        "error_type": "type_mismatch",
                        "message": f"Expected {expected_type}, got {actual_type}",
                    }

        return {"success": True, "error_at": None, "error_type": None}

    def _validate_design_time(self, workflow: dict) -> dict:
        """
        Validate workflow at design time using GA type inference.

        Returns error information and suggestions if validation fails.
        """
        stored_schemas = {}
        errors = []
        suggestions = []

        for step in workflow["steps"]:
            # Record output schema
            if "store_as" in step:
                stored_schemas[step["store_as"]] = step.get("output_type", "any")

            # Validate binding
            if "input_binding" in step:
                ref_name = step["input_binding"].replace("${", "").replace("}", "")

                # Reference resolution check
                if ref_name not in stored_schemas:
                    errors.append(
                        {
                            "type": "unresolved_reference",
                            "message": f"Unresolved reference: ${{{ref_name}}}",
                            "step": step.get("capability"),
                        }
                    )
                    continue

                # Type compatibility check
                actual_type = stored_schemas[ref_name]
                expected_type = step.get("input_expects", "any")

                if expected_type != "any" and actual_type != expected_type:
                    compatible = _TYPES.get(actual_type, {}).get("compatible_with", [])
                    if expected_type not in compatible:
                        error = {
                            "type": "type_mismatch",
                            "message": f"Type mismatch: {actual_type} -> {expected_type}",
                            "step": step.get("capability"),
                        }
                        errors.append(error)

                        # Check for coercion
                        coercion_key = (actual_type, expected_type)
                        if coercion_key in COERCIONS:
                            suggestions.append(
                                {
                                    "insert_transform": COERCIONS[coercion_key],
                                    "before_step": step.get("capability"),
                                }
                            )

        if errors:
            return {
                "success": False,
                "error_at": "design_time",
                "errors": errors,
                "suggestions": suggestions,
            }

        return {"success": True, "error_at": None, "errors": [], "suggestions": []}

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: Runtime-only error detection.

        Executes workflow and catches errors during execution.
        """
        results = []
        errors_detected = 0

        for workflow in self.test_workflows:
            result = self._simulate_runtime_execution(workflow)

            detected = not result["success"]
            if detected:
                errors_detected += 1

            # Baseline never detects at design time
            results.append(
                {
                    "workflow_id": workflow["id"],
                    "has_error": workflow["has_error"],
                    "detected": detected,
                    "detected_at": result.get("error_at"),
                    "suggestions": [],
                }
            )

        error_workflows = [w for w in self.test_workflows if w["has_error"]]
        detection_rate = (
            errors_detected / len(error_workflows) if error_workflows else 1.0
        )

        self.log(f"Baseline detection rate: {detection_rate:.0%}")
        self.log("Baseline design-time detections: 0%")

        return {
            "detection_rate": detection_rate,
            "design_time_detection_rate": 0.0,
            "runtime_detection_rate": detection_rate,
            "suggestion_accuracy": 0.0,  # No suggestions
            "results": results,
        }

    def run_ga(self) -> dict[str, Any]:
        """
        Grounded Agency: Design-time type validation.

        Validates workflow before execution and suggests coercions.
        """
        results = []
        errors_detected = 0
        design_time_detections = 0
        correct_suggestions = 0
        total_coercible = 0

        for workflow in self.test_workflows:
            result = self._validate_design_time(workflow)

            detected = not result["success"]
            if detected:
                errors_detected += 1
                design_time_detections += 1

            # Check suggestion accuracy for coercible errors
            if workflow.get("coercion_exists"):
                total_coercible += 1
                expected_coercion = workflow.get("coercion")
                suggested_coercions = [
                    s["insert_transform"] for s in result.get("suggestions", [])
                ]
                if expected_coercion in suggested_coercions:
                    correct_suggestions += 1

            results.append(
                {
                    "workflow_id": workflow["id"],
                    "has_error": workflow["has_error"],
                    "detected": detected,
                    "detected_at": result.get("error_at"),
                    "suggestions": result.get("suggestions", []),
                }
            )

        error_workflows = [w for w in self.test_workflows if w["has_error"]]
        detection_rate = (
            errors_detected / len(error_workflows) if error_workflows else 1.0
        )
        suggestion_accuracy = (
            correct_suggestions / total_coercible if total_coercible else 1.0
        )

        self.log(f"GA detection rate: {detection_rate:.0%}")
        self.log(f"GA design-time detection rate: {detection_rate:.0%}")
        self.log(f"GA suggestion accuracy: {suggestion_accuracy:.0%}")

        return {
            "detection_rate": detection_rate,
            "design_time_detection_rate": detection_rate,
            "runtime_detection_rate": 0.0,  # All caught at design time
            "suggestion_accuracy": suggestion_accuracy,
            "results": results,
        }

    def compare(
        self, baseline_result: dict[str, Any], ga_result: dict[str, Any]
    ) -> dict[str, float]:
        """Compare detection rates and timing."""
        design_time_improvement = (
            ga_result["design_time_detection_rate"]
            - baseline_result["design_time_detection_rate"]
        )

        comparison = {
            "design_time_detection_improvement": design_time_improvement,
            "runtime_errors_prevented": baseline_result["runtime_detection_rate"],
            "suggestion_accuracy": ga_result["suggestion_accuracy"],
        }

        self.log(f"Design-time detection improvement: +{design_time_improvement:.0%}")
        self.log(
            f"Runtime errors prevented: {baseline_result['runtime_detection_rate']:.0%}"
        )
        self.log(f"Suggestion accuracy: {ga_result['suggestion_accuracy']:.0%}")

        return comparison
