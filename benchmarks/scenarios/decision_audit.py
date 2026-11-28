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
- Faithfulness: each reason the explanation gives is compared with the
  actual reasoning (criteria values and scores); an explanation's own
  labels are never read
- Evidence coverage: All decision factors explained
- Consistency: Same explanation for same query
"""

import math
import random
import re
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

        Cites a criterion picked at random 40% of the time, which may or may
        not be the one that decided; otherwise gives no checkable reason.
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
                "cited_criterion": wrong_criterion,
            }
        else:
            # Correct but vague explanation
            explanation = {
                "decision": winner,
                "primary_reason": f"{winner} had the best overall score",
                "evidence_anchors": [],  # Still no evidence
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
            "scores": scores,
        }

        return explanation

    @staticmethod
    def _primary_criterion(actual_reasoning: dict) -> str:
        """The criterion that contributed most to the winner's lead: the
        largest weighted margin of the winner over the best other option."""
        winner = actual_reasoning["winner"]
        values = actual_reasoning["criteria_values"]
        weights = actual_reasoning["weights"]

        def margin(criterion: str) -> float:
            best_other = max(v[criterion] for opt, v in values.items() if opt != winner)
            return float(weights[criterion] * (values[winner][criterion] - best_other))

        primary: str = max(weights, key=margin)
        return primary

    @staticmethod
    def _parse_reason(reason: str) -> tuple[str, float, dict[str, float]] | None:
        """``criterion=value (vs A=1, C=2) per ref`` as its criterion, value
        and the other options' values; None for any other text."""
        match = re.fullmatch(r"(\w+)=([\d.]+) \(vs ([^)]*)\) per \S+", reason)
        if match is None:
            return None
        others = {}
        for pair in match.group(3).split(", "):
            opt, _, val = pair.partition("=")
            others[opt] = float(val)
        return match.group(1), float(match.group(2)), others

    def _check_claims(self, explanation: dict, actual_reasoning: dict) -> list[str]:
        """The verdict on each reason the explanation gives, compared with
        the actual reasoning (``criteria_values``, ``scores``):
        ``supported``, ``unsupported`` or ``contradicted``. The explanation's
        own labels are never read."""
        winner = actual_reasoning["winner"]
        values = actual_reasoning["criteria_values"]
        verdicts: list[str] = []

        cited = explanation.get("cited_criterion")
        if cited is not None:
            others_best = max(v[cited] for opt, v in values.items() if opt != winner)
            if values[winner][cited] <= others_best:
                # The winner was not ahead on the criterion it was chosen for.
                verdicts.append("contradicted")
            elif cited == self._primary_criterion(actual_reasoning):
                verdicts.append("supported")
            else:
                # Ahead on it, but it is not what decided.
                verdicts.append("unsupported")

        for reason in explanation.get("detailed_reasons") or []:
            parsed = self._parse_reason(reason)
            if parsed is None:
                verdicts.append("unsupported")
                continue
            criterion, value, others = parsed
            if criterion not in values[winner]:
                verdicts.append("unsupported")
                continue
            stated = {winner: value, **others}
            if any(
                opt not in values or values[opt][criterion] != val
                for opt, val in stated.items()
            ) or any(value <= val for val in others.values()):
                verdicts.append("contradicted")
            else:
                verdicts.append("supported")

        scores = explanation.get("scores")
        if scores is not None:
            actual = actual_reasoning["scores"]
            same = set(scores) == set(actual) and all(
                math.isclose(scores[k], actual[k]) for k in actual
            )
            verdicts.append("supported" if same else "contradicted")
        return verdicts

    def _evaluate_faithfulness(
        self, explanation: dict, actual_reasoning: dict
    ) -> dict[str, Any]:
        """How faithful an explanation is to the actual reasoning.

        ``faithfulness`` (0 to 1) is the mean of two parts: the decision it
        names is the actual winner, and the share of its reasons that the
        actual reasoning supports (0 when it gives no reason it can be
        checked on). ``confabulated`` is true when any reason is unsupported
        or contradicted.
        """
        verdicts = self._check_claims(explanation, actual_reasoning)
        decision_ok = (
            1.0 if explanation["decision"] == actual_reasoning["winner"] else 0.0
        )
        supported = verdicts.count("supported")
        reasons_ok = supported / len(verdicts) if verdicts else 0.0
        return {
            "faithfulness": (decision_ok + reasons_ok) / 2,
            "confabulated": supported < len(verdicts),
            "unsupported": verdicts.count("unsupported"),
            "contradicted": verdicts.count("contradicted"),
        }

    def _evaluate_all(self, generate: Any, label: str) -> dict[str, Any]:
        """Generate an explanation of every decision and check it against
        the actual reasoning."""
        total_faithfulness = 0.0
        explanations_with_evidence = 0
        confabulation_count = 0
        unsupported = contradicted = 0
        results = []

        for decision in self.decisions:
            explanation = generate(decision)
            checked = self._evaluate_faithfulness(
                explanation, decision["actual_reasoning"]
            )
            total_faithfulness += checked["faithfulness"]
            unsupported += checked["unsupported"]
            contradicted += checked["contradicted"]
            if explanation.get("evidence_anchors"):
                explanations_with_evidence += 1
            if checked["confabulated"]:
                confabulation_count += 1
            results.append(
                {
                    "decision_id": decision["id"],
                    "faithfulness": checked["faithfulness"],
                    "has_evidence": bool(explanation.get("evidence_anchors")),
                    "confabulated": checked["confabulated"],
                    "anchor_count": len(explanation.get("evidence_anchors", [])),
                }
            )

        n = len(self.decisions)
        metrics = {
            "faithfulness": total_faithfulness / n,
            "evidence_coverage": explanations_with_evidence / n,
            "confabulation_rate": confabulation_count / n,
            "unsupported_claims": unsupported,
            "contradicted_claims": contradicted,
            "results": results,
        }
        self.log(f"{label} faithfulness: {metrics['faithfulness']:.2%}")
        self.log(f"{label} evidence rate: {metrics['evidence_coverage']:.2%}")
        self.log(f"{label} confabulation rate: {metrics['confabulation_rate']:.2%}")
        return metrics

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: Generate explanations without audit trail.

        Explanations may cite the wrong criterion or give no reason.
        """
        return self._evaluate_all(self._generate_baseline_explanation, "Baseline")

    def run_ga(self) -> dict[str, Any]:
        """
        Grounded Agency: Generate explanations from evidence anchors.

        Traverses actual audit trail to explain decisions.
        """
        return self._evaluate_all(self._generate_ga_explanation, "GA")

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
