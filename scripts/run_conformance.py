#!/usr/bin/env python3
"""Conformance test runner.

Runs the reference validator against each fixture `workflow_catalog.yaml`.

The validator expects fixed paths relative to:
`reference/claude_world_modeling_skill_system`,
so we temporarily swap `workflows/workflow_catalog.yaml` with fixture content.
"""

import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF  = ROOT / "reference" / "claude_world_modeling_skill_system"
CAT  = REF / "workflows" / "workflow_catalog.yaml"
VAL  = REF / "tools" / "validate_workflows.py"
FIX  = ROOT / "conformance_fixtures"

EXPECT = json.loads((FIX / "EXPECTATIONS.json").read_text(encoding="utf-8"))

def run_fixture(name: str, path: Path) -> dict:
    backup = CAT.read_text(encoding="utf-8")
    try:
        CAT.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(VAL), "--emit-patch"], cwd=str(REF), capture_output=True, text=True)
        ok = proc.returncode == 0
        return {"name": name, "ok": ok, "stdout": proc.stdout, "stderr": proc.stderr}
    finally:
        CAT.write_text(backup, encoding="utf-8")

def main():
    results=[]
    failed=0
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

    (ROOT / "conformance_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if failed:
        print(f"\nConformance FAILED ({failed} failures)")
        sys.exit(1)
    print("\nConformance PASSED")
    sys.exit(0)

if __name__ == "__main__":
    main()
