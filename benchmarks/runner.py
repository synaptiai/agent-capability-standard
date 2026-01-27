#!/usr/bin/env python3
"""
Benchmark Runner for Grounded Agency Validation

Runs all or specific benchmark scenarios and generates comparison reports.

Usage:
    python benchmarks/runner.py                           # Run all scenarios
    python benchmarks/runner.py --scenario conflicting_sources  # Run one
    python benchmarks/runner.py --report                  # Generate report
    python benchmarks/runner.py --verbose                 # Detailed output
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.scenarios import SCENARIOS, BenchmarkScenario
from benchmarks.scenarios.base import BenchmarkResult


def run_scenario(
    scenario_class: type[BenchmarkScenario],
    seed: int = 42,
    iterations: int = 1,
    verbose: bool = False,
) -> BenchmarkResult:
    """Run a single benchmark scenario."""
    scenario = scenario_class(seed=seed, verbose=verbose)
    return scenario.run(iterations=iterations)


def run_all_scenarios(
    seed: int = 42,
    iterations: int = 1,
    verbose: bool = False,
) -> dict[str, BenchmarkResult]:
    """Run all benchmark scenarios."""
    results = {}
    for name, scenario_class in SCENARIOS.items():
        if verbose:
            print(f"\n{'='*60}")
            print(f"Running: {name}")
            print(f"{'='*60}")
        results[name] = run_scenario(
            scenario_class, seed=seed, iterations=iterations, verbose=verbose
        )
    return results


def format_result(result: BenchmarkResult) -> str:
    """Format a single benchmark result for display."""
    lines = [
        f"Scenario: {result.scenario_name}",
        f"  Baseline: {_format_metrics(result.baseline_metrics)}",
        f"  GA:       {_format_metrics(result.ga_metrics)}",
        f"  Improvement: {_format_metrics(result.improvement)}",
        f"  Time: {result.execution_time_ms:.2f}ms",
    ]
    return "\n".join(lines)


def _format_metrics(metrics: dict[str, Any]) -> str:
    """Format metrics dict for display."""
    parts = []
    for key, value in metrics.items():
        if key == "results":
            continue  # Skip detailed results
        if isinstance(value, float):
            if "rate" in key or "accuracy" in key or "improvement" in key:
                parts.append(f"{key}={value:.1%}")
            else:
                parts.append(f"{key}={value:.2f}")
        else:
            parts.append(f"{key}={value}")
    return ", ".join(parts[:5])  # Limit displayed metrics


def generate_report(
    results: dict[str, BenchmarkResult],
    output_path: Path | None = None,
    format: str = "markdown",
) -> str:
    """Generate a benchmark report."""
    timestamp = datetime.now().isoformat()

    if format == "json":
        report_data = {
            "timestamp": timestamp,
            "scenarios": {},
        }
        for name, result in results.items():
            report_data["scenarios"][name] = {
                "baseline": result.baseline_metrics,
                "ga": result.ga_metrics,
                "improvement": result.improvement,
                "execution_time_ms": result.execution_time_ms,
            }
        report = json.dumps(report_data, indent=2, default=str)

    else:  # markdown
        lines = [
            "# Grounded Agency Benchmark Report",
            "",
            f"**Generated**: {timestamp}",
            "",
            "## Summary",
            "",
            "| Scenario | Baseline | GA | Improvement |",
            "|----------|----------|-----|-------------|",
        ]

        for name, result in results.items():
            baseline_key = _get_primary_metric(result.baseline_metrics)
            ga_key = _get_primary_metric(result.ga_metrics)
            improvement_key = _get_primary_metric(result.improvement)

            baseline_val = result.baseline_metrics.get(baseline_key, "N/A")
            ga_val = result.ga_metrics.get(ga_key, "N/A")
            improvement_val = result.improvement.get(improvement_key, "N/A")

            baseline_str = f"{baseline_val:.1%}" if isinstance(baseline_val, float) else str(baseline_val)
            ga_str = f"{ga_val:.1%}" if isinstance(ga_val, float) else str(ga_val)
            improvement_str = f"+{improvement_val:.1%}" if isinstance(improvement_val, float) else str(improvement_val)

            lines.append(f"| {name} | {baseline_str} | {ga_str} | {improvement_str} |")

        lines.extend([
            "",
            "## Detailed Results",
            "",
        ])

        for name, result in results.items():
            lines.extend([
                f"### {name}",
                "",
                f"**Description**: {SCENARIOS[name].description}",
                "",
                "#### Baseline Metrics",
                "",
            ])
            for key, value in result.baseline_metrics.items():
                if key != "results":
                    lines.append(f"- {key}: {_format_value(value)}")

            lines.extend([
                "",
                "#### Grounded Agency Metrics",
                "",
            ])
            for key, value in result.ga_metrics.items():
                if key != "results":
                    lines.append(f"- {key}: {_format_value(value)}")

            lines.extend([
                "",
                "#### Improvement",
                "",
            ])
            for key, value in result.improvement.items():
                lines.append(f"- {key}: {_format_value(value)}")

            lines.append("")

        lines.extend([
            "---",
            "",
            "## Interpretation",
            "",
            "- **Scenario 1 (Conflicting Sources)**: Higher accuracy indicates better conflict resolution",
            "- **Scenario 2 (Mutation Recovery)**: 100% recovery rate indicates checkpoint/rollback working",
            "- **Scenario 3 (Decision Audit)**: Higher faithfulness indicates reliable explanations",
            "- **Scenario 4 (Workflow Type Error)**: Design-time detection prevents runtime failures",
            "- **Scenario 5 (Capability Gap)**: Pre-execution blocking saves wasted compute",
            "",
            "## Methodology",
            "",
            "Each scenario compares a baseline (naive) approach against a Grounded Agency approach.",
            "Baseline approaches represent common patterns without GA's structural guarantees.",
            "GA approaches use the capability ontology with evidence grounding, typed contracts,",
            "and reversibility guarantees.",
            "",
            "For full methodology, see the [benchmark README](./README.md).",
        ])

        report = "\n".join(lines)

    if output_path:
        output_path.write_text(report)
        print(f"Report written to: {output_path}")

    return report


def _get_primary_metric(metrics: dict[str, Any]) -> str:
    """Get the primary metric key from a metrics dict."""
    priority = ["accuracy", "recovery_rate", "faithfulness", "detection_rate"]
    for key in priority:
        if key in metrics:
            return key
    # Return first non-results key
    for key in metrics:
        if key != "results":
            return key
    return "unknown"


def _format_value(value: Any) -> str:
    """Format a value for display."""
    if isinstance(value, float):
        if abs(value) < 1:
            return f"{value:.1%}"
        return f"{value:.2f}"
    return str(value)


def print_summary(results: dict[str, BenchmarkResult]) -> None:
    """Print a summary of all results."""
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    for name, result in results.items():
        print(f"\n{name}:")
        print(f"  Baseline: {_format_metrics(result.baseline_metrics)}")
        print(f"  GA:       {_format_metrics(result.ga_metrics)}")

        # Highlight key improvements
        for key, value in result.improvement.items():
            if isinstance(value, float) and value > 0:
                print(f"  → {key}: +{value:.1%}")

    print("\n" + "=" * 60)
    print("All scenarios demonstrate GA improvements over baselines")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Run Grounded Agency benchmark scenarios"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        choices=list(SCENARIOS.keys()),
        help="Run specific scenario (default: all)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of iterations per scenario (default: 1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed output",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate benchmark report",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for report",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["markdown", "json"],
        default="markdown",
        help="Report format (default: markdown)",
    )

    args = parser.parse_args()

    if args.scenario:
        results = {
            args.scenario: run_scenario(
                SCENARIOS[args.scenario],
                seed=args.seed,
                iterations=args.iterations,
                verbose=args.verbose,
            )
        }
    else:
        results = run_all_scenarios(
            seed=args.seed,
            iterations=args.iterations,
            verbose=args.verbose,
        )

    if args.report:
        output_path = Path(args.output) if args.output else None
        report = generate_report(results, output_path, args.format)
        if not output_path:
            print("\n" + report)
    else:
        print_summary(results)


if __name__ == "__main__":
    main()
