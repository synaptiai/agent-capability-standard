#!/usr/bin/env python3
"""Conformance test runner.

Runs the reference validator against each fixture ``workflow_catalog.yaml``
using the ``--catalog`` flag so the production catalog is never modified.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAL  = ROOT / "tools" / "validate_workflows.py"
FIX  = ROOT / "tests"

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

def main() -> None:
    results = []
    failed = 0
    for name, meta in EXPECT.items():
        path = FIX / f"{name}.workflow_catalog.yaml"
        if not path.exists():
            print(f"Missing fixture: {path}")
            failed += 1
            continue
        res = run_fixture(name, path)
        should_pass = meta.get("should_pass", False)
        if res["ok"] != should_pass:
            failed += 1
            print(f"FAIL: {name} expected should_pass={should_pass} got ok={res['ok']}")
            print(res["stdout"])
            print(res["stderr"])
        else:
            print(f"PASS: {name}")
        results.append(res)

    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    (build_dir / "conformance_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if failed:
        print(f"\nConformance FAILED ({failed} failures)")
        sys.exit(1)
    print("\nConformance PASSED")
    sys.exit(0)

if __name__ == "__main__":
    main()
