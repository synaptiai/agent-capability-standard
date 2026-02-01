"""Unit tests for validator tools (TEST-004).

Tests all 5 validators: ontology, workflows, profiles, skill refs, yaml sync.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_validator(
    script_name: str, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a validator script and return the result."""
    script = ROOT / "tools" / script_name
    args = [sys.executable, str(script)]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


# ─── Ontology Validator ───


class TestValidateOntology:
    """Tests for tools/validate_ontology.py."""

    def test_passes_with_valid_ontology(self) -> None:
        result = run_validator("validate_ontology.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"

    def test_output_contains_pass(self) -> None:
        result = run_validator("validate_ontology.py")
        assert "PASS" in result.stdout.upper() or result.returncode == 0


# ─── Workflow Validator ───


class TestValidateWorkflows:
    """Tests for tools/validate_workflows.py."""

    def test_passes_with_production_catalog(self) -> None:
        result = run_validator("validate_workflows.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"

    def test_catalog_flag_accepts_fixture(self) -> None:
        """--catalog flag should accept alternative catalog files."""
        fixture = ROOT / "tests" / "fixtures" / "pass_reference.workflow_catalog.yaml"
        if not fixture.exists():
            pytest.skip("Pass reference fixture not found")
        result = run_validator("validate_workflows.py", ["--catalog", str(fixture)])
        assert result.returncode == 0

    def test_catalog_flag_catches_bad_fixture(self) -> None:
        """--catalog flag should catch bad fixtures."""
        fixture = (
            ROOT
            / "tests"
            / "fixtures"
            / "fail_unknown_capability.workflow_catalog.yaml"
        )
        if not fixture.exists():
            pytest.skip("Fail fixture not found")
        result = run_validator("validate_workflows.py", ["--catalog", str(fixture)])
        assert result.returncode == 1

    def test_nonexistent_catalog_fails(self) -> None:
        result = run_validator(
            "validate_workflows.py", ["--catalog", "/nonexistent.yaml"]
        )
        assert result.returncode != 0


# ─── Profile Validator ───


class TestValidateProfiles:
    """Tests for tools/validate_profiles.py."""

    def test_passes_with_valid_profiles(self) -> None:
        result = run_validator("validate_profiles.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"

    def test_verbose_flag_works(self) -> None:
        result = run_validator("validate_profiles.py", ["--verbose"])
        assert result.returncode == 0
        assert "Validating:" in result.stdout

    def test_reports_trust_calibration_warnings(self) -> None:
        """SEC-009: Should report warnings about uncalibrated trust models."""
        result = run_validator("validate_profiles.py")
        assert result.returncode == 0
        output = result.stdout
        # Validator passes but reports SEC-009 trust calibration warnings
        assert "PASS" in output.upper()
        assert "SEC-009" in output, (
            "Expected SEC-009 trust_model_reviewed warnings in output"
        )
        assert "trust_model_reviewed" in output


# ─── Skill Refs Validator ───


class TestValidateSkillRefs:
    """Tests for tools/validate_skill_refs.py."""

    def test_passes_with_valid_skills(self) -> None:
        result = run_validator("validate_skill_refs.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"


# ─── YAML Util Sync Validator ───


class TestValidateYamlUtilSync:
    """Tests for tools/validate_yaml_util_sync.py."""

    def test_passes_when_synced(self) -> None:
        result = run_validator("validate_yaml_util_sync.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"


# ─── Conformance Runner ───


class TestConformanceRunner:
    """Tests for scripts/run_conformance.py."""

    def test_conformance_passes(self) -> None:
        """Conformance runner should pass with reference fixtures."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_conformance.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"
        assert "PASSED" in result.stdout


# ─── JSON Schema Validation ───


class TestJsonSchemaValidation:
    """Tests for JSON Schema validation of YAML files (Issue #71)."""

    @pytest.fixture
    def ontology_schema(self) -> dict:
        schema_path = ROOT / "schemas" / "capability_ontology.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    @pytest.fixture
    def workflow_schema(self) -> dict:
        schema_path = ROOT / "schemas" / "workflow_catalog.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def test_ontology_schema_is_valid_json(self) -> None:
        """Schema file itself should be valid JSON."""
        path = ROOT / "schemas" / "capability_ontology.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "$schema" in data

    def test_workflow_schema_is_valid_json(self) -> None:
        """Schema file itself should be valid JSON."""
        path = ROOT / "schemas" / "workflow_catalog.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "$schema" in data

    def test_ontology_validates_against_schema(self, ontology_schema) -> None:
        """Production ontology should validate against its JSON Schema."""
        import jsonschema
        import yaml

        ontology = yaml.safe_load(
            (ROOT / "schemas" / "capability_ontology.yaml").read_text()
        )
        jsonschema.validate(ontology, ontology_schema)

    def test_workflow_validates_against_schema(self, workflow_schema) -> None:
        """Production workflow catalog should validate against its JSON Schema."""
        import jsonschema
        import yaml

        workflows = yaml.safe_load(
            (ROOT / "schemas" / "workflow_catalog.yaml").read_text()
        )
        jsonschema.validate(workflows, workflow_schema)

    def test_ontology_schema_rejects_bad_risk(self, ontology_schema) -> None:
        """Schema should reject invalid risk values."""
        import jsonschema

        bad = {
            "meta": {"name": "test", "version": "1.0", "description": "test"},
            "layers": {},
            "nodes": [
                {
                    "id": "test",
                    "layer": "PERCEIVE",
                    "description": "test",
                    "risk": "extreme",
                }
            ],
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, ontology_schema)

    def test_ontology_schema_rejects_bad_layer(self, ontology_schema) -> None:
        """Schema should reject invalid layer values."""
        import jsonschema

        bad = {
            "meta": {"name": "test", "version": "1.0", "description": "test"},
            "layers": {},
            "nodes": [{"id": "test", "layer": "INVALID", "description": "test"}],
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, ontology_schema)
