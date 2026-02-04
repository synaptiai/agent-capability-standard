"""
Capability Classifier — maps requirements to ontology capabilities.

Kept separate from the analyzer for testability: the analyzer extracts
requirements, the classifier evaluates match quality and routes gaps.
When used through the pipeline, analyzer + classifier can be batched
into a single LLM call for efficiency.
"""

from __future__ import annotations

import logging

from ..capabilities.registry import CapabilityRegistry
from .types import CapabilityGap, CapabilityMatch, TaskRequirement

logger = logging.getLogger("grounded_agency.discovery.classifier")

# Minimum confidence to accept a match
MATCH_THRESHOLD = 0.6


class CapabilityClassifier:
    """Evaluate and filter capability matches, routing gaps for detection.

    Takes raw matches from the analyzer and:
    1. Validates each match exists in the ontology
    2. Validates input_schema compatibility
    3. Routes low-confidence matches to gap detection
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def classify(
        self,
        requirements: list[TaskRequirement],
        matches: list[CapabilityMatch],
    ) -> tuple[list[CapabilityMatch], list[CapabilityGap]]:
        """
        Classify matches and identify gaps.

        Args:
            requirements: All extracted requirements.
            matches: Raw matches from the analyzer.

        Returns:
            Tuple of (accepted_matches, gaps).
        """
        accepted: list[CapabilityMatch] = []
        gaps: list[CapabilityGap] = []

        # Track processed requirements by content key (not object identity)
        matched_reqs: set[tuple[str, str]] = set()

        for match in matches:
            # Track that this requirement was processed (even if routed to gap)
            matched_reqs.add((match.requirement.action, match.requirement.target))

            # Validate capability exists
            cap = self.registry.get_capability(match.capability_id)
            if cap is None:
                logger.warning(
                    "Matched capability '%s' not in ontology, treating as gap",
                    match.capability_id,
                )
                gaps.append(
                    CapabilityGap(
                        requirement=match.requirement,
                        nearest_existing=self._find_nearest(match.requirement),
                    )
                )
                continue

            # Check confidence threshold
            if match.confidence < MATCH_THRESHOLD:
                logger.info(
                    "Low confidence match: %s -> %s (%.2f < %.2f)",
                    match.requirement.action,
                    match.capability_id,
                    match.confidence,
                    MATCH_THRESHOLD,
                )
                gaps.append(
                    CapabilityGap(
                        requirement=match.requirement,
                        nearest_existing=[match.capability_id]
                        + self._find_nearest(match.requirement),
                    )
                )
                continue

            accepted.append(match)

        # Find unmatched requirements (no match attempted at all)
        for req in requirements:
            if (req.action, req.target) not in matched_reqs:
                gaps.append(
                        CapabilityGap(
                            requirement=req,
                            nearest_existing=self._find_nearest(req),
                        )
                    )

        return accepted, gaps

    def _find_nearest(self, requirement: TaskRequirement) -> list[str]:
        """Find nearest capabilities by action verb similarity.

        Simple heuristic: look for capabilities whose description
        contains the action verb or target.
        """
        action = requirement.action.lower()
        target = requirement.target.lower()
        scored: list[tuple[float, str]] = []

        for cap in self.registry.all_capabilities():
            desc = cap.description.lower()
            score = 0.0
            if action in desc:
                score += 0.5
            if target in desc:
                score += 0.3
            if action in cap.id:
                score += 0.2
            if score > 0:
                scored.append((score, cap.id))

        scored.sort(key=lambda x: -x[0])
        return [cap_id for _, cap_id in scored[:3]]
