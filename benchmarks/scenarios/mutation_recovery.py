"""
Scenario 2: Mutation Failure Recovery

Tests whether Grounded Agency's checkpoint/rollback pattern
enables recovery from failed mutations.

Setup:
- Original file with known content
- Mutation operation that fails partway through
- Baseline has no checkpointing
- GA takes a checkpoint with CheckpointTracker, whose snapshot store
  copies the file, and restores it with restore_checkpoint

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

from grounded_agency.state.checkpoint_tracker import CheckpointTracker
from grounded_agency.state.snapshots import FileSnapshotStore

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
        self.original_hash = hashlib.sha256(self.original_content.encode()).hexdigest()

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

    def _simulate_mutation_with_failure(self, file_path: Path) -> dict[str, Any]:
        """
        Run a mutation of ``file_path`` (already holding the original
        content) that fails partway through, leaving the file in a partial
        state.

        Returns:
            Whether the mutation failed and how many lines it wrote
        """
        start_time = time.time()
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

        return {
            "failed": failed,
            "lines_written": lines_written,
            "elapsed_ms": (time.time() - start_time) * 1000,
        }

    def _on_disk_hash(self, file_path: Path) -> str:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    def run_baseline(self) -> dict[str, Any]:
        """
        Baseline: No checkpointing.

        Mutation failure leaves file in corrupted state
        with no automatic recovery.
        """
        if self.temp_dir is None:
            raise RuntimeError("setup() must be called before run_baseline()")
        work = self.temp_dir / "baseline"
        work.mkdir(exist_ok=True)
        file_path = work / "file.txt"
        file_path.write_text(self.original_content)

        result = self._simulate_mutation_with_failure(file_path)
        intact = self._on_disk_hash(file_path) == self.original_hash

        # Without checkpoint, recovery is impossible
        recovery_rate = 1.0 if intact else 0.0
        integrity_rate = 1.0 if intact else 0.0

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
        Grounded Agency: checkpoint before the mutation, restore after it
        fails, both through the shipped ``CheckpointTracker``.

        The tracker's snapshot store copies the file when the checkpoint
        is taken; ``restore_checkpoint`` puts it back and returns a
        ``Restore``. Recovery counts only when the ``Restore`` says the
        file was restored and the file on disk hashes to the original.
        """
        if self.temp_dir is None:
            raise RuntimeError("setup() must be called before run_ga()")
        work = self.temp_dir / "ga"
        work.mkdir(exist_ok=True)
        file_path = work / "file.txt"
        file_path.write_text(self.original_content)

        snapshots = FileSnapshotStore(root=work, store_dir=self.temp_dir / "ga_store")
        tracker = CheckpointTracker(
            checkpoint_dir=self.temp_dir / "ga_checkpoints", snapshots=snapshots
        )

        checkpoint_id = tracker.create_checkpoint(
            scope=[file_path.name],
            reason="Before mutation benchmark",
        )
        if not tracker.has_valid_checkpoint():
            raise RuntimeError("Checkpoint should be valid after creation")
        manifest = snapshots.manifest(checkpoint_id)
        if manifest is None or file_path.name not in manifest["files"]:
            raise RuntimeError("The checkpoint did not capture the file")

        self.log(f"GA: Created checkpoint {checkpoint_id[:20]}... before mutation")

        # The mutation uses the checkpoint up (one checkpoint per gated call).
        consumed_id = tracker.consume_checkpoint()
        if consumed_id != checkpoint_id:
            raise RuntimeError("Consumed checkpoint should match created")
        if tracker.has_valid_checkpoint():
            raise RuntimeError("No valid checkpoint should remain after consumption")

        result = self._simulate_mutation_with_failure(file_path)
        damaged = self._on_disk_hash(file_path) != self.original_hash

        restore = None
        recovery_time_ms = 0.0
        if result["failed"]:
            recovery_start = time.time()
            # A rollback uses no checkpoint, and works on a used one.
            restore = tracker.restore_checkpoint(checkpoint_id)
            recovery_time_ms = (time.time() - recovery_start) * 1000

        intact = self._on_disk_hash(file_path) == self.original_hash
        restored = restore is not None and restore.restored and not restore.unrestored
        recovered = restored and intact
        recovery_rate = 1.0 if recovered or not result["failed"] else 0.0
        integrity_rate = 1.0 if intact else 0.0

        self.log(f"GA failed during mutation: {result['failed']}")
        self.log(f"GA file damaged before restore: {damaged}")
        self.log(f"GA Restore: {restore}")
        self.log(f"GA recovery rate: {recovery_rate:.0%}")
        self.log(f"GA data integrity: {integrity_rate:.0%}")
        self.log(f"GA recovery time: {recovery_time_ms:.2f}ms")

        return {
            "recovery_rate": recovery_rate,
            "data_integrity_rate": integrity_rate,
            "lines_preserved": self.file_lines if intact else 0,
            "lines_lost": 0 if intact else self.file_lines,
            "recovery_time_ms": recovery_time_ms,
            "has_checkpoint": True,
            "damaged_before_restore": damaged,
            "restore_restored": bool(restore and restore.restored),
            "restore_unrestored": len(restore.unrestored) if restore else 0,
            "restore_changes_reverted": len(restore.changes_reverted) if restore else 0,
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
