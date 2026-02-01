#!/usr/bin/env python3
"""Transform reference validator: checks that mapping_ref paths resolve to existing files.

Validates:
1) All mapping_ref entries in transform_coercion_registry.yaml
2) All mapping_ref entries in workflow_catalog.yaml step definitions

Usage:
    python3 tools/validate_transform_refs.py
    python3 tools/validate_transform_refs.py --verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yaml_util import safe_yaml_load

ROOT = Path(__file__).resolve().parents[1]

REGISTRY_PATH = ROOT / "schemas" / "transforms" / "transform_coercion_registry.yaml"
WORKFLOW_PATH = ROOT / "schemas" / "workflow_catalog.yaml"


def validate_registry(errors: list[str], verbose: bool) -> int:
    """Validate mapping_ref paths in the coercion registry.

    Returns number of refs checked.
    """
    if not REGISTRY_PATH.exists():
        errors.append(f"Registry file not found: {REGISTRY_PATH}")
        return 0

    data = safe_yaml_load(REGISTRY_PATH)
    coercions = data.get("coercions", [])
    count = 0

    for entry in coercions:
        ref = entry.get("mapping_ref")
        if ref is None:
            continue
        count += 1
        resolved = ROOT / ref
        if resolved.exists():
            if verbose:
                print(f"  OK (registry): {ref}")
        else:
            errors.append(
                f"[registry] mapping_ref does not resolve: {ref} "
                f"(expected at {resolved})"
            )

    return count


def validate_workflows(errors: list[str], verbose: bool) -> int:
    """Validate mapping_ref paths in workflow catalog steps.

    Returns number of refs checked.
    """
    if not WORKFLOW_PATH.exists():
        if verbose:
            print(f"  SKIP: Workflow catalog not found: {WORKFLOW_PATH}")
        return 0

    data = safe_yaml_load(WORKFLOW_PATH)
    workflows = data.get("workflows", [])
    count = 0

    for wf in workflows:
        wf_name = wf.get("name", "<unnamed>")
        steps = wf.get("steps", [])
        for step in steps:
            ref = step.get("mapping_ref")
            if ref is None:
                continue
            count += 1
            resolved = ROOT / ref
            if resolved.exists():
                if verbose:
                    print(f"  OK (workflow/{wf_name}): {ref}")
            else:
                errors.append(
                    f"[workflow/{wf_name}] mapping_ref does not resolve: {ref} "
                    f"(expected at {resolved})"
                )

    return count


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Validate mapping_ref paths in transform and workflow files"
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true", help="Show all checked references"
    )
    args = ap.parse_args()

    errors: list[str] = []

    reg_count = validate_registry(errors, args.verbose)
    wf_count = validate_workflows(errors, args.verbose)
    total = reg_count + wf_count

    if errors:
        print("TRANSFORM REFERENCE VALIDATION FAIL:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nChecked {total} refs with {len(errors)} errors")
        sys.exit(1)

    print(f"TRANSFORM REFERENCE VALIDATION PASS: {total} refs validated")


if __name__ == "__main__":
    main()
