#!/usr/bin/env python3
"""Validate that safe_yaml.py and yaml_util.py remain in sync.

Both files expose the same public API (safe_yaml_load, YAMLSizeExceededError,
DEFAULT_MAX_BYTES, ONTOLOGY_MAX_BYTES) and must have identical functional code.
Module-level and function-level docstrings are allowed to differ (each file
documents its own role), but class bodies, function bodies, and constant
values must match exactly.

This validator catches drift between the canonical source and its standalone
mirror for tools/ scripts.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "grounded_agency" / "utils" / "safe_yaml.py"
MIRROR = ROOT / "tools" / "yaml_util.py"

# Public symbols that must match between the two files.
# MAINTENANCE: Update this set when adding or removing public symbols from
# safe_yaml.py.  If a new symbol is added to the canonical file but not here,
# the sync validator will silently ignore it, allowing drift.
SYNCED_NAMES = {
    "safe_yaml_load",
    "YAMLSizeExceededError",
    "DEFAULT_MAX_BYTES",
    "ONTOLOGY_MAX_BYTES",
}


def _strip_docstring(source: str) -> str:
    """Remove the leading docstring from a function/class source block."""
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                # Remove the docstring node
                node.body.pop(0)
            return ast.unparse(node)
    return source


def _extract_definitions(source: str) -> dict[str, str]:
    """Extract normalized source text for top-level definitions by name.

    For functions and classes, strips the docstring before comparison so
    that documentation differences (expected) don't trigger false alarms.
    For constants, extracts the assignment value expression.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    defs: dict[str, str] = {}

    for node in ast.iter_child_nodes(tree):
        name: str | None = None

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id

        if name and name in SYNCED_NAMES:
            assert hasattr(node, "lineno") and hasattr(node, "end_lineno")
            start = node.lineno - 1
            end = node.end_lineno if node.end_lineno else start + 1
            raw = "".join(lines[start:end])

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Normalize: strip docstring, unparse to canonical form
                defs[name] = _strip_docstring(raw)
            else:
                # Constants: compare the unparsed AST (ignores whitespace)
                defs[name] = ast.unparse(node)

    return defs


def main() -> int:
    errors: list[str] = []

    if not CANONICAL.exists():
        errors.append(f"Canonical file missing: {CANONICAL.relative_to(ROOT)}")
    if not MIRROR.exists():
        errors.append(f"Mirror file missing: {MIRROR.relative_to(ROOT)}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    canonical_src = CANONICAL.read_text(encoding="utf-8")
    mirror_src = MIRROR.read_text(encoding="utf-8")

    canonical_defs = _extract_definitions(canonical_src)
    mirror_defs = _extract_definitions(mirror_src)

    for name in sorted(SYNCED_NAMES):
        if name not in canonical_defs:
            errors.append(f"{name!r} missing from canonical ({CANONICAL.relative_to(ROOT)})")
        if name not in mirror_defs:
            errors.append(f"{name!r} missing from mirror ({MIRROR.relative_to(ROOT)})")
        if name in canonical_defs and name in mirror_defs:
            if canonical_defs[name] != mirror_defs[name]:
                errors.append(
                    f"{name!r} differs between files — update mirror to match canonical"
                )

    if errors:
        print("YAML util sync FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"YAML util sync OK — {len(SYNCED_NAMES)} definitions match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
