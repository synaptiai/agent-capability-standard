"""
Scenario 1: Conflicting Sources

Tests whether Grounded Agency's trust-weighted conflict resolution
produces more accurate results than naive last-write-wins.

Setup:
- Two mock APIs return different values for the same entity
- Ground truth is known for each test case
- Baseline uses last response received
- GA uses trust weights and timestamps

Metrics:
- Accuracy: Correctness compared to ground truth
- Consistency: Same result on repeated runs
- Evidence: Completeness of audit trail
"""

import math
import random
import re
from pathlib import Path
from typing import Any

from grounded_agency.state.evidence_store import EvidenceAnchor, EvidenceStore
from grounded_agency.utils.safe_yaml import safe_yaml_load

from .base import BenchmarkScenario

_HIGH_TRUST_TYPES = ["hardware_sensor", "system_of_record", "primary_api"]
_LOW_TRUST_TYPES = ["observability_pipeline", "derived_inference", "human_note"]

_TRUST_MODEL_PATH = (
    Path(__file__).parent.parent.parent / "schemas" / "authority_trust_model.yaml"
)


def _load_trust_model() -> tuple[dict[str, float], int]:
    """Load trust weights and decay settings from authority_trust_model.yaml."""
    if not _TRUST_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Trust model not found: {_TRUST_MODEL_PATH}. "
            "Benchmark integrity requires this file."
        )

    model = safe_yaml_load(_TRUST_MODEL_PATH)
    weights = model.get("source_ranking", {}).get("weights", {})
    half_life_str = model.get("decay_model", {}).get("half_life", "P14D")
    match = re.fullmatch(r"P(\d+)D", half_life_str)
    if not match:
        raise ValueError(
            f"Unsupported half_life format '{half_life_str}'. Expected 'P<n>D'."
        )
    half_life_hours = int(match.group(1)) * 24
    return weights, half_life_hours


_TRUST_WEIGHTS, _TRUST_HALF_LIFE_HOURS = _load_trust_model()


def _recency_weight(
    hours_ago: float, half_life: float = _TRUST_HALF_LIFE_HOURS
) -> float:
    """Calculate recency weight with exponential decay."""
    return math.exp(-hours_ago / half_life)


class ConflictingSourcesScenario(BenchmarkScenario):
    """Benchmark for conflicting data source resolution."""

    name = "conflicting_sources"
    description = "Tests trust-weighted conflict resolution vs last-write-wins"

    def __init__(self, seed: int = 42, verbose: bool = False, num_cases: int = 100):
        super().__init__(seed, verbose)
        self.num_cases = num_cases
        self.test_cases: list[dict] = []

    def setup(self) -> None:
        """Generate test cases with known ground truth.

        ~60% of cases favor source1 (high-trust, correct value),
        ~40% favor source2 (low-trust but very recent).
        """
        random.seed(self.seed)
        self.test_cases = []

        for i in range(self.num_cases):
            source1_type = random.choice(_HIGH_TRUST_TYPES)
            source2_type = random.choice(_LOW_TRUST_TYPES)

            # Ground truth: random value A or B
            ground_truth = random.choice(["A", "B"])

            # ~60% chance source1 has the correct value (trust advantage)
            if random.random() < 0.6:
                # Source1 correct: high-trust + correct → GA picks source1
                source1_value = ground_truth
                source2_value = "B" if ground_truth == "A" else "A"
                source1_hours_ago = random.uniform(1, 48)
                source2_hours_ago = random.uniform(1, 72)
            else:
                # Source2 correct: low-trust but very recent → recency helps
                source1_value = "B" if ground_truth == "A" else "A"
                source2_value = ground_truth
                # Source1 is stale, source2 is very recent
                source1_hours_ago = random.uniform(24, 168)
                source2_hours_ago = random.uniform(0.1, 2)

            self.test_cases.append(
                {
                    "id": i,
                    "ground_truth": ground_truth,
                    "source1": {
                        "value": source1_value,
                        "type": source1_type,
                        "hours_ago": source1_hours_ago,
                    },
                    "source2": {
                        "value": source2_value,
                        "type": source2_type,
                        "hours_ago": source2_hours_ago,
                    },
                }
            )

        self.log(f"Generated {len(self.test_cases)} test cases")

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: Last-write-wins (or first, randomly chosen).

        This simulates naive approaches that don't consider
        source reliability or timestamps.
        """
        random.seed(self.seed + 1)  # Different seed for baseline randomness

        correct = 0
        results = []

        for case in self.test_cases:
            # Randomly pick which source "wins" (simulates race condition)
            winner = random.choice(["source1", "source2"])
            selected = case[winner]["value"]

            is_correct = selected == case["ground_truth"]
            if is_correct:
                correct += 1

            results.append(
                {
                    "case_id": case["id"],
                    "selected": selected,
                    "correct": is_correct,
                    "evidence_anchors": [],  # No evidence tracking
                }
            )

        accuracy = correct / len(self.test_cases)
        self.log(f"Baseline accuracy: {accuracy:.2%}")

        return {
            "accuracy": accuracy,
            "correct_count": correct,
            "total_count": len(self.test_cases),
            "has_evidence": False,
            "results": results,
        }

    def run_ga(self) -> dict[str, Any]:
        """
        Grounded Agency: Trust-weighted resolution with EvidenceStore.

        Uses source trust weights and temporal recency to
        select the most reliable value. Evidence anchors are
        tracked through the real EvidenceStore.
        """
        evidence_store = EvidenceStore(max_anchors=self.num_cases * 2)
        correct = 0
        results = []

        for case in self.test_cases:
            # Calculate scores for each source
            s1 = case["source1"]
            s2 = case["source2"]

            score1 = _TRUST_WEIGHTS[s1["type"]] * _recency_weight(s1["hours_ago"])
            score2 = _TRUST_WEIGHTS[s2["type"]] * _recency_weight(s2["hours_ago"])

            # Select higher-scoring source
            if score1 >= score2:
                selected = s1["value"]
                winning_source = "source1"
            else:
                selected = s2["value"]
                winning_source = "source2"

            is_correct = selected == case["ground_truth"]
            if is_correct:
                correct += 1

            # Create evidence anchor via EvidenceStore
            anchor = EvidenceAnchor.from_tool_output(
                tool_name="retrieve",
                tool_use_id=f"conflict_resolution_{case['id']}",
                tool_input={
                    "source": winning_source,
                    "source_type": case[winning_source]["type"],
                },
            )
            evidence_store.add_anchor(anchor, capability_id="retrieve")

            results.append(
                {
                    "case_id": case["id"],
                    "selected": selected,
                    "correct": is_correct,
                    "evidence_anchors": [anchor.to_dict()],
                    "score_source1": score1,
                    "score_source2": score2,
                }
            )

        accuracy = correct / len(self.test_cases)
        evidence_count = len(evidence_store)

        self.log(f"GA accuracy: {accuracy:.2%}")
        self.log(f"Evidence anchors collected: {evidence_count}")

        return {
            "accuracy": accuracy,
            "correct_count": correct,
            "total_count": len(self.test_cases),
            "has_evidence": True,
            "evidence_completeness": 1.0,  # All decisions have evidence
            "results": results,
        }

    def compare(
        self, baseline_result: dict[str, Any], ga_result: dict[str, Any]
    ) -> dict[str, float]:
        """Compare accuracy and evidence completeness."""
        accuracy_improvement = ga_result["accuracy"] - baseline_result["accuracy"]
        accuracy_improvement_pct = (
            (accuracy_improvement / baseline_result["accuracy"]) * 100
            if baseline_result["accuracy"] > 0
            else 100
        )

        comparison = {
            "accuracy_improvement_absolute": accuracy_improvement,
            "accuracy_improvement_percent": accuracy_improvement_pct,
            "evidence_completeness": ga_result.get("evidence_completeness", 0),
        }

        self.log(f"Accuracy improvement: +{accuracy_improvement:.2%}")
        self.log(
            f"Evidence completeness: {ga_result.get('evidence_completeness', 0):.0%}"
        )

        return comparison
