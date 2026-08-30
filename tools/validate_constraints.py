#!/usr/bin/env python3
"""Validate that constraints.txt agrees with pyproject.toml.

``pyproject.toml`` declares the range each dependency supports;
``constraints.txt`` declares the single version CI installs. Two files stating
overlapping facts about the same package is the shape that has produced a
string of defects in this repo -- a value written twice with nothing asserting
the copies agree. This validator is the assertion.

It checks that every pin in constraints.txt:

1. names a package that pyproject.toml actually declares, and
2. falls inside the range pyproject.toml declares for it.

Without (2) a well-meaning bound like ``ruff>=0.17`` would silently make the
constraints file unsatisfiable, and the failure would surface as an opaque pip
resolution error in CI rather than here.

Exit status is 0 when the two files agree, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CONSTRAINTS = ROOT / "constraints.txt"

# "name==1.2.3", ignoring environment markers and trailing comments.
PIN_PATTERN = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*==\s*(?P<version>[^\s;#]+)",
)
# A single specifier such as ">=0.16" or "<0.17" from a requirement string.
SPEC_PATTERN = re.compile(r"(?P<op><=|>=|==|!=|~=|<|>)\s*(?P<version>[0-9][^,\s]*)")
REQ_NAME_PATTERN = re.compile(r"^\s*(?P<name>[A-Za-z0-9._-]+)")


def normalize(name: str) -> str:
    """PEP 503 normalized distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a release version into a comparable tuple.

    Only the numeric release segment is compared. Pre-release and local
    segments are dropped, which is sufficient here: the constraints file pins
    released tool versions.
    """
    numbers: list[int] = []
    for part in version.split("."):
        match = re.match(r"^(\d+)", part)
        if not match:
            break
        numbers.append(int(match.group(1)))
    return tuple(numbers)


def compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """Three-way compare two release tuples, zero-padding the shorter one."""
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    if padded_left < padded_right:
        return -1
    return 1 if padded_left > padded_right else 0


def satisfies(version: str, requirement: str) -> bool:
    """Whether *version* satisfies every specifier in *requirement*."""
    pinned = parse_version(version)
    for spec in SPEC_PATTERN.finditer(requirement):
        op = spec.group("op")
        bound = parse_version(spec.group("version"))
        result = compare(pinned, bound)
        if op == ">=" and result < 0:
            return False
        if op == ">" and result <= 0:
            return False
        if op == "<=" and result > 0:
            return False
        if op == "<" and result >= 0:
            return False
        if op == "==" and result != 0:
            return False
        if op == "!=" and result == 0:
            return False
    return True


def iter_declared_requirements(text: str) -> list[str]:
    """Yield every requirement string in pyproject's dependency arrays.

    Deliberately does not use ``tomllib``: that is stdlib only on 3.11+, and
    this project supports 3.10, so importing it would make the validator crash
    for part of its own supported range. The parse is narrow by design -- it
    reads the ``[project]`` and ``[project.optional-dependencies]`` tables and
    collects the quoted strings inside their arrays, which is all this check
    needs.
    """
    requirements: list[str] = []
    section = ""
    in_array = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith('"') else raw
        stripped = line.strip()

        header = re.match(r"^\[([^\]]+)\]$", stripped)
        if header:
            section = header.group(1)
            in_array = False
            continue

        relevant = section == "project" or section.endswith("optional-dependencies")
        if not relevant:
            continue

        if not in_array:
            # `dependencies = [` under [project], or `<extra> = [` under
            # [project.optional-dependencies].
            key = re.match(r"^([A-Za-z0-9_-]+)\s*=\s*\[", stripped)
            if key and (
                section.endswith("optional-dependencies")
                or key.group(1) == "dependencies"
            ):
                in_array = True
                stripped = stripped[stripped.index("[") + 1 :]
            else:
                continue

        if in_array:
            requirements.extend(re.findall(r'"([^"]+)"', stripped))
            if "]" in stripped:
                in_array = False

    return requirements


def collect_requirements() -> dict[str, list[str]]:
    """Map normalized package name to every requirement string declaring it."""
    requirements = iter_declared_requirements(PYPROJECT.read_text(encoding="utf-8"))

    by_name: dict[str, list[str]] = {}
    for requirement in requirements:
        match = REQ_NAME_PATTERN.match(requirement)
        if not match:
            continue
        by_name.setdefault(normalize(match.group("name")), []).append(requirement)
    return by_name


def main() -> int:
    if not CONSTRAINTS.exists():
        print(f"ERROR: {CONSTRAINTS.name} not found at {CONSTRAINTS}")
        return 1
    if not PYPROJECT.exists():
        print(f"ERROR: {PYPROJECT.name} not found at {PYPROJECT}")
        return 1

    declared = collect_requirements()
    errors: list[str] = []
    checked = 0

    for lineno, raw in enumerate(
        CONSTRAINTS.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.match(line)
        if not match:
            errors.append(
                f"{CONSTRAINTS.name}:{lineno}: not an exact pin: {line!r}. "
                "Every entry must be 'package==version' -- a range here would "
                "defeat the file's purpose."
            )
            continue

        name = normalize(match.group("name"))
        version = match.group("version")
        checked += 1

        requirements = declared.get(name)
        if not requirements:
            errors.append(
                f"{CONSTRAINTS.name}:{lineno}: '{name}' is pinned but not "
                f"declared in {PYPROJECT.name}. A constraint on a package "
                "nothing depends on is silently ignored by pip."
            )
            continue

        for requirement in requirements:
            if not satisfies(version, requirement):
                errors.append(
                    f"{CONSTRAINTS.name}:{lineno}: '{name}=={version}' is "
                    f"outside the range {PYPROJECT.name} declares "
                    f"({requirement!r}). pip would fail to resolve."
                )

    if errors:
        print(f"FAIL: {len(errors)} constraint problem(s)\n")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"OK: {checked} pin(s) in {CONSTRAINTS.name} agree with {PYPROJECT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
