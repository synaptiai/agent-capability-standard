#!/usr/bin/env python3
"""Ontology version check: a breaking safety change needs a new MAJOR version.

STANDARD §11.6 makes these ontology changes MAJOR: a change to a capability's
`risk`, `mutation`, `requires_checkpoint`, `requires_approval` or
`mutation_overridable`; removing a capability or moving it to another layer;
adding or removing a `requires`, `precedes` or `conflicts_with` edge. This
check compares `schemas/capability_ontology.yaml` with the ontology of the
latest release, and fails when any of those changed while `meta.version`
kept the release's MAJOR number.

The release is the newest tag `vX.Y.Z` (no pre-release suffix) reachable from
HEAD, so the check needs the repository's tags (CI checks out with
`fetch-depth: 0`). It fails when no such tag or file can be read, rather than
passing with nothing to compare.

Usage:
- python3 tools/check_ontology_version.py
- python3 tools/check_ontology_version.py --base-ref v2.0.0
- python3 tools/check_ontology_version.py --base-file old_ontology.yaml
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from yaml_util import ONTOLOGY_MAX_BYTES, safe_yaml_load

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = "schemas/capability_ontology.yaml"

SAFETY_FLAGS = (
    "risk",
    "mutation",
    "requires_checkpoint",
    "requires_approval",
    "mutation_overridable",
)
BOOLEAN_FLAGS = frozenset(SAFETY_FLAGS) - {"risk"}
HARD_EDGE_TYPES = frozenset({"requires", "precedes", "conflicts_with"})
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def latest_release_tag() -> str:
    """The newest `vX.Y.Z` tag reachable from HEAD."""
    tags: dict[tuple[int, ...], str] = {}
    for tag in git("tag", "--list", "v*", "--merged", "HEAD").split():
        match = RELEASE_TAG.match(tag)
        if match:
            tags[tuple(int(n) for n in match.groups())] = tag
    if not tags:
        raise RuntimeError(
            "no release tag vX.Y.Z is reachable from HEAD; fetch the tags "
            "(git fetch --tags, or check out with fetch-depth: 0)"
        )
    return tags[max(tags)]


def load_at_ref(ref: str) -> dict[str, Any]:
    text = git("show", f"{ref}:{ONTOLOGY}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "capability_ontology.yaml"
        path.write_text(text, encoding="utf-8")
        return load(path)


def load(path: Path) -> dict[str, Any]:
    data = safe_yaml_load(path, max_size=ONTOLOGY_MAX_BYTES)
    if not isinstance(data, dict):
        raise RuntimeError(f"{path}: not an ontology mapping")
    return data


def major(ontology: dict[str, Any], label: str) -> int:
    version = str((ontology.get("meta") or {}).get("version", ""))
    match = VERSION.match(version)
    if match is None:
        raise RuntimeError(f"{label}: meta.version {version!r} is not X.Y.Z")
    return int(match.group(1))


def flags(node: dict[str, Any]) -> dict[str, Any]:
    """A node's layer and safety flags; an absent boolean flag is false."""
    values: dict[str, Any] = {"layer": node.get("layer")}
    for flag in SAFETY_FLAGS:
        value = node.get(flag)
        values[flag] = bool(value) if flag in BOOLEAN_FLAGS else value
    return values


def hard_edges(ontology: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (str(edge.get("from")), str(edge.get("type")), str(edge.get("to")))
        for edge in ontology.get("edges") or []
        if edge.get("type") in HARD_EDGE_TYPES
    }


def breaking_changes(base: dict[str, Any], head: dict[str, Any]) -> list[str]:
    """The §11.6 MAJOR changes this check covers, from base to head."""
    changes: list[str] = []
    base_nodes = {node["id"]: flags(node) for node in base.get("nodes") or []}
    head_nodes = {node["id"]: flags(node) for node in head.get("nodes") or []}

    for cap in sorted(base_nodes.keys() - head_nodes.keys()):
        changes.append(f"capability {cap} removed or renamed")
    for cap in sorted(base_nodes.keys() & head_nodes.keys()):
        for key, old in base_nodes[cap].items():
            new = head_nodes[cap][key]
            if old != new:
                changes.append(f"{cap}.{key}: {old!r} -> {new!r}")

    base_edges, head_edges = hard_edges(base), hard_edges(head)
    for source, kind, target in sorted(base_edges - head_edges):
        changes.append(f"edge removed: {source} {kind} {target}")
    for source, kind, target in sorted(head_edges - base_edges):
        changes.append(f"edge added: {source} {kind} {target}")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base-ref", help="Git ref of the released ontology")
    source.add_argument("--base-file", help="Path of the released ontology")
    parser.add_argument(
        "--ontology", default=str(ROOT / ONTOLOGY), help="The ontology to check"
    )
    args = parser.parse_args()

    try:
        if args.base_file:
            label = args.base_file
            base = load(Path(args.base_file))
        else:
            label = args.base_ref or latest_release_tag()
            base = load_at_ref(label)
        head = load(Path(args.ontology))
        base_major = major(base, label)
        head_major = major(head, args.ontology)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"ONTOLOGY VERSION CHECK FAIL: {exc}")
        sys.exit(1)

    changes = breaking_changes(base, head)
    print(
        f"Base {label}: ontology {base['meta']['version']}, "
        f"{len(base.get('nodes') or [])} capabilities, "
        f"{len(hard_edges(base))} requires/precedes/conflicts_with edges"
    )
    print(
        f"Head: ontology {head['meta']['version']}, "
        f"{len(head.get('nodes') or [])} capabilities, "
        f"{len(hard_edges(head))} requires/precedes/conflicts_with edges"
    )
    for change in changes:
        print(f"  - {change}")

    if changes and head_major <= base_major:
        print(
            f"ONTOLOGY VERSION CHECK FAIL: {len(changes)} MAJOR change(s) "
            f"(STANDARD §11.6) since {label}, but meta.version keeps MAJOR "
            f"{base_major}; raise it to {base_major + 1}.0.0"
        )
        sys.exit(1)
    if changes:
        print(
            f"ONTOLOGY VERSION CHECK PASS: {len(changes)} MAJOR change(s), "
            f"with MAJOR {base_major} -> {head_major}"
        )
    else:
        print(f"ONTOLOGY VERSION CHECK PASS: no MAJOR change since {label}")


if __name__ == "__main__":
    main()
