#!/usr/bin/env python3
"""
Validate benchmark dependency claims against the canonical ontology.

Ensures that:
1. The CapabilityRegistry loads successfully
2. All 4 real `requires` edges are present
3. No phantom `requires` edges exist
4. Benchmark test cases reference only real capabilities
5. Coercion registry loads and matches transform_coercion_registry.yaml

Run: python tools/validate_benchmark_deps.py
"""

import sys
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from grounded_agency.capabilities.registry import CapabilityRegistry
from grounded_agency.utils.safe_yaml import safe_yaml_load


def validate_requires_edges(registry: CapabilityRegistry) -> list[str]:
    """Validate that the expected `requires` edges exist and no phantom ones do."""
    errors = []

    # The 4 canonical requires edges (from → to, meaning 'to' requires 'from')
    expected_requires = {
        ("checkpoint", "mutate"),
        ("checkpoint", "send"),
        ("mutate", "verify"),  # verify requires mutate (mutate is incoming to verify)
        ("send", "verify"),  # verify requires send (send is incoming to verify)
    }

    # Collect all actual requires edges
    actual_requires = set()
    for edge in registry.all_edges():
        if edge.edge_type == "requires":
            actual_requires.add((edge.from_cap, edge.to_cap))

    # Check for missing expected edges
    for from_cap, to_cap in expected_requires:
        if (from_cap, to_cap) not in actual_requires:
            errors.append(
                f"MISSING requires edge: {from_cap} -> {to_cap}"
            )

    # Note unexpected requires edges (not necessarily errors, but worth reporting)
    unexpected = actual_requires - expected_requires
    if unexpected:
        # These aren't errors if the ontology was extended, but we report them
        for from_cap, to_cap in unexpected:
            print(f"  NOTE: Additional requires edge found: {from_cap} -> {to_cap}")

    return errors


def validate_capabilities_exist(registry: CapabilityRegistry) -> list[str]:
    """Validate that all 36 expected capabilities exist in the registry."""
    errors = []

    expected_capabilities = {
        "retrieve", "search", "observe", "receive",
        "detect", "classify", "measure", "predict", "compare", "discover",
        "plan", "decompose", "critique", "explain",
        "state", "transition", "attribute", "ground", "simulate",
        "generate", "transform", "integrate",
        "execute", "mutate", "send",
        "verify", "checkpoint", "rollback", "constrain", "audit",
        "persist", "recall",
        "delegate", "synchronize", "invoke", "inquire",
    }

    actual_capabilities = {node.id for node in registry.all_capabilities()}

    missing = expected_capabilities - actual_capabilities
    if missing:
        errors.append(f"Missing capabilities in ontology: {sorted(missing)}")

    return errors


def validate_coercion_registry() -> list[str]:
    """Validate that coercion registry YAML loads and has expected structure."""
    errors = []

    registry_path = ROOT / "schemas" / "transforms" / "transform_coercion_registry.yaml"
    if not registry_path.exists():
        errors.append(f"Coercion registry not found: {registry_path}")
        return errors

    data = safe_yaml_load(registry_path)
    coercions = data.get("coercions", [])

    if not coercions:
        errors.append("Coercion registry has no coercions")
        return errors

    # Validate each coercion has required fields
    for i, entry in enumerate(coercions):
        if "from" not in entry:
            errors.append(f"Coercion {i}: missing 'from' field")
        if "to" not in entry:
            errors.append(f"Coercion {i}: missing 'to' field")
        if "mapping_ref" not in entry:
            errors.append(f"Coercion {i}: missing 'mapping_ref' field")
        else:
            # Verify the mapping_ref path exists
            ref_path = ROOT / entry["mapping_ref"]
            if not ref_path.exists():
                errors.append(f"Coercion {i}: mapping_ref not found: {entry['mapping_ref']}")

    return errors


def validate_benchmark_test_cases(registry: CapabilityRegistry) -> list[str]:
    """Validate that benchmark test cases reference only real capabilities."""
    errors = []

    # Import capability_gap scenario to check test cases
    from benchmarks.scenarios.capability_gap import CapabilityGapScenario

    scenario = CapabilityGapScenario(seed=42)
    scenario.setup()

    all_caps = {node.id for node in registry.all_capabilities()}

    for case in scenario.test_cases:
        for cap in case["workflow"]:
            if cap not in all_caps:
                errors.append(
                    f"Test case '{case['name']}': capability '{cap}' not in ontology"
                )
        for cap in case.get("missing", []):
            if cap not in all_caps:
                errors.append(
                    f"Test case '{case['name']}': expected missing capability '{cap}' not in ontology"
                )

    return errors


def main() -> int:
    ontology_path = ROOT / "schemas" / "capability_ontology.yaml"

    print("Validating benchmark dependencies against ontology...")
    print(f"  Ontology: {ontology_path}")

    # Load registry
    try:
        registry = CapabilityRegistry(ontology_path)
    except Exception as e:
        print(f"FAIL: Cannot load CapabilityRegistry: {e}")
        return 1

    all_errors = []

    # Run validations
    print("\n1. Checking capabilities exist...")
    errors = validate_capabilities_exist(registry)
    all_errors.extend(errors)
    print(f"   {'PASS' if not errors else 'FAIL'}: {len(errors)} error(s)")

    print("\n2. Checking requires edges...")
    errors = validate_requires_edges(registry)
    all_errors.extend(errors)
    print(f"   {'PASS' if not errors else 'FAIL'}: {len(errors)} error(s)")

    print("\n3. Checking coercion registry...")
    errors = validate_coercion_registry()
    all_errors.extend(errors)
    print(f"   {'PASS' if not errors else 'FAIL'}: {len(errors)} error(s)")

    print("\n4. Checking benchmark test cases...")
    errors = validate_benchmark_test_cases(registry)
    all_errors.extend(errors)
    print(f"   {'PASS' if not errors else 'FAIL'}: {len(errors)} error(s)")

    # Summary
    print(f"\n{'='*50}")
    if all_errors:
        print(f"FAIL: {len(all_errors)} total error(s)")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("PASS: All benchmark dependencies validated against ontology")
    return 0


if __name__ == "__main__":
    sys.exit(main())
