#!/usr/bin/env python3
"""Canonical schema validator: validates the five schemas designated by §6.1.

STANDARD-v1.0.0 §6.1 designates five canonical schemas that conformant
implementations depend on. Until issue #107 no validator covered any of them,
so every defect in them shipped through a green CI -- see #105 (a decay formula
inconsistent with its own field name, and a benchmark fixture drifted from the
schema it mirrors) and #106 (a floor declared, cited by compliance artifacts as
an implemented control, and read by nothing).

Validates:
1) Every §6.1 schema exists, parses, and carries the shared schema header
2) STANDARD §6.2 -- canonical events declare every MUST field as required
3) STANDARD §6.3 -- world state declares every MUST field as required
4) authority_trust_model internal consistency (source symmetry, decay model)
5) identity_resolution_policy threshold ordering and weight ranges
6) entity_taxonomy id convention
7) Cross-file agreement between the trust model and the benchmark fixture
8) Skill reference/ copies of a canonical schema match their source

Usage:
- python3 tools/validate_canonical_schemas.py
- python3 tools/validate_canonical_schemas.py --verbose

"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from yaml_util import YAMLSizeExceededError, safe_yaml_load

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMAS_DIR = ROOT / "schemas"
DEFAULT_SKILLS_DIR = ROOT / "skills"
TRUST_FIXTURE = ROOT / "benchmarks" / "fixtures" / "mock_apis.json"


# -------------------- Schema Constants --------------------

# STANDARD-v1.0.0 §6.1 Required Schema Files
CANONICAL_SCHEMAS = [
    "world_state_schema",
    "event_schema",
    "entity_taxonomy",
    "authority_trust_model",
    "identity_resolution_policy",
]

REQUIRED_HEADER_FIELDS = ["name", "version", "description"]

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
ISO_DAYS_PATTERN = re.compile(r"^P(\d+)D$")
# `exp(` as a call, not as a substring of an identifier such as `regexp(`.
EXP_CALL_PATTERN = re.compile(r"(?<![A-Za-z0-9_])exp\s*\(")

# STANDARD §6.2 Observation Requirements -- canonical-event namespace
EVENT_REQUIRED_FIELDS = [
    "event_id",
    "timestamp",
    "source",
    "event_type",
    "raw",
    "canonical",
    "anchors",
    "provenance",
]

# STANDARD §6.3 World State Requirements
WORLD_STATE_REQUIRED_FIELDS = [
    "entities",
    "relationships",
    "state_variables",
    "observations",
    "transition_rules",
    "actions",
    "indexes",
]
WORLD_STATE_META_REQUIRED_FIELDS = [
    "world_id",
    "as_of",
    "timezone",
    "version_id",
    "lineage",
]

# identity_resolution_policy thresholds, strictly descending
ALIAS_THRESHOLD_ORDER = [
    "auto_merge",
    "suggest_merge",
    "no_merge",
    "force_split_review",
]


# -------------------- Validation Functions --------------------


def _display_path(path: Path) -> str:
    """Repo-relative when possible; absolute otherwise (e.g. a test fixture)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_header(schema: dict[str, Any], errors: list[str], name: str) -> None:
    """Every canonical schema carries a `schema:` header block."""
    header = schema.get("schema")
    if not isinstance(header, dict):
        errors.append(f"[{name}] Missing or malformed top-level 'schema' header")
        return

    for field in REQUIRED_HEADER_FIELDS:
        if not header.get(field):
            errors.append(f"[{name}] schema.{field} is missing or empty")

    version = header.get("version")
    if isinstance(version, str) and not VERSION_PATTERN.match(version):
        errors.append(f"[{name}] schema.version '{version}' is not semantic versioning")


def validate_event_schema(schema: dict[str, Any], errors: list[str], name: str) -> None:
    """STANDARD §6.2: canonical events declare every MUST field as required."""
    event = schema.get("event")
    if not isinstance(event, dict):
        errors.append(f"[{name}] Missing top-level 'event' object")
        return

    required = set(event.get("required") or [])
    properties = set((event.get("properties") or {}).keys())

    for field in EVENT_REQUIRED_FIELDS:
        if field not in properties:
            errors.append(
                f"[{name}] STANDARD §6.2 requires '{field}'; not declared in "
                f"event.properties"
            )
        elif field not in required:
            errors.append(
                f"[{name}] STANDARD §6.2 requires '{field}'; declared but absent "
                f"from event.required"
            )


def validate_world_state_schema(
    schema: dict[str, Any], errors: list[str], name: str
) -> None:
    """STANDARD §6.3: world state declares every MUST field as required."""
    world_state = schema.get("world_state")
    if not isinstance(world_state, dict):
        errors.append(f"[{name}] Missing top-level 'world_state' object")
        return

    required = set(world_state.get("required") or [])
    for field in WORLD_STATE_REQUIRED_FIELDS:
        if field not in required:
            errors.append(
                f"[{name}] STANDARD §6.3 requires '{field}'; absent from "
                f"world_state.required"
            )

    meta = (world_state.get("properties") or {}).get("meta")
    if not isinstance(meta, dict):
        errors.append(f"[{name}] world_state.properties.meta is missing")
        return

    meta_required = set(meta.get("required") or [])
    meta_properties = set((meta.get("properties") or {}).keys())
    for field in WORLD_STATE_META_REQUIRED_FIELDS:
        if field not in meta_properties:
            errors.append(
                f"[{name}] STANDARD §6.3 requires 'meta.{field}'; not declared"
            )
        elif field not in meta_required:
            errors.append(
                f"[{name}] STANDARD §6.3 requires 'meta.{field}'; declared but "
                f"absent from meta.required"
            )


def validate_trust_model(schema: dict[str, Any], errors: list[str], name: str) -> None:
    """Internal consistency of the authority trust model."""
    ranking = schema.get("source_ranking") or {}
    weights = ranking.get("weights") or {}
    order = ranking.get("default_order") or []

    if not weights:
        errors.append(f"[{name}] source_ranking.weights is missing or empty")
        return

    for source in order:
        if source not in weights:
            errors.append(
                f"[{name}] source_ranking.default_order lists '{source}' with no "
                f"entry in weights"
            )
    for source in weights:
        if source not in order:
            errors.append(
                f"[{name}] source_ranking.weights defines '{source}' with no "
                f"entry in default_order"
            )

    for source, weight in weights.items():
        if not isinstance(weight, int | float) or not 0.0 <= weight <= 1.0:
            errors.append(
                f"[{name}] source_ranking.weights['{source}'] = {weight!r} is not "
                f"a number in [0.0, 1.0]"
            )

    # Every source named as a field authority must be a known source.  This is
    # the check that would have caught the NIST profile citing an
    # `unverified: 0.20` source that never existed (issue #105).
    for entry in schema.get("field_authority", {}).get("examples") or []:
        field = entry.get("field", "<unnamed>")
        for source in entry.get("authorities") or []:
            if source not in weights:
                errors.append(
                    f"[{name}] field_authority['{field}'] names unknown source "
                    f"'{source}'"
                )

    decay = schema.get("decay_model") or {}
    half_life = decay.get("half_life")
    half_life_match = (
        ISO_DAYS_PATTERN.match(half_life) if isinstance(half_life, str) else None
    )
    if half_life_match is None:
        errors.append(
            f"[{name}] decay_model.half_life {half_life!r} is not an ISO-8601 "
            f"day duration (P<n>D)"
        )
    elif int(half_life_match.group(1)) < 1:
        # `0.5 ** (age / 0)` raises ZeroDivisionError, and the loader in
        # conflicting_sources.py evaluates it at import time (issue #107).
        errors.append(
            f"[{name}] decay_model.half_life {half_life!r} must be at least one "
            f"day; a zero half-life divides by zero in the decay curve"
        )

    min_trust = decay.get("min_trust")
    if min_trust is not None and (
        not isinstance(min_trust, int | float) or not 0.0 <= min_trust <= 1.0
    ):
        errors.append(
            f"[{name}] decay_model.min_trust = {min_trust!r} is not a number in "
            f"[0.0, 1.0]"
        )

    # The decay must be a true half-life, not an exponential time constant.
    # `exp(-age/half_life)` returns 0.368 at age == half_life (issue #105).
    recency = str(
        (schema.get("conflict_resolution_function") or {}).get("recency_factor", "")
    )
    if EXP_CALL_PATTERN.search(recency):
        errors.append(
            f"[{name}] conflict_resolution_function.recency_factor {recency!r} "
            f"uses exp(); a true half-life returns 0.5 at age == half_life. Use "
            f"0.5 ** (age/half_life)."
        )


def validate_identity_policy(
    schema: dict[str, Any], errors: list[str], name: str
) -> None:
    """Alias thresholds are ordered and feature weights are in range."""
    scoring = schema.get("alias_confidence_scoring") or {}

    for feature in scoring.get("features") or []:
        weight = feature.get("weight")
        fname = feature.get("name", "<unnamed>")
        if not isinstance(weight, int | float) or not 0.0 <= weight <= 1.0:
            errors.append(
                f"[{name}] alias feature '{fname}' weight {weight!r} is not a "
                f"number in [0.0, 1.0]"
            )

    thresholds = scoring.get("thresholds") or {}
    present = [t for t in ALIAS_THRESHOLD_ORDER if t in thresholds]
    for higher, lower in zip(present, present[1:], strict=False):
        if not thresholds[higher] > thresholds[lower]:
            errors.append(
                f"[{name}] alias thresholds must strictly descend: "
                f"{higher}={thresholds[higher]} is not greater than "
                f"{lower}={thresholds[lower]}"
            )


def validate_entity_taxonomy(
    schema: dict[str, Any], errors: list[str], name: str
) -> None:
    """Entity IDs declare a hierarchical namespace convention (§7.1)."""
    convention = schema.get("id_convention") or {}
    fmt = convention.get("format")
    if not isinstance(fmt, str) or "<" not in fmt:
        errors.append(
            f"[{name}] id_convention.format {fmt!r} does not declare a "
            f"placeholder convention"
        )
    if not convention.get("examples"):
        errors.append(f"[{name}] id_convention.examples is missing or empty")
    if not schema.get("classes"):
        errors.append(f"[{name}] classes is missing or empty")


def validate_trust_fixture_sync(schema: dict[str, Any], errors: list[str]) -> None:
    """The benchmark fixture must not drift from the trust model (issue #105)."""
    if not TRUST_FIXTURE.exists():
        return

    try:
        fixture = json.loads(TRUST_FIXTURE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"[mock_apis.json] Could not read fixture: {exc}")
        return

    decay = schema.get("decay_model") or {}
    temporal = fixture.get("temporal_decay") or {}
    label = "authority_trust_model <-> mock_apis.json"

    match = ISO_DAYS_PATTERN.match(str(decay.get("half_life", "")))
    if match:
        expected_hours = int(match.group(1)) * 24
        actual_hours = temporal.get("half_life_hours")
        if actual_hours != expected_hours:
            errors.append(
                f"[{label}] half_life_hours = {actual_hours!r}, expected "
                f"{expected_hours} from half_life={decay.get('half_life')!r}"
            )

    if "min_trust" in decay and temporal.get("min_weight") != decay["min_trust"]:
        errors.append(
            f"[{label}] min_weight = {temporal.get('min_weight')!r}, expected "
            f"{decay['min_trust']!r} from decay_model.min_trust"
        )

    fixture_weights = fixture.get("trust_weights") or {}
    schema_weights = (schema.get("source_ranking") or {}).get("weights") or {}
    for source, weight in fixture_weights.items():
        if source not in schema_weights:
            errors.append(f"[{label}] fixture defines unknown source '{source}'")
        elif schema_weights[source] != weight:
            errors.append(
                f"[{label}] '{source}' weight {weight!r} does not match schema "
                f"weight {schema_weights[source]!r}"
            )


def validate_vendored_copies(
    schemas_dir: Path, skills_dir: Path, errors: list[str]
) -> None:
    """Skill reference/ copies of a canonical schema must match the source.

    `sync_skill_schemas.py` only bundles transitive dependencies into skills
    that have a `reference/workflow_catalog.yaml`, so a copy in a skill without
    one is unreachable by that tool and can drift unnoticed -- as
    `skills/receive/reference/event_schema.yaml` did (issue #107).
    """
    for name in CANONICAL_SCHEMAS:
        source = schemas_dir / f"{name}.yaml"
        if not source.exists():
            continue

        try:
            expected = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"[{name}] Could not read {_display_path(source)}: {exc}")
            continue

        for copy in sorted(skills_dir.glob(f"*/reference/{name}.yaml")):
            try:
                actual = copy.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(
                    f"[{name}] Could not read {_display_path(copy)}: {exc}"
                )
                continue

            if actual != expected:
                errors.append(
                    f"[{name}] vendored copy {_display_path(copy)} has drifted "
                    f"from schemas/{name}.yaml; run "
                    f"python tools/sync_skill_schemas.py"
                )


PER_SCHEMA_VALIDATORS = {
    "event_schema": validate_event_schema,
    "world_state_schema": validate_world_state_schema,
    "authority_trust_model": validate_trust_model,
    "identity_resolution_policy": validate_identity_policy,
    "entity_taxonomy": validate_entity_taxonomy,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the five canonical schemas designated by §6.1"
    )
    parser.add_argument("--verbose", action="store_true", help="Print each schema")
    parser.add_argument(
        "--schemas-dir",
        default=None,
        help=(
            "Override the schemas directory. Lets tests validate a fixture copy "
            "instead of mutating tracked files."
        ),
    )
    parser.add_argument(
        "--skills-dir",
        default=None,
        help="Override the skills directory searched for vendored copies.",
    )
    args = parser.parse_args()

    schemas_dir = Path(args.schemas_dir) if args.schemas_dir else DEFAULT_SCHEMAS_DIR
    skills_dir = Path(args.skills_dir) if args.skills_dir else DEFAULT_SKILLS_DIR

    errors: list[str] = []
    validated_count = 0

    for name in CANONICAL_SCHEMAS:
        path = schemas_dir / f"{name}.yaml"

        if args.verbose:
            print(f"Validating: {name}")

        if not path.exists():
            errors.append(
                f"[{name}] STANDARD §6.1 requires {path.name}; file not found"
            )
            continue

        try:
            schema = safe_yaml_load(path) or {}
        except (
            yaml.YAMLError,
            YAMLSizeExceededError,
            OSError,
            UnicodeDecodeError,
        ) as exc:
            errors.append(f"[{name}] Could not load {_display_path(path)}: {exc}")
            continue

        validate_header(schema, errors, name)

        validator = PER_SCHEMA_VALIDATORS.get(name)
        if validator is not None:
            validator(schema, errors, name)

        if name == "authority_trust_model":
            validate_trust_fixture_sync(schema, errors)

        validated_count += 1

    validate_vendored_copies(schemas_dir, skills_dir, errors)

    if errors:
        print("CANONICAL SCHEMA VALIDATION FAIL:")
        for error in errors:
            print(f"  - {error}")
        print(f"\nValidated {validated_count} schemas with {len(errors)} errors")
        sys.exit(1)

    print(f"CANONICAL SCHEMA VALIDATION PASS: {validated_count} schemas validated")


if __name__ == "__main__":
    main()
