"""Tests for CLI scaffolder (Issue #75)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Ensure tools/ is importable for direct function tests
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from scaffold import (  # noqa: E402
    LAYERS,
    NAME_MAX,
    validate_name,
)

SCAFFOLD_PY = TOOLS_DIR / "scaffold.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_ontology(tmp_path: Path) -> Path:
    """Create a minimal ontology file for isolated tests."""
    ontology = {
        "meta": {
            "name": "Test Ontology",
            "version": "1.0.0",
            "description": "Test ontology",
        },
        "layers": {
            layer: {
                "description": f"{layer} layer",
                "capabilities": ["retrieve"] if layer == "PERCEIVE" else [],
            }
            for layer in LAYERS
        },
        "nodes": [
            {
                "id": "retrieve",
                "layer": "PERCEIVE",
                "description": "Existing capability",
                "risk": "low",
                "mutation": False,
            },
        ],
        "edges": [],
    }
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    ontology_path = schemas_dir / "capability_ontology.yaml"
    with open(ontology_path, "w", encoding="utf-8") as f:
        yaml.dump(ontology, f, default_flow_style=False, sort_keys=False)

    return ontology_path


def _make_minimal_catalog(tmp_path: Path) -> Path:
    """Create a minimal workflow catalog for isolated tests."""
    catalog = {
        "existing_workflow": {
            "goal": "An existing workflow",
            "risk": "low",
            "steps": [],
            "success": ["done"],
        },
    }
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = schemas_dir / "workflow_catalog.yaml"
    with open(catalog_path, "w", encoding="utf-8") as f:
        yaml.dump(catalog, f, default_flow_style=False, sort_keys=False)
    return catalog_path


def _make_skill_template(tmp_path: Path) -> Path:
    """Create a minimal skill template for isolated tests."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    template_path = templates_dir / "SKILL_TEMPLATE_ENHANCED.md"
    content = """\
# Enhanced Skill Template

```markdown
---
name: <capability-name>
description: <verb phrase describing what this capability does>. Use when needed.
allowed-tools: <comma-separated list from ontology default_tools>
agent: <explore|general-purpose>
---

## Safety Constraints

- `mutation`: <true|false from ontology>
- `requires_checkpoint`: <true|false from ontology>
- `requires_approval`: <true|false from ontology>
- `risk`: <low|medium|high from ontology>
```

---

## Template Usage Guidelines
"""
    template_path.write_text(content, encoding="utf-8")
    return template_path


def _make_profiles_dir(tmp_path: Path) -> Path:
    """Create a profiles directory with an existing profile."""
    profiles_dir = tmp_path / "schemas" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    existing = profiles_dir / "existing-prof.yaml"
    existing.write_text("domain: existing-prof\n", encoding="utf-8")
    return profiles_dir


def _setup_isolated_repo(tmp_path: Path) -> Path:
    """Set up a complete isolated repo structure for testing."""
    _make_minimal_ontology(tmp_path)
    _make_minimal_catalog(tmp_path)
    _make_skill_template(tmp_path)
    _make_profiles_dir(tmp_path)
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _run_scaffold(args: list[str]) -> subprocess.CompletedProcess:
    """Run scaffold.py as a subprocess."""
    cmd = [sys.executable, str(SCAFFOLD_PY)] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Monkey-patch helper for unit tests
# ---------------------------------------------------------------------------


def _run_main_isolated(tmp_path: Path, argv: list[str]) -> None:
    """Run scaffold main() with REPO_ROOT patched to tmp_path."""
    import scaffold as scaffold_mod

    original_root = scaffold_mod.REPO_ROOT
    scaffold_mod.REPO_ROOT = tmp_path
    try:
        scaffold_mod.main(argv)
    finally:
        scaffold_mod.REPO_ROOT = original_root


# ===========================================================================
# TestNameValidation
# ===========================================================================


class TestNameValidation:
    """Test name validation for all subcommands."""

    def test_valid_simple_name(self) -> None:
        assert validate_name("detect") is None

    def test_valid_kebab_case(self) -> None:
        assert validate_name("detect-anomaly") is None

    def test_valid_with_digits(self) -> None:
        assert validate_name("step2-check") is None

    def test_valid_min_length(self) -> None:
        assert validate_name("ab") is None

    def test_valid_max_length(self) -> None:
        name = "a" * NAME_MAX
        assert validate_name(name) is None

    def test_reject_uppercase(self) -> None:
        err = validate_name("Detect")
        assert err is not None
        assert "kebab-case" in err

    def test_reject_spaces(self) -> None:
        err = validate_name("detect anomaly")
        assert err is not None

    def test_reject_underscores(self) -> None:
        err = validate_name("detect_anomaly")
        assert err is not None

    def test_reject_special_chars(self) -> None:
        err = validate_name("detect@anomaly")
        assert err is not None

    def test_reject_too_short(self) -> None:
        err = validate_name("a")
        assert err is not None
        assert "at least" in err

    def test_reject_too_long(self) -> None:
        name = "a" * (NAME_MAX + 1)
        err = validate_name(name)
        assert err is not None
        assert "at most" in err

    def test_reject_leading_hyphen(self) -> None:
        err = validate_name("-detect")
        assert err is not None

    def test_reject_trailing_hyphen(self) -> None:
        err = validate_name("detect-")
        assert err is not None

    def test_reject_empty(self) -> None:
        err = validate_name("")
        assert err is not None


# ===========================================================================
# TestCapabilityScaffold
# ===========================================================================


class TestCapabilityScaffold:
    """Test capability scaffolding."""

    def test_dry_run_no_files_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Dry-run should print actions without writing files."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "test-cap",
                "--layer",
                "PERCEIVE",
                "--dry-run",
            ],
        )
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "test-cap" in out
        # No skill directory should be created
        assert not (tmp_path / "skills" / "test-cap").exists()

    def test_create_valid_capability(self, tmp_path: Path) -> None:
        """Creating a valid capability adds to ontology and creates skill."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "test-cap",
                "--layer",
                "PERCEIVE",
            ],
        )

        # Check ontology was updated
        ontology_path = tmp_path / "schemas" / "capability_ontology.yaml"
        with open(ontology_path, encoding="utf-8") as f:
            ontology = yaml.safe_load(f)

        node_ids = [n["id"] for n in ontology["nodes"]]
        assert "test-cap" in node_ids

        # Check the node properties
        new_node = next(n for n in ontology["nodes"] if n["id"] == "test-cap")
        assert new_node["layer"] == "PERCEIVE"
        assert new_node["risk"] == "low"
        assert new_node["mutation"] is False
        assert new_node["requires_checkpoint"] is False

        # Check layer capabilities updated
        assert "test-cap" in ontology["layers"]["PERCEIVE"]["capabilities"]

        # Check skill files created
        skill_path = tmp_path / "skills" / "test-cap" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text(encoding="utf-8")
        assert "test-cap" in content

    def test_duplicate_name_rejected(self, tmp_path: Path) -> None:
        """Attempting to create a capability with an existing name should fail."""
        _setup_isolated_repo(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            _run_main_isolated(
                tmp_path,
                [
                    "capability",
                    "retrieve",
                    "--layer",
                    "PERCEIVE",
                ],
            )
        assert exc_info.value.code == 1

    def test_invalid_layer_rejected(self, tmp_path: Path) -> None:
        """An invalid layer name should be rejected by argparse."""
        _setup_isolated_repo(tmp_path)
        with pytest.raises(SystemExit):
            _run_main_isolated(
                tmp_path,
                [
                    "capability",
                    "test-cap",
                    "--layer",
                    "INVALID",
                ],
            )

    def test_mutation_flag(self, tmp_path: Path) -> None:
        """--mutation flag should set mutation=true and requires_checkpoint=true."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "mutate-data",
                "--layer",
                "EXECUTE",
                "--mutation",
            ],
        )

        ontology_path = tmp_path / "schemas" / "capability_ontology.yaml"
        with open(ontology_path, encoding="utf-8") as f:
            ontology = yaml.safe_load(f)

        new_node = next(n for n in ontology["nodes"] if n["id"] == "mutate-data")
        assert new_node["mutation"] is True
        assert new_node["requires_checkpoint"] is True

    def test_skill_directory_created(self, tmp_path: Path) -> None:
        """Skill directory and SKILL.md should exist after creation."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "my-skill",
                "--layer",
                "REASON",
            ],
        )
        skill_dir = tmp_path / "skills" / "my-skill"
        assert skill_dir.is_dir()
        assert (skill_dir / "SKILL.md").is_file()

    def test_ontology_node_added_correctly(self, tmp_path: Path) -> None:
        """The new node should have correct input/output schema."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "analyze-data",
                "--layer",
                "UNDERSTAND",
                "--risk",
                "medium",
            ],
        )

        ontology_path = tmp_path / "schemas" / "capability_ontology.yaml"
        with open(ontology_path, encoding="utf-8") as f:
            ontology = yaml.safe_load(f)

        new_node = next(n for n in ontology["nodes"] if n["id"] == "analyze-data")
        assert new_node["risk"] == "medium"
        assert "target" in new_node["input_schema"]["required"]
        assert "result" in new_node["output_schema"]["required"]
        assert "evidence_anchors" in new_node["output_schema"]["required"]
        assert "confidence" in new_node["output_schema"]["required"]

    def test_layer_capabilities_updated(self, tmp_path: Path) -> None:
        """The layer's capabilities list should include the new capability."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "plan-step",
                "--layer",
                "REASON",
            ],
        )

        ontology_path = tmp_path / "schemas" / "capability_ontology.yaml"
        with open(ontology_path, encoding="utf-8") as f:
            ontology = yaml.safe_load(f)

        assert "plan-step" in ontology["layers"]["REASON"]["capabilities"]

    def test_low_risk_uses_explore_agent(self, tmp_path: Path) -> None:
        """Low risk capabilities should use explore agent."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "scan-data",
                "--layer",
                "PERCEIVE",
                "--risk",
                "low",
            ],
        )
        skill_content = (tmp_path / "skills" / "scan-data" / "SKILL.md").read_text()
        assert "agent: explore" in skill_content

    def test_high_risk_uses_general_purpose_agent(self, tmp_path: Path) -> None:
        """High risk capabilities should use general-purpose agent."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "deploy-code",
                "--layer",
                "EXECUTE",
                "--risk",
                "high",
            ],
        )
        skill_content = (tmp_path / "skills" / "deploy-code" / "SKILL.md").read_text()
        assert "agent: general-purpose" in skill_content

    def test_mutation_adds_edit_bash_tools(self, tmp_path: Path) -> None:
        """Mutation capabilities should include Edit and Bash in allowed tools."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "capability",
                "write-file",
                "--layer",
                "EXECUTE",
                "--mutation",
            ],
        )
        skill_content = (tmp_path / "skills" / "write-file" / "SKILL.md").read_text()
        assert "Edit" in skill_content
        assert "Bash" in skill_content


# ===========================================================================
# TestWorkflowScaffold
# ===========================================================================


class TestWorkflowScaffold:
    """Test workflow scaffolding."""

    def test_dry_run_no_files_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Dry-run should print actions without modifying the catalog."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(
            tmp_path,
            [
                "workflow",
                "test-wf",
                "--dry-run",
            ],
        )
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "test_wf" in out

        # Catalog should not have the new workflow
        catalog_path = tmp_path / "schemas" / "workflow_catalog.yaml"
        with open(catalog_path, encoding="utf-8") as f:
            catalog = yaml.safe_load(f)
        assert "test_wf" not in catalog

    def test_create_valid_workflow(self, tmp_path: Path) -> None:
        """Creating a valid workflow adds a stub to the catalog."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["workflow", "my-workflow"])

        catalog_path = tmp_path / "schemas" / "workflow_catalog.yaml"
        with open(catalog_path, encoding="utf-8") as f:
            catalog = yaml.safe_load(f)

        assert "my_workflow" in catalog
        wf = catalog["my_workflow"]
        assert wf["goal"] == "TODO: Define workflow goal"
        assert wf["risk"] == "low"
        assert len(wf["steps"]) == 1
        assert wf["steps"][0]["capability"] == "retrieve"

    def test_duplicate_workflow_rejected(self, tmp_path: Path) -> None:
        """Attempting to create a workflow with an existing name should fail."""
        _setup_isolated_repo(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            _run_main_isolated(tmp_path, ["workflow", "existing-workflow"])
        assert exc_info.value.code == 1

    def test_workflow_has_success_section(self, tmp_path: Path) -> None:
        """New workflow should have a success array of strings."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["workflow", "check-workflow"])

        catalog_path = tmp_path / "schemas" / "workflow_catalog.yaml"
        with open(catalog_path, encoding="utf-8") as f:
            catalog = yaml.safe_load(f)

        wf = catalog["check_workflow"]
        assert isinstance(wf["success"], list)
        assert len(wf["success"]) > 0
        assert all(isinstance(s, str) for s in wf["success"])

    def test_workflow_step_has_failure_modes(self, tmp_path: Path) -> None:
        """Workflow steps should include failure_modes with schema-compliant fields."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["workflow", "fail-mode-wf"])

        catalog_path = tmp_path / "schemas" / "workflow_catalog.yaml"
        with open(catalog_path, encoding="utf-8") as f:
            catalog = yaml.safe_load(f)

        step = catalog["fail_mode_wf"]["steps"][0]
        assert "failure_modes" in step
        assert len(step["failure_modes"]) > 0
        fm = step["failure_modes"][0]
        assert "condition" in fm
        assert "action" in fm
        assert "recovery" in fm


# ===========================================================================
# TestProfileScaffold
# ===========================================================================


class TestProfileScaffold:
    """Test profile scaffolding."""

    def test_dry_run_no_files_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Dry-run should print actions without creating the profile file."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["profile", "test-prof", "--dry-run"])
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "test-prof" in out
        assert not (tmp_path / "schemas" / "profiles" / "test-prof.yaml").exists()

    def test_create_valid_profile(self, tmp_path: Path) -> None:
        """Creating a valid profile writes a YAML file."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["profile", "my-domain"])

        profile_path = tmp_path / "schemas" / "profiles" / "my-domain.yaml"
        assert profile_path.exists()

        with open(profile_path, encoding="utf-8") as f:
            profile = yaml.safe_load(f)

        assert profile["domain"] == "my-domain"
        assert profile["version"] == "1.0.0"
        assert "trust_weights" in profile
        assert "risk_thresholds" in profile
        assert "checkpoint_policy" in profile
        assert "evidence_policy" in profile
        assert profile["trust_model_reviewed"] is False

    def test_duplicate_profile_rejected(self, tmp_path: Path) -> None:
        """Attempting to create a profile that already exists should fail."""
        _setup_isolated_repo(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            _run_main_isolated(tmp_path, ["profile", "existing-prof"])
        assert exc_info.value.code == 1

    def test_profile_has_required_schema_fields(self, tmp_path: Path) -> None:
        """Profile should have all fields required by profile_schema.yaml."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["profile", "schema-check"])

        profile_path = tmp_path / "schemas" / "profiles" / "schema-check.yaml"
        with open(profile_path, encoding="utf-8") as f:
            profile = yaml.safe_load(f)

        # Required fields from profile_schema.yaml
        required = [
            "domain",
            "version",
            "trust_weights",
            "risk_thresholds",
            "checkpoint_policy",
            "evidence_policy",
        ]
        for field in required:
            assert field in profile, f"Missing required field: {field}"

    def test_profile_trust_weights_valid(self, tmp_path: Path) -> None:
        """Trust weights should be between 0 and 1."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["profile", "trust-check"])

        profile_path = tmp_path / "schemas" / "profiles" / "trust-check.yaml"
        with open(profile_path, encoding="utf-8") as f:
            profile = yaml.safe_load(f)

        for key, value in profile["trust_weights"].items():
            assert 0.0 <= value <= 1.0, f"trust_weights.{key} out of range: {value}"

    def test_profile_evidence_confidence_valid(self, tmp_path: Path) -> None:
        """Evidence minimum_confidence should be between 0 and 1."""
        _setup_isolated_repo(tmp_path)
        _run_main_isolated(tmp_path, ["profile", "evidence-check"])

        profile_path = tmp_path / "schemas" / "profiles" / "evidence-check.yaml"
        with open(profile_path, encoding="utf-8") as f:
            profile = yaml.safe_load(f)

        conf = profile["evidence_policy"]["minimum_confidence"]
        assert 0.0 <= conf <= 1.0


# ===========================================================================
# TestCLIInterface
# ===========================================================================


class TestCLIInterface:
    """Test CLI argument parsing."""

    def test_no_subcommand_shows_help(self) -> None:
        """Running with no subcommand should exit with code 1."""
        result = _run_scaffold([])
        assert result.returncode == 1

    def test_help_output(self) -> None:
        """--help should show usage information."""
        result = _run_scaffold(["--help"])
        assert result.returncode == 0
        assert "scaffold" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_capability_help(self) -> None:
        """capability --help should show capability options."""
        result = _run_scaffold(["capability", "--help"])
        assert result.returncode == 0
        assert "--layer" in result.stdout

    def test_workflow_help(self) -> None:
        """workflow --help should show workflow options."""
        result = _run_scaffold(["workflow", "--help"])
        assert result.returncode == 0
        assert "name" in result.stdout.lower()

    def test_profile_help(self) -> None:
        """profile --help should show profile options."""
        result = _run_scaffold(["profile", "--help"])
        assert result.returncode == 0
        assert "name" in result.stdout.lower()

    def test_capability_missing_layer(self) -> None:
        """capability without --layer should fail."""
        result = _run_scaffold(["capability", "test-cap"])
        assert result.returncode != 0

    def test_capability_dry_run_flag(self) -> None:
        """capability --dry-run should run without errors."""
        result = _run_scaffold(
            [
                "capability",
                "test-cap",
                "--layer",
                "PERCEIVE",
                "--dry-run",
            ]
        )
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout

    def test_workflow_dry_run_flag(self) -> None:
        """workflow --dry-run should run without errors."""
        result = _run_scaffold(["workflow", "test-wf", "--dry-run"])
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout

    def test_profile_dry_run_flag(self) -> None:
        """profile --dry-run should run without errors."""
        result = _run_scaffold(["profile", "test-prof", "--dry-run"])
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout

    def test_invalid_name_via_cli(self) -> None:
        """Invalid name should produce a non-zero exit code."""
        result = _run_scaffold(
            [
                "capability",
                "INVALID_NAME",
                "--layer",
                "PERCEIVE",
                "--dry-run",
            ]
        )
        assert result.returncode == 1
        assert "Error" in result.stderr
