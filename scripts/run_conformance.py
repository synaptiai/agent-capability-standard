#!/usr/bin/env python3
"""Conformance test runner.

Runs the reference validator against each fixture ``workflow_catalog.yaml``
using the ``--catalog`` flag so the production catalog is never modified.

TEST-007: Uses tempfile.TemporaryDirectory for build output isolation
and signal handlers for cleanup safety.
"""

import json
import signal
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAL = ROOT / "tools" / "validate_workflows.py"
SUGGESTIONS_JSON = ROOT / "tools" / "validator_suggestions.json"
FIX = ROOT / "tests" / "fixtures"

EXPECT = json.loads((FIX / "EXPECTATIONS.json").read_text(encoding="utf-8"))


def run_fixture(name: str, path: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(VAL), "--catalog", str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _read_emitted_codes() -> set[str]:
    """Read error codes from the validator's suggestions JSON output.

    Returns an empty set if the file is missing or unreadable.
    Callers should use ``_clear_suggestions()`` before each fixture run
    to prevent stale data from a prior run.
    """
    if not SUGGESTIONS_JSON.exists():
        return set()
    try:
        data = json.loads(SUGGESTIONS_JSON.read_text(encoding="utf-8"))
        codes: set[str] = set()
        for err in data.get("structured_errors", []):
            code = err.get("code")
            if code:
                codes.add(code)
        return codes
    except (json.JSONDecodeError, KeyError):
        return set()


def _clear_suggestions() -> None:
    """Remove stale suggestions JSON before each fixture run."""
    if SUGGESTIONS_JSON.exists():
        SUGGESTIONS_JSON.unlink()


def main() -> None:
    # TEST-007: Use temporary directory for build output isolation.
    # This ensures conformance runs don't pollute the working directory
    # and cleanup happens automatically, even on signal interruption.
    with tempfile.TemporaryDirectory(prefix="conformance_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Install signal handler for clean shutdown
        def _signal_handler(signum: int, frame: types.FrameType | None) -> None:
            print(f"\nInterrupted by signal {signum}, cleaning up...")
            sys.exit(128 + signum)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        results = []
        failed = 0
        for name, meta in EXPECT.items():
            path = FIX / f"{name}.workflow_catalog.yaml"
            if not path.exists():
                print(f"Missing fixture: {path}")
                failed += 1
                continue
            _clear_suggestions()
            res = run_fixture(name, path)
            should_pass = meta.get("should_pass", False)
            if res["ok"] != should_pass:
                failed += 1
                print(
                    f"FAIL: {name} expected should_pass={should_pass} got ok={res['ok']}"
                )
                print(res["stdout"])
                print(res["stderr"])
            else:
                # Verify expected error codes if specified
                expected_codes = meta.get("expected_error_codes")
                if expected_codes and not res["ok"]:
                    emitted_codes = _read_emitted_codes()
                    missing = set(expected_codes) - emitted_codes
                    if missing:
                        failed += 1
                        print(
                            f"FAIL: {name} missing expected error codes: "
                            f"{sorted(missing)} (emitted: {sorted(emitted_codes)})"
                        )
                        results.append(res)
                        continue
                print(f"PASS: {name}")
            results.append(res)

        # Write results to temp dir first, then copy to build/
        results_file = tmp_path / "conformance_results.json"
        results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

        # Copy to persistent build dir only on success
        build_dir = ROOT / "build"
        build_dir.mkdir(exist_ok=True)
        (build_dir / "conformance_results.json").write_text(
            results_file.read_text(encoding="utf-8"), encoding="utf-8"
        )

    if failed:
        print(f"\nConformance FAILED ({failed} failures)")
        sys.exit(1)
    print("\nConformance PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
