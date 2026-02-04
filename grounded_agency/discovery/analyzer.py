"""
Task Analyzer — LLM-based structured extraction.

Decomposes natural language task descriptions into atomic capability
requirements, then maps each to the closest ontology capability.
"""

from __future__ import annotations

import json
import logging

from ..capabilities.registry import CapabilityRegistry
from .prompts import build_analysis_prompt
from .types import CapabilityMatch, LLMFunction, TaskRequirement

logger = logging.getLogger("grounded_agency.discovery.analyzer")

# Verb → capability heuristic table for keyword fallback
_VERB_HEURISTICS: dict[str, str] = {
    # PERCEIVE
    "get": "retrieve",
    "fetch": "retrieve",
    "load": "retrieve",
    "read": "retrieve",
    "find": "search",
    "search": "search",
    "look": "search",
    "query": "search",
    "watch": "observe",
    "monitor": "observe",
    "observe": "observe",
    "listen": "receive",
    "receive": "receive",
    "accept": "receive",
    # UNDERSTAND
    "detect": "detect",
    "identify": "detect",
    "spot": "detect",
    "classify": "classify",
    "categorize": "classify",
    "label": "classify",
    "measure": "measure",
    "estimate": "measure",
    "calculate": "measure",
    "count": "measure",
    "predict": "predict",
    "forecast": "predict",
    "compare": "compare",
    "diff": "compare",
    "discover": "discover",
    "explore": "discover",
    # REASON
    "plan": "plan",
    "design": "plan",
    "strategy": "plan",
    "decompose": "decompose",
    "break": "decompose",
    "split": "decompose",
    "critique": "critique",
    "review": "critique",
    "evaluate": "critique",
    "explain": "explain",
    "describe": "explain",
    "summarize": "explain",
    # MODEL
    "model": "state",
    "snapshot": "state",
    "capture": "state",
    "transition": "transition",
    "update": "transition",
    "attribute": "attribute",
    "ground": "ground",
    "verify": "ground",
    "simulate": "simulate",
    "emulate": "simulate",
    # SYNTHESIZE
    "generate": "generate",
    "create": "generate",
    "write": "generate",
    "compose": "generate",
    "build": "generate",
    "transform": "transform",
    "convert": "transform",
    "format": "transform",
    "translate": "transform",
    "integrate": "integrate",
    "merge": "integrate",
    "combine": "integrate",
    # EXECUTE
    "execute": "execute",
    "run": "execute",
    "deploy": "execute",
    "install": "execute",
    "modify": "mutate",
    "change": "mutate",
    "delete": "mutate",
    "remove": "mutate",
    "edit": "mutate",
    "send": "send",
    "email": "send",
    "publish": "send",
    "notify": "send",
    "post": "send",
    # VERIFY
    "check": "verify",
    "validate": "verify",
    "test": "verify",
    "assert": "verify",
    "checkpoint": "checkpoint",
    "save": "checkpoint",
    "backup": "checkpoint",
    "rollback": "rollback",
    "undo": "rollback",
    "revert": "rollback",
    "constrain": "constrain",
    "limit": "constrain",
    "restrict": "constrain",
    "audit": "audit",
    "log": "audit",
    "trace": "audit",
    # REMEMBER
    "persist": "persist",
    "store": "persist",
    "cache": "persist",
    "recall": "recall",
    "remember": "recall",
    # COORDINATE
    "delegate": "delegate",
    "assign": "delegate",
    "synchronize": "synchronize",
    "sync": "synchronize",
    "coordinate": "synchronize",
    "invoke": "invoke",
    "call": "invoke",
    "trigger": "invoke",
    "ask": "inquire",
    "prompt": "inquire",
    "request": "inquire",
    "confirm": "inquire",
}

# Confidence for keyword fallback — intentionally below classifier's
# MATCH_THRESHOLD (0.6) so that keyword-only matches are routed to gap
# detection.  This is by design: keyword heuristics are too imprecise to
# accept without LLM validation, so they serve as *suggestions* that the
# gap detector can propose as new capabilities.
_KEYWORD_CONFIDENCE = 0.5


class TaskAnalyzer:
    """Extract structured capability requirements from natural language.

    Uses an LLM to decompose task descriptions into atomic action-target
    pairs and map each to ontology capabilities. Falls back to keyword
    matching when no LLM function is provided.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        llm_fn: LLMFunction | None = None,
    ) -> None:
        self.registry = registry
        self._llm_fn = llm_fn

    async def analyze(
        self,
        task_description: str,
        domain: str | None = None,
    ) -> tuple[list[TaskRequirement], list[CapabilityMatch]]:
        """
        Analyze a task description and return requirements with matches.

        When an LLM function is available, sends a combined analysis +
        classification prompt for efficiency (single LLM call).
        Falls back to keyword heuristics otherwise.

        Args:
            task_description: Natural language task description.
            domain: Optional domain context for specialization.

        Returns:
            Tuple of (requirements, matches).
        """
        if self._llm_fn is not None:
            return await self._analyze_with_llm(task_description, domain)
        return self._analyze_with_keywords(task_description, domain)

    async def _analyze_with_llm(
        self,
        task_description: str,
        domain: str | None,
    ) -> tuple[list[TaskRequirement], list[CapabilityMatch]]:
        """LLM-based analysis using structured output."""
        system_prompt, user_prompt, schema = build_analysis_prompt(
            task_description, self.registry, domain
        )

        prompt = f"{system_prompt}\n\n{user_prompt}\n\nRespond with JSON:\n{json.dumps(schema)}"

        # Caller gates on `self._llm_fn is not None`
        try:
            response = await self._llm_fn(prompt, schema)  # type: ignore[misc]
        except Exception as e:
            logger.warning("LLM analysis failed, falling back to keywords: %s", e)
            return self._analyze_with_keywords(task_description, domain)

        # Parse requirements
        requirements: list[TaskRequirement] = []
        for req_data in response.get("requirements", []):
            requirements.append(TaskRequirement.from_dict(req_data))

        # Parse matches, linking to requirements by index
        matches: list[CapabilityMatch] = []
        for match_data in response.get("matches", []):
            idx = match_data.get("requirement_index", 0)
            if 0 <= idx < len(requirements):
                req = requirements[idx]
            else:
                # If index out of range, create a placeholder requirement
                req = TaskRequirement(
                    action=match_data.get("capability_id", ""),
                    target="unknown",
                )
            # Validate capability exists in ontology
            cap_id = match_data.get("capability_id", "")
            if self.registry.get_capability(cap_id) is not None:
                matches.append(CapabilityMatch.from_dict(match_data, req))
            else:
                logger.warning(
                    "LLM returned unknown capability '%s', skipping", cap_id
                )

        return requirements, matches

    def _analyze_with_keywords(
        self,
        task_description: str,
        domain: str | None,
    ) -> tuple[list[TaskRequirement], list[CapabilityMatch]]:
        """Keyword-based fallback analysis."""
        words = task_description.lower().split()
        requirements: list[TaskRequirement] = []
        matches: list[CapabilityMatch] = []
        seen_capabilities: set[str] = set()

        for i, word in enumerate(words):
            # Strip punctuation
            clean = word.strip(".,;:!?()\"'")
            if clean not in _VERB_HEURISTICS:
                continue

            cap_id = _VERB_HEURISTICS[clean]
            if cap_id in seen_capabilities:
                continue

            # Determine target (next meaningful word)
            target = words[i + 1] if i + 1 < len(words) else "unspecified"
            target = target.strip(".,;:!?()\"'")

            req = TaskRequirement(
                action=clean,
                target=target,
                domain_hint=domain,
            )
            requirements.append(req)

            # Only match if capability exists in ontology
            if self.registry.get_capability(cap_id) is not None:
                match = CapabilityMatch(
                    capability_id=cap_id,
                    confidence=_KEYWORD_CONFIDENCE,
                    requirement=req,
                    reasoning=f"Keyword match: '{clean}' -> {cap_id}",
                    domain=domain,
                )
                matches.append(match)
                seen_capabilities.add(cap_id)

        return requirements, matches
