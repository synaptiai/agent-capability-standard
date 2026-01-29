#!/usr/bin/env python3
"""Skill reference validator: checks that file paths in SKILL.md files resolve to existing files.

Scans all SKILL.md files under skills/ for structured file path references
in dependency sections (Compatible schemas, References) and verifies they
exist in the repository. This prevents phantom references — paths to files
that were never created or have since been removed.

Validates:
1) Paths in "Compatible schemas" sections
2) Paths in "References" sections
3) Paths in "Bundled Scripts" / "Located at" sections

Allows:
- Cross-references in Workflow/Composition sections (shorthand pointers)
- Example/documentation paths in procedure text and code blocks
- URLs (http://, https://)

Usage:
- python3 tools/validate_skill_refs.py
- python3 tools/validate_skill_refs.py --verbose

"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

# Match backtick-quoted file paths with common extensions
PATH_REF_RE = re.compile(
    r"`((?:[\w./-]+/)?[\w.-]+\.(?:yaml|yml|md|py|json|sh)(?:#\S*)?)`"
)

# Sections where file references are structural dependencies
STRICT_SECTIONS = {
    "Compatible schemas:",
    "References:",
    "Located at:",
}

CODE_FENCE = "```"


def find_skill_files() -> list[Path]:
    """Find all SKILL.md files under skills/."""
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def parse_sections(lines: list[str]) -> list[Tuple[str, int, int]]:
    """Identify strict validation sections and their line ranges.

    Returns list of (section_name, start_line, end_line) tuples.
    """
    sections = []
    in_strict = False
    current_section = ""
    start_line = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check if we're entering a strict section
        for section_marker in STRICT_SECTIONS:
            if section_marker in stripped:
                if in_strict:
                    sections.append((current_section, start_line, i - 1))
                in_strict = True
                current_section = section_marker
                start_line = i
                break
        else:
            # Check if we've left the strict section (hit a new ## heading
            # or a blank line followed by non-list content)
            if in_strict:
                if stripped.startswith("## ") or stripped.startswith("# "):
                    sections.append((current_section, start_line, i - 1))
                    in_strict = False
                elif (
                    stripped == ""
                    and i + 1 < len(lines)
                    and not lines[i + 1].strip().startswith("- ")
                ):
                    sections.append((current_section, start_line, i))
                    in_strict = False

    if in_strict:
        sections.append((current_section, start_line, len(lines) - 1))

    return sections


def is_in_code_block(lines: list[str], line_idx: int) -> bool:
    """Check if a line is inside a fenced code block."""
    fence_count = 0
    for i in range(line_idx):
        if lines[i].strip().startswith(CODE_FENCE):
            fence_count += 1
    return fence_count % 2 == 1


def validate_skill(skill_path: Path, errors: list[str], verbose: bool) -> None:
    """Validate file references in structured dependency sections of a SKILL.md."""
    skill_name = skill_path.parent.name
    content = skill_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    sections = parse_sections(lines)

    for section_name, start, end in sections:
        for line_idx in range(start, min(end + 1, len(lines))):
            line = lines[line_idx]

            if is_in_code_block(lines, line_idx):
                continue

            for match in PATH_REF_RE.finditer(line):
                ref = match.group(1)
                ref_path = ref.split("#")[0]

                # Skip URLs
                if ref_path.startswith(("http://", "https://")):
                    continue

                # Skip CLAUDE.md
                if ref_path == "CLAUDE.md":
                    continue

                # Check repo root first, then skill-local
                resolved = ROOT / ref_path
                skill_relative = skill_path.parent / ref_path

                if resolved.exists():
                    if verbose:
                        print(f"  OK (repo-root): [{skill_name}] {ref}")
                elif skill_relative.exists():
                    if verbose:
                        print(f"  OK (skill-local): [{skill_name}] {ref}")
                else:
                    errors.append(
                        f"[{skill_name}] line {line_idx + 1}: "
                        f"reference `{ref}` in {section_name.strip(':')} "
                        f"does not resolve to an existing file"
                    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Validate file references in SKILL.md dependency sections"
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true", help="Show all checked references"
    )
    args = ap.parse_args()

    if not SKILLS_DIR.exists():
        print(f"ERROR: Skills directory not found: {SKILLS_DIR}")
        sys.exit(1)

    skill_files = find_skill_files()

    if not skill_files:
        print(f"WARNING: No SKILL.md files found in {SKILLS_DIR}")
        sys.exit(0)

    errors: List[str] = []
    validated_count = 0

    for skill_path in skill_files:
        if args.verbose:
            print(f"Validating: {skill_path.parent.name}")

        validate_skill(skill_path, errors, args.verbose)
        validated_count += 1

    if errors:
        print("SKILL REFERENCE VALIDATION FAIL:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nValidated {validated_count} skills with {len(errors)} errors")
        sys.exit(1)

    print(f"SKILL REFERENCE VALIDATION PASS: {validated_count} skills validated")


if __name__ == "__main__":
    main()
