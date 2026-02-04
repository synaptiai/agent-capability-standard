"""
Workflow Synthesizer — builds valid workflow DAGs from capability matches.

Two-phase approach:
1. Graph construction (deterministic): topological sort, dependency
   resolution, checkpoint injection, conflict detection.
2. LLM binding generation: data flow bindings between steps.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict, deque
from typing import Any

from ..capabilities.registry import CapabilityNode, CapabilityRegistry
from ..workflows.engine import WorkflowEngine
from .prompts import build_binding_prompt
from .types import CapabilityMatch, LLMFunction, SynthesizedWorkflow

logger = logging.getLogger("grounded_agency.discovery.synthesizer")

# Layer ordering for tiebreaking in topological sort
_LAYER_ORDER: dict[str, int] = {
    "PERCEIVE": 0,
    "UNDERSTAND": 1,
    "REASON": 2,
    "MODEL": 3,
    "SYNTHESIZE": 4,
    "EXECUTE": 5,
    "VERIFY": 6,
    "REMEMBER": 7,
    "COORDINATE": 8,
}


class WorkflowSynthesizer:
    """Build valid workflow DAGs from capability matches.

    Phase 1 (deterministic):
    - Resolve transitive ``requires`` dependencies
    - Insert ``checkpoint`` before mutation capabilities
    - Topological sort respecting ``precedes`` edges
    - Verify no ``conflicts_with`` violations
    - Layer-based ordering as tiebreaker

    Phase 2 (LLM-assisted):
    - Generate input bindings using ``${ref}`` syntax
    - Generate gate conditions and store_as names
    - Validate bindings via WorkflowEngine
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        engine: WorkflowEngine,
        llm_fn: LLMFunction | None = None,
    ) -> None:
        self.registry = registry
        self.engine = engine
        self._llm_fn = llm_fn

    async def synthesize(
        self,
        matches: list[CapabilityMatch],
        task_description: str,
        domain: str | None = None,
    ) -> SynthesizedWorkflow:
        """
        Synthesize a complete workflow from capability matches.

        Args:
            matches: Accepted capability matches from classifier.
            task_description: Original task for binding context.
            domain: Optional domain parameter.

        Returns:
            SynthesizedWorkflow with steps, bindings, and validation.
        """
        if not matches:
            return SynthesizedWorkflow(
                name="empty_workflow",
                description="No capabilities matched",
                steps=[],
                confidence=0.0,
            )

        # Collect capability IDs (dedup, preserving order of first occurrence)
        capability_ids: list[str] = []
        seen: set[str] = set()
        for m in matches:
            if m.capability_id not in seen:
                capability_ids.append(m.capability_id)
                seen.add(m.capability_id)

        # Phase 1: Deterministic graph construction
        all_ids = self._resolve_dependencies(set(capability_ids))
        all_ids = self._inject_safety_steps(all_ids)

        # Check for conflicts
        conflicts = self._check_conflicts(all_ids)
        if conflicts:
            logger.warning("Workflow has capability conflicts: %s", conflicts)

        # Topological sort
        ordered = self._topological_sort(all_ids)

        # Build step dicts
        match_by_cap = {m.capability_id: m for m in matches}
        steps = self._build_steps(ordered, match_by_cap, domain)

        # Phase 2: Generate bindings (LLM or deterministic fallback)
        if self._llm_fn is not None:
            try:
                steps = await self._generate_bindings_llm(
                    steps, task_description, ordered
                )
            except Exception as e:
                logger.warning("LLM binding generation failed: %s", e)
                steps = self._generate_bindings_deterministic(steps)
        else:
            steps = self._generate_bindings_deterministic(steps)

        # Generate workflow name from task
        name = self._generate_name(task_description)

        # Calculate confidence from matches
        if matches:
            confidence = sum(m.confidence for m in matches) / len(matches)
        else:
            confidence = 0.0

        workflow = SynthesizedWorkflow(
            name=name,
            description=task_description,
            steps=steps,
            bindings={s.get("store_as", ""): s.get("purpose", "") for s in steps},
            confidence=confidence,
        )

        # Validate via engine if possible
        workflow.validation_result = self._validate_workflow(workflow)

        return workflow

    def _resolve_dependencies(self, capability_ids: set[str]) -> set[str]:
        """Resolve transitive ``requires`` dependencies, adding missing capabilities."""
        resolved: set[str] = set(capability_ids)
        queue = deque(capability_ids)

        while queue:
            cap_id = queue.popleft()
            required = self.registry.get_required_capabilities(cap_id)
            for req_id in required:
                if req_id not in resolved:
                    resolved.add(req_id)
                    queue.append(req_id)

        return resolved

    def _inject_safety_steps(self, capability_ids: set[str]) -> set[str]:
        """Insert ``checkpoint`` before mutation capabilities and ``audit`` at end."""
        result = set(capability_ids)
        has_mutation = False

        for cap_id in list(capability_ids):
            cap = self.registry.get_capability(cap_id)
            if cap and cap.requires_checkpoint:
                result.add("checkpoint")
                has_mutation = True

        # Add audit if any mutations present
        if has_mutation:
            result.add("audit")

        return result

    def _check_conflicts(self, capability_ids: set[str]) -> list[tuple[str, str]]:
        """Check for ``conflicts_with`` violations."""
        conflicts: list[tuple[str, str]] = []
        id_list = list(capability_ids)

        for i, cap_id in enumerate(id_list):
            conflicting = set(self.registry.get_conflicting_capabilities(cap_id))
            for other_id in id_list[i + 1 :]:
                if other_id in conflicting:
                    conflicts.append((cap_id, other_id))

        return conflicts

    def _topological_sort(self, capability_ids: set[str]) -> list[str]:
        """Kahn's algorithm respecting ``precedes`` and ``requires`` edges.

        Uses layer ordering as a tiebreaker when multiple capabilities
        have no remaining dependencies.
        """
        # Build adjacency: cap_id → set of capabilities that must come after
        graph: dict[str, set[str]] = defaultdict(set)
        in_degree: dict[str, int] = {cap_id: 0 for cap_id in capability_ids}
        seen_edges: set[tuple[str, str]] = set()

        for cap_id in capability_ids:
            # precedes edges: cap_id must come before targets
            for edge in self.registry.get_outgoing_edges(cap_id):
                if edge.edge_type == "precedes" and edge.to_cap in capability_ids:
                    pair = (cap_id, edge.to_cap)
                    if pair not in seen_edges:
                        seen_edges.add(pair)
                        graph[cap_id].add(edge.to_cap)
                        in_degree[edge.to_cap] += 1

            # requires edges: dependencies must come before this cap
            for edge in self.registry.get_incoming_edges(cap_id):
                if edge.edge_type == "requires" and edge.from_cap in capability_ids:
                    pair = (edge.from_cap, cap_id)
                    if pair not in seen_edges:
                        seen_edges.add(pair)
                        graph[edge.from_cap].add(cap_id)
                        in_degree[cap_id] += 1

        # Kahn's algorithm with layer-based tiebreaking
        queue: list[str] = sorted(
            [cap_id for cap_id, deg in in_degree.items() if deg == 0],
            key=lambda c: self._layer_order(c),
        )
        result: list[str] = []

        while queue:
            # Sort by layer order for deterministic tiebreaking
            queue.sort(key=lambda c: self._layer_order(c))
            cap_id = queue.pop(0)
            result.append(cap_id)

            for neighbor in graph.get(cap_id, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If cycle detected, append remaining in layer order
        remaining = capability_ids - set(result)
        if remaining:
            logger.warning("Cycle detected in capability graph: %s", remaining)
            result.extend(sorted(remaining, key=lambda c: self._layer_order(c)))

        # Ensure checkpoint comes before any mutation capability
        result = self._ensure_checkpoint_ordering(result)

        return result

    def _ensure_checkpoint_ordering(self, ordered: list[str]) -> list[str]:
        """Ensure checkpoint appears before any mutation capability."""
        if "checkpoint" not in ordered:
            return ordered

        # Find first mutation index
        first_mutation_idx = len(ordered)
        for i, cap_id in enumerate(ordered):
            cap = self.registry.get_capability(cap_id)
            if cap and cap.requires_checkpoint and cap_id != "checkpoint":
                first_mutation_idx = i
                break

        # Find checkpoint index
        cp_idx = ordered.index("checkpoint")

        # Move checkpoint before first mutation if needed
        if cp_idx > first_mutation_idx:
            ordered.remove("checkpoint")
            ordered.insert(first_mutation_idx, "checkpoint")

        return ordered

    def _layer_order(self, cap_id: str) -> int:
        """Get sort key for a capability based on its layer."""
        cap = self.registry.get_capability(cap_id)
        if cap is None:
            return 999
        return _LAYER_ORDER.get(cap.layer, 999)

    def _build_steps(
        self,
        ordered: list[str],
        match_by_cap: dict[str, CapabilityMatch],
        domain: str | None,
    ) -> list[dict[str, Any]]:
        """Build workflow step dicts from ordered capability IDs."""
        steps: list[dict[str, Any]] = []

        for cap_id in ordered:
            cap = self.registry.get_capability(cap_id)
            if cap is None:
                continue

            match = match_by_cap.get(cap_id)
            step: dict[str, Any] = {
                "capability": cap_id,
                "purpose": match.reasoning if match else f"Auto-added: {cap.description}",
                "risk": cap.risk,
                "mutation": cap.mutation,
                "requires_checkpoint": cap.requires_checkpoint,
                "requires_approval": cap.requires_approval,
                "store_as": f"{cap_id}_out",
            }

            # Apply domain from match or parameter
            step_domain = None
            if match and match.domain:
                step_domain = match.domain
            elif domain:
                step_domain = domain
            if step_domain:
                step["domain"] = step_domain

            steps.append(step)

        return steps

    async def _generate_bindings_llm(
        self,
        steps: list[dict[str, Any]],
        task_description: str,
        ordered: list[str],
    ) -> list[dict[str, Any]]:
        """Use LLM to generate data flow bindings between steps."""
        # Get capability schemas for context
        cap_schemas: list[CapabilityNode] = []
        for cap_id in ordered:
            cap = self.registry.get_capability(cap_id)
            if cap:
                cap_schemas.append(cap)

        system_prompt, user_prompt, schema = build_binding_prompt(
            steps, task_description, cap_schemas
        )

        prompt = (
            f"{system_prompt}\n\n{user_prompt}\n\n"
            f"Respond with JSON:\n{json.dumps(schema)}"
        )

        assert self._llm_fn is not None  # guarded by caller
        response = await self._llm_fn(prompt, schema)

        # Merge LLM bindings back into steps
        llm_steps = response.get("steps", [])
        for i, llm_step in enumerate(llm_steps):
            if i < len(steps):
                if "input_bindings" in llm_step:
                    steps[i]["input_bindings"] = llm_step["input_bindings"]
                if "store_as" in llm_step:
                    steps[i]["store_as"] = llm_step["store_as"]
                if "purpose" in llm_step and not steps[i].get("purpose"):
                    steps[i]["purpose"] = llm_step["purpose"]
                if "gates" in llm_step:
                    steps[i]["gates"] = llm_step["gates"]

        return steps

    def _generate_bindings_deterministic(
        self,
        steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate simple sequential bindings without LLM.

        Each step receives the previous step's output as input.
        """
        for i, step in enumerate(steps):
            if i == 0:
                continue
            prev_store = steps[i - 1].get("store_as", "")
            if prev_store:
                step.setdefault("input_bindings", {})
                step["input_bindings"]["input"] = f"${{{prev_store}}}"
        return steps

    def _check_existing_workflows(
        self, capability_ids: set[str]
    ) -> str | None:
        """Check if an existing catalog workflow covers 80%+ of needed capabilities."""
        for wf_name in self.engine.list_workflows():
            wf = self.engine.get_workflow(wf_name)
            if wf is None:
                continue
            wf_caps = {step.capability for step in wf.steps}
            if not capability_ids:
                continue
            overlap = len(capability_ids & wf_caps) / len(capability_ids)
            if overlap >= 0.8:
                return wf_name
        return None

    def _validate_workflow(
        self, workflow: SynthesizedWorkflow
    ) -> dict[str, Any]:
        """Validate synthesized workflow structure."""
        errors: list[str] = []

        # Validate capability IDs exist
        for step in workflow.steps:
            cap_id = step.get("capability", "")
            if self.registry.get_capability(cap_id) is None:
                errors.append(f"Unknown capability: {cap_id}")

        # Validate binding references
        defined_vars: set[str] = set()
        binding_ref_pattern = re.compile(r"\$\{(\w+)")
        for step in workflow.steps:
            step_cap = step.get("capability", "")
            store_as = step.get("store_as", "")
            bindings = step.get("input_bindings", {})
            for value in bindings.values():
                if isinstance(value, str):
                    for ref_match in binding_ref_pattern.finditer(value):
                        ref_name = ref_match.group(1)
                        if ref_name not in defined_vars:
                            errors.append(
                                f"Step '{step_cap}' references undefined "
                                f"variable '${{{ref_name}}}'"
                            )
            if store_as:
                defined_vars.add(store_as)

        return {"valid": len(errors) == 0, "errors": errors}

    def _generate_name(self, task_description: str) -> str:
        """Generate a workflow name from the task description."""
        # Take first few words, lowercase, replace spaces with underscores
        words = task_description.lower().split()[:5]
        clean = "_".join(
            re.sub(r"[^a-z0-9]", "", w) for w in words if re.sub(r"[^a-z0-9]", "", w)
        )
        return clean or "synthesized_workflow"
