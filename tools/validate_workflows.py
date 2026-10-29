#!/usr/bin/env python3
"""Workflow validator CLI.

A thin command-line front end to the reference validator in the Rust core
(``core/src/validate``, exposed as ``grounded_agency._core``). All checks —
capability existence and prerequisites, ``$ref`` resolution, binding type
inference, consumer contract checking and patch suggestions (STANDARD §5,
§10 levels L1–L4) — run in the core; this script only formats the report and
renders the optional patch.

Outputs:
- prints errors and warnings, then ``VALIDATION PASS`` or ``VALIDATION FAIL``;
- always writes ``tools/validator_suggestions.json`` (or the
  ``--suggestions-out`` path) with the structured diagnostics (§9.7 shape
  plus ``severity``) and machine-usable fixes;
- with ``--emit-patch``, writes ``tools/validator_patch.diff``, a unified diff
  applying the suggested transform insertions.

Exit status is 1 when there are errors (or, with ``--strict``, warnings).

Usage:
- ``python3 tools/validate_workflows.py``
- ``python3 tools/validate_workflows.py --catalog path/to/catalog.yaml``
- ``python3 tools/validate_workflows.py --strict``
- ``python3 tools/validate_workflows.py --emit-patch``
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from yaml_util import ONTOLOGY_MAX_BYTES, safe_yaml_load

# Direct import works when the package is installed; fall back to the source
# tree for a bare `python tools/validate_workflows.py` from a checkout whose
# extension was built in place.
try:
    from grounded_agency import _core
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]
ONTO = ROOT / "schemas" / "capability_ontology.yaml"
WF = ROOT / "schemas" / "workflow_catalog.yaml"
SUGGESTIONS_JSON = ROOT / "tools" / "validator_suggestions.json"
PATCH_DIFF = ROOT / "tools" / "validator_patch.diff"


def describe(d: dict[str, Any]) -> str:
    """One line for a diagnostic: where, code, message, and any hint."""
    loc = d.get("location", {})
    where = []
    if "workflow" in loc:
        where.append(f"[{loc['workflow']}]")
    if "step" in loc:
        cap = f" ({loc['capability']})" if "capability" in loc else ""
        where.append(f"step {loc['step']}{cap}")
    prefix = " ".join(where)
    hint = f" — {d['suggestion']}" if d.get("suggestion") else ""
    return f"{prefix + ': ' if prefix else ''}{d['code']} {d['message']}{hint}"


def apply_patch_suggestions_to_yaml(
    workflows: dict[str, Any], suggestions: list[dict[str, Any]]
) -> str:
    """Return the catalog as YAML with the transform-insertion patches applied.

    Several patches can target the same consumer step (one per mismatched
    input). All of a step's transforms are inserted before it together, and
    then all of its binding updates are applied to the step itself.
    """
    wf_copy = json.loads(json.dumps(workflows))
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for s in suggestions:
        if s.get("kind") == "consumer_input_type_mismatch" and s.get("patch"):
            p = s["patch"]
            grouped.setdefault(s["workflow"], {}).setdefault(
                p["insert_at_step_index"], []
            ).append(p)

    for wf_name, by_step in grouped.items():
        if wf_name not in wf_copy:
            continue
        steps = wf_copy[wf_name].get("steps", [])
        # Highest index first, so inserting never shifts a step still to patch.
        for index in sorted(by_step, reverse=True):
            patches = by_step[index]
            if not 0 <= index < len(steps):
                continue
            consumer = steps[index]
            consumer.setdefault("input_bindings", {})
            for p in patches:
                consumer["input_bindings"].update(
                    p["update_step"]["input_bindings_update"]
                )
            steps[index:index] = [p["new_step"] for p in patches]
        wf_copy[wf_name]["steps"] = steps

    return yaml.safe_dump(wf_copy, sort_keys=False, allow_unicode=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--emit-patch",
        action="store_true",
        help="Write a unified diff patch for suggested transform insertions.",
    )
    ap.add_argument("--catalog", default=None, help="Override workflow catalog path.")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors.")
    ap.add_argument(
        "--suggestions-out",
        default=None,
        help="Where to write the suggestions JSON (default tools/validator_suggestions.json).",
    )
    args = ap.parse_args()
    suggestions_json = (
        Path(args.suggestions_out) if args.suggestions_out else SUGGESTIONS_JSON
    )

    wf_path = Path(args.catalog) if args.catalog else WF
    try:
        report = _core.validate_catalog(str(wf_path), str(ONTO), str(ROOT))
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    diagnostics = report["diagnostics"]
    errors = [d for d in diagnostics if d["severity"] == "error"]
    warnings = [d for d in diagnostics if d["severity"] == "warning"]
    suggestions = report["suggestions"]

    output = {
        "errors": [describe(d) for d in errors],
        "warnings": [describe(d) for d in warnings],
        "structured_errors": errors,
        "structured_warnings": warnings,
        "suggestions": suggestions,
    }
    suggestions_json.write_text(json.dumps(output, indent=2), encoding="utf-8")

    if args.emit_patch and suggestions:
        workflows = safe_yaml_load(wf_path, max_size=ONTOLOGY_MAX_BYTES) or {}
        modified = apply_patch_suggestions_to_yaml(workflows, suggestions)
        original = wf_path.read_text(encoding="utf-8")
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="workflow_catalog.yaml",
            tofile="workflow_catalog.yaml (suggested)",
        )
        PATCH_DIFF.write_text("".join(diff), encoding="utf-8")

    if warnings:
        print("WARNINGS:")
        for w in output["warnings"]:
            print(" -", w)

    failed = bool(errors) or (args.strict and bool(warnings))
    if failed:
        print("VALIDATION FAIL:")
        for err in output["errors"]:
            print(" -", err)
        if args.strict and warnings:
            print(f" ({len(warnings)} warning(s) count as errors under --strict)")
        print(f"\nSuggestions written to: {suggestions_json}")
        if args.emit_patch:
            print(f"Patch diff written to: {PATCH_DIFF}")
        sys.exit(1)

    print("VALIDATION PASS")
    print(f"Suggestions written to: {suggestions_json}")


if __name__ == "__main__":
    main()
