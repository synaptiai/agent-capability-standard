"""Unit tests for validator tools (TEST-004).

Tests all 5 validators: ontology, workflows, profiles, skill refs, yaml sync.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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

    def test_warnings_pass_unless_strict(self, tmp_path: Path) -> None:
        """A warning (W612) passes by default and fails under --strict."""
        catalog = tmp_path / "warn.workflow_catalog.yaml"
        catalog.write_text(
            "w:\n"
            "  goal: g\n"
            "  risk: low\n"
            "  steps:\n"
            "  - capability: search\n"
            "    purpose: p\n"
            "    store_as: s\n"
            "    input_bindings: {query: q}\n"
            "  - capability: integrate\n"
            "    purpose: p\n"
            "    store_as: i\n"
            "    input_bindings:\n"
            "      sources:\n"
            "      - ${s.results: array<object>}\n"
        )
        lenient = run_validator("validate_workflows.py", ["--catalog", str(catalog)])
        assert lenient.returncode == 0, lenient.stdout
        assert "W612" in lenient.stdout
        strict = run_validator(
            "validate_workflows.py", ["--catalog", str(catalog), "--strict"]
        )
        assert strict.returncode == 1

    def test_suggestions_json_shape(self, tmp_path: Path) -> None:
        """Structured output plus a transform patch for a consumer mismatch."""
        catalog = tmp_path / "coerce.workflow_catalog.yaml"
        catalog.write_text(
            "w:\n"
            "  goal: g\n"
            "  risk: low\n"
            "  steps:\n"
            "  - capability: search\n"
            "    purpose: p\n"
            "    store_as: s\n"
            "    input_bindings: {query: q}\n"
            "  - capability: search\n"
            "    purpose: p\n"
            "    store_as: t\n"
            "    input_bindings: {query: q, scope: '${s.total_count}'}\n"
        )
        result = run_validator(
            "validate_workflows.py", ["--catalog", str(catalog), "--emit-patch"]
        )
        assert result.returncode == 1
        data = json.loads((ROOT / "tools" / "validator_suggestions.json").read_text())
        assert set(data) >= {
            "errors",
            "warnings",
            "structured_errors",
            "structured_warnings",
            "suggestions",
        }
        assert all(e["severity"] == "error" for e in data["structured_errors"])
        (suggestion,) = data["suggestions"]
        assert suggestion["kind"] == "consumer_input_type_mismatch"
        assert (suggestion["from_type"], suggestion["to_type"]) == ("integer", "string")
        diff = (ROOT / "tools" / "validator_patch.diff").read_text()
        assert "capability: transform" in diff


def test_patch_application_handles_two_transforms_for_one_step() -> None:
    """Both transforms go before the consumer, and both updates land on it."""
    import importlib.util

    sys.path.insert(0, str(ROOT / "tools"))  # for its `yaml_util` import
    spec = importlib.util.spec_from_file_location(
        "validate_workflows", ROOT / "tools" / "validate_workflows.py"
    )
    assert spec is not None and spec.loader is not None
    validate_workflows = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validate_workflows)

    workflows = {
        "w": {
            "steps": [
                {"capability": "search", "store_as": "s"},
                {"capability": "search", "store_as": "t", "input_bindings": {}},
            ]
        }
    }

    def patch(key: str) -> dict:
        return {
            "kind": "consumer_input_type_mismatch",
            "workflow": "w",
            "patch": {
                "insert_at_step_index": 1,
                "new_step": {"capability": "transform", "store_as": f"coerce_{key}"},
                "update_step": {
                    "step_index": 1,
                    "input_bindings_update": {key: f"${{coerce_{key}.transformed}}"},
                },
            },
        }

    import yaml

    out = yaml.safe_load(
        validate_workflows.apply_patch_suggestions_to_yaml(
            workflows, [patch("scope"), patch("query")]
        )
    )
    steps = out["w"]["steps"]
    assert [s["capability"] for s in steps] == [
        "search",
        "transform",
        "transform",
        "search",
    ]
    assert steps[3]["input_bindings"] == {
        "scope": "${coerce_scope.transformed}",
        "query": "${coerce_query.transformed}",
    }


# ─── Profile Validator ───


def test_example_catalog_matches_the_reference_catalog() -> None:
    """examples/digital_twin_sync_loop copies its workflows verbatim from the
    reference catalog; an edit to one must be made to both."""
    import yaml

    example = yaml.safe_load(
        (ROOT / "examples" / "digital_twin_sync_loop.workflow_catalog.yaml").read_text()
    )
    reference = yaml.safe_load((ROOT / "schemas" / "workflow_catalog.yaml").read_text())
    assert set(example) == {
        "world_model_build",
        "digital_twin_sync_loop",
        "digital_twin_bootstrap",
    }
    for name, workflow in example.items():
        assert workflow == reference[name], name


def fixture_set(fixtures: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """An expectation's ``catalogs`` and ``agents`` (STANDARD v1.2 §10.3) as
    validator arguments: further catalogs of the catalog set, and agent
    manifests (a file, or a directory of ``*.agent.yaml`` files)."""
    agents: list[str] = []
    for a in meta.get("agents", []):
        p = fixtures / a
        agents += (
            [str(m) for m in sorted(p.glob("*.agent.yaml"))] if p.is_dir() else [str(p)]
        )
    return {
        "catalogs": [str(fixtures / c) for c in meta.get("catalogs", [])] or None,
        "agents": agents or None,
    }


def test_w615_only_where_expected() -> None:
    """The fixtures bind every required input, so W615 appears only in those
    that expect it. The core's unit tests filter W615 out of their code
    lists; this catches a W615 raised where it should not be."""
    from grounded_agency import _core

    validator = _core.Validator(ROOT / "schemas" / "capability_ontology.yaml", ROOT)
    expectations = json.loads(
        (ROOT / "tests" / "fixtures" / "EXPECTATIONS.json").read_text()
    )
    fixtures = ROOT / "tests" / "fixtures"
    for name, meta in expectations.items():
        path = fixtures / f"{name}.workflow_catalog.yaml"
        report = validator.validate_file(path, **fixture_set(fixtures, meta))
        emitted = {d["code"] for d in report["diagnostics"]}
        expected = "W615" in meta.get("expected_warning_codes", [])
        assert ("W615" in emitted) == expected, name


class TestValidateProfiles:
    """Tests for tools/validate_profiles.py."""

    def test_passes_with_valid_profiles(self) -> None:
        result = run_validator("validate_profiles.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"

    def test_verbose_flag_works(self) -> None:
        result = run_validator("validate_profiles.py", ["--verbose"])
        assert result.returncode == 0
        assert "Validating:" in result.stdout

    def test_boolean_weights_are_refused(self) -> None:
        """YAML ``true`` is an int in Python, but not a weight: the core
        reports S303 at each (Standard v1.2 §5.21.2)."""
        from grounded_agency import _core

        validator = _core.Validator(
            str(ROOT / "schemas" / "capability_ontology.yaml"), str(ROOT)
        )
        report = validator.check_profiles(
            [
                {
                    "domain": "p",
                    "version": "1.0.0",
                    "trust_weights": {"a": True, "b": 0.5},
                    "evidence_policy": {"minimum_confidence": False},
                    "domain_sources": [{"name": "s", "default_trust": True}],
                }
            ]
        )
        found = {(d["code"], d["location"]["field"]) for d in report["diagnostics"]}
        assert found == {
            ("S303", "trust_weights.a"),
            ("S303", "evidence_policy.minimum_confidence"),
            ("S303", "domain_sources[0].default_trust"),
        }
        # A NaN weight cannot reach the core as data.
        with pytest.raises(ValueError, match="non-finite"):
            validator.check_profiles(
                [
                    {
                        "domain": "p",
                        "version": "1.0.0",
                        "trust_weights": {"a": float("nan")},
                    }
                ]
            )

    def test_a_misspelled_rule_fails(self, tmp_path: Path) -> None:
        """A checkpoint_policy key that is no capability id is V101, an
        error: no misspelled rule is ignored."""
        profiles = tmp_path / "profiles"
        shutil.copytree(ROOT / "schemas" / "profiles", profiles)
        path = profiles / "vision.yaml"
        text = path.read_text()
        assert "  mutate: always\n" in text
        path.write_text(text.replace("  mutate: always\n", "  mutat: always\n", 1))
        result = run_validator(
            "validate_profiles.py", ["--profiles-dir", str(profiles)]
        )
        assert result.returncode != 0
        assert "V101" in result.stdout and "mutate" in result.stdout

    def test_a_shipped_profile_cites_the_current_versions(self, tmp_path: Path) -> None:
        profiles = tmp_path / "profiles"
        shutil.copytree(ROOT / "schemas" / "profiles", profiles)
        path = profiles / "audio.yaml"
        path.write_text(
            path.read_text().replace('standard: "1.2.0"', 'standard: "1.1.0"')
        )
        result = run_validator(
            "validate_profiles.py", ["--profiles-dir", str(profiles)]
        )
        assert result.returncode != 0
        assert "'standard' must be '1.2.0'" in result.stdout

    def test_no_trust_calibration_warnings(self) -> None:
        """SEC-009: All profiles have trust_model_reviewed: true — no warnings."""
        result = run_validator("validate_profiles.py")
        assert result.returncode == 0
        output = result.stdout
        assert "PASS" in output.upper()
        # All profiles now have trust_model_reviewed: true, so no SEC-009 warnings
        assert "SEC-009" not in output, (
            "Unexpected SEC-009 warnings — all profiles should have trust_model_reviewed: true"
        )


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


class TestConformanceHelpers:
    """Unit tests for conformance runner helper functions."""

    def test_read_emitted_codes_missing_file(self, tmp_path: Path) -> None:
        """Returns empty set when suggestions JSON does not exist."""
        import scripts.run_conformance as rc

        missing = tmp_path / "nonexistent.json"
        assert rc._read_emitted_codes(missing, "structured_errors") == set()

    def test_read_emitted_codes_valid_json(self, tmp_path: Path) -> None:
        """Returns the codes under the requested key."""
        import scripts.run_conformance as rc

        f = tmp_path / "suggestions.json"
        f.write_text(
            json.dumps(
                {
                    "structured_errors": [
                        {"code": "V101", "name": "UNKNOWN_CAPABILITY", "message": "t"},
                        {"code": "V104", "name": "DUPLICATE_STORE_AS", "message": "t"},
                    ],
                    "structured_warnings": [
                        {"code": "W601", "name": "SOFT_REQUIRES", "message": "t"}
                    ],
                }
            )
        )
        assert rc._read_emitted_codes(f, "structured_errors") == {"V101", "V104"}
        assert rc._read_emitted_codes(f, "structured_warnings") == {"W601"}

    def test_read_emitted_codes_malformed_json(self, tmp_path: Path) -> None:
        """Returns empty set on malformed JSON."""
        import scripts.run_conformance as rc

        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        assert rc._read_emitted_codes(f, "structured_errors") == set()

    def test_suggestions_out_writes_where_asked(self, tmp_path: Path) -> None:
        """--suggestions-out writes the report to the given path."""
        out = tmp_path / "out.json"
        fixture = (
            ROOT
            / "tests"
            / "fixtures"
            / "fail_unknown_capability.workflow_catalog.yaml"
        )
        result = run_validator(
            "validate_workflows.py",
            ["--catalog", str(fixture), "--suggestions-out", str(out)],
        )
        assert result.returncode == 1
        data = json.loads(out.read_text())
        assert {d["code"] for d in data["structured_errors"]} == {"V101"}


# ─── Transform Refs Validator ───


class TestValidateTransformRefs:
    """Tests for tools/validate_transform_refs.py."""

    def test_passes_with_valid_refs(self) -> None:
        result = run_validator("validate_transform_refs.py")
        assert result.returncode == 0, f"Failed: {result.stdout}\n{result.stderr}"

    def test_verbose_flag_works(self) -> None:
        result = run_validator("validate_transform_refs.py", ["--verbose"])
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_output_contains_pass(self) -> None:
        result = run_validator("validate_transform_refs.py")
        assert "PASS" in result.stdout


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

    def test_passing_fixtures_validate_against_schema(self, workflow_schema) -> None:
        """Every catalog the validator accepts is valid under the JSON Schema,
        so the schema never requires what STANDARD §5 leaves optional."""
        import jsonschema
        import yaml

        expectations = json.loads(
            (ROOT / "tests" / "fixtures" / "EXPECTATIONS.json").read_text()
        )
        passing = [n for n, meta in expectations.items() if meta["should_pass"]]
        assert passing
        for name in passing:
            path = ROOT / "tests" / "fixtures" / f"{name}.workflow_catalog.yaml"
            jsonschema.validate(yaml.safe_load(path.read_text()), workflow_schema)

    def test_workflow_schema_allows_inherited_flags(self, workflow_schema) -> None:
        """Safety flags, risk and failure_modes may be omitted: they inherit
        from the ontology (STANDARD v1.1 §5.2)."""
        import jsonschema

        minimal = {
            "w": {
                "goal": "g",
                "risk": "low",
                "steps": [{"capability": "retrieve", "purpose": "p", "store_as": "r"}],
            }
        }
        jsonschema.validate(minimal, workflow_schema)

    @pytest.mark.parametrize(
        "step_patch",
        [
            {"purpose": None},
            {"gates": [{"when": "true", "action": "skip", "phase": "after"}]},
            {"gates": [{"when": "true", "action": "halt"}]},
            {"gates": [{"when": "true", "action": "stop", "phase": "during"}]},
            {"failure_modes": [{"condition": "c", "action": "stop", "when": 1}]},
            {"handler": True},
            {"failure_modes": [{"condition": "c", "action": "escalate"}]},
            {
                "failure_modes": [
                    {
                        "condition": "c",
                        "action": "escalate",
                        "recovery": {"goto_step": "h", "max_loops": 2},
                    }
                ]
            },
            {"store_as": "_recovery"},
            {"wait": {"source_kind": "api"}},
            {"wait": {"event_type": "e"}},
            {
                "quorum": {
                    "verdicts": "${v}",
                    "reviewers": ["r"],
                    "vocabulary": ["ok"],
                    "pass_values": ["ok"],
                    "min_pass": 1,
                    "pinned_to": "${p}",
                }
            },
            {
                "wait": {
                    "event_type": "e",
                    "liveness": {"mode": "push", "interval": "0s"},
                }
            },
            {"approval": {"approver": {"kind": "standing_mandate"}}},
            {"approval": {"approver": {"kind": "human", "mandate_ref": "m"}}},
            {"approval": {"approver": {"kind": "human"}, "expires": "PT0S"}},
        ],
        ids=[
            "missing-purpose",
            "after-gate-skip",
            "bad-gate-action",
            "bad-gate-phase",
            "non-string-failure-when",
            "handler-not-invoke",
            "escalate-without-target",
            "escalate-with-loop-fields",
            "reserved-store-as",
            "wait-without-event-type",
            "wait-without-timeout",
            "quorum-one-word-vocabulary",
            "zero-liveness-interval",
            "mandate-without-ref",
            "human-with-mandate-ref",
            "zero-expiry",
        ],
    )
    def test_workflow_schema_rejects_bad_steps(
        self, workflow_schema, step_patch: dict
    ) -> None:
        import jsonschema

        step: dict = {"capability": "retrieve", "purpose": "p", "store_as": "r"}
        for key, value in step_patch.items():
            if value is None:
                del step[key]
            else:
                step[key] = value
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"w": {"goal": "g", "risk": "low", "steps": [step]}}, workflow_schema
            )

    def test_review_verdict_schema_matches_the_executor(self) -> None:
        """Quorum verdicts (STANDARD v1.1 §5.16): the fields the executor
        counts are the schema's required ones."""
        import yaml

        schema = yaml.safe_load(
            (ROOT / "schemas" / "review_verdict_schema.yaml").read_text()
        )
        verdict = schema["review_verdict"]
        assert verdict["type"] == "object"
        assert verdict["required"] == ["reviewer_id", "value", "pinned"]
        assert set(verdict["properties"]) >= {
            "reviewer_id",
            "value",
            "pinned",
            "scope",
            "evidence_anchors",
            "notes",
        }
        # The executor counts full sweeps by these two values only.
        assert verdict["properties"]["scope"]["enum"] == ["full", "delta"]

    def test_workflow_schema_rejects_malformed_spec_version(
        self, workflow_schema
    ) -> None:
        import jsonschema

        bad = {"w": {"goal": "g", "risk": "low", "steps": [], "spec_version": "v1"}}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, workflow_schema)


# ─── Canonical Schema Validator ───


class TestValidateCanonicalSchemas:
    """Tests for tools/validate_canonical_schemas.py (issue #107).

    STANDARD-v1.0.0 §6.1 designates five canonical schemas. Until this
    validator existed nothing checked them, so the defects in #105 and #106 all
    shipped through a green CI. The negative cases below reproduce those exact
    defects to prove the validator would now catch them.

    Drift is injected into a temporary copy via ``--schemas-dir`` rather than
    into the tracked files, following the ``--catalog`` precedent in
    validate_workflows.py. Mutating tracked schemas in place races with any
    concurrent run and can leave the tree dirty if a test is interrupted.
    """

    SCHEMAS = ROOT / "schemas"

    def _schemas_copy(self, tmp_path: Path) -> Path:
        target = tmp_path / "schemas"
        shutil.copytree(self.SCHEMAS, target)
        return target

    def _assert_drift_is_caught(
        self, tmp_path: Path, filename: str, old: str, new: str
    ) -> None:
        """Inject a defect into a throwaway copy; the validator must reject it."""
        schemas = self._schemas_copy(tmp_path)
        path = schemas / filename
        original = path.read_text()
        assert old in original, f"anchor not found in {filename}: {old!r}"
        path.write_text(original.replace(old, new, 1))

        result = run_validator(
            "validate_canonical_schemas.py", ["--schemas-dir", str(schemas)]
        )

        assert result.returncode != 0, (
            f"validator passed despite injected drift in {filename}"
        )
        assert "FAIL" in result.stdout

    def test_passes_with_current_schemas(self) -> None:
        result = run_validator("validate_canonical_schemas.py")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout

    def test_verbose_flag_lists_every_canonical_schema(self) -> None:
        result = run_validator("validate_canonical_schemas.py", ["--verbose"])
        assert result.returncode == 0
        for name in (
            "world_state_schema",
            "event_schema",
            "entity_taxonomy",
            "authority_trust_model",
            "identity_resolution_policy",
        ):
            assert name in result.stdout

    def test_schemas_dir_override_accepts_an_untouched_copy(
        self, tmp_path: Path
    ) -> None:
        schemas = self._schemas_copy(tmp_path)
        result = run_validator(
            "validate_canonical_schemas.py", ["--schemas-dir", str(schemas)]
        )
        assert result.returncode == 0, result.stdout

    def test_catches_exponential_decay_regression(self, tmp_path: Path) -> None:
        """Issue #105: exp(-age/half_life) is not a half-life."""
        self._assert_drift_is_caught(
            tmp_path,
            "authority_trust_model.yaml",
            "recency_factor: max(0.5 ** (age/half_life), min_trust)",
            "recency_factor: exp(-age/half_life)",
        )

    def test_catches_benchmark_fixture_drift(self, tmp_path: Path) -> None:
        """Issue #105: mock_apis.json silently disagreed with the schema."""
        self._assert_drift_is_caught(
            tmp_path, "authority_trust_model.yaml", "half_life: P10D", "half_life: P14D"
        )

    def test_catches_phantom_field_authority_source(self, tmp_path: Path) -> None:
        """Issue #105: the NIST profile cited a source that never existed."""
        self._assert_drift_is_caught(
            tmp_path,
            "authority_trust_model.yaml",
            "    - hardware_sensor\n    - system_of_record",
            "    - unverified\n    - system_of_record",
        )

    def test_catches_a_taxonomy_example_outside_the_pattern(
        self, tmp_path: Path
    ) -> None:
        """Standard v1.2 §7.1: every example is an id of the grammar."""
        self._assert_drift_is_caught(
            tmp_path,
            "entity_taxonomy.yaml",
            "  - svc:acme/payments/prod/api",
            "  - svc:acme",
        )

    def test_catches_a_taxonomy_example_of_an_unknown_class(
        self, tmp_path: Path
    ) -> None:
        self._assert_drift_is_caught(
            tmp_path,
            "entity_taxonomy.yaml",
            "  - svc:acme/payments/prod/api",
            "  - robot:acme/payments/prod/api",
        )

    def test_catches_a_missing_section_7_1_example(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path,
            "entity_taxonomy.yaml",
            "  - person:org.company/user/12345\n",
            "",
        )

    def test_catches_an_unknown_tie_breaker(self, tmp_path: Path) -> None:
        """Standard v1.2 §8.2 defines four tie-breakers."""
        self._assert_drift_is_caught(
            tmp_path,
            "authority_trust_model.yaml",
            "  - prefer_high_confidence\n  - escalate_to_human",
            "  - prefer_loudest\n  - escalate_to_human",
        )

    def test_catches_missing_field_authority_fields(self, tmp_path: Path) -> None:
        """§8.2 reads field_authority.fields; examples are illustrative."""
        self._assert_drift_is_caught(
            tmp_path, "authority_trust_model.yaml", "  fields:\n", "  feilds:\n"
        )

    def test_catches_phantom_source_in_the_examples(self, tmp_path: Path) -> None:
        """`examples`, kept from 1.1, is checked as `fields` is."""
        schemas = self._schemas_copy(tmp_path)
        path = schemas / "authority_trust_model.yaml"
        text = path.read_text()
        examples = text.index("  examples:")
        path.write_text(
            text[:examples]
            + text[examples:].replace("- hardware_sensor", "- unverified", 1)
        )
        result = run_validator(
            "validate_canonical_schemas.py", ["--schemas-dir", str(schemas)]
        )
        assert result.returncode != 0
        assert "field_authority.examples['serial_number']" in result.stdout

    def test_catches_anchor_drift_between_event_and_world_state(
        self, tmp_path: Path
    ) -> None:
        """The world state's Anchor is the event schema's (Standard v1.2 §6.5)."""
        self._assert_drift_is_caught(
            tmp_path,
            "world_state_schema.yaml",
            "|human_note|api|record|",
            "|human_note|record|",
        )

    def test_catches_identity_model_id_drift(self, tmp_path: Path) -> None:
        """The world state's AgentIdentity is agent_identity, model_id too."""
        self._assert_drift_is_caught(
            tmp_path,
            "world_state_schema.yaml",
            "      model_id:\n        type: string",
            "      model_id:\n        type: integer",
        )

    def test_catches_source_ranking_asymmetry(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path,
            "authority_trust_model.yaml",
            "    human_note: 0.55",
            "    human_note: 0.55\n    ghost_source: 0.5",
        )

    def test_catches_trust_class_without_weight(self, tmp_path: Path) -> None:
        """Every agent_identity trust class has a default weight (RFC-0004)."""
        self._assert_drift_is_caught(
            tmp_path, "authority_trust_model.yaml", "    external: 0.35\n", ""
        )

    def test_catches_unknown_trust_class(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path,
            "authority_trust_model.yaml",
            "    external: 0.35",
            "    external: 0.35\n    stranger: 0.1",
        )

    @pytest.mark.parametrize(
        ("filename", "old", "new"),
        [
            (
                "authority_trust_model.yaml",
                "    human_note: 0.55",
                "    human_note: true",
            ),
            ("authority_trust_model.yaml", "    external: 0.35", "    external: true"),
            ("authority_trust_model.yaml", "min_trust: 0.25", "min_trust: true"),
            (
                "identity_resolution_policy.yaml",
                "    weight: 1.0\n    rule: id string equality",
                "    weight: true\n    rule: id string equality",
            ),
        ],
        ids=["source-weight", "trust-class-weight", "min-trust", "alias-feature"],
    )
    def test_catches_boolean_weights(
        self, tmp_path: Path, filename: str, old: str, new: str
    ) -> None:
        """``true`` is an int in Python (== 1), but not a weight."""
        self._assert_drift_is_caught(tmp_path, filename, old, new)

    def test_catches_identity_type_drift(self, tmp_path: Path) -> None:
        """The world state's AgentIdentity copies agent_identity exactly."""
        self._assert_drift_is_caught(
            tmp_path,
            "agent_identity_schema.yaml",
            "      - service\n",
            "      - service\n      - robot\n",
        )

    def test_catches_out_of_range_min_trust(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path, "authority_trust_model.yaml", "min_trust: 0.25", "min_trust: 25"
        )

    def test_catches_missing_spec_6_2_required_field(self, tmp_path: Path) -> None:
        """STANDARD §6.2 lists provenance as MUST."""
        self._assert_drift_is_caught(
            tmp_path,
            "event_schema.yaml",
            "  - provenance\n  properties:\n    event_id:",
            "  properties:\n    event_id:",
        )

    def test_catches_missing_spec_6_3_required_field(self, tmp_path: Path) -> None:
        """STANDARD §6.3 lists snapshot lineage as MUST."""
        self._assert_drift_is_caught(
            tmp_path,
            "world_state_schema.yaml",
            "      - version_id\n      - lineage",
            "      - version_id",
        )

    def test_catches_zero_half_life(self, tmp_path: Path) -> None:
        """A zero half-life divides by zero in the decay curve (finding F1)."""
        self._assert_drift_is_caught(
            tmp_path, "authority_trust_model.yaml", "half_life: P10D", "half_life: P0D"
        )

    def test_exp_detection_does_not_match_identifier_substrings(
        self, tmp_path: Path
    ) -> None:
        """`regexp(` contains `exp(` but is not an exponential (finding F3)."""
        schemas = self._schemas_copy(tmp_path)
        path = schemas / "authority_trust_model.yaml"
        path.write_text(
            path.read_text().replace(
                "recency_factor: max(0.5 ** (age/half_life), min_trust)",
                "recency_factor: max(0.5 ** (regexp(age)/half_life), min_trust)",
                1,
            )
        )

        result = run_validator(
            "validate_canonical_schemas.py", ["--schemas-dir", str(schemas)]
        )

        assert result.returncode == 0, (
            f"'regexp(' was misread as an exponential:\n{result.stdout}"
        )

    def test_unreadable_schema_fails_cleanly(self, tmp_path: Path) -> None:
        """Bad bytes produce a validation error, not a traceback (finding F4)."""
        schemas = self._schemas_copy(tmp_path)
        (schemas / "entity_taxonomy.yaml").write_bytes(b"\xff\xfe\x00binary")

        result = run_validator(
            "validate_canonical_schemas.py", ["--schemas-dir", str(schemas)]
        )

        assert result.returncode != 0
        assert "Traceback" not in result.stderr, result.stderr
        assert "Could not load" in result.stdout

    def test_catches_unordered_alias_thresholds(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path,
            "identity_resolution_policy.yaml",
            "auto_merge: 0.9",
            "auto_merge: 0.5",
        )

    def test_catches_malformed_schema_version(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path, "entity_taxonomy.yaml", "  version: 1.1.0", "  version: v1"
        )

    def test_catches_missing_canonical_schema_file(self, tmp_path: Path) -> None:
        """STANDARD §6.1 requires all five files to be present."""
        schemas = self._schemas_copy(tmp_path)
        (schemas / "entity_taxonomy.yaml").unlink()

        result = run_validator(
            "validate_canonical_schemas.py", ["--schemas-dir", str(schemas)]
        )

        assert result.returncode != 0
        assert "§6.1" in result.stdout

    def test_vendored_skill_copies_match_their_source(self) -> None:
        """Every reference/ copy in the real tree agrees with schemas/."""
        result = run_validator("validate_canonical_schemas.py")
        assert result.returncode == 0, result.stdout

    def test_catches_drifted_vendored_copy(self, tmp_path: Path) -> None:
        """A desynced skill copy must fail the validator (issue #107).

        sync_skill_schemas.py only reaches skills that bundle a
        reference/workflow_catalog.yaml, so skills/receive/reference/ is an
        orphan copy no tooling maintains -- exactly the copy that had drifted.
        """
        skills = tmp_path / "skills"
        (skills / "receive" / "reference").mkdir(parents=True)
        copy = skills / "receive" / "reference" / "event_schema.yaml"
        source = (self.SCHEMAS / "event_schema.yaml").read_text()
        copy.write_text(source.replace("  - provenance\n", "", 1))

        result = run_validator(
            "validate_canonical_schemas.py", ["--skills-dir", str(skills)]
        )

        assert result.returncode != 0
        assert "has drifted" in result.stdout

    def test_accepts_an_in_sync_vendored_copy(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        (skills / "receive" / "reference").mkdir(parents=True)
        shutil.copy(
            self.SCHEMAS / "event_schema.yaml",
            skills / "receive" / "reference" / "event_schema.yaml",
        )

        result = run_validator(
            "validate_canonical_schemas.py", ["--skills-dir", str(skills)]
        )

        assert result.returncode == 0, result.stdout


# ─── Skill Schema Sync ───


class TestSyncSkillSchemas:
    """Tests for tools/sync_skill_schemas.py (issue #107)."""

    @staticmethod
    def _tree(tmp_path: Path) -> Path:
        """A copy of everything the sync reads and writes."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_sync_deps", ROOT / "tools" / "sync_skill_schemas.py"
        )
        assert spec and spec.loader
        sys.path.insert(0, str(ROOT / "tools"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for rel in (
            "schemas/capability_ontology.yaml",
            "schemas/workflow_catalog.yaml",
            *module.WORKFLOW_CATALOG_TRANSITIVE_DEPS,
        ):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, tmp_path / rel)
        shutil.copytree(ROOT / "skills", tmp_path / "skills")
        return tmp_path

    @staticmethod
    def _sync(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "sync_skill_schemas.py"),
                "--root",
                str(root),
                *flags,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_sync_is_idempotent(self, tmp_path: Path) -> None:
        """Re-running the sync on a synced tree must change nothing.

        The comment rewrite `schemas/workflows/` -> `(repo-level)
        schemas/workflows/` used to reapply itself to already-rewritten text,
        so each run stacked another `(repo-level)` prefix onto the 17 bundled
        catalogs. Runs on a copy, so the test never touches the tree (or
        repairs drift that test_check_passes_on_the_tree must see).
        """
        root = self._tree(tmp_path)
        assert self._sync(root).returncode == 0
        generated = sorted((root / "skills").rglob("*.yaml"))
        before = {path: path.read_bytes() for path in generated}
        second = self._sync(root)
        assert second.returncode == 0, second.stdout + second.stderr
        assert "SYNC COMPLETE: 0 of" in second.stdout
        assert {p: p.read_bytes() for p in generated} == before

    @staticmethod
    def _module():
        import importlib.util

        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location(
            "sync_skill_schemas", ROOT / "tools" / "sync_skill_schemas.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["sync_skill_schemas"] = module
        spec.loader.exec_module(module)
        return module

    def test_rewrite_heals_already_doubled_prefixes(self) -> None:
        """The rewrite must collapse existing stacking, not merely stop adding.

        Replacing one layer then re-applying makes double-prefixed content a
        fixed point: the sync would preserve corruption a previous run wrote
        rather than repairing it.
        """
        module = self._module()
        old_prefix, new_prefix = next(
            iter(module.WORKFLOW_CATALOG_COMMENT_REWRITES.items())
        )
        note = new_prefix[: -len(old_prefix)]  # e.g. "(repo-level) "
        expected = f"#   - {new_prefix}x.yaml"

        for layers in (0, 1, 2, 3):
            content = module.rewrite_paths(f"#   - {note * layers}{old_prefix}x.yaml")
            assert content == expected, (
                f"{layers} stacked note(s) collapsed to {content!r}, "
                f"expected {expected!r}"
            )

    def test_check_passes_on_the_tree(self) -> None:
        """Every generated file in the repository matches its source."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sync_skill_schemas.py"), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    @staticmethod
    def _source_header() -> str:
        return (ROOT / "schemas" / "workflow_catalog.yaml").read_text().splitlines()[0]

    def test_check_reports_a_drifted_catalog_and_sync_repairs_it(
        self, tmp_path: Path
    ) -> None:
        """A vendored catalog edited by hand (or left behind when the source
        changed) fails --check; a sync regenerates it from the source."""
        root = self._tree(tmp_path)
        vendored = root / "skills" / "observe" / "reference" / "workflow_catalog.yaml"
        header = self._source_header()
        vendored.write_text(vendored.read_text().replace(header, "# edited", 1))

        check = self._sync(root, "--check")
        assert check.returncode == 1
        assert "skills/observe/reference/workflow_catalog.yaml" in check.stdout
        assert self._sync(root).returncode == 0
        assert self._sync(root, "--check").returncode == 0
        assert vendored.read_text().startswith(header + "\n")

    def test_orphaned_output_schema_is_reported_and_removed(
        self, tmp_path: Path
    ) -> None:
        root = self._tree(tmp_path)
        orphan_dir = root / "skills" / "retired" / "schemas"
        orphan_dir.mkdir(parents=True)
        orphan = orphan_dir / "output_schema.yaml"
        shutil.copy(
            root / "skills" / "observe" / "schemas" / "output_schema.yaml", orphan
        )
        hand_written = orphan_dir.parent / "notes.yaml"
        hand_written.write_text("kept: true\n")

        check = self._sync(root, "--check")
        assert check.returncode == 1
        assert "skills/retired/schemas/output_schema.yaml" in check.stdout
        assert self._sync(root).returncode == 0
        assert not orphan.exists() and hand_written.exists()
        assert self._sync(root, "--check").returncode == 0

    def test_unbundled_vendored_copy_is_maintained(self, tmp_path: Path) -> None:
        """A skill that vendors a schema without bundling a catalog (receive)
        gets its copy kept current too, instead of drifting unnoticed (#107)."""
        root = self._tree(tmp_path)
        copy = root / "skills" / "receive" / "reference" / "event_schema.yaml"
        assert copy.exists()
        assert not (copy.parent / "workflow_catalog.yaml").exists()
        copy.write_text(copy.read_text() + "# stale\n")

        check = self._sync(root, "--check")
        assert check.returncode == 1
        assert "skills/receive/reference/event_schema.yaml" in check.stdout
        assert self._sync(root).returncode == 0
        assert (
            copy.read_bytes() == (root / "schemas" / "event_schema.yaml").read_bytes()
        )

    def test_vendored_ontology_copies_are_maintained(self, tmp_path: Path) -> None:
        """Every skills/*/reference/capability_ontology.yaml is the ontology
        with its $refs pointed at the co-located copies; a stale one fails
        --check and a sync repairs it."""
        root = self._tree(tmp_path)
        copies = sorted((root / "skills").glob("*/reference/capability_ontology.yaml"))
        assert copies, "expected skills that vendor the ontology"
        stale = copies[0]
        stale.write_text(stale.read_text() + "# stale\n")

        check = self._sync(root, "--check")
        assert check.returncode == 1
        assert str(stale.relative_to(root)) in check.stdout
        assert self._sync(root).returncode == 0
        source = (root / "schemas" / "capability_ontology.yaml").read_text()
        rendered = self._module().render_vendored_ontology(source)
        assert all(copy.read_text() == rendered for copy in copies)

    def test_vendored_ontology_differs_only_in_its_refs(self) -> None:
        """The rendering only points `schemas/event_schema.yaml` at the copy
        beside it, which every vendoring skill has; undone, it is the source."""
        module = self._module()
        source = (ROOT / "schemas" / "capability_ontology.yaml").read_text()
        rendered = module.render_vendored_ontology(source)
        assert "schemas/event_schema.yaml" in source
        assert "schemas/event_schema.yaml" not in rendered
        # Every mention of the file in the source is the repository path, so
        # putting the directory back undoes the rendering.
        assert source.count("event_schema.yaml") == source.count(
            "schemas/event_schema.yaml"
        )
        undone = rendered.replace("event_schema.yaml", "schemas/event_schema.yaml")
        assert undone == source
        for copy in sorted(
            (ROOT / "skills").glob("*/reference/capability_ontology.yaml")
        ):
            assert (copy.parent / "event_schema.yaml").is_file(), copy

    def test_skill_output_schemas_hold_no_ref(self) -> None:
        """Skill-local output schemas are self-contained: the resolved
        contract, with every $ref inlined."""
        for path in sorted((ROOT / "skills").glob("*/schemas/output_schema.yaml")):
            text = path.read_text()
            assert "$ref" not in text, path.relative_to(ROOT)
            assert "STANDARD v1.2 §4.1.2" in text, path.relative_to(ROOT)

    def test_crlf_checkout_is_not_drift(self, tmp_path: Path) -> None:
        root = self._tree(tmp_path)
        for path in (root / "skills").rglob("*.yaml"):
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        assert self._sync(root, "--check").returncode == 0

    def test_vendored_catalog_carries_the_source_version(self) -> None:
        module = self._module()
        rendered = module.render_vendored_catalog(
            (ROOT / "schemas" / "workflow_catalog.yaml").read_text()
        )
        first, second = rendered.splitlines()[:2]
        assert first == self._source_header()
        assert first.startswith("# Standard version: ")
        assert second.startswith("# Vendored copy of schemas/workflow_catalog.yaml")

    def test_sync_does_not_stack_the_repo_level_note(self) -> None:
        for path in sorted((ROOT / "skills").glob("*/reference/workflow_catalog.yaml")):
            assert "(repo-level) (repo-level)" not in path.read_text(), (
                f"{path.relative_to(ROOT)} carries a doubled '(repo-level)' note"
            )


# ─── RFC Validator ───


class TestValidateRFCs:
    """Tests for tools/validate_rfcs.py (issue #104).

    spec/GOVERNANCE.md requires community proposals to arrive as RFCs carrying
    motivation, alternatives, a backward-compatibility analysis, and conformance
    test updates. Nothing enforced that, and RFC-0001 was missing two of them.
    """

    RFC = ROOT / "spec" / "RFC-0002-agent-reliability-profile.md"

    def _fixture(
        self, tmp_path: Path, mutate=None, name: str = "RFC-0009-x.md"
    ) -> Path:
        """Write a valid RFC (optionally mutated) into a throwaway directory."""
        text = self.RFC.read_text().replace("# RFC-0002:", "# RFC-0009:")
        if mutate is not None:
            text = mutate(text)
        directory = tmp_path / "rfcs"
        directory.mkdir(exist_ok=True)
        (directory / name).write_text(text)
        return directory

    def _assert_rejected(self, directory: Path) -> str:
        result = run_validator("validate_rfcs.py", ["--rfc-dir", str(directory)])
        assert result.returncode != 0, f"validator accepted it:\n{result.stdout}"
        assert "FAIL" in result.stdout
        return result.stdout

    def test_passes_with_repository_rfcs(self) -> None:
        result = run_validator("validate_rfcs.py")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout

    def test_verbose_flag_lists_each_rfc(self) -> None:
        result = run_validator("validate_rfcs.py", ["--verbose"])
        assert result.returncode == 0
        assert "RFC-0001" in result.stdout
        assert "RFC-0002" in result.stdout

    def test_accepts_a_valid_fixture(self, tmp_path: Path) -> None:
        result = run_validator(
            "validate_rfcs.py", ["--rfc-dir", str(self._fixture(tmp_path))]
        )
        assert result.returncode == 0, result.stdout

    def test_rejects_missing_governance_section(self, tmp_path: Path) -> None:
        """GOVERNANCE requires a backward-compatibility analysis."""
        directory = self._fixture(
            tmp_path,
            lambda t: t.replace("## Backward compatibility", "## Something else"),
        )
        assert "Backward compatibility" in self._assert_rejected(directory)

    def test_rejects_empty_section(self, tmp_path: Path) -> None:
        def blank_motivation(text: str) -> str:
            start = text.index("## Motivation")
            end = text.index("## Goals")
            return text.replace(text[start:end], "## Motivation\n\n")

        assert "is empty" in self._assert_rejected(
            self._fixture(tmp_path, blank_motivation)
        )

    def test_rejects_malformed_filename(self, tmp_path: Path) -> None:
        directory = self._fixture(tmp_path, name="RFC-9-Bad_Name.md")
        assert "Filename must match" in self._assert_rejected(directory)

    def test_rejects_title_and_filename_number_mismatch(self, tmp_path: Path) -> None:
        directory = self._fixture(
            tmp_path, lambda t: t.replace("# RFC-0009:", "# RFC-0007:")
        )
        assert "Title says RFC-0007" in self._assert_rejected(directory)

    def test_rejects_malformed_status(self, tmp_path: Path) -> None:
        directory = self._fixture(
            tmp_path, lambda t: t.replace("**Status:** Draft", "**Status:** kinda")
        )
        assert "Status" in self._assert_rejected(directory)

    def test_rejects_malformed_date(self, tmp_path: Path) -> None:
        directory = self._fixture(
            tmp_path, lambda t: t.replace("**Date:** 2026-08-29", "**Date:** Aug 2026")
        )
        assert "Date" in self._assert_rejected(directory)

    def test_rejects_phantom_path_reference(self, tmp_path: Path) -> None:
        """An RFC must not cite files that do not exist."""
        directory = self._fixture(
            tmp_path,
            lambda t: t.replace(
                "`grounded_agency/coordination/registry.py`",
                "`grounded_agency/coordination/no_such_file.py`",
                1,
            ),
        )
        assert "does not exist" in self._assert_rejected(directory)

    def test_rejects_duplicate_rfc_numbers(self, tmp_path: Path) -> None:
        directory = self._fixture(tmp_path, name="RFC-0009-a.md")
        self._fixture(tmp_path, name="RFC-0009-b.md")
        assert "Duplicate RFC number" in self._assert_rejected(directory)

    def test_heading_inside_a_fence_does_not_satisfy_a_section(
        self, tmp_path: Path
    ) -> None:
        """A fenced example must not be read as document structure (finding F2).

        This is the false-PASS half: without stripping fences, a required
        heading appearing inside a code sample would satisfy the check while
        the RFC has no such section.
        """
        directory = self._fixture(
            tmp_path,
            lambda t: (
                t.replace("## Backward compatibility", "## Placeholder")
                + "\n\n```md\n## Backward compatibility\nnot a real section\n```\n"
            ),
        )
        assert "Backward compatibility" in self._assert_rejected(directory)

    def test_path_inside_a_fence_is_not_checked_for_existence(
        self, tmp_path: Path
    ) -> None:
        """The false-FAIL half: a path in a YAML sample is illustrative."""
        directory = self._fixture(
            tmp_path,
            lambda t: (
                t
                + "\n\n```yaml\n# see docs/not_a_real_file.md\nref: `docs/not_a_real_file.md`\n```\n"
            ),
        )
        result = run_validator("validate_rfcs.py", ["--rfc-dir", str(directory)])
        assert result.returncode == 0, result.stdout

    def test_tilde_fences_are_stripped_too(self, tmp_path: Path) -> None:
        directory = self._fixture(
            tmp_path,
            lambda t: (
                t.replace("## Backward compatibility", "## Placeholder")
                + "\n\n~~~md\n## Backward compatibility\nnot a real section\n~~~\n"
            ),
        )
        assert "Backward compatibility" in self._assert_rejected(directory)

    def test_unreadable_rfc_fails_cleanly(self, tmp_path: Path) -> None:
        directory = tmp_path / "rfcs"
        directory.mkdir()
        (directory / "RFC-0009-x.md").write_bytes(b"\xff\xfe\x00binary")

        result = run_validator("validate_rfcs.py", ["--rfc-dir", str(directory)])

        assert result.returncode != 0
        assert "Traceback" not in result.stderr, result.stderr
        assert "Could not read" in result.stdout

    # An Accepted RFC records its review window and who accepted it
    # (spec/GOVERNANCE.md, "Decision-making"; issue #164, ORG-201-D).

    def _accepted(
        self,
        tmp_path: Path,
        window: str | None = "2026-11-01 to 2026-11-15",
        accepted_by: str | None = "@maintainer-a",
        name: str = "RFC-0099-x.md",
    ) -> list[str]:
        """Validator args for an Accepted RFC with the given review lines,
        against a CODEOWNERS naming @maintainer-a and @maintainer-b."""
        number = name[4:8]
        lines = ["**Status:** Accepted", "**Target:** Standard v1.3.0"]
        lines.append("**Date:** 2026-11-15")
        if window is not None:
            lines.append(f"**Review window:** {window}")
        if accepted_by is not None:
            lines.append(f"**Accepted by:** {accepted_by}")
        text = self.RFC.read_text().replace("# RFC-0002:", f"# RFC-{number}:")
        text = text.replace("**Status:** Draft", "\n".join(lines[:1]))
        text = text.replace("**Date:** 2026-08-29", "\n".join(lines[2:]))
        directory = tmp_path / "rfcs"
        directory.mkdir(exist_ok=True)
        (directory / name).write_text(text)
        owners = tmp_path / "CODEOWNERS"
        owners.write_text("# owners\n/spec/ @maintainer-a @Maintainer-B\n")
        return ["--rfc-dir", str(directory), "--codeowners", str(owners)]

    def test_accepts_an_accepted_rfc_with_its_review_record(
        self, tmp_path: Path
    ) -> None:
        result = run_validator("validate_rfcs.py", self._accepted(tmp_path))
        assert result.returncode == 0, result.stdout

    def test_approver_handles_match_codeowners_in_any_case(
        self, tmp_path: Path
    ) -> None:
        args = self._accepted(tmp_path, accepted_by="@maintainer-b")
        result = run_validator("validate_rfcs.py", args)
        assert result.returncode == 0, result.stdout

    @pytest.mark.parametrize(
        ("window", "accepted_by", "message"),
        [
            (None, "@maintainer-a", "Review window:"),
            ("2026-11-14 to 2026-11-15", "@maintainer-a", "is 1 days"),
            ("2026-11-01 to 2026-11-16", "@maintainer-a", "ends 2026-11-16"),
            ("2026-11-01 to 2026-11-15", None, "Accepted by:"),
            ("2026-11-01 to 2026-11-15", "the maintainer", "Accepted by:"),
            ("2026-11-01 to 2026-11-15", "@someone-else", "does not name"),
        ],
    )
    def test_rejects_an_accepted_rfc_without_a_valid_review_record(
        self,
        tmp_path: Path,
        window: str | None,
        accepted_by: str | None,
        message: str,
    ) -> None:
        args = self._accepted(tmp_path, window=window, accepted_by=accepted_by)
        result = run_validator("validate_rfcs.py", args)
        assert result.returncode != 0, result.stdout
        assert message in result.stdout

    def test_rfcs_accepted_before_the_rule_are_exempt(self, tmp_path: Path) -> None:
        args = self._accepted(
            tmp_path, window=None, accepted_by=None, name="RFC-0010-x.md"
        )
        result = run_validator("validate_rfcs.py", args)
        assert result.returncode == 0, result.stdout

    def test_review_lines_below_line_eight_are_read(self, tmp_path: Path) -> None:
        """The header runs to the first section, not a fixed eight lines."""
        args = self._accepted(tmp_path)
        rfc = next((tmp_path / "rfcs").glob("RFC-*.md"))
        text = rfc.read_text().replace(
            "**Status:** Accepted", "**Status:** Accepted\n**Note:** a\n**Other:** b"
        )
        rfc.write_text(text)
        result = run_validator("validate_rfcs.py", args)
        assert result.returncode == 0, result.stdout


# ─── Ontology version check ───


class TestCheckOntologyVersion:
    """Tests for tools/check_ontology_version.py (issue #164, ORG-201-E).

    STANDARD §11.6 makes a change to a safety flag, a layer, a capability's
    presence or a requires/precedes/conflicts_with edge a MAJOR change.
    """

    ONTOLOGY = ROOT / "schemas" / "capability_ontology.yaml"

    def _run(self, tmp_path: Path, edit, version: str | None = None):
        import yaml

        head = yaml.safe_load(self.ONTOLOGY.read_text())
        edit(head)
        if version is not None:
            head["meta"]["version"] = version
        path = tmp_path / "head.yaml"
        path.write_text(yaml.safe_dump(head, sort_keys=False))
        return run_validator(
            "check_ontology_version.py",
            ["--base-file", str(self.ONTOLOGY), "--ontology", str(path)],
        )

    @staticmethod
    def _node(ontology: dict, cap: str) -> dict:
        return next(n for n in ontology["nodes"] if n["id"] == cap)

    @staticmethod
    def _module(monkeypatch):
        # The test jobs check out one commit with no tags, so the tag lookup
        # is tested on a stubbed `git tag` listing, not on this repository's.
        monkeypatch.syspath_prepend(str(ROOT / "tools"))
        import check_ontology_version

        return check_ontology_version

    def test_the_base_is_the_newest_release_tag(self, monkeypatch) -> None:
        module = self._module(monkeypatch)
        listing = "v1.2.0\nv2.0.0\nv10.0.0-rc1\nv2.0.10\nv9\nvx\n"
        monkeypatch.setattr(module, "git", lambda *args: listing)
        assert module.latest_release_tag() == "v2.0.10"

    def test_no_release_tag_is_an_error(self, monkeypatch) -> None:
        module = self._module(monkeypatch)
        monkeypatch.setattr(module, "git", lambda *args: "v3.0.0-rc1\n")
        with pytest.raises(RuntimeError, match="no release tag"):
            module.latest_release_tag()

    def test_passes_with_no_change(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, lambda o: None)
        assert result.returncode == 0, result.stdout
        assert "no MAJOR change" in result.stdout

    def test_description_change_needs_no_major(self, tmp_path: Path) -> None:
        def edit(o: dict) -> None:
            self._node(o, "mutate")["description"] = "changed"

        assert self._run(tmp_path, edit).returncode == 0

    @pytest.mark.parametrize(
        ("label", "message"),
        [
            ("flag", "mutate.requires_approval: True -> False"),
            ("absent-flag", "retrieve.mutation_overridable: False -> True"),
            ("layer", "retrieve.layer"),
            ("edge-added", "edge added: retrieve requires detect"),
            ("edge-removed", "edge removed: checkpoint requires mutate"),
            ("capability-removed", "capability recall removed"),
        ],
    )
    def test_breaking_change_fails_without_a_major_bump(
        self, tmp_path: Path, label: str, message: str
    ) -> None:
        def edit(o: dict) -> None:
            if label == "flag":
                self._node(o, "mutate")["requires_approval"] = False
            elif label == "absent-flag":
                self._node(o, "retrieve")["mutation_overridable"] = True
            elif label == "layer":
                self._node(o, "retrieve")["layer"] = "UNDERSTAND"
            elif label == "edge-added":
                o["edges"].append(
                    {"from": "retrieve", "to": "detect", "type": "requires"}
                )
            elif label == "edge-removed":
                o["edges"] = [
                    e
                    for e in o["edges"]
                    if (e["from"], e["to"], e["type"])
                    != ("checkpoint", "mutate", "requires")
                ]
            else:
                o["nodes"] = [n for n in o["nodes"] if n["id"] != "recall"]

        result = self._run(tmp_path, edit, version="2.3.0")
        assert result.returncode != 0, result.stdout
        assert message in result.stdout
        assert "raise it to 3.0.0" in result.stdout

        bumped = self._run(tmp_path, edit, version="3.0.0")
        assert bumped.returncode == 0, bumped.stdout

    def test_soft_edge_change_needs_no_major(self, tmp_path: Path) -> None:
        def edit(o: dict) -> None:
            o["edges"].append({"from": "recall", "to": "plan", "type": "enables"})

        assert self._run(tmp_path, edit).returncode == 0

    def test_fails_when_the_base_cannot_be_read(self) -> None:
        result = run_validator(
            "check_ontology_version.py", ["--base-ref", "no-such-ref-xyz"]
        )
        assert result.returncode != 0
        assert "Traceback" not in result.stderr, result.stderr
        assert "FAIL" in result.stdout


def _resolved_depth(doc: Any, pointer: str) -> tuple[int, int]:
    """How many tokens of an RFC 6901 pointer resolve in ``doc``, and how
    many it has."""
    if pointer == "":
        return 0, 0
    tokens = [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]
    node = doc
    for i, token in enumerate(tokens):
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return i, len(tokens)
    return len(tokens), len(tokens)


def test_every_fixture_diagnostic_has_an_exact_path() -> None:
    """Every diagnostic about a catalog document carries ``location.path``
    (STANDARD v1.2 §9.8), an RFC 6901 pointer that resolves in that
    document (another catalog of the set when ``catalog`` names it), or,
    for a finding about a member that is missing, whose workflow or step
    does; and ``field`` ends with the pointer's last token, so the two name
    the same member. A finding whose pointer is inside a step concerns that
    step, so it carries ``step`` and the step's ``capability`` (§9.8), and
    its ``field`` is relative to the step."""
    import yaml

    from grounded_agency import _core

    fixtures = ROOT / "tests" / "fixtures"
    validator = _core.Validator(ROOT / "schemas" / "capability_ontology.yaml", ROOT)
    expectations = json.loads((fixtures / "EXPECTATIONS.json").read_text())
    # Findings about a member the document lacks: a required field or input,
    # the version, a flag the step does not declare, a plan it does not give.
    missing_members = {"S304", "W605", "W615", "V103", "F501", "W606"}
    for name, meta in expectations.items():
        path = fixtures / f"{name}.workflow_catalog.yaml"
        docs: dict[str | None, Any] = {None: yaml.safe_load(path.read_text())}
        for c in meta.get("catalogs", []):
            doc = yaml.safe_load((fixtures / c).read_text())
            docs[doc["catalog"]["id"]] = doc
        report = validator.validate_file(path, **fixture_set(fixtures, meta))
        for d in report["diagnostics"]:
            loc = d["location"]
            # A finding about a workflow names it in its own catalog: the
            # primary's, or the one `catalog` names (§9.8), header findings
            # included.
            if "workflow" in loc and "profile" not in loc and "tool" not in loc:
                assert loc.get("catalog") in docs, (name, d)
                assert loc["workflow"] in docs[loc.get("catalog")], (name, d)
            if (
                loc.get("field") == "# Standard version"
                or "profile" in loc
                or "tool" in loc
            ):
                assert "path" not in loc, (name, d)
                continue
            assert "path" in loc, (name, d)
            tokens = loc["path"].split("/")
            if "workflow" in loc and len(tokens) > 3 and tokens[2] == "steps":
                assert loc.get("step") == int(tokens[3]), (name, d)
                key = tokens[1].replace("~1", "/").replace("~0", "~")
                wf = docs[loc.get("catalog")][key]
                step = wf["steps"][int(tokens[3])]
                capability = step.get("capability") if isinstance(step, dict) else None
                if isinstance(capability, str):
                    assert loc.get("capability") == capability, (name, d)
                assert not loc.get("field", "").startswith("steps["), (name, d)
            depth, length = _resolved_depth(docs[loc.get("catalog")], loc["path"])
            anchor = (1 if "workflow" in loc else 0) + (2 if "step" in loc else 0)
            assert depth == length or (
                d["code"] in missing_members and depth >= anchor
            ), (name, d)
            if "field" in loc and loc["path"]:
                last = (
                    loc["path"].rsplit("/", 1)[1].replace("~1", "/").replace("~0", "~")
                )
                assert loc["field"].endswith(last) or loc["field"].endswith(
                    f"[{last}]"
                ), (
                    name,
                    d,
                )
