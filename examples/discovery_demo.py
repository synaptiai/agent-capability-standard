#!/usr/bin/env python3
"""
Capability Discovery Demo

Demonstrates the automated capability discovery pipeline:
1. Keyword-based analysis (no LLM required)
2. Capability matching with confidence scores
3. Gap detection for unknown capabilities
4. Workflow synthesis with safety steps

Usage:
    python examples/discovery_demo.py
    python examples/discovery_demo.py "Your custom task description"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add parent to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent))

from grounded_agency import CapabilityRegistry, WorkflowEngine
from grounded_agency.discovery import DiscoveryPipeline
from grounded_agency.state.evidence_store import EvidenceStore

ONTOLOGY_PATH = str(Path(__file__).parent.parent / "schemas" / "capability_ontology.yaml")
CATALOG_PATH = str(Path(__file__).parent.parent / "schemas" / "workflow_catalog.yaml")


async def demo_simple_analysis():
    """Demonstrate basic task analysis and capability matching."""
    print("\n" + "=" * 60)
    print("Demo 1: Simple Task Analysis (Keyword Fallback)")
    print("=" * 60)

    registry = CapabilityRegistry(ONTOLOGY_PATH)
    engine = WorkflowEngine(ontology_path=ONTOLOGY_PATH)
    engine.load_catalog(CATALOG_PATH)

    pipeline = DiscoveryPipeline(registry, engine)
    result = await pipeline.discover("Search for Python files and detect TODO comments")

    print(f"\nTask: {result.task_description}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"\nRequirements found: {len(result.requirements)}")
    for req in result.requirements:
        print(f"  - action={req.action!r}, target={req.target!r}")

    print(f"\nCapability matches: {len(result.matches)}")
    for match in result.matches:
        print(
            f"  - {match.capability_id} (confidence={match.confidence:.2f}): "
            f"{match.reasoning}"
        )

    print(f"\nGaps: {len(result.gaps)}")
    for gap in result.gaps:
        print(f"  - {gap.requirement.action!r} -> nearest: {gap.nearest_existing}")


async def demo_mutation_workflow():
    """Demonstrate workflow synthesis with safety steps for mutations."""
    print("\n" + "=" * 60)
    print("Demo 2: Mutation Workflow with Safety Steps")
    print("=" * 60)

    registry = CapabilityRegistry(ONTOLOGY_PATH)
    engine = WorkflowEngine(ontology_path=ONTOLOGY_PATH)
    engine.load_catalog(CATALOG_PATH)
    store = EvidenceStore()

    pipeline = DiscoveryPipeline(registry, engine, evidence_store=store)
    result = await pipeline.discover(
        "Delete old log files older than 30 days and send a cleanup report"
    )

    print(f"\nTask: {result.task_description}")
    print(f"Confidence: {result.confidence:.2f}")

    if result.synthesized_workflow:
        wf = result.synthesized_workflow
        print(f"\nSynthesized workflow: {wf.name}")
        print(f"Steps ({len(wf.steps)}):")
        for i, step in enumerate(wf.steps, 1):
            cap = step["capability"]
            purpose = step.get("purpose", "")
            risk = step.get("risk", "low")
            mutation = step.get("mutation", False)
            flags = []
            if mutation:
                flags.append("MUTATION")
            if step.get("requires_checkpoint"):
                flags.append("NEEDS_CHECKPOINT")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {i}. {cap} (risk={risk}){flag_str}")
            print(f"     {purpose}")

        if wf.validation_result:
            valid = wf.validation_result.get("valid", False)
            errors = wf.validation_result.get("errors", [])
            print(f"\nValidation: {'PASS' if valid else 'FAIL'}")
            for err in errors:
                print(f"  - {err}")

    print(f"\nEvidence anchors: {len(result.evidence_anchors)}")
    print(f"Evidence store entries: {len(store)}")


async def demo_custom_task(task: str):
    """Analyze a custom task description."""
    print("\n" + "=" * 60)
    print("Demo 3: Custom Task Analysis")
    print("=" * 60)

    registry = CapabilityRegistry(ONTOLOGY_PATH)
    engine = WorkflowEngine(ontology_path=ONTOLOGY_PATH)
    engine.load_catalog(CATALOG_PATH)

    pipeline = DiscoveryPipeline(registry, engine)
    result = await pipeline.discover(task)

    print(f"\nTask: {result.task_description}")
    print(f"Overall confidence: {result.confidence:.2f}")

    print(f"\nMatched capabilities ({len(result.matches)}):")
    for m in result.matches:
        domain_str = f" (domain={m.domain})" if m.domain else ""
        print(f"  - {m.capability_id}{domain_str}: {m.confidence:.2f}")
        print(f"    {m.reasoning}")

    print(f"\nGaps ({len(result.gaps)}):")
    for g in result.gaps:
        print(f"  - {g.requirement.action!r} on {g.requirement.target!r}")
        if g.proposed_capability:
            print(f"    Proposed: {g.proposed_capability.id} (layer={g.proposed_capability.layer})")
        elif g.nearest_existing:
            print(f"    Nearest: {', '.join(g.nearest_existing[:3])}")

    if result.synthesized_workflow:
        wf = result.synthesized_workflow
        print(f"\nWorkflow: {wf.name} ({len(wf.steps)} steps, confidence={wf.confidence:.2f})")
        for step in wf.steps:
            print(f"  -> {step['capability']}: {step.get('purpose', '')[:60]}")

    if result.existing_workflow_match:
        print(f"\nExisting workflow match: {result.existing_workflow_match}")


async def main():
    """Run all demos."""
    await demo_simple_analysis()
    await demo_mutation_workflow()

    # Check for custom task from command line
    if len(sys.argv) > 1:
        custom_task = " ".join(sys.argv[1:])
        await demo_custom_task(custom_task)
    else:
        await demo_custom_task("Analyze this CSV for anomalies and send a report")

    print("\n" + "=" * 60)
    print("All demos complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
