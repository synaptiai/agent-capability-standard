"""
Scenario 2: Mutation Failure Recovery

Tests whether Grounded Agency's checkpoint/rollback pattern
enables recovery from failed mutations.

Setup:
- Original file with known content
- Mutation operation that fails partway through
- Baseline has no checkpointing
- GA creates checkpoint before mutation

Metrics:
- Recovery rate: Successful state restoration
- Data integrity: Bytes match original
- Recovery time: How quickly state is restored
"""

import atexit
import hashlib
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .base import BenchmarkScenario


class MutationRecoveryScenario(BenchmarkScenario):
    """Benchmark for mutation failure recovery."""

    name = "mutation_recovery"
    description = "Tests checkpoint/rollback recovery vs no checkpointing"

    def __init__(
        self,
        seed: int = 42,
        verbose: bool = False,
        file_lines: int = 100,
        mutation_start: int = 50,
        mutation_end: int = 60,
        failure_line: int = 55,
    ):
        super().__init__(seed, verbose)
        self.file_lines = file_lines
        self.mutation_start = mutation_start
        self.mutation_end = mutation_end
        self.failure_line = failure_line
        self.original_content: str = ""
        self.original_hash: str = ""
        self.temp_dir: Path | None = None
        self._cleanup_registered: bool = False

    def setup(self) -> None:
        """Create test file with known content."""
        # Generate original file content
        lines = [f"line_{i}: original_value_{i}" for i in range(self.file_lines)]
        self.original_content = "\n".join(lines)
        self.original_hash = hashlib.sha256(
            self.original_content.encode()
        ).hexdigest()

        # Create temporary directory for test files
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ga_benchmark_"))

        # Register cleanup with atexit for reliable resource management (only once)
        if not self._cleanup_registered:
            atexit.register(self._cleanup)
            self._cleanup_registered = True

        self.log(f"Original file: {self.file_lines} lines")
        self.log(f"Original hash: {self.original_hash[:16]}...")
        self.log(f"Mutation range: lines {self.mutation_start}-{self.mutation_end}")
        self.log(f"Failure point: line {self.failure_line}")

    def _simulate_mutation_with_failure(
        self, file_path: Path, checkpoint_content: str | None = None
    ) -> dict[str, Any]:
        """
        Simulate a mutation operation that fails partway through.

        Args:
            file_path: Path to the file to mutate
            checkpoint_content: If provided, used for rollback on failure

        Returns:
            Result dict with recovery status and final content
        """
        start_time = time.time()

        # Write original content
        file_path.write_text(self.original_content)

        # Attempt mutation (line by line to simulate partial failure)
        lines = self.original_content.split("\n")
        failed = False
        lines_written = 0

        try:
            with open(file_path, "w") as f:
                for i, line in enumerate(lines):
                    # Simulate failure at specific line during mutation
                    if (
                        self.mutation_start <= i <= self.mutation_end
                        and i == self.failure_line
                    ):
                        # Simulate crash - file left in partial state
                        failed = True
                        break

                    # Write mutated or original line
                    if self.mutation_start <= i <= self.mutation_end:
                        f.write(f"line_{i}: MUTATED_value_{i}\n")
                    else:
                        f.write(line + "\n")

                    lines_written = i + 1

        except Exception:
            failed = True

        elapsed_ms = (time.time() - start_time) * 1000

        # Check final state
        final_content = file_path.read_text()
        final_hash = hashlib.sha256(final_content.encode()).hexdigest()

        # Attempt recovery if checkpoint available
        recovered = False
        recovery_time_ms = 0

        if failed and checkpoint_content is not None:
            recovery_start = time.time()
            file_path.write_text(checkpoint_content)
            recovery_time_ms = (time.time() - recovery_start) * 1000

            final_content = file_path.read_text()
            final_hash = hashlib.sha256(final_content.encode()).hexdigest()
            recovered = final_hash == self.original_hash

        return {
            "failed": failed,
            "lines_written": lines_written,
            "recovered": recovered,
            "recovery_time_ms": recovery_time_ms,
            "data_integrity": final_hash == self.original_hash,
            "final_hash": final_hash,
            "elapsed_ms": elapsed_ms,
        }

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: No checkpointing.

        Mutation failure leaves file in corrupted state
        with no automatic recovery.
        """
        assert self.temp_dir is not None, "setup() must be called before run_baseline()"
        file_path = self.temp_dir / "baseline_file.txt"

        result = self._simulate_mutation_with_failure(file_path, checkpoint_content=None)

        # Without checkpoint, recovery is impossible
        recovery_rate = 0.0 if result["failed"] else 1.0
        integrity_rate = 1.0 if result["data_integrity"] else 0.0

        self.log(f"Baseline failed: {result['failed']}")
        self.log(f"Baseline recovery rate: {recovery_rate:.0%}")
        self.log(f"Baseline data integrity: {integrity_rate:.0%}")

        return {
            "recovery_rate": recovery_rate,
            "data_integrity_rate": integrity_rate,
            "lines_preserved": result["lines_written"],
            "lines_lost": self.file_lines - result["lines_written"],
            "recovery_time_ms": 0,  # No recovery possible
            "has_checkpoint": False,
        }

    def run_ga(self) -> dict[str, Any]:
        """
        Grounded Agency: Checkpoint before mutation.

        Creates recovery point, attempts mutation, and
        rolls back on failure.
        """
        assert self.temp_dir is not None, "setup() must be called before run_ga()"
        file_path = self.temp_dir / "ga_file.txt"

        # Create checkpoint (GA approach)
        checkpoint_content = self.original_content
        checkpoint_hash = self.original_hash

        self.log("GA: Created checkpoint before mutation")

        result = self._simulate_mutation_with_failure(
            file_path, checkpoint_content=checkpoint_content
        )

        recovery_rate = 1.0 if result["recovered"] or not result["failed"] else 0.0
        integrity_rate = 1.0 if result["data_integrity"] else 0.0

        self.log(f"GA failed during mutation: {result['failed']}")
        self.log(f"GA recovered via rollback: {result['recovered']}")
        self.log(f"GA recovery rate: {recovery_rate:.0%}")
        self.log(f"GA data integrity: {integrity_rate:.0%}")
        self.log(f"GA recovery time: {result['recovery_time_ms']:.2f}ms")

        return {
            "recovery_rate": recovery_rate,
            "data_integrity_rate": integrity_rate,
            "lines_preserved": self.file_lines if result["data_integrity"] else 0,
            "lines_lost": 0 if result["data_integrity"] else self.file_lines,
            "recovery_time_ms": result["recovery_time_ms"],
            "has_checkpoint": True,
            "checkpoint_hash": checkpoint_hash,
        }

    def compare(
        self, baseline_result: dict[str, Any], ga_result: dict[str, Any]
    ) -> dict[str, float]:
        """Compare recovery rates and data integrity."""
        recovery_improvement = (
            ga_result["recovery_rate"] - baseline_result["recovery_rate"]
        )
        integrity_improvement = (
            ga_result["data_integrity_rate"] - baseline_result["data_integrity_rate"]
        )
        lines_saved = ga_result["lines_preserved"] - baseline_result["lines_preserved"]

        comparison = {
            "recovery_rate_improvement": recovery_improvement,
            "data_integrity_improvement": integrity_improvement,
            "lines_saved": lines_saved,
            "recovery_time_ms": ga_result["recovery_time_ms"],
        }

        self.log(f"Recovery improvement: +{recovery_improvement:.0%}")
        self.log(f"Integrity improvement: +{integrity_improvement:.0%}")
        self.log(f"Lines saved: {lines_saved}")

        return comparison

    def _cleanup(self) -> None:
        """Cleanup temporary files. Registered with atexit for reliability."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
