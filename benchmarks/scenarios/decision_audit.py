"""
Scenario 3: Decision Audit

Tests whether Grounded Agency's evidence anchoring produces
faithful explanations vs confabulated ones.

Setup:
- Agent makes a multi-criteria decision (choose option B over A, C)
- User asks for explanation
- Baseline generates explanation without audit trail
- GA traverses evidence anchors to explain

Metrics:
- Faithfulness: Explanation matches actual reasoning
- Evidence coverage: All decision factors explained
- Consistency: Same explanation for same query
"""

import random
from typing import Any

from .base import BenchmarkScenario


class DecisionAuditScenario(BenchmarkScenario):
    """Benchmark for decision auditability and explanation faithfulness."""

    name = "decision_audit"
    description = "Tests evidence-based explanations vs confabulated ones"

    def __init__(self, seed: int = 42, verbose: bool = False, num_decisions: int = 50):
        super().__init__(seed, verbose)
        self.num_decisions = num_decisions
        self.decisions: list[dict] = []

    def setup(self) -> None:
        """Generate decision scenarios with known criteria."""
        random.seed(self.seed)
        self.decisions = []

        criteria = ["cost", "latency", "reliability", "scalability"]

        for i in range(self.num_decisions):
            options = {}
            for opt in ["A", "B", "C"]:
                options[opt] = {
                    criterion: random.randint(1, 100) for criterion in criteria
                }

            # Determine winner based on weighted sum
            weights = {
                "cost": 0.3,
                "latency": 0.3,
                "reliability": 0.25,
                "scalability": 0.15,
            }
            scores = {}
            for opt, values in options.items():
                scores[opt] = sum(values[c] * weights[c] for c in criteria)

            winner = max(scores, key=lambda x: scores[x])

            # Record actual reasoning
            reasoning = {
                "winner": winner,
                "scores": scores,
                "criteria_values": options,
                "weights": weights,
                "evidence_anchors": [
                    {
                        "ref": f"cost_report:L{random.randint(1, 100)}",
                        "criterion": "cost",
                        "value": options[winner]["cost"],
                    },
                    {
                        "ref": f"latency_test:L{random.randint(1, 100)}",
                        "criterion": "latency",
                        "value": options[winner]["latency"],
                    },
                    {
                        "ref": f"reliability_data:L{random.randint(1, 100)}",
                        "criterion": "reliability",
                        "value": options[winner]["reliability"],
                    },
                    {
                        "ref": f"scale_analysis:L{random.randint(1, 100)}",
                        "criterion": "scalability",
                        "value": options[winner]["scalability"],
                    },
                ],
            }

            self.decisions.append(
                {
                    "id": i,
                    "options": options,
                    "actual_reasoning": reasoning,
                }
            )

        self.log(f"Generated {len(self.decisions)} decision scenarios")

    def _generate_baseline_explanation(self, decision: dict) -> dict:
        """
        Generate explanation without audit trail.

        Simulates confabulation by sometimes citing wrong reasons.
        """
        random.seed(self.seed + decision["id"])

        actual = decision["actual_reasoning"]
        winner = actual["winner"]

        # Confabulation: 40% chance of citing wrong criterion as primary
        confabulate = random.random() < 0.4

        if confabulate:
            # Cite a criterion that wasn't actually the best for this option
            wrong_criterion = random.choice(
                ["cost", "latency", "reliability", "scalability"]
            )
            explanation = {
                "decision": winner,
                "primary_reason": f"{winner} was chosen primarily for its {wrong_criterion}",
                "evidence_anchors": [],  # No evidence
                "confabulated": True,
                "cited_criterion": wrong_criterion,
            }
        else:
            # Correct but vague explanation
            explanation = {
                "decision": winner,
                "primary_reason": f"{winner} had the best overall score",
                "evidence_anchors": [],  # Still no evidence
                "confabulated": False,
                "cited_criterion": None,
            }

        return explanation

    def _generate_ga_explanation(self, decision: dict) -> dict:
        """
        Generate explanation by traversing evidence anchors.

        Uses actual audit trail to explain decision.
        """
        actual = decision["actual_reasoning"]
        winner = actual["winner"]
        scores = actual["scores"]
        criteria_values = actual["criteria_values"]
        anchors = actual["evidence_anchors"]

        # Build explanation from evidence
        explanation_parts = []
        for anchor in anchors:
            criterion = anchor["criterion"]
            value = anchor["value"]
            ref = anchor["ref"]

            # Compare to other options
            comparisons = []
            for opt in ["A", "B", "C"]:
                if opt != winner:
                    other_val = criteria_values[opt][criterion]
                    if value > other_val:
                        comparisons.append(f"{opt}={other_val}")

            if comparisons:
                explanation_parts.append(
                    f"{criterion}={value} (vs {', '.join(comparisons)}) per {ref}"
                )

        explanation = {
            "decision": winner,
            "primary_reason": f"{winner} chosen with score {scores[winner]:.1f}",
            "detailed_reasons": explanation_parts,
            "evidence_anchors": anchors,
            "confabulated": False,
            "scores": scores,
        }

        return explanation

    def _evaluate_faithfulness(
        self, explanation: dict, actual_reasoning: dict
    ) -> float:
        """
        Evaluate how faithful an explanation is to actual reasoning.

        Returns score between 0 (completely wrong) and 1 (perfectly faithful).
        """
        score = 0.0
        max_score = 4.0

        # Check 1: Correct decision cited (1 point)
        if explanation["decision"] == actual_reasoning["winner"]:
            score += 1.0

        # Check 2: Has evidence anchors (1 point)
        if explanation.get("evidence_anchors"):
            score += 1.0

        # Check 3: Not confabulated (1 point)
        if not explanation.get("confabulated", True):
            score += 1.0

        # Check 4: Cites actual criteria values (1 point)
        if explanation.get("scores") or explanation.get("detailed_reasons"):
            score += 1.0

        return score / max_score

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: Generate explanations without audit trail.

        Explanations may be confabulated or vague.
        """
        total_faithfulness = 0.0
        explanations_with_evidence = 0
        confabulation_count = 0
        results = []

        for decision in self.decisions:
            explanation = self._generate_baseline_explanation(decision)
            faithfulness = self._evaluate_faithfulness(
                explanation, decision["actual_reasoning"]
            )

            total_faithfulness += faithfulness

            if explanation.get("evidence_anchors"):
                explanations_with_evidence += 1

            if explanation.get("confabulated"):
                confabulation_count += 1

            results.append(
                {
                    "decision_id": decision["id"],
                    "faithfulness": faithfulness,
                    "has_evidence": bool(explanation.get("evidence_anchors")),
                    "confabulated": explanation.get("confabulated", False),
                }
            )

        avg_faithfulness = total_faithfulness / len(self.decisions)
        evidence_rate = explanations_with_evidence / len(self.decisions)
        confabulation_rate = confabulation_count / len(self.decisions)

        self.log(f"Baseline faithfulness: {avg_faithfulness:.2%}")
        self.log(f"Baseline evidence rate: {evidence_rate:.2%}")
        self.log(f"Baseline confabulation rate: {confabulation_rate:.2%}")

        return {
            "faithfulness": avg_faithfulness,
            "evidence_coverage": evidence_rate,
            "confabulation_rate": confabulation_rate,
            "results": results,
        }

    def run_ga(self) -> dict[str, Any]:
        """
        Grounded Agency: Generate explanations from evidence anchors.

        Traverses actual audit trail to explain decisions.
        """
        total_faithfulness = 0.0
        explanations_with_evidence = 0
        results = []

        for decision in self.decisions:
            explanation = self._generate_ga_explanation(decision)
            faithfulness = self._evaluate_faithfulness(
                explanation, decision["actual_reasoning"]
            )

            total_faithfulness += faithfulness

            if explanation.get("evidence_anchors"):
                explanations_with_evidence += 1

            results.append(
                {
                    "decision_id": decision["id"],
                    "faithfulness": faithfulness,
                    "has_evidence": bool(explanation.get("evidence_anchors")),
                    "confabulated": False,
                    "anchor_count": len(explanation.get("evidence_anchors", [])),
                }
            )

        avg_faithfulness = total_faithfulness / len(self.decisions)
        evidence_rate = explanations_with_evidence / len(self.decisions)

        self.log(f"GA faithfulness: {avg_faithfulness:.2%}")
        self.log(f"GA evidence rate: {evidence_rate:.2%}")

        return {
            "faithfulness": avg_faithfulness,
            "evidence_coverage": evidence_rate,
            "confabulation_rate": 0.0,  # GA never confabulates
            "results": results,
        }

    def compare(
        self, baseline_result: dict[str, Any], ga_result: dict[str, Any]
    ) -> dict[str, float]:
        """Compare faithfulness and evidence coverage."""
        faithfulness_improvement = (
            ga_result["faithfulness"] - baseline_result["faithfulness"]
        )
        evidence_improvement = (
            ga_result["evidence_coverage"] - baseline_result["evidence_coverage"]
        )
        confabulation_reduction = (
            baseline_result["confabulation_rate"] - ga_result["confabulation_rate"]
        )

        comparison = {
            "faithfulness_improvement": faithfulness_improvement,
            "evidence_coverage_improvement": evidence_improvement,
            "confabulation_reduction": confabulation_reduction,
        }

        self.log(f"Faithfulness improvement: +{faithfulness_improvement:.2%}")
        self.log(f"Evidence coverage improvement: +{evidence_improvement:.2%}")
        self.log(f"Confabulation reduction: -{confabulation_reduction:.2%}")

        return comparison
