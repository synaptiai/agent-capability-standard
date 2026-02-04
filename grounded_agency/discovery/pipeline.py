"""
Discovery Pipeline — orchestrates the full capability discovery flow.

Composes TaskAnalyzer, CapabilityClassifier, GapDetector, and
WorkflowSynthesizer into a single async pipeline.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..capabilities.registry import CapabilityRegistry
from ..state.evidence_store import EvidenceAnchor, EvidenceStore
from ..workflows.engine import WorkflowEngine
from .analyzer import TaskAnalyzer
from .classifier import CapabilityClassifier
from .gap_detector import GapDetector
from .synthesizer import WorkflowSynthesizer
from .types import DiscoveryResult, LLMFunction

logger = logging.getLogger("grounded_agency.discovery.pipeline")


class DiscoveryPipeline:
    """Orchestrate the full capability discovery flow.

    Pipeline stages:
    1. ``analyze`` — extract requirements + initial matches
    2. ``classify`` — validate matches, route gaps
    3. ``detect_gaps`` — enrich gaps with proposals
    4. ``synthesize`` — build workflow from matches
    5. Package into ``DiscoveryResult``

    Usage:
        pipeline = DiscoveryPipeline(registry, engine)
        result = await pipeline.discover("Analyze CSV for anomalies")
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        engine: WorkflowEngine,
        llm_fn: LLMFunction | None = None,
        domain: str | None = None,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        self.registry = registry
        self.engine = engine
        self.domain = domain
        self._evidence_store = evidence_store
        self._llm_fn = llm_fn

        # Initialize sub-components
        self.analyzer = TaskAnalyzer(registry, llm_fn=llm_fn)
        self.classifier = CapabilityClassifier(registry)
        self.gap_detector = GapDetector(registry, llm_fn=llm_fn)
        self.synthesizer = WorkflowSynthesizer(registry, engine, llm_fn=llm_fn)

        # Per-turn cache keyed by prompt hash
        self._cache: dict[str, DiscoveryResult] = {}

    async def discover(
        self,
        task_description: str,
        domain: str | None = None,
    ) -> DiscoveryResult:
        """
        Run the full discovery pipeline.

        Args:
            task_description: Natural language task description.
            domain: Optional domain override (defaults to pipeline domain).

        Returns:
            Complete DiscoveryResult with matches, gaps, and workflow.
        """
        effective_domain = domain or self.domain

        # Check cache
        cache_key = self._cache_key(task_description, effective_domain)
        if cache_key in self._cache:
            logger.debug("Discovery cache hit for: %s", task_description[:50])
            return self._cache[cache_key]

        # Stage 1: Analyze
        requirements, raw_matches = await self.analyzer.analyze(
            task_description, effective_domain
        )

        # Stage 2: Classify
        accepted_matches, gaps = self.classifier.classify(requirements, raw_matches)

        # Stage 3: Gap detection
        enriched_gaps = await self.gap_detector.detect_gaps(gaps)

        # Stage 4: Synthesize workflow
        workflow = None
        existing_match = None
        if accepted_matches:
            workflow = await self.synthesizer.synthesize(
                accepted_matches, task_description, effective_domain
            )
            # Check for existing workflow match
            cap_ids = {m.capability_id for m in accepted_matches}
            existing_match = self.synthesizer.check_existing_workflows(cap_ids)

        # Build evidence anchors
        evidence_anchors = self._collect_evidence(task_description, accepted_matches)

        # Calculate overall confidence
        if accepted_matches:
            match_conf = sum(m.confidence for m in accepted_matches) / len(
                accepted_matches
            )
        else:
            match_conf = 0.0

        gap_penalty = len(enriched_gaps) * 0.1
        confidence = max(0.0, min(1.0, match_conf - gap_penalty))

        result = DiscoveryResult(
            task_description=task_description,
            requirements=requirements,
            matches=accepted_matches,
            gaps=enriched_gaps,
            synthesized_workflow=workflow,
            existing_workflow_match=existing_match,
            evidence_anchors=evidence_anchors,
            confidence=confidence,
        )

        # Cache result
        self._cache[cache_key] = result

        return result

    def invalidate_cache(self) -> None:
        """Clear the per-turn cache (call on new user message)."""
        self._cache.clear()

    def _cache_key(self, task_description: str, domain: str | None) -> str:
        """Generate cache key from task + domain."""
        raw = f"{task_description}|{domain or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _collect_evidence(
        self,
        task_description: str,
        matches: list[Any],
    ) -> list[dict[str, Any]]:
        """Create evidence anchors for the discovery process."""
        raw_anchors: list[EvidenceAnchor] = []

        # Create discovery evidence anchor
        raw_anchors.append(
            EvidenceAnchor.from_tool_output(
                tool_name="DiscoveryPipeline",
                tool_use_id="discovery",
                tool_input={"task_description": task_description},
            )
        )

        # Record each match as evidence
        for match in matches:
            raw_anchors.append(
                EvidenceAnchor.from_tool_output(
                    tool_name="CapabilityClassifier",
                    tool_use_id=f"match_{match.capability_id}",
                    tool_input={
                        "capability_id": match.capability_id,
                        "confidence": match.confidence,
                    },
                )
            )

        # Add original anchors to evidence store (preserves metadata)
        if self._evidence_store is not None:
            for anchor in raw_anchors:
                self._evidence_store.add_anchor(anchor)

        # Return dict representations for the DiscoveryResult
        return [a.to_dict() for a in raw_anchors]
