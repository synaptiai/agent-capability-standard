#!/usr/bin/env python3
"""Domain profile validator (STANDARD v1.2 §5.21).

Every profile under ``schemas/profiles/`` (``profile_schema.yaml`` aside) is
loaded and checked by the core (``_core.Validator.check_profiles``), the one
implementation of §5.21.2 that the executor, the validator and the Python
adapter apply; every diagnostic it reports is a failure here, warnings
included. On top, the repository's own rules for its shipped profiles:

1) ``standard`` and ``ontology`` are present and name the current Standard
   (the newest ``spec/STANDARD-v*.md``) and ontology (``meta.version``)
2) the file is named after the profile's ``domain`` (``-`` may be written ``_``)
3) ``profile_schema.yaml`` loads and its ``schema.version`` is SemVer
4) SEC-009: a warning (not a failure) when ``trust_model_reviewed`` is not
   true

Usage:
- python3 tools/validate_profiles.py
- python3 tools/validate_profiles.py --verbose
- python3 tools/validate_profiles.py --profiles-dir <dir>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Direct import works when the package is installed; fall back to the source
# tree for a bare run from a checkout whose extension was built in place.
try:
    from grounded_agency import _core
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "schemas" / "profiles"
ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"
SCHEMA_FILE = "profile_schema.yaml"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def current_standard() -> str:
    """The newest Standard version with its own file."""

    def version(path: Path) -> tuple[int, ...]:
        return tuple(int(x) for x in path.stem.removeprefix("STANDARD-v").split("."))

    newest = max((ROOT / "spec").glob("STANDARD-v*.md"), key=version)
    return newest.stem.removeprefix("STANDARD-v")


def describe(d: dict[str, Any]) -> str:
    where = d.get("location", {})
    hint = f" ({d['suggestion']})" if d.get("suggestion") else ""
    return f"{d['code']} at {where.get('field')!r}: {d['message']}{hint}"


def check_profile(
    path: Path,
    profile: Any,
    validator: _core.Validator,
    versions: dict[str, str],
    errors: list[str],
    warnings: list[str],
) -> None:
    name = path.stem
    for d in validator.check_profiles([profile])["diagnostics"]:
        errors.append(f"[{name}] {describe(d)}")
    if not isinstance(profile, dict):
        return
    for member, expected in versions.items():
        if profile.get(member) != expected:
            what = "Standard" if member == "standard" else "ontology"
            errors.append(
                f"[{name}] '{member}' must be {expected!r}, the current {what} "
                f"version (a shipped profile cites it, §11.6); found "
                f"{profile.get(member)!r}"
            )
    domain = profile.get("domain")
    if isinstance(domain, str) and name not in (domain, domain.replace("-", "_")):
        errors.append(
            f"[{name}] the file is named after the domain: expected "
            f"{domain.replace('-', '_')}.yaml"
        )
    reviewed = profile.get("trust_model_reviewed")
    if reviewed is not True:
        warnings.append(
            f"[{name}] SEC-009: trust_model_reviewed is {reviewed!r}. Trust "
            f"weights may not reflect intentional calibration. Set "
            f"trust_model_reviewed: true after reviewing trust_weights."
        )


def check_schema_file(path: Path, errors: list[str]) -> None:
    try:
        doc = _core.load_yaml(str(path))
    except (OSError, ValueError) as e:
        errors.append(f"[{path.stem}] cannot be loaded: {e}")
        return
    meta = doc.get("schema") if isinstance(doc, dict) else None
    version = meta.get("version") if isinstance(meta, dict) else None
    if not isinstance(version, str) or not SEMVER.match(version):
        errors.append(f"[{path.stem}] schema.version {version!r} is not SemVer")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Validate the domain profiles (STANDARD v1.2 §5.21)"
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    ap.add_argument(
        "--profiles-dir",
        type=Path,
        default=PROFILES_DIR,
        help="Directory of the profiles (default: schemas/profiles)",
    )
    args = ap.parse_args()
    directory: Path = args.profiles_dir

    if not directory.exists():
        print(f"ERROR: Profiles directory not found: {directory}")
        sys.exit(1)

    validator = _core.Validator(str(ONTOLOGY), str(ROOT))
    ontology_version = str(_core.load_yaml(str(ONTOLOGY))["meta"]["version"])
    versions = {"standard": current_standard(), "ontology": ontology_version}

    errors: list[str] = []
    warnings: list[str] = []
    schema = directory / SCHEMA_FILE
    if schema.exists():
        check_schema_file(schema, errors)
    else:
        errors.append(f"[{SCHEMA_FILE}] is missing")

    paths = sorted(p for p in directory.glob("*.yaml") if p.name != SCHEMA_FILE)
    if not paths:
        print(f"WARNING: No profile files found in {directory}")
        sys.exit(0)
    for path in paths:
        if args.verbose:
            print(f"Validating: {path.stem}")
        try:
            profile = _core.load_yaml(str(path))
        except (OSError, ValueError) as e:
            errors.append(f"[{path.stem}] YAML load error: {e}")
            continue
        check_profile(path, profile, validator, versions, errors, warnings)

    if errors:
        print("PROFILE VALIDATION FAIL:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nValidated {len(paths)} profiles with {len(errors)} errors")
        sys.exit(1)
    if warnings:
        print(f"PROFILE VALIDATION PASS (with {len(warnings)} warnings):")
        for w in warnings:
            print(f"  ⚠ {w}")
    else:
        print(f"PROFILE VALIDATION PASS: {len(paths)} profiles validated")


if __name__ == "__main__":
    main()
