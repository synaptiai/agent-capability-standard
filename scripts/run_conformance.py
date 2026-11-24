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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VAL = ROOT / "tools" / "validate_workflows.py"
FIX = ROOT / "tests" / "fixtures"

EXPECT = json.loads((FIX / "EXPECTATIONS.json").read_text(encoding="utf-8"))


def run_fixture(
    name: str, path: Path, suggestions: Path, meta: dict | None = None
) -> dict:
    """Validate one fixture, writing its suggestions JSON to ``suggestions``
    (one file per run, so concurrent runs and stale output cannot mix). The
    expectation's ``profiles`` are repository-relative domain profiles to
    validate it with (STANDARD v1.2 §5.21); its ``catalogs`` (further
    catalogs of the catalog set) and ``agents`` (agent manifests) are paths
    relative to ``tests/fixtures/`` (STANDARD v1.2 §10.3)."""
    extra: list[str] = []
    for p in (meta or {}).get("profiles", []):
        extra += ["--profile", str(ROOT / p)]
    for c in (meta or {}).get("catalogs", []):
        extra += ["--with-catalog", str(FIX / c)]
    for a in (meta or {}).get("agents", []):
        extra += ["--agents", str(FIX / a)]
    proc = subprocess.run(
        [
            sys.executable,
            str(VAL),
            "--catalog",
            str(path),
            "--suggestions-out",
            str(suggestions),
            *extra,
        ],
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


def _read_emitted_codes(suggestions: Path, key: str) -> set[str]:
    """Diagnostic codes in a run's suggestions JSON: errors with
    ``key="structured_errors"``, warnings with ``key="structured_warnings"``.
    Empty if the file is missing or unreadable."""
    try:
        data = json.loads(suggestions.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return set()
    return {d["code"] for d in data.get(key, []) if d.get("code")}


def _read_locations(suggestions: Path) -> list[tuple[str, dict[str, Any]]]:
    """The ``(code, location)`` of every diagnostic of a run (STANDARD v1.2
    §9.8)."""
    try:
        data = json.loads(suggestions.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return []
    found = []
    for key in ("structured_errors", "structured_warnings"):
        for d in data.get(key, []):
            if d.get("code"):
                found.append((d["code"], d.get("location", {})))
    return found


def _located(
    expected: dict[str, Any], located: list[tuple[str, dict[str, Any]]]
) -> bool:
    """Whether a diagnostic has the expected ``code`` and every other member
    the expectation gives (its ``path``, or for a finding with no ``path``
    its ``catalog``, ``workflow`` and ``field``) in its location."""
    members = {k: v for k, v in expected.items() if k != "code"}
    return any(
        code == expected["code"] and all(loc.get(k) == v for k, v in members.items())
        for code, loc in located
    )


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
            suggestions = tmp_path / f"{name}.suggestions.json"
            res = run_fixture(name, path, suggestions, meta)
            should_pass = meta.get("should_pass", False)
            if not suggestions.is_file():
                # No report means the validator did not run to the end.
                failed += 1
                print(f"FAIL: {name} wrote no report")
                print(res["stdout"])
                print(res["stderr"])
            elif res["ok"] != should_pass:
                failed += 1
                print(
                    f"FAIL: {name} expected should_pass={should_pass} got ok={res['ok']}"
                )
                print(res["stdout"])
                print(res["stderr"])
            else:
                # The listed codes must be exactly the codes emitted: a
                # fixture that also trips unrelated checks does not isolate
                # what it tests. An absent list means none may be emitted.
                missing_msgs = []
                for kind, key, applies in (
                    ("error", "structured_errors", not res["ok"]),
                    ("warning", "structured_warnings", True),
                ):
                    if not applies:
                        continue
                    emitted = _read_emitted_codes(suggestions, key)
                    expected = set(meta.get(f"expected_{kind}_codes", []))
                    if emitted != expected:
                        missing_msgs.append(
                            f"expected {kind} codes {sorted(expected)}, "
                            f"emitted {sorted(emitted)}"
                        )
                # Each expected location must be among the diagnostics.
                located = _read_locations(suggestions)
                for loc in meta.get("expected_locations", []):
                    if not _located(loc, located):
                        missing_msgs.append(f"expected {loc!r}, located {located}")
                if missing_msgs:
                    failed += 1
                    print(f"FAIL: {name} " + "; ".join(missing_msgs))
                    results.append(res)
                    continue
                print(f"PASS: {name}")
            results.append(res)

        # Write results to temp dir first, then copy to build/
        results_file = tmp_path / "conformance_results.json"
        results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

        # Copy to the persistent build dir, pass or fail
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
