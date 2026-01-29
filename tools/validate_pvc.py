#!/usr/bin/env python3
"""
Validate PVC (Perspective Validation Checklist) review reports.

This validator checks:
1) Report presence and YAML structure
2) Allowed score values (PASS / PARTIAL / FAIL / N/A)
3) Required fields and minimal shape
4) Basic evidence reference sanity (file paths exist when using file:)
5) Optional CI rule: if "critical paths" change, a PVC report must change too

Usage:
  python tools/validate_pvc.py
  python tools/validate_pvc.py --diff-base <git-sha>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PVC_DIR = ROOT / "docs" / "reviews" / "pvc"

ALLOWED_STATUSES = {"PASS", "PARTIAL", "FAIL", "N/A"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}
ALLOWED_ARTIFACTS = {"doc", "workflow", "policy", "hook", "test", "benchmark", "code"}

REQUIRED_SCORE_KEYS = [
    "HF-101",
    "HF-102",
    "HF-103",
    "ORG-201",
    "GOV-202",
    "ECON-301",
    "ECON-302",
    "SEC-401",
    "SEC-402",
    "CTRL-501",
    "ASSUR-601",
    "ASSUR-602",
    "DG-701",
    "ETH-801",
    "ECO-901",
]

CRITICAL_PREFIXES = (
    "schemas/",
    "hooks/",
    "grounded_agency/",
    "skills/",
    "tools/",
    "spec/",
)
CRITICAL_EXACT_EXEMPTIONS = {
    "tools/validate_pvc.py",
}


def _err(path: Path, message: str) -> str:
    rel = path.relative_to(ROOT) if path.is_absolute() else path
    return f"{rel}: {message}"


def _extract_file_ref_path(evidence_ref: str) -> str | None:
    if not evidence_ref.startswith("file:"):
        return None
    raw = evidence_ref[len("file:") :]
    raw = raw.split("#", 1)[0]

    # Support `file:path:line` style by stripping a trailing `:<digits>`
    m = re.match(r"^(?P<path>.+?)(?::(?P<line>\d+))?$", raw)
    if not m:
        return raw.strip() or None
    return (m.group("path") or "").strip() or None


def _validate_report(path: Path, data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return [_err(path, "Report must be a YAML mapping/object at top-level.")]

    required_top = [
        "target",
        "context",
        "stakeholders",
        "assumptions",
        "evidence",
        "scorecard",
        "actions",
    ]
    for key in required_top:
        if key not in data:
            errors.append(_err(path, f"Missing required top-level key: {key!r}."))

    target = data.get("target")
    if target is not None and not isinstance(target, str):
        errors.append(_err(path, "Field 'target' must be a string."))

    context = data.get("context")
    if context is not None and not isinstance(context, dict):
        errors.append(_err(path, "Field 'context' must be a mapping/object."))
    else:
        for key in ("domain", "deployment", "risk_tier"):
            if not isinstance((context or {}).get(key), str):
                errors.append(_err(path, f"Field 'context.{key}' must be a string."))

    stakeholders = data.get("stakeholders")
    if stakeholders is not None and not (
        isinstance(stakeholders, list) and all(isinstance(x, str) for x in stakeholders)
    ):
        errors.append(_err(path, "Field 'stakeholders' must be a list of strings."))

    assumptions = data.get("assumptions")
    if assumptions is not None and not (
        isinstance(assumptions, list) and all(isinstance(x, str) for x in assumptions)
    ):
        errors.append(_err(path, "Field 'assumptions' must be a list of strings."))

    evidence = data.get("evidence")
    if evidence is not None and not (
        isinstance(evidence, list) and all(isinstance(x, str) for x in evidence)
    ):
        errors.append(_err(path, "Field 'evidence' must be a list of strings."))
    else:
        for ev in evidence or []:
            file_path = _extract_file_ref_path(ev)
            if file_path:
                candidate = (ROOT / file_path).resolve()
                if not candidate.is_relative_to(ROOT):
                    errors.append(
                        _err(path, f"Evidence reference escapes repository root: {ev!r}.")
                    )
                elif not candidate.exists():
                    errors.append(
                        _err(path, f"Evidence reference points to missing file: {ev!r}.")
                    )

    scorecard = data.get("scorecard")
    if scorecard is not None and not isinstance(scorecard, dict):
        errors.append(_err(path, "Field 'scorecard' must be a mapping/object."))
    else:
        for key in REQUIRED_SCORE_KEYS:
            if key not in (scorecard or {}):
                errors.append(_err(path, f"Missing scorecard key: {key!r}."))
        for k, v in (scorecard or {}).items():
            if not isinstance(v, str) or v not in ALLOWED_STATUSES:
                errors.append(
                    _err(
                        path,
                        f"Invalid score for {k!r}: {v!r} (allowed: {sorted(ALLOWED_STATUSES)}).",
                    )
                )

    actions = data.get("actions")
    if actions is not None and not isinstance(actions, list):
        errors.append(_err(path, "Field 'actions' must be a list."))
    else:
        for i, action in enumerate(actions or []):
            if not isinstance(action, dict):
                errors.append(_err(path, f"Action[{i}] must be a mapping/object."))
                continue
            for req in ("id", "priority", "fix", "artifact", "owner"):
                if req not in action:
                    errors.append(_err(path, f"Action[{i}] missing key: {req!r}."))
            if isinstance(action.get("priority"), str) and action["priority"] not in ALLOWED_PRIORITIES:
                errors.append(
                    _err(
                        path,
                        f"Action[{i}].priority must be one of {sorted(ALLOWED_PRIORITIES)}.",
                    )
                )
            if isinstance(action.get("artifact"), str) and action["artifact"] not in ALLOWED_ARTIFACTS:
                errors.append(
                    _err(
                        path,
                        f"Action[{i}].artifact must be one of {sorted(ALLOWED_ARTIFACTS)}.",
                    )
                )

    return errors


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _git_changed_files(diff_base: str) -> list[str] | None:
    if not diff_base or diff_base == "0000000000000000000000000000000000000000":
        return None
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{diff_base}..HEAD"],
            cwd=ROOT,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Warning: git diff failed (exit {e.returncode}); skipping critical-path gate.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: unexpected error running git diff: {e}; skipping critical-path gate.", file=sys.stderr)
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def _is_critical_change(path: str) -> bool:
    if path in CRITICAL_EXACT_EXEMPTIONS:
        return False
    return path.startswith(CRITICAL_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--diff-base",
        help="Optional git SHA to diff against; when provided, requires PVC report updates for critical-path changes.",
        default="",
    )
    args = parser.parse_args()

    if not PVC_DIR.exists():
        print(f"PVC directory missing: {PVC_DIR}", file=sys.stderr)
        return 1

    report_paths = sorted(
        [p for p in PVC_DIR.glob("*.y*ml") if p.is_file() and p.name != "README.md"]
    )
    if not report_paths:
        print("No PVC reports found in docs/reviews/pvc/.", file=sys.stderr)
        if args.diff_base:
            # In CI mode, absence of reports is only an error if critical paths changed
            changed = _git_changed_files(args.diff_base)
            if changed and any(_is_critical_change(p) for p in changed):
                return 1
            print("No critical-path changes detected; skipping.", file=sys.stderr)
            return 0
        return 0

    # Optional CI rule: require report update if critical paths changed
    changed = _git_changed_files(args.diff_base)
    if changed is not None:
        critical_changed = any(_is_critical_change(p) for p in changed)
        pvc_changed = any(p.startswith("docs/reviews/pvc/") and p.endswith((".yaml", ".yml")) for p in changed)
        if critical_changed and not pvc_changed:
            print(
                "PVC required: critical paths changed but no PVC report was updated.\n"
                "Add or update a report in `docs/reviews/pvc/`.",
                file=sys.stderr,
            )
            return 1

    errors: list[str] = []
    for path in report_paths:
        try:
            data = _read_yaml(path)
        except Exception as e:
            errors.append(_err(path, f"Failed to parse YAML: {e}"))
            continue
        errors.extend(_validate_report(path, data))

    if errors:
        print("PVC VALIDATION FAIL", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        return 1

    print("PVC VALIDATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

