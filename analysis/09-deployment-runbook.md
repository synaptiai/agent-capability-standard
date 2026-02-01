# Deployment Runbook

## Document Metadata

| Field           | Value                                      |
|-----------------|--------------------------------------------|
| Document        | `analysis/09-deployment-runbook.md`        |
| Project         | Agent Capability Standard                  |
| Version         | 0.1.0                                      |
| Last Updated    | 2026-01-30                                 |
| Status          | Active                                     |

---

## Table of Contents

1. [Distribution Channels](#1-distribution-channels)
2. [Release Checklist](#2-release-checklist)
3. [Configuration Management](#3-configuration-management)
4. [Version Management Strategy](#4-version-management-strategy)
5. [Monitoring](#5-monitoring)
6. [Rollback Procedures](#6-rollback-procedures)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Distribution Channels

The Agent Capability Standard is distributed through three independent channels. Each channel serves a different consumer audience and follows its own packaging conventions.

### 1.1 Claude Code Plugin Marketplace (Synapti)

**Target audience:** Claude Code users who want capability skills, safety hooks, and workflow validation integrated directly into their agent sessions.

**Marketplace repository:** `synaptiai/synapti-marketplace`

**Installation commands:**

```bash
# Add the Synapti marketplace (one-time setup)
claude plugin marketplace add synaptiai/synapti-marketplace

# Install the plugin
claude plugin install agent-capability-standard
```

**What gets installed:**

| Component | Source Path | Description |
|-----------|-----------|-------------|
| 36 Skills | `skills/*/SKILL.md` | Atomic capability implementations organized by cognitive layer |
| Workflow Patterns | `schemas/workflow_catalog.yaml` | 12 composed workflows with typed bindings and recovery loops |
| Safety Hooks | `hooks/hooks.json` | PreToolUse checkpoint enforcement + PostToolUse audit logging |
| Domain Profiles | `schemas/profiles/*.yaml` | Trust weights, risk thresholds, checkpoint/evidence policies |
| Ontology Schema | `schemas/capability_ontology.yaml` | 36-capability ontology with I/O contracts |

**Plugin manifest:** `.claude-plugin/plugin.json`

```json
{
  "name": "agent-capability-standard",
  "version": "1.0.5",
  "description": "Grounded Agency: 36 atomic capabilities across 9 cognitive layers...",
  "author": {
    "name": "Agent Capability Standard Contributors",
    "url": "https://github.com/synaptiai/agent-capability-standard"
  },
  "homepage": "https://github.com/synaptiai/agent-capability-standard",
  "repository": "https://github.com/synaptiai/agent-capability-standard",
  "license": "Apache-2.0",
  "skills": "./skills/"
}
```

The `skills` field points Claude Code to the flat skill directory structure. Each skill subdirectory contains a `SKILL.md` file with YAML frontmatter declaring `name`, `description`, `allowed-tools`, `agent` type, and `layer`. The hooks are loaded from `hooks/hooks.json` and enforce checkpoint-before-mutation and audit-after-skill policies structurally.

### 1.2 PyPI Package (grounded-agency)

**Target audience:** Python developers integrating the Grounded Agency safety layer into Claude Agent SDK workflows.

**Package name:** `grounded-agency`
**Build system:** Hatchling (`hatchling.build`)
**Minimum Python:** 3.10+
**License:** MIT

**Install commands:**

```bash
# Core package (PyYAML only)
pip install grounded-agency

# With Claude Agent SDK integration
pip install grounded-agency[sdk]

# With development tools (pytest, mypy, ruff)
pip install grounded-agency[dev]

# Everything
pip install grounded-agency[all]
```

**Package contents (wheel target):**

The wheel includes only the `grounded_agency/` Python package. The sdist target additionally bundles `schemas/` and `skills/` directories so consumers can access the ontology and skill definitions at build time.

```toml
# pyproject.toml build targets
[tool.hatch.build.targets.wheel]
packages = ["grounded_agency"]

[tool.hatch.build.targets.sdist]
include = ["/grounded_agency", "/schemas", "/skills"]
```

**Dependencies:**

| Dependency | Version | Required For |
|-----------|---------|-------------|
| `pyyaml` | >=6.0 | Core (ontology/schema parsing) |
| `claude-agent-sdk` | >=0.1.0 | Optional `[sdk]` extra |
| `pytest` | >=7.0 | Optional `[dev]` extra |
| `pytest-asyncio` | >=0.21 | Optional `[dev]` extra |
| `mypy` | >=1.0 | Optional `[dev]` extra |
| `ruff` | >=0.1.0 | Optional `[dev]` extra |

**Key exported components:**

| Component | Class | Purpose |
|-----------|-------|---------|
| Main adapter | `GroundedAgentAdapter` | Wraps SDK options with safety layer |
| Config | `GroundedAgentConfig` | Configuration dataclass (strict_mode, etc.) |
| Registry | `CapabilityRegistry` | Loads and queries `capability_ontology.yaml` |
| Mapper | `ToolCapabilityMapper` | Maps SDK tools to capability metadata |
| Checkpoint | `CheckpointTracker` | Manages checkpoint lifecycle for mutation safety |
| Evidence | `EvidenceStore` | Collects evidence anchors from tool executions |

### 1.3 GitHub Source Distribution

**Repository:** `https://github.com/synaptiai/agent-capability-standard`

**Target audience:** Contributors, auditors, and users who want the full source tree including archived files, documentation, methodology, and validator tools.

**Clone and setup:**

```bash
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard
python -m venv .venv && source .venv/bin/activate
pip install pyyaml

# Editable install with all extras
pip install -e ".[all]"
```

**Release artifacts:** GitHub Releases should include:
- Tagged source archives (`.tar.gz`, `.zip`)
- Wheel and sdist (same artifacts uploaded to PyPI)
- Release notes linking to the CHANGELOG entry

---

## 2. Release Checklist

The following steps must be completed in order for each release. Steps marked with [GATE] are blocking -- if they fail, the release must not proceed.

### Step 1: Update Version in pyproject.toml

**File:** `pyproject.toml`
**Field:** `project.version`
**Current value:** `0.1.0`

```toml
[project]
name = "grounded-agency"
version = "0.2.0"  # Update from 0.1.0
```

Follow semantic versioning: MAJOR for breaking API changes, MINOR for new features, PATCH for bug fixes. The SDK package is currently in pre-1.0 development (`0.x.y`), meaning any MINOR bump may include breaking changes per SemVer convention.

### Step 2: Update Version in .claude-plugin/plugin.json

**File:** `.claude-plugin/plugin.json`
**Field:** `version`
**Current value:** `1.0.5`

```json
{
  "version": "1.0.6"
}
```

The plugin version follows its own track. It is already at `1.x.y` because the plugin capability set (skills, hooks, ontology) was considered stable before the SDK package was published. Increment the PATCH for skill updates and hook changes, MINOR for new capabilities or workflow additions, MAJOR for ontology restructuring.

### Step 3: Update __version__ in grounded_agency/__init__.py

**File:** `grounded_agency/__init__.py`
**Field:** `__version__`
**Current value:** `0.1.0`

```python
__version__ = "0.2.0"  # Must match pyproject.toml
```

This value must exactly match the version in `pyproject.toml`. It is the runtime-accessible version (accessible via `grounded_agency.__version__` or `importlib.metadata.version("grounded-agency")`).

### Step 4: Run All 5 Validators [GATE]

Each validator must exit with code 0. Any failure blocks the release.

```bash
# 1. Validate workflow definitions against the ontology
python tools/validate_workflows.py
# Expected output: VALIDATION PASS

# 2. Validate domain profiles against profile schema
python tools/validate_profiles.py
# Expected output: All profiles valid

# 3. Validate skill file references (no phantom paths)
python tools/validate_skill_refs.py
# Expected output: All skill references valid

# 4. Validate ontology graph (orphans, cycles, symmetry)
python tools/validate_ontology.py
# Expected output: Ontology graph valid

# 5. Sync and verify skill-local schemas
python tools/sync_skill_schemas.py
# Expected output: All schemas in sync
```

**One-liner for CI:**

```bash
python tools/validate_workflows.py && \
python tools/validate_profiles.py && \
python tools/validate_skill_refs.py && \
python tools/validate_ontology.py && \
python tools/sync_skill_schemas.py
```

### Step 5: Run All Tests [GATE]

```bash
pytest tests/ -v
```

This runs:
- `tests/test_sdk_integration.py` -- SDK class unit tests (CapabilityRegistry, ToolCapabilityMapper, CheckpointTracker, EvidenceStore, GroundedAgentAdapter)
- `tests/test_oasf_adapter.py` -- OASF compatibility adapter tests

All tests must pass. The pytest configuration in `pyproject.toml` sets `testpaths = ["tests"]`, `asyncio_mode = "auto"`, and `addopts = "-v"`.

### Step 6: Run Type Checking [GATE]

```bash
mypy grounded_agency/
```

The mypy configuration in `pyproject.toml` enforces:
- `python_version = "3.10"` (minimum supported version)
- `warn_return_any = true`
- `warn_unused_configs = true`
- `disallow_untyped_defs = true`
- Excludes `.venv/` and `_archive/`

Zero errors required for release.

### Step 7: Run Linting [GATE]

```bash
ruff check .
```

The ruff configuration in `pyproject.toml` targets Python 3.10, enforces 88-character lines, and selects rule sets: E (pycodestyle errors), W (pycodestyle warnings), F (pyflakes), I (isort), B (flake8-bugbear), C4 (flake8-comprehensions), UP (pyupgrade). The only ignored rule is E501 (line length, handled by formatter).

Zero violations required for release.

### Step 8: Run Conformance Tests [GATE]

```bash
python scripts/run_conformance.py
```

The conformance runner (`scripts/run_conformance.py`) tests the reference validator against fixture workflow catalogs located in `tests/`. For each fixture, it temporarily swaps `schemas/workflow_catalog.yaml` with the fixture content, runs `tools/validate_workflows.py`, and checks the exit code against the expected result defined in `tests/EXPECTATIONS.json`.

**Output artifacts:**
- Console: `Conformance PASSED (N/N)` or `Conformance FAILED`
- File: `conformance_results.json` (written to project root)

### Step 9: Update CHANGELOG

Document changes for the release version. Group changes by category:
- **Added** -- New capabilities, workflows, profiles, or features
- **Changed** -- Modifications to existing behavior
- **Fixed** -- Bug fixes
- **Deprecated** -- Features to be removed in future versions
- **Removed** -- Removed features
- **Security** -- Security-related fixes

### Step 10: Build Package

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build sdist and wheel
python -m build
```

This produces:
- `dist/grounded_agency-0.2.0.tar.gz` (sdist with schemas/ and skills/)
- `dist/grounded_agency-0.2.0-py3-none-any.whl` (wheel with grounded_agency/ only)

Verify the built artifacts:

```bash
# Check wheel contents
python -m zipfile -l dist/grounded_agency-*.whl

# Check sdist contents
tar tzf dist/grounded_agency-*.tar.gz | head -20
```

### Step 11: Tag Release

```bash
git add -A
git commit -m "release: v0.2.0"
git tag -a v0.2.0 -m "Release v0.2.0 -- description of changes"
git push origin main --tags
```

Use annotated tags (`-a`) for releases so they carry the tagger identity and message. Lightweight tags are acceptable only for pre-releases and release candidates.

### Step 12: Publish to PyPI

```bash
# Upload to PyPI (requires API token)
twine upload dist/*

# Verify installation from PyPI
pip install grounded-agency==0.2.0
python -c "import grounded_agency; print(grounded_agency.__version__)"
```

For first-time publishing, configure `~/.pypirc` with your API token or use `twine upload --repository pypi dist/* --username __token__ --password pypi-<token>`.

**Test PyPI (recommended for pre-releases):**

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ grounded-agency==0.2.0
```

### Step 13: Update Marketplace Listing

After the PyPI release and GitHub tag are confirmed:

1. Update the marketplace entry in `synaptiai/synapti-marketplace` to reference the new plugin version
2. Verify installation from marketplace:

```bash
claude plugin install agent-capability-standard
```

3. Test that skills load correctly, hooks fire as expected, and the ontology version matches

---

## 3. Configuration Management

### 3.1 Domain Profiles

**Location:** `schemas/profiles/*.yaml`
**Schema:** `schemas/profiles/profile_schema.yaml`

Domain profiles configure the Grounded Agency behavior for specific operational contexts. Each profile defines four required sections:

| Section | Purpose | Example Fields |
|---------|---------|----------------|
| `trust_weights` | Source-specific trust values (0.0--1.0) | `ehr_system: 0.94`, `patient_reported: 0.75` |
| `risk_thresholds` | Risk tolerance for autonomous actions | `auto_approve: none`, `require_review: low` |
| `checkpoint_policy` | When checkpoints are mandatory | `before_any_mutation: always` |
| `evidence_policy` | Evidence requirements for claims | `minimum_confidence: 0.90` |

**Available profiles:**

| Profile | File | Domain |
|---------|------|--------|
| Healthcare | `schemas/profiles/healthcare.yaml` | Clinical decision support |
| Manufacturing | `schemas/profiles/manufacturing.yaml` | Industrial operations |
| Data Analysis | `schemas/profiles/data_analysis.yaml` | Data science workflows |
| Personal Assistant | `schemas/profiles/personal_assistant.yaml` | Consumer assistance |
| Vision | `schemas/profiles/vision.yaml` | Computer vision modality |
| Audio | `schemas/profiles/audio.yaml` | Audio processing modality |
| Multimodal | `schemas/profiles/multimodal.yaml` | Combined modality processing |

**Validation:**

```bash
python tools/validate_profiles.py
```

This validates every YAML file in `schemas/profiles/` (excluding `profile_schema.yaml`) against the profile schema, checking for required fields, type correctness, and value constraints.

**Adding a new profile:**

1. Copy an existing profile as a starting template
2. Set the `domain` field (kebab-case identifier)
3. Set the `version` field (semver format: `"1.0.0"`)
4. Configure all four required sections
5. Run `python tools/validate_profiles.py` to confirm validity

### 3.2 Ontology Versioning

**File:** `schemas/capability_ontology.yaml`
**Version field:** `meta.version`
**Current value:** `2.0.0`

The ontology version is independent of the SDK and plugin versions. It tracks changes to the capability graph itself:

- MAJOR: Capabilities removed, renamed, or fundamentally restructured
- MINOR: New capabilities added, new edge types, new layers
- PATCH: Documentation fixes, description updates, non-breaking metadata changes

The ontology version is embedded in the `meta` block:

```yaml
meta:
  name: Grounded Agency Capability Ontology
  version: 2.0.0
  generated_at: '2026-01-26T00:00:00.000Z'
  description: 36 atomic capabilities derived from first principles
```

### 3.3 Plugin Versioning

**File:** `.claude-plugin/plugin.json`
**Field:** `version`
**Current value:** `1.0.5`

The plugin version tracks changes to the Claude Code integration surface: skill files, hook scripts, and the plugin manifest itself. It follows its own release cadence because plugin updates can ship without SDK changes.

### 3.4 SDK Versioning

**File:** `pyproject.toml`
**Field:** `project.version`
**Current value:** `0.1.0`

The SDK version tracks the `grounded_agency` Python package. It is mirrored in `grounded_agency/__init__.py` as `__version__` for runtime access.

---

## 4. Version Management Strategy

Four independent version sources must stay synchronized at release time. Failure to synchronize these values will cause version mismatch errors, confusing audit trails, and broken compatibility checks.

### 4.1 Version Matrix

| Source | File | Field | Current | Tracks |
|--------|------|-------|---------|--------|
| SDK Package | `pyproject.toml` | `project.version` | `0.1.0` | Python package releases |
| Plugin | `.claude-plugin/plugin.json` | `version` | `1.0.5` | Claude Code plugin releases |
| Runtime | `grounded_agency/__init__.py` | `__version__` | `0.1.0` | Must match pyproject.toml |
| Ontology | `schemas/capability_ontology.yaml` | `meta.version` | `2.0.0` | Capability graph changes |

### 4.2 Synchronization Rules

**Rule 1: SDK and Runtime must always match.**
The `__version__` in `grounded_agency/__init__.py` must equal the `version` in `pyproject.toml`. A mismatch means `importlib.metadata.version("grounded-agency")` and `grounded_agency.__version__` will return different values.

**Rule 2: Plugin and SDK are independently versioned.**
The plugin version (`1.0.5`) and SDK version (`0.1.0`) follow separate tracks. A plugin update that only changes skill files does not require an SDK release. An SDK release that only changes adapter logic does not require a plugin update.

**Rule 3: Ontology version changes propagate.**
When the ontology version changes, both the plugin and SDK should be tested against the new ontology. If the change is breaking (MAJOR bump), both may need releases.

**Rule 4: Document cross-version compatibility.**
Each release should document which ontology version it targets. For example, SDK `0.2.0` might target ontology `2.0.0`, while plugin `1.0.6` also targets ontology `2.0.0`.

### 4.3 Pre-Release Version Check Script

Before tagging a release, verify version consistency:

```bash
# Extract versions from all four sources
PYPROJECT_VER=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
PLUGIN_VER=$(python -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
INIT_VER=$(python -c "from grounded_agency import __version__; print(__version__)")
ONTOLOGY_VER=$(python -c "import yaml; print(yaml.safe_load(open('schemas/capability_ontology.yaml'))['meta']['version'])")

echo "pyproject.toml:  $PYPROJECT_VER"
echo "plugin.json:     $PLUGIN_VER"
echo "__init__.py:     $INIT_VER"
echo "ontology:        $ONTOLOGY_VER"

# Verify SDK/runtime match
if [ "$PYPROJECT_VER" != "$INIT_VER" ]; then
  echo "ERROR: pyproject.toml ($PYPROJECT_VER) != __init__.py ($INIT_VER)"
  exit 1
fi
echo "SDK/Runtime version match: OK"
```

---

## 5. Monitoring

### 5.1 Audit Log

**Location:** `.claude/audit.log`
**Written by:** `hooks/posttooluse_log_tool.sh`
**Trigger:** Every PostToolUse event matching the `Skill` matcher

The audit log captures timestamped entries for every skill invocation during a Claude Code session. Each entry records:
- Timestamp (ISO 8601)
- Skill name
- Tool context (what tool triggered the skill)

**Example entries:**

```
2026-01-30T10:15:23Z skill=checkpoint tool=Write scope=src/*.py
2026-01-30T10:15:45Z skill=mutate tool=Edit target=src/auth.py
2026-01-30T10:16:02Z skill=verify tool=Bash command=pytest
```

**Monitoring approach:**
- Review audit logs after each agent session to verify safety compliance
- Check that every `mutate` or `send` entry is preceded by a `checkpoint` entry
- Alert on skill invocations that bypass the expected workflow sequence
- The healthcare domain profile requires 2,555 days (7 years) of audit retention

### 5.2 Conformance Results

**Location:** `conformance_results.json` (project root)
**Written by:** `scripts/run_conformance.py`
**Format:** JSON array of test results

Each entry in the conformance results file contains:

```json
{
  "name": "fixture_name",
  "ok": true,
  "stdout": "...",
  "stderr": "..."
}
```

**Monitoring approach:**
- Run conformance tests as part of every CI pipeline
- Track pass/fail trends across releases
- Any regression from a previously passing fixture is a release blocker
- Store historical conformance results alongside release artifacts

### 5.3 Validator Output

The five validators (`validate_workflows.py`, `validate_profiles.py`, `validate_skill_refs.py`, `validate_ontology.py`, `sync_skill_schemas.py`) each write diagnostic output to stdout and signal success or failure via exit code.

**Automated monitoring:**

```bash
# Run all validators and capture exit codes
declare -A RESULTS
for validator in validate_workflows validate_profiles validate_skill_refs validate_ontology; do
  python "tools/${validator}.py" > "/tmp/${validator}.log" 2>&1
  RESULTS[$validator]=$?
done

# Report
for validator in "${!RESULTS[@]}"; do
  status="PASS"
  if [ "${RESULTS[$validator]}" -ne 0 ]; then status="FAIL"; fi
  echo "${validator}: ${status}"
done
```

**Recommended CI integration:**
- Run all five validators on every pull request
- Run conformance tests on merges to main
- Run the full release checklist (Steps 4--8) on release branches

---

## 6. Rollback Procedures

### 6.1 Schema Rollback (Ontology or Workflow Changes)

When a schema change introduces validation failures, broken workflows, or unexpected behavior:

```bash
# Identify the breaking commit
git log --oneline schemas/

# Revert the specific commit
git revert <commit-hash>

# Re-validate after revert
python tools/validate_workflows.py
python tools/validate_profiles.py
python tools/validate_ontology.py
python tools/validate_skill_refs.py
python tools/sync_skill_schemas.py

# Confirm conformance
python scripts/run_conformance.py
```

If the breaking change spans multiple commits:

```bash
# Revert a range (creates one revert commit per original)
git revert --no-commit <oldest-commit>^..<newest-commit>
git commit -m "revert: rollback schema changes from <oldest> to <newest>"

# Re-validate
python tools/validate_workflows.py && python tools/validate_ontology.py
```

### 6.2 SDK Rollback (Python Package)

When a published SDK version introduces bugs:

**For consumers:**

```bash
# Install the previous known-good version
pip install grounded-agency==<previous_version>

# Verify the rollback
python -c "import grounded_agency; print(grounded_agency.__version__)"
```

**For maintainers:**

```bash
# Yank the broken version from PyPI (prevents new installs)
# Note: yanking does NOT delete -- existing pins still work
pip install twine
# Yanking must be done via PyPI web UI or API

# Publish a patch release with the fix
# Update version to next patch (e.g., 0.1.1)
# Follow the full release checklist
```

### 6.3 Plugin Rollback (Claude Code)

When a plugin update breaks skill loading or hook execution:

```bash
# Uninstall the current version
claude plugin uninstall agent-capability-standard

# Install from a specific known-good Git reference
git checkout v1.0.4  # Previous known-good tag
claude plugin install .  # Install from local checkout

# Or reinstall from marketplace (if marketplace is updated to previous version)
claude plugin install agent-capability-standard
```

If the marketplace listing has already been updated to the broken version, the maintainer must:
1. Update the marketplace entry to point to the previous version
2. Notify users to reinstall

### 6.4 Checkpoint Rollback (Runtime Safety)

When the CheckpointTracker is in an inconsistent state (e.g., orphaned checkpoints, false validity):

```python
from grounded_agency import CheckpointTracker

tracker = CheckpointTracker()

# Invalidate all active and pending checkpoints
tracker.invalidate_all()

# This marks the active checkpoint as consumed and moves it to history.
# After invalidation, any mutation attempt will be blocked until
# a new checkpoint is explicitly created.

# Verify clean state
assert not tracker.has_valid_checkpoint()
assert tracker.get_active_checkpoint() is None

# Clear expired checkpoints from history
cleared = tracker.clear_expired()
print(f"Cleared {cleared} expired checkpoints from history")
```

The `invalidate_all()` method is the nuclear option for checkpoint state. It is appropriate when:
- A mutation failed partway through and the checkpoint scope no longer matches reality
- An agent session was interrupted and checkpoint state may be stale
- Testing or debugging requires a clean checkpoint state

After invalidation, the agent must create a new checkpoint before any further mutations. This is enforced by the PreToolUse hook (`pretooluse_require_checkpoint.sh`), which checks for a valid checkpoint marker before allowing Write or Edit operations.

### 6.5 Domain Profile Rollback

When a profile change causes incorrect risk thresholds or trust weights:

```bash
# Revert the specific profile
git checkout HEAD~1 -- schemas/profiles/<domain>.yaml

# Validate the reverted profile
python tools/validate_profiles.py

# Commit the revert
git add schemas/profiles/<domain>.yaml
git commit -m "revert: rollback <domain> profile to previous version"
```

---

## 7. Troubleshooting

### 7.1 Plugin Installation Failures

**Symptom:** `claude plugin install agent-capability-standard` fails with "plugin not found."

**Diagnosis:**
1. Verify the marketplace is added:
   ```bash
   claude plugin marketplace list
   ```
2. If the marketplace is not listed:
   ```bash
   claude plugin marketplace add synaptiai/synapti-marketplace
   ```
3. If the marketplace is listed but the plugin is not found, the marketplace index may be stale. Re-add the marketplace.

**Symptom:** Plugin installs but skills are not loaded.

**Diagnosis:**
1. Verify the `skills` field in `.claude-plugin/plugin.json` points to `./skills/`
2. Verify each skill directory contains a `SKILL.md` file with valid YAML frontmatter
3. Run `python tools/validate_skill_refs.py` to check for phantom paths

### 7.2 Hook Execution Failures

**Symptom:** Mutations proceed without checkpoint enforcement.

**Diagnosis:**
1. Verify `hooks/hooks.json` is valid JSON:
   ```bash
   python -c "import json; json.load(open('hooks/hooks.json'))"
   ```
2. Verify the hook script is executable:
   ```bash
   ls -la hooks/pretooluse_require_checkpoint.sh
   chmod +x hooks/pretooluse_require_checkpoint.sh
   ```
3. Verify the `${CLAUDE_PLUGIN_ROOT}` variable resolves correctly in the Claude Code environment
4. Check that the `matcher` field (`Write|Edit`) correctly matches the tools being used

**Symptom:** Audit log is not written.

**Diagnosis:**
1. Verify the `.claude/` directory exists and is writable
2. Verify `jq` is installed (required by `posttooluse_log_tool.sh`):
   ```bash
   which jq
   ```
3. Verify the PostToolUse hook is configured for the `Skill` matcher in `hooks/hooks.json`

### 7.3 Validator Failures

**Symptom:** `validate_workflows.py` reports unknown capability references.

**Cause:** A workflow in `schemas/workflow_catalog.yaml` references a capability ID not defined in `schemas/capability_ontology.yaml`.

**Fix:**
1. Check the spelling of the capability ID in the workflow definition
2. Verify the capability exists in the ontology under the correct layer
3. If the capability was recently renamed, update all workflow references
4. Run `python tools/validate_workflows.py --emit-patch` to get suggested fixes

**Symptom:** `validate_ontology.py` reports orphan nodes or asymmetric edges.

**Cause:** A capability was added to the ontology without connecting edges, or a bidirectional edge (like `alternative_to`) was defined in only one direction.

**Fix:**
1. Add missing edges to connect the orphan to related capabilities
2. For `alternative_to` and `conflicts_with` edges, ensure both directions are defined
3. Re-run `python tools/validate_ontology.py`

**Symptom:** `validate_skill_refs.py` reports phantom paths.

**Cause:** A skill SKILL.md references a file (schema, template, etc.) that does not exist on disk.

**Fix:**
1. Create the missing file, or
2. Remove the reference from the SKILL.md, or
3. Run `python tools/sync_skill_schemas.py` to regenerate local schemas from the ontology

### 7.4 Build Failures

**Symptom:** `python -m build` fails with import errors.

**Diagnosis:**
1. Verify hatchling is installed:
   ```bash
   pip install hatchling
   ```
2. Verify the build-system configuration in `pyproject.toml`:
   ```toml
   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"
   ```
3. Verify the package directory exists and contains `__init__.py`:
   ```bash
   ls grounded_agency/__init__.py
   ```

**Symptom:** Built wheel is missing schemas or skills.

**Cause:** The wheel target only includes `grounded_agency/`. Schemas and skills are only in the sdist.

**Fix:** This is by design. If consumers need schemas at runtime, they should install from sdist or access them via `importlib.resources` after packaging them inside the `grounded_agency/` tree.

### 7.5 Test Failures

**Symptom:** `pytest tests/ -v` fails with `ModuleNotFoundError: No module named 'grounded_agency'`.

**Fix:**
```bash
# Install the package in editable mode
pip install -e ".[dev]"
```

**Symptom:** Async tests fail with `RuntimeError: no running event loop`.

**Fix:**
1. Verify `pytest-asyncio` is installed:
   ```bash
   pip install pytest-asyncio>=0.21
   ```
2. Verify `asyncio_mode = "auto"` is set in `pyproject.toml`:
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   ```

**Symptom:** Conformance tests fail with `Missing fixture: tests/<name>.workflow_catalog.yaml`.

**Cause:** The fixture file referenced in `tests/EXPECTATIONS.json` does not exist.

**Fix:**
1. Create the missing fixture file, or
2. Remove the entry from `tests/EXPECTATIONS.json`
3. Re-run `python scripts/run_conformance.py`

### 7.6 Type Checking Failures

**Symptom:** mypy reports `error: Function is missing a type annotation`.

**Cause:** The `disallow_untyped_defs = true` setting in `pyproject.toml` requires all function definitions to have type annotations.

**Fix:** Add type annotations to all parameters and return values. For functions that return nothing, annotate with `-> None`.

**Symptom:** mypy reports errors in archived files.

**Cause:** The `_archive/` directory should be excluded from type checking.

**Fix:** Verify the exclusion is configured:
```toml
[tool.mypy]
exclude = ["^.venv/", "^_archive/"]
```

### 7.7 Version Mismatch Errors

**Symptom:** Runtime reports a different version than expected.

**Diagnosis:**

```python
import grounded_agency
print(grounded_agency.__version__)  # Runtime version from __init__.py

import importlib.metadata
print(importlib.metadata.version("grounded-agency"))  # Installed package version
```

If these differ, the package was installed from a different source than the current working tree.

**Fix:**
1. Reinstall in editable mode: `pip install -e .`
2. Verify `__version__` in `grounded_agency/__init__.py` matches `version` in `pyproject.toml`
3. Run the pre-release version check script from Section 4.3

---

## Appendix A: Release Cadence Recommendations

| Channel | Cadence | Trigger |
|---------|---------|---------|
| Plugin (marketplace) | As needed | New skills, hook updates, ontology changes |
| SDK (PyPI) | Monthly or as needed | API changes, bug fixes, new features |
| Ontology | Infrequent | Capability additions require governance review |
| Profiles | As needed | Domain-specific tuning |

The ontology should change least frequently because it defines the fundamental capability vocabulary. Changes to the ontology ripple through skills, workflows, profiles, and SDK code. The EXTENSION_GOVERNANCE process (`docs/methodology/EXTENSION_GOVERNANCE.md`) governs when and how new capabilities are added.

## Appendix B: CI/CD Pipeline Outline

A recommended CI/CD pipeline for the project:

```
on:
  pull_request:
    - Run all 5 validators
    - Run pytest tests/ -v
    - Run mypy grounded_agency/
    - Run ruff check .

  push (main branch):
    - All PR checks
    - Run conformance tests
    - Build package (python -m build)
    - Upload conformance_results.json as artifact

  tag (v*):
    - All main branch checks
    - Version consistency check (Section 4.3)
    - Build package
    - Publish to PyPI (twine upload)
    - Create GitHub Release with notes
    - Update marketplace listing
```

## Appendix C: Emergency Hotfix Process

When a critical issue requires an immediate fix outside the normal release cadence:

1. Create a hotfix branch from the latest release tag:
   ```bash
   git checkout -b hotfix/v0.1.1 v0.1.0
   ```
2. Apply the minimal fix
3. Run the abbreviated gate checks (Steps 4, 5, 6 from the release checklist)
4. Bump the PATCH version in all three version files
5. Tag, build, and publish
6. Merge the hotfix branch back to main:
   ```bash
   git checkout main
   git merge hotfix/v0.1.1
   ```
