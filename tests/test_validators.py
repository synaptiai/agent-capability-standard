"""Unit tests for validator tools (TEST-004).

Tests all 5 validators: ontology, workflows, profiles, skill refs, yaml sync.
"""

from __future__ import annotations

import json
import shutil
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
        # Import the helper by manipulating its module-level constant
        import scripts.run_conformance as rc

        original = rc.SUGGESTIONS_JSON
        try:
            rc.SUGGESTIONS_JSON = tmp_path / "nonexistent.json"
            assert rc._read_emitted_codes() == set()
        finally:
            rc.SUGGESTIONS_JSON = original

    def test_read_emitted_codes_valid_json(self, tmp_path: Path) -> None:
        """Returns correct codes from well-formed suggestions JSON."""
        import scripts.run_conformance as rc

        original = rc.SUGGESTIONS_JSON
        try:
            f = tmp_path / "suggestions.json"
            f.write_text(
                json.dumps(
                    {
                        "structured_errors": [
                            {
                                "code": "V101",
                                "name": "UNKNOWN_CAPABILITY",
                                "message": "test",
                            },
                            {
                                "code": "V104",
                                "name": "DUPLICATE_STORE_AS",
                                "message": "test",
                            },
                        ]
                    }
                )
            )
            rc.SUGGESTIONS_JSON = f
            assert rc._read_emitted_codes() == {"V101", "V104"}
        finally:
            rc.SUGGESTIONS_JSON = original

    def test_read_emitted_codes_malformed_json(self, tmp_path: Path) -> None:
        """Returns empty set on malformed JSON."""
        import scripts.run_conformance as rc

        original = rc.SUGGESTIONS_JSON
        try:
            f = tmp_path / "bad.json"
            f.write_text("{not valid json")
            rc.SUGGESTIONS_JSON = f
            assert rc._read_emitted_codes() == set()
        finally:
            rc.SUGGESTIONS_JSON = original

    def test_clear_suggestions_removes_file(self, tmp_path: Path) -> None:
        """_clear_suggestions deletes the file if it exists."""
        import scripts.run_conformance as rc

        original = rc.SUGGESTIONS_JSON
        try:
            f = tmp_path / "suggestions.json"
            f.write_text("{}")
            rc.SUGGESTIONS_JSON = f
            rc._clear_suggestions()
            assert not f.exists()
        finally:
            rc.SUGGESTIONS_JSON = original

    def test_clear_suggestions_noop_when_missing(self, tmp_path: Path) -> None:
        """_clear_suggestions is a no-op when file doesn't exist."""
        import scripts.run_conformance as rc

        original = rc.SUGGESTIONS_JSON
        try:
            rc.SUGGESTIONS_JSON = tmp_path / "nonexistent.json"
            rc._clear_suggestions()  # should not raise
        finally:
            rc.SUGGESTIONS_JSON = original


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

    def test_catches_source_ranking_asymmetry(self, tmp_path: Path) -> None:
        self._assert_drift_is_caught(
            tmp_path,
            "authority_trust_model.yaml",
            "    human_note: 0.55",
            "    human_note: 0.55\n    ghost_source: 0.5",
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
            tmp_path, "entity_taxonomy.yaml", "  version: 1.0.0", "  version: v1"
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

    def test_sync_is_idempotent(self) -> None:
        """Re-running the sync on a synced tree must change nothing.

        The comment rewrite `schemas/workflows/` -> `(repo-level)
        schemas/workflows/` used to reapply itself to already-rewritten text,
        so each run stacked another `(repo-level)` prefix onto the 17 bundled
        catalogs. CLAUDE.md documents this command, so following the project's
        own instructions corrupted those files.
        """
        catalogs = sorted((ROOT / "skills").glob("*/reference/workflow_catalog.yaml"))
        assert catalogs, "expected bundled workflow catalogs"
        before = {path: path.read_text() for path in catalogs}

        # The sync writes to the tracked tree, so anything it changes is
        # restored before this test returns. Without that, a failure -- or a
        # concurrent checkout of a branch whose sync tool predates the
        # idempotency fix -- leaves the repository dirty.
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "sync_skill_schemas.py")],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, result.stdout + result.stderr

            drifted = [
                path.relative_to(ROOT)
                for path, original in before.items()
                if path.read_text() != original
            ]
            assert not drifted, (
                f"{drifted} changed on a no-op sync; "
                f"sync_skill_schemas.py is not idempotent"
            )
        finally:
            for path, original in before.items():
                if path.read_text() != original:
                    path.write_text(original)

    def test_rewrite_heals_already_doubled_prefixes(self) -> None:
        """The rewrite must collapse existing stacking, not merely stop adding.

        Replacing one layer then re-applying makes double-prefixed content a
        fixed point: the sync would preserve corruption a previous run wrote
        rather than repairing it.
        """
        import importlib.util

        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location(
            "sync_skill_schemas", ROOT / "tools" / "sync_skill_schemas.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["sync_skill_schemas"] = module
        spec.loader.exec_module(module)

        old_prefix, new_prefix = next(
            iter(module.WORKFLOW_CATALOG_COMMENT_REWRITES.items())
        )
        note = new_prefix[: -len(old_prefix)]  # e.g. "(repo-level) "
        expected = f"#   - {new_prefix}x.yaml"

        for layers in (0, 1, 2, 3):
            content = f"#   - {note * layers}{old_prefix}x.yaml"

            # The rewrite as implemented in bundle_workflow_catalog_deps.
            while new_prefix in content:
                content = content.replace(new_prefix, old_prefix)
            content = content.replace(old_prefix, new_prefix)

            assert content == expected, (
                f"{layers} stacked note(s) collapsed to {content!r}, "
                f"expected {expected!r}"
            )

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
