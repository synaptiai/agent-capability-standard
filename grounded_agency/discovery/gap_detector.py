"""
Gap Detector — identifies ontology gaps and proposes new capabilities.

When the classifier can't map a requirement to an existing capability
with sufficient confidence, the gap detector finds the nearest existing
capabilities and optionally proposes a new one via LLM.
"""

from __future__ import annotations

import json
import logging

from ..capabilities.registry import CapabilityRegistry
from .prompts import build_gap_proposal_prompt
from .types import CapabilityGap, LLMFunction, ProposedCapability, TaskRequirement

logger = logging.getLogger("grounded_agency.discovery.gap_detector")


class GapDetector:
    """Identify ontology gaps and propose new capabilities.

    For each unmatched requirement:
    1. Find nearest existing capabilities by semantic similarity
    2. If LLM available, generate a ProposedCapability with full schema
    3. Otherwise, return the gap with nearest capabilities only
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        llm_fn: LLMFunction | None = None,
    ) -> None:
        self.registry = registry
        self._llm_fn = llm_fn

    async def detect_gaps(
        self,
        gaps: list[CapabilityGap],
    ) -> list[CapabilityGap]:
        """
        Enrich gaps with proposals where possible.

        Args:
            gaps: Gaps identified by the classifier.

        Returns:
            Enriched gaps with ProposedCapability where LLM is available.
        """
        enriched: list[CapabilityGap] = []
        for gap in gaps:
            if self._llm_fn is not None:
                try:
                    proposal = await self._propose_capability(gap.requirement)
                    enriched.append(
                        CapabilityGap(
                            requirement=gap.requirement,
                            proposed_capability=proposal,
                            nearest_existing=gap.nearest_existing,
                        )
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        "Failed to propose capability for '%s': %s",
                        gap.requirement.action,
                        e,
                    )
            enriched.append(gap)
        return enriched

    async def _propose_capability(
        self,
        requirement: TaskRequirement,
    ) -> ProposedCapability:
        """Generate a full capability proposal via LLM."""
        # Find nearest capabilities for context
        nearest_caps = []
        for cap in self.registry.all_capabilities():
            desc = cap.description.lower()
            action = requirement.action.lower()
            if action in desc or action in cap.id:
                nearest_caps.append(cap)
        nearest_caps = nearest_caps[:5]  # Limit context size

        system_prompt, user_prompt, schema = build_gap_proposal_prompt(
            action=requirement.action,
            target=requirement.target,
            constraints=requirement.constraints,
            nearest_capabilities=nearest_caps,
            registry=self.registry,
        )

        prompt = (
            f"{system_prompt}\n\n{user_prompt}\n\n"
            f"Respond with JSON:\n{json.dumps(schema)}"
        )

        assert self._llm_fn is not None  # guarded by caller
        response = await self._llm_fn(prompt, schema)
        return ProposedCapability.from_dict(response)
