"""
Base class for benchmark scenarios.

Each scenario must implement:
- setup(): Prepare test fixtures
- run_baseline(): Execute naive approach
- run_ga(): Execute Grounded Agency approach
- compare(): Generate comparison metrics
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""

    scenario_name: str
    baseline_metrics: dict[str, Any]
    ga_metrics: dict[str, Any]
    improvement: dict[str, float]
    execution_time_ms: float
    metadata: dict[str, Any] | None = None


class BenchmarkScenario(ABC):
    """Abstract base class for benchmark scenarios."""

    name: str = "base"
    description: str = "Base benchmark scenario"

    def __init__(self, seed: int = 42, verbose: bool = False):
        """
        Initialize scenario.

        Args:
            seed: Random seed for reproducibility
            verbose: Whether to print detailed output
        """
        self.seed = seed
        self.verbose = verbose

    @abstractmethod
    def setup(self) -> None:
        """Prepare test fixtures and initial state."""
        pass

    @abstractmethod
    def run_baseline(self) -> dict[str, Any]:
        """
        Execute baseline (naive) approach.

        Returns:
            Dictionary of metrics from baseline run
        """
        pass

    @abstractmethod
    def run_ga(self) -> dict[str, Any]:
        """
        Execute Grounded Agency approach.

        Returns:
            Dictionary of metrics from GA run
        """
        pass

    @abstractmethod
    def compare(
        self, baseline_result: dict[str, Any], ga_result: dict[str, Any]
    ) -> dict[str, float]:
        """
        Compare baseline and GA results.

        Args:
            baseline_result: Metrics from baseline run
            ga_result: Metrics from GA run

        Returns:
            Dictionary of improvement metrics
        """
        pass

    def run(self, iterations: int = 1) -> BenchmarkResult:
        """
        Execute the full benchmark.

        Args:
            iterations: Number of times to run (for averaging)

        Returns:
            BenchmarkResult with all metrics
        """
        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"Scenario: {self.name}")
            print(f"Description: {self.description}")
            print(f"Iterations: {iterations}")
            print(f"{'=' * 60}")

        self.setup()

        baseline_results = []
        ga_results = []
        total_time = 0

        for i in range(iterations):
            if self.verbose and iterations > 1:
                print(f"\n--- Iteration {i + 1}/{iterations} ---")

            start = time.time()

            baseline = self.run_baseline()
            ga = self.run_ga()

            total_time += (time.time() - start) * 1000

            baseline_results.append(baseline)
            ga_results.append(ga)

        # Average results across iterations
        avg_baseline = self._average_metrics(baseline_results)
        avg_ga = self._average_metrics(ga_results)
        improvement = self.compare(avg_baseline, avg_ga)

        return BenchmarkResult(
            scenario_name=self.name,
            baseline_metrics=avg_baseline,
            ga_metrics=avg_ga,
            improvement=improvement,
            execution_time_ms=total_time,
            metadata={"iterations": iterations, "seed": self.seed},
        )

    def _average_metrics(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Average numeric metrics across multiple runs."""
        if not results:
            return {}

        averaged = {}
        for key in results[0]:
            values = [r[key] for r in results if key in r]
            if all(isinstance(v, (int, float)) for v in values):
                averaged[key] = sum(values) / len(values)
            else:
                # For non-numeric, take the last value
                averaged[key] = values[-1]

        return averaged

    def log(self, message: str) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {message}")
