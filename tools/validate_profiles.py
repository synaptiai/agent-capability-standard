#!/usr/bin/env python3
"""Domain profile validator: validates profiles against profile_schema.yaml

This validator ensures all domain profiles conform to the profile schema,
catching configuration errors early and maintaining consistency.

Validates:
1) Required fields are present (domain, version, trust_weights, etc.)
2) Trust weight values are between 0.0 and 1.0
3) Enum values match allowed values (risk thresholds, checkpoint policies)
4) Semantic version format for version field
5) Source types match allowed enum values

Usage:
- python3 tools/validate_profiles.py
- python3 tools/validate_profiles.py --verbose

"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "schemas" / "profiles"


# -------------------- Schema Constants --------------------

REQUIRED_FIELDS = [
    "domain",
    "version",
    "trust_weights",
    "risk_thresholds",
    "checkpoint_policy",
    "evidence_policy",
]

RISK_AUTO_APPROVE_ENUM = ["none", "low", "medium", "high"]
RISK_REQUIRE_REVIEW_ENUM = ["low", "medium", "high"]
RISK_REQUIRE_HUMAN_ENUM = ["low", "medium", "high", "critical"]
CHECKPOINT_POLICY_ENUM = ["always", "high_risk", "medium_risk", "never"]
SOURCE_TYPE_ENUM = ["api", "sensor", "database", "human", "document", "system_log"]

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


# -------------------- Validation Functions --------------------


def validate_required_fields(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check that all required fields are present."""
    for field in REQUIRED_FIELDS:
        if field not in profile:
            errors.append(f"[{name}] Missing required field: '{field}'")


def validate_version_format(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check version follows semantic versioning pattern."""
    version = profile.get("version")
    if version is not None:
        if not isinstance(version, str):
            errors.append(f"[{name}] Field 'version' must be a string, got {type(version).__name__}")
        elif not VERSION_PATTERN.match(version):
            errors.append(f"[{name}] Invalid version format '{version}': expected semantic version (e.g., '1.0.0')")


def validate_trust_weights(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check all trust weight values are between 0.0 and 1.0."""
    trust_weights = profile.get("trust_weights")
    if trust_weights is None:
        return

    if not isinstance(trust_weights, dict):
        errors.append(f"[{name}] Field 'trust_weights' must be an object, got {type(trust_weights).__name__}")
        return

    for key, value in trust_weights.items():
        if not isinstance(value, (int, float)):
            errors.append(f"[{name}] trust_weights.{key}: expected number, got {type(value).__name__}")
        elif value < 0.0 or value > 1.0:
            errors.append(f"[{name}] trust_weights.{key}: value {value} is outside valid range [0.0, 1.0]")


def validate_risk_thresholds(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check risk threshold enum values."""
    risk_thresholds = profile.get("risk_thresholds")
    if risk_thresholds is None:
        return

    if not isinstance(risk_thresholds, dict):
        errors.append(f"[{name}] Field 'risk_thresholds' must be an object, got {type(risk_thresholds).__name__}")
        return

    # Check auto_approve
    auto_approve = risk_thresholds.get("auto_approve")
    if auto_approve is not None and auto_approve not in RISK_AUTO_APPROVE_ENUM:
        errors.append(
            f"[{name}] risk_thresholds.auto_approve: invalid value '{auto_approve}', "
            f"must be one of {RISK_AUTO_APPROVE_ENUM}"
        )

    # Check require_review
    require_review = risk_thresholds.get("require_review")
    if require_review is not None and require_review not in RISK_REQUIRE_REVIEW_ENUM:
        errors.append(
            f"[{name}] risk_thresholds.require_review: invalid value '{require_review}', "
            f"must be one of {RISK_REQUIRE_REVIEW_ENUM}"
        )

    # Check require_human
    require_human = risk_thresholds.get("require_human")
    if require_human is not None and require_human not in RISK_REQUIRE_HUMAN_ENUM:
        errors.append(
            f"[{name}] risk_thresholds.require_human: invalid value '{require_human}', "
            f"must be one of {RISK_REQUIRE_HUMAN_ENUM}"
        )

    # Check block_autonomous is a list of strings
    block_autonomous = risk_thresholds.get("block_autonomous")
    if block_autonomous is not None:
        if not isinstance(block_autonomous, list):
            errors.append(
                f"[{name}] risk_thresholds.block_autonomous: expected array, "
                f"got {type(block_autonomous).__name__}"
            )
        else:
            for i, item in enumerate(block_autonomous):
                if not isinstance(item, str):
                    errors.append(
                        f"[{name}] risk_thresholds.block_autonomous[{i}]: expected string, "
                        f"got {type(item).__name__}"
                    )


def validate_checkpoint_policy(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check checkpoint policy enum values."""
    checkpoint_policy = profile.get("checkpoint_policy")
    if checkpoint_policy is None:
        return

    if not isinstance(checkpoint_policy, dict):
        errors.append(f"[{name}] Field 'checkpoint_policy' must be an object, got {type(checkpoint_policy).__name__}")
        return

    for key, value in checkpoint_policy.items():
        if not isinstance(value, str):
            errors.append(
                f"[{name}] checkpoint_policy.{key}: expected string, "
                f"got {type(value).__name__}"
            )
        elif value not in CHECKPOINT_POLICY_ENUM:
            errors.append(
                f"[{name}] checkpoint_policy.{key}: invalid value '{value}', "
                f"must be one of {CHECKPOINT_POLICY_ENUM}"
            )


def validate_evidence_policy(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check evidence policy structure and values."""
    evidence_policy = profile.get("evidence_policy")
    if evidence_policy is None:
        return

    if not isinstance(evidence_policy, dict):
        errors.append(f"[{name}] Field 'evidence_policy' must be an object, got {type(evidence_policy).__name__}")
        return

    # Check required_anchor_types is a list of strings
    anchor_types = evidence_policy.get("required_anchor_types")
    if anchor_types is not None:
        if not isinstance(anchor_types, list):
            errors.append(
                f"[{name}] evidence_policy.required_anchor_types: expected array, "
                f"got {type(anchor_types).__name__}"
            )
        else:
            for i, item in enumerate(anchor_types):
                if not isinstance(item, str):
                    errors.append(
                        f"[{name}] evidence_policy.required_anchor_types[{i}]: expected string, "
                        f"got {type(item).__name__}"
                    )

    # Check minimum_confidence is between 0.0 and 1.0
    min_confidence = evidence_policy.get("minimum_confidence")
    if min_confidence is not None:
        if not isinstance(min_confidence, (int, float)):
            errors.append(
                f"[{name}] evidence_policy.minimum_confidence: expected number, "
                f"got {type(min_confidence).__name__}"
            )
        elif min_confidence < 0.0 or min_confidence > 1.0:
            errors.append(
                f"[{name}] evidence_policy.minimum_confidence: value {min_confidence} "
                f"is outside valid range [0.0, 1.0]"
            )

    # Check require_grounding is a list of strings
    require_grounding = evidence_policy.get("require_grounding")
    if require_grounding is not None:
        if not isinstance(require_grounding, list):
            errors.append(
                f"[{name}] evidence_policy.require_grounding: expected array, "
                f"got {type(require_grounding).__name__}"
            )
        else:
            for i, item in enumerate(require_grounding):
                if not isinstance(item, str):
                    errors.append(
                        f"[{name}] evidence_policy.require_grounding[{i}]: expected string, "
                        f"got {type(item).__name__}"
                    )


def validate_domain_sources(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check domain_sources structure and enum values."""
    domain_sources = profile.get("domain_sources")
    if domain_sources is None:
        return

    if not isinstance(domain_sources, list):
        errors.append(f"[{name}] Field 'domain_sources' must be an array, got {type(domain_sources).__name__}")
        return

    for i, source in enumerate(domain_sources):
        if not isinstance(source, dict):
            errors.append(f"[{name}] domain_sources[{i}]: expected object, got {type(source).__name__}")
            continue

        # Check type enum
        source_type = source.get("type")
        if source_type is not None and source_type not in SOURCE_TYPE_ENUM:
            errors.append(
                f"[{name}] domain_sources[{i}].type: invalid value '{source_type}', "
                f"must be one of {SOURCE_TYPE_ENUM}"
            )

        # Check default_trust is between 0.0 and 1.0
        default_trust = source.get("default_trust")
        if default_trust is not None:
            if not isinstance(default_trust, (int, float)):
                errors.append(
                    f"[{name}] domain_sources[{i}].default_trust: expected number, "
                    f"got {type(default_trust).__name__}"
                )
            elif default_trust < 0.0 or default_trust > 1.0:
                errors.append(
                    f"[{name}] domain_sources[{i}].default_trust: value {default_trust} "
                    f"is outside valid range [0.0, 1.0]"
                )


def validate_workflows(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Check workflows is a list of strings."""
    workflows = profile.get("workflows")
    if workflows is None:
        return

    if not isinstance(workflows, list):
        errors.append(f"[{name}] Field 'workflows' must be an array, got {type(workflows).__name__}")
        return

    for i, item in enumerate(workflows):
        if not isinstance(item, str):
            errors.append(f"[{name}] workflows[{i}]: expected string, got {type(item).__name__}")


def validate_profile(profile: dict[str, Any], errors: list[str], name: str) -> None:
    """Run all validations on a profile."""
    validate_required_fields(profile, errors, name)
    validate_version_format(profile, errors, name)
    validate_trust_weights(profile, errors, name)
    validate_risk_thresholds(profile, errors, name)
    validate_checkpoint_policy(profile, errors, name)
    validate_evidence_policy(profile, errors, name)
    validate_domain_sources(profile, errors, name)
    validate_workflows(profile, errors, name)


# -------------------- Main --------------------


def find_profile_files() -> list[Path]:
    """Find all profile YAML files (excluding the schema itself)."""
    profile_files = []
    for path in PROFILES_DIR.glob("*.yaml"):
        # Exclude the schema file
        if path.name != "profile_schema.yaml":
            profile_files.append(path)
    return sorted(profile_files)


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate domain profiles against profile schema")
    ap.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    args = ap.parse_args()

    if not PROFILES_DIR.exists():
        print(f"ERROR: Profiles directory not found: {PROFILES_DIR}")
        sys.exit(1)

    profile_files = find_profile_files()

    if not profile_files:
        print(f"WARNING: No profile files found in {PROFILES_DIR}")
        sys.exit(0)

    errors: list[str] = []
    validated_count = 0

    for profile_path in profile_files:
        profile_name = profile_path.stem

        if args.verbose:
            print(f"Validating: {profile_name}")

        try:
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            errors.append(f"[{profile_name}] YAML parse error: {e}")
            continue

        validate_profile(profile, errors, profile_name)
        validated_count += 1

    # Report results
    if errors:
        print("PROFILE VALIDATION FAIL:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nValidated {validated_count} profiles with {len(errors)} errors")
        sys.exit(1)

    print(f"PROFILE VALIDATION PASS: {validated_count} profiles validated")


if __name__ == "__main__":
    main()
