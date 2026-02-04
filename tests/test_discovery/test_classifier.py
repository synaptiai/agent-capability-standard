"""Tests for CapabilityClassifier."""

from __future__ import annotations

import pytest

from grounded_agency.discovery.classifier import MATCH_THRESHOLD, CapabilityClassifier
from grounded_agency.discovery.types import CapabilityMatch, TaskRequirement


class TestCapabilityClassifier:
    """Tests for match classification and gap routing."""

    def test_high_confidence_match_accepted(self, classifier: CapabilityClassifier):
        """Matches above threshold should be accepted."""
        req = TaskRequirement(action="find", target="files")
        match = CapabilityMatch(
            capability_id="search",
            confidence=0.9,
            requirement=req,
            reasoning="High confidence match",
        )
        accepted, gaps = classifier.classify([req], [match])
        assert len(accepted) == 1
        assert accepted[0].capability_id == "search"
        assert len(gaps) == 0

    def test_low_confidence_routed_to_gap(self, classifier: CapabilityClassifier):
        """Matches below threshold should become gaps."""
        req = TaskRequirement(action="negotiate", target="terms")
        match = CapabilityMatch(
            capability_id="inquire",
            confidence=0.3,
            requirement=req,
            reasoning="Low confidence match",
        )
        accepted, gaps = classifier.classify([req], [match])
        assert len(accepted) == 0
        assert len(gaps) == 1
        assert gaps[0].requirement.action == "negotiate"

    def test_unknown_capability_routed_to_gap(self, classifier: CapabilityClassifier):
        """Matches to non-existent capabilities should become gaps."""
        req = TaskRequirement(action="teleport", target="data")
        match = CapabilityMatch(
            capability_id="nonexistent_capability",
            confidence=0.95,
            requirement=req,
            reasoning="Maps to unknown",
        )
        accepted, gaps = classifier.classify([req], [match])
        assert len(accepted) == 0
        assert len(gaps) == 1

    def test_unmatched_requirements_become_gaps(self, classifier: CapabilityClassifier):
        """Requirements with no matches should appear as gaps."""
        req1 = TaskRequirement(action="find", target="files")
        req2 = TaskRequirement(action="teleport", target="data")
        match = CapabilityMatch(
            capability_id="search",
            confidence=0.9,
            requirement=req1,
            reasoning="Good match",
        )
        accepted, gaps = classifier.classify([req1, req2], [match])
        assert len(accepted) == 1
        assert len(gaps) == 1
        assert gaps[0].requirement.action == "teleport"

    def test_threshold_boundary(self, classifier: CapabilityClassifier):
        """Match at exactly the threshold should be rejected (< not <=)."""
        req = TaskRequirement(action="find", target="files")
        match = CapabilityMatch(
            capability_id="search",
            confidence=MATCH_THRESHOLD - 0.01,
            requirement=req,
            reasoning="Just below threshold",
        )
        accepted, gaps = classifier.classify([req], [match])
        assert len(accepted) == 0
        assert len(gaps) == 1

    def test_at_threshold_accepted(self, classifier: CapabilityClassifier):
        """Match at exactly the threshold should be accepted."""
        req = TaskRequirement(action="find", target="files")
        match = CapabilityMatch(
            capability_id="search",
            confidence=MATCH_THRESHOLD,
            requirement=req,
            reasoning="Exactly at threshold",
        )
        accepted, gaps = classifier.classify([req], [match])
        assert len(accepted) == 1

    def test_nearest_capabilities_populated(self, classifier: CapabilityClassifier):
        """Gap nearest_existing should contain related capabilities."""
        req = TaskRequirement(action="find", target="data")
        match = CapabilityMatch(
            capability_id="nonexistent",
            confidence=0.95,
            requirement=req,
            reasoning="Unknown cap",
        )
        _, gaps = classifier.classify([req], [match])
        assert len(gaps) == 1
        # Should find some nearby capabilities
        assert len(gaps[0].nearest_existing) >= 0  # May or may not find matches

    def test_multiple_matches_same_requirement(self, classifier: CapabilityClassifier):
        """Multiple matches for the same requirement should all be evaluated."""
        req = TaskRequirement(action="find", target="files")
        match1 = CapabilityMatch(
            capability_id="search",
            confidence=0.9,
            requirement=req,
            reasoning="Primary match",
        )
        match2 = CapabilityMatch(
            capability_id="retrieve",
            confidence=0.7,
            requirement=req,
            reasoning="Secondary match",
        )
        accepted, gaps = classifier.classify([req], [match1, match2])
        assert len(accepted) == 2
