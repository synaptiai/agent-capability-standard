#!/usr/bin/env python3
"""Ontology graph validator: detects orphan capabilities and validates edge semantics.

Usage:
    python tools/validate_ontology.py [--verbose] [--check-duplicates]

This script validates the capability ontology by:
1. Detecting orphan capabilities (no incoming or outgoing edges)
2. Validating symmetric edge types have bidirectional edges
3. Detecting cycles in hard dependency edges (requires, precedes)
4. Validating all edge references point to valid capabilities
5. Optionally checking for multiple edge types between capability pairs
"""

import argparse
from pathlib import Path
from collections import defaultdict
from typing import Any

import yaml


def load_ontology(path: Path) -> dict[str, Any]:
    """Load the capability ontology from YAML."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_all_capability_ids(ontology: dict) -> set[str]:
    """Extract all capability IDs from nodes."""
    return {node["id"] for node in ontology.get("nodes", [])}


def build_edge_graph(edges: list[dict]) -> tuple[dict[str, set], dict[str, set]]:
    """Build adjacency lists for outgoing and incoming edges."""
    outgoing = defaultdict(set)
    incoming = defaultdict(set)

    for edge in edges:
        from_cap = edge["from"]
        to_cap = edge["to"]
        outgoing[from_cap].add(to_cap)
        incoming[to_cap].add(from_cap)

    return dict(outgoing), dict(incoming)


def find_orphans(capability_ids: set[str], outgoing: dict, incoming: dict) -> list[str]:
    """Find capabilities with no edges at all."""
    orphans = []
    for cap_id in capability_ids:
        has_outgoing = cap_id in outgoing
        has_incoming = cap_id in incoming
        if not has_outgoing and not has_incoming:
            orphans.append(cap_id)
    return sorted(orphans)


def validate_edge_references(edges: list[dict], capability_ids: set[str]) -> list[str]:
    """Validate all edge references point to valid capabilities."""
    errors = []
    for edge in edges:
        from_cap = edge["from"]
        to_cap = edge["to"]
        if from_cap not in capability_ids:
            errors.append(f"Edge references unknown capability: {from_cap}")
        if to_cap not in capability_ids:
            errors.append(f"Edge references unknown capability: {to_cap}")
    return errors


def validate_symmetric_edges(edges: list[dict], symmetric_types: list[str]) -> list[str]:
    """Check that symmetric edge types have bidirectional edges."""
    warnings = []

    # Group edges by type
    edges_by_type = defaultdict(set)
    for edge in edges:
        edge_type = edge["type"]
        edges_by_type[edge_type].add((edge["from"], edge["to"]))

    # Check symmetric types
    for edge_type in symmetric_types:
        type_edges = edges_by_type.get(edge_type, set())
        for from_cap, to_cap in type_edges:
            reverse = (to_cap, from_cap)
            if reverse not in type_edges and from_cap != to_cap:
                warnings.append(
                    f"Asymmetric '{edge_type}' edge: {from_cap} -> {to_cap} "
                    f"(missing reverse: {to_cap} -> {from_cap})"
                )

    return warnings


def check_duplicate_edges(edges: list[dict]) -> list[str]:
    """Warn about multiple edges between the same capability pair."""
    warnings = []
    edge_pairs = defaultdict(list)
    for edge in edges:
        key = (edge["from"], edge["to"])
        edge_pairs[key].append(edge["type"])

    for (from_cap, to_cap), types in sorted(edge_pairs.items()):
        if len(types) > 1:
            warnings.append(f"Multiple edge types {from_cap} -> {to_cap}: {types}")
    return warnings


def detect_cycles(edges: list[dict], cycle_types: list[str]) -> list[list[str]]:
    """Detect cycles in edges of specified types using DFS."""
    cycles = []

    # Build graph for cycle-relevant edges only
    graph = defaultdict(set)
    for edge in edges:
        if edge["type"] in cycle_types:
            graph[edge["from"]].add(edge["to"])

    # DFS for cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(int)
    path = []

    def dfs(node: str) -> bool:
        color[node] = GRAY
        path.append(node)

        for neighbor in graph.get(node, []):
            if color[neighbor] == GRAY:
                # Found cycle - extract it
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
                return True
            elif color[neighbor] == WHITE:
                if dfs(neighbor):
                    return False  # Continue searching for more cycles

        path.pop()
        color[node] = BLACK
        return False

    # Check all nodes
    all_nodes = set(graph.keys()) | {n for neighbors in graph.values() for n in neighbors}
    for node in all_nodes:
        if color[node] == WHITE:
            dfs(node)

    return cycles


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate capability ontology graph")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--check-duplicates",
        action="store_true",
        help="Warn about multiple edge types between the same capability pair"
    )
    parser.add_argument(
        "--ontology",
        default="schemas/capability_ontology.yaml",
        help="Path to ontology file"
    )
    args = parser.parse_args()

    ontology_path = Path(args.ontology)
    if not ontology_path.exists():
        print(f"Error: Ontology file not found: {ontology_path}")
        return 1

    print(f"Validating ontology: {ontology_path}")
    print("=" * 60)

    ontology = load_ontology(ontology_path)
    capability_ids = get_all_capability_ids(ontology)
    edges = ontology.get("edges", [])

    print(f"Total capabilities: {len(capability_ids)}")
    print(f"Total edges: {len(edges)}")
    print()

    errors = []
    warnings = []

    # 1. Validate edge references
    ref_errors = validate_edge_references(edges, capability_ids)
    errors.extend(ref_errors)

    # 2. Find orphan capabilities
    outgoing, incoming = build_edge_graph(edges)
    orphans = find_orphans(capability_ids, outgoing, incoming)

    if orphans:
        errors.append(f"Found {len(orphans)} orphan capabilities (no edges): {orphans}")

    # 3. Validate symmetric edges
    symmetric_types = ["conflicts_with", "alternative_to"]
    sym_warnings = validate_symmetric_edges(edges, symmetric_types)
    warnings.extend(sym_warnings)

    # 4. Detect cycles in hard dependencies
    cycle_types = ["requires", "precedes"]
    cycles = detect_cycles(edges, cycle_types)
    for cycle in cycles:
        errors.append(f"Cycle detected in {cycle_types} edges: {' -> '.join(cycle)}")

    # 5. Check for duplicate edges (optional)
    if args.check_duplicates:
        dup_warnings = check_duplicate_edges(edges)
        warnings.extend(dup_warnings)

    # Report results
    if args.verbose:
        print("Edge distribution:")
        print("-" * 40)
        for cap_id in sorted(capability_ids):
            out_count = len(outgoing.get(cap_id, []))
            in_count = len(incoming.get(cap_id, []))
            status = "ORPHAN" if out_count == 0 and in_count == 0 else "OK"
            print(f"  {cap_id}: {in_count} incoming, {out_count} outgoing [{status}]")
        print()

    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    if errors:
        print(f"Errors ({len(errors)}):")
        for error in errors:
            print(f"  - {error}")
        print()
        print("VALIDATION FAILED")
        return 1

    # Success summary
    caps_with_outgoing = len([c for c in capability_ids if c in outgoing])
    caps_with_incoming = len([c for c in capability_ids if c in incoming])

    print("Graph statistics:")
    print(f"  - Capabilities with outgoing edges: {caps_with_outgoing}/{len(capability_ids)}")
    print(f"  - Capabilities with incoming edges: {caps_with_incoming}/{len(capability_ids)}")
    print(f"  - Orphan capabilities: {len(orphans)}")
    print()
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    exit(main())
