# Environment Setup Guide

> Agent Capability Standard -- Developer Environment Reference

This document provides comprehensive instructions for setting up, configuring, and validating a development environment for the Agent Capability Standard project. It covers all three installation methods, dependency management, editor integration, project structure, and troubleshooting.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation Methods](#2-installation-methods)
3. [Development Environment Setup](#3-development-environment-setup)
4. [Configuration Reference](#4-configuration-reference)
5. [Validation Commands](#5-validation-commands)
6. [Project Structure](#6-project-structure)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

### Required Software

| Dependency | Minimum Version | Purpose | Verification Command |
|------------|----------------|---------|---------------------|
| **Python** | 3.10+ | Runtime, validators, SDK package | `python --version` |
| **Git** | 2.x | Version control, clone, hooks | `git --version` |
| **pip** | 22.0+ | Package installation | `pip --version` |
| **Rust toolchain** | rustc 1.86+ | Builds the validator/executor core (`core/`, crate `acs-core`) into `grounded_agency._core` via maturin; needed for any install from source, including `pip install -e` | `rustc --version` |
| **PyYAML** | 6.0+ (<7) | Only runtime Python dependency (installed automatically) | `python -c "import yaml; print(yaml.__version__)"` |

There is deliberately no pure-Python fallback for the core: `pip install -e ".[dev]" -c constraints.txt` compiles the Rust crate, and every consumer (the SDK, `tools/validate_workflows.py`, the conformance runner) runs that one implementation. CI pins the toolchain it uses (`RUST_TOOLCHAIN` in `.github/workflows/ci.yml`) and also checks the minimum supported version (1.86).

### Optional Software

| Dependency | Purpose | Verification Command |
|------------|---------|---------------------|
| **Claude Code CLI** | Plugin hooks, skills execution, marketplace install | `claude --version` |
| **jq** | JSON processing in audit log hook (`posttooluse_log_tool.sh`) | `jq --version` |
| **mypy** | Static type checking (development) | `mypy --version` |
| **ruff** | Linting and formatting (development) | `ruff --version` |
| **Go** | Only for the CEL differential check (`tools/cel_differential/`, run in CI) | `go version` |

### Why Python 3.10+?

The `grounded_agency` Python package and its tooling require Python 3.10 as the minimum supported version (configured in `pyproject.toml` via `requires-python = ">=3.10"`). This is not an arbitrary choice; three language features introduced in Python 3.10 are used throughout the codebase:

1. **Union type syntax with `|` (PEP 604)** -- The adapter and state modules use `str | None` and `list[str] | str` instead of `Optional[str]` and `Union[list[str], str]`. This appears in type annotations across `adapter.py`, `checkpoint_tracker.py`, `evidence_store.py`, and other modules.

2. **`slots=True` in dataclasses (PEP 680)** -- The `GroundedAgentConfig` dataclass uses `@dataclass(slots=True)` for memory efficiency and to prevent accidental attribute creation. This keyword argument is not available in Python 3.9 or earlier.

3. **Structural pattern matching (`match` statements, PEP 634)** -- While not pervasive, the codebase is designed to accommodate `match/case` constructs for capability routing and tool dispatch.

The `pyproject.toml` classifiers confirm tested versions:

```
Programming Language :: Python :: 3.10
Programming Language :: Python :: 3.11
Programming Language :: Python :: 3.12
```

Attempting to use Python 3.9 or earlier will produce `SyntaxError` on the `|` type union expressions and `TypeError` on the `slots=True` dataclass parameter.

---

## 2. Installation Methods

The project supports three installation methods depending on your use case: as a Claude Code plugin for agent workflows, as a pip-installable Python package for SDK integration, or from source for development and contribution.

### Method A: Claude Code Plugin (Marketplace)

This is the recommended method for **end users** who want to use the 36 atomic capability skills, workflow patterns, and safety hooks within Claude Code sessions.

```bash
# Step 1: Add the Synapti marketplace (one-time setup)
claude plugin marketplace add synaptiai/synapti-marketplace

# Step 2: Install the plugin
claude plugin install agent-capability-standard
```

**What this installs:**

| Component | Description |
|-----------|-------------|
| 36 Skills | Atomic capability implementations in `skills/<name>/SKILL.md` |
| Workflow Patterns | Reusable compositions (analyze, mitigate, optimize, orchestrate) |
| Safety Hooks | Pre-tool hooks enforcing checkpoints before mutations |
| Audit Hooks | Post-tool hooks maintaining action lineage in `.claude/audit.log` |
| Validator | Design-time validation for custom workflows |

The plugin metadata is defined in `.claude-plugin/plugin.json`:

```json
{
  "name": "agent-capability-standard",
  "version": "1.2.0",
  "description": "Grounded Agency: 36 atomic capabilities across 9 cognitive layers...",
  "skills": "./skills/"
}
```

The marketplace URL is hosted at:
`https://github.com/synaptiai/synapti-marketplace`

After installation, the plugin hooks defined in `hooks/hooks.json` are automatically registered, providing checkpoint enforcement on `Write|Edit` operations and audit logging on `Skill` invocations.

### Method B: pip install (SDK Package Only)

This method installs the `grounded_agency` Python package for programmatic integration with the Claude Agent SDK. It does not install the Claude Code plugin, skills, or hooks.

```bash
# Core package -- PyYAML plus the compiled core, no SDK dependency
pip install grounded-agency

# With Claude Agent SDK integration (adds claude-agent-sdk>=0.1.25,<0.3)
pip install grounded-agency[sdk]

# With development tools (adds pytest, mypy, ruff)
pip install grounded-agency[dev]

# Everything: SDK + dev tools
pip install grounded-agency[all]
```

**Dependency breakdown by extra:**

| Extra | Added Dependencies | Use Case |
|-------|--------------------|----------|
| *(core)* | `pyyaml>=6.0,<7` (the validator/executor ships inside the wheel as `grounded_agency._core`) | Ontology loading, schema parsing, workflow validation |
| `[sdk]` | `claude-agent-sdk>=0.1.25,<0.3` | Wrapping SDK options with safety layer |
| `[dev]` | `pytest>=7.0,<9`, `pytest-asyncio>=0.21,<1`, `mypy>=1.0,<2`, `ruff>=0.16,<0.17`, `types-PyYAML`, `hypothesis`, `jsonschema`, `claude-agent-sdk` | Testing, type checking, linting |

Wheels are built per platform with the stable ABI (abi3, Python >= 3.10). Where no wheel matches the platform, pip builds from the sdist, which needs a Rust toolchain (>= 1.86).
| `[all]` | All of the above | Full development environment |

**Post-install verification:**

```bash
# Verify the package is importable
python -c "from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig; print('OK')"

# Verify version
python -c "import grounded_agency; print(grounded_agency.__version__)"
# Expected: 0.1.0
```

### Method C: From Source (Development)

This is the recommended method for **contributors** and anyone who needs to modify the ontology, skills, validators, or SDK integration code.

```bash
# Step 1: Clone the repository
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard

# Step 2: Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows (PowerShell)
# .venv\Scripts\activate.bat     # Windows (cmd)

# Step 3: Install in editable mode with all dependencies
# (compiles the Rust core; needs rustc >= 1.86)
pip install -e ".[dev]" -c constraints.txt

# Step 4: Verify installation
python -c "from grounded_agency import GroundedAgentAdapter; print('SDK OK')"
python tools/validate_workflows.py
python tools/validate_ontology.py
```

**Why editable mode (`-e`)?** Editable installs point the virtual environment at your source tree. Changes to Python files under `grounded_agency/` take effect immediately without reinstallation; changes to the Rust code under `core/` do not -- re-run the `pip install -e` line to rebuild the `grounded_agency._core` extension. The `[dev]` extra already includes the SDK. Pass `-c constraints.txt` so the tool versions (notably ruff) match exactly what CI runs.

The package is built with maturin; `pyproject.toml` configures the layout:

```toml
[build-system]
requires = ["maturin>=1.9,<2"]
build-backend = "maturin"

[tool.maturin]
manifest-path = "core/Cargo.toml"
module-name = "grounded_agency._core"
python-source = "."
python-packages = ["grounded_agency"]
features = ["python"]
include = [
    { path = "schemas/**/*", format = "sdist" },
    { path = "skills/**/*", format = "sdist" },
]
```

Note that the sdist includes `schemas/` and `skills/` alongside the Python package and the Rust crate, ensuring the `capability_ontology.yaml` is available for ontology path resolution even when installed from a source distribution.

---

## 3. Development Environment Setup

### Virtual Environment

Always use a virtual environment to isolate project dependencies from system Python:

```bash
# Create
python -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Verify active environment
which python
# Expected: /path/to/agent-capability-standard/.venv/bin/python

# Deactivate when done
deactivate
```

The `.gitignore` excludes `.venv/` from version control:

```
.venv/
*.pyc
__pycache__/
```

### Installing All Dependencies

For a full development environment, install the `dev` extra (which includes the SDK) against the constraints file:

```bash
pip install -e ".[dev]" -c constraints.txt
```

This builds the Rust core and provides:

| Package | Version (supported range; exact pins in `constraints.txt`) | Purpose |
|---------|---------|---------|
| `pyyaml` | >=6.0,<7 | YAML parsing for ontology, schemas, profiles |
| `claude-agent-sdk` | >=0.1.25,<0.3 | SDK integration for `GroundedAgentAdapter` |
| `pytest` | >=7.0,<9 | Test runner |
| `pytest-asyncio` | >=0.21,<1 | Async test support (adapter hooks are async) |
| `mypy` | >=1.0,<2 | Static type analysis |
| `ruff` | >=0.16,<0.17 | Linting, formatting and import sorting |
| `types-PyYAML`, `hypothesis`, `jsonschema` | see `pyproject.toml` | Type stubs, property tests, schema tests |

For the Rust core itself, the checks CI runs are:

```bash
cd core
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo clippy --all-targets --features python -- -D warnings
cargo test
```

### Editor Configuration

The project defines tool settings in `pyproject.toml`. Configure your editor to respect these.

#### mypy Settings

From `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
exclude = [
    "^.venv/",
    "^_archive/",
]
```

Key implications:
- All function definitions must have type annotations (`disallow_untyped_defs = true`)
- Functions returning `Any` trigger a warning (`warn_return_any = true`)
- The archived v1 codebase (`_archive/`) and virtualenv are excluded from checks

**VS Code** -- Add to `.vscode/settings.json`:

```json
{
  "python.analysis.typeCheckingMode": "basic",
  "mypy-type-checker.args": ["--config-file=pyproject.toml"],
  "python.defaultInterpreterPath": ".venv/bin/python"
}
```

#### ruff Settings

From `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py310"
line-length = 88

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by formatter)
]

[tool.ruff.lint.isort]
known-first-party = ["grounded_agency"]
```

Key implications:
- Line length is 88 characters (Black-compatible), but E501 is ignored since the formatter handles wrapping
- Import sorting treats `grounded_agency` as first-party
- `UP` rules enforce modern Python idioms (e.g., `dict` instead of `typing.Dict`)

**VS Code** -- Add to `.vscode/settings.json`:

```json
{
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  }
}
```

#### pytest Settings

From `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v"
```

Key implications:
- Tests are discovered only in `tests/` (not project-wide)
- Async tests run automatically without explicit `@pytest.mark.asyncio` decorators
- Verbose output is the default

### Hook Script Permissions

The shell-based hooks must be executable. After cloning, verify and fix permissions:

```bash
# Verify current permissions
ls -la hooks/*.sh

# Make executable if needed
chmod +x hooks/pretooluse_require_checkpoint.sh
chmod +x hooks/posttooluse_log_tool.sh
```

The `.gitattributes` file contains settings to preserve these across platforms:

```
*.sh text eol=lf
```

---

## 4. Configuration Reference

### GroundedAgentConfig Defaults

The `GroundedAgentConfig` dataclass (defined in `grounded_agency/adapter.py`) controls the behavior of the SDK integration layer. All fields have defaults and are optional to specify:

```python
@dataclass(slots=True)
class GroundedAgentConfig:
    ontology_path: str = field(default_factory=get_default_ontology_path)
    strict_mode: bool = True
    audit_log_path: str = ".claude/audit.log"
    checkpoint_dir: str = ".checkpoints"
    expiry_minutes: int = 30
```

**Detailed field reference:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ontology_path` | `str` | Auto-detected | Path to `capability_ontology.yaml`. Uses a three-level fallback resolution strategy (see below). |
| `strict_mode` | `bool` | `True` | When `True`, mutations without a valid checkpoint are blocked with `PermissionResultDeny`. When `False`, a warning is logged but the operation proceeds. |
| `audit_log_path` | `str` | `".claude/audit.log"` | File path for audit log entries. The directory is created automatically by the audit hook. |
| `checkpoint_dir` | `str` | `".checkpoints"` | Directory for storing checkpoint state files. |
| `expiry_minutes` | `int` | `30` | Default time-to-live for checkpoints in minutes. After expiry, a checkpoint is no longer valid and a new one must be created before mutations. |

### Ontology Path Resolution

The `get_default_ontology_path()` function uses a three-level fallback to locate `capability_ontology.yaml`:

```
Priority 1: importlib.resources (installed package)
  -> files("grounded_agency") / "../schemas/capability_ontology.yaml"

Priority 2: File-relative paths (development layout)
  -> grounded_agency/../schemas/capability_ontology.yaml
  -> grounded_agency/schemas/capability_ontology.yaml

Priority 3: CWD-relative fallback
  -> schemas/capability_ontology.yaml
```

The resolved path is cached at module level (`_DEFAULT_ONTOLOGY_PATH`) so subsequent accesses do not repeat the filesystem scan.

**Override example:**

```python
config = GroundedAgentConfig(
    ontology_path="/absolute/path/to/capability_ontology.yaml",
    strict_mode=False,
    expiry_minutes=60,
)
adapter = GroundedAgentAdapter(config)
```

### Plugin Settings (settings.json)

The `settings.json` at the project root configures Claude Code plugin behavior:

```json
{
  "hooks": {
    "pretooluse_require_checkpoint": {
      "enabled": true,
      "description": "Require checkpoint before high-impact file modifications",
      "configurable": true
    },
    "posttooluse_log_tool": {
      "enabled": true,
      "description": "Log all tool usage for audit trail",
      "configurable": true
    }
  },
  "validation": {
    "strict_mode": false,
    "require_provenance": true,
    "trust_decay_enabled": true,
    "default_trust_level": 0.8
  },
  "world_modeling": {
    "enable_digital_twin": false,
    "state_persistence": "memory",
    "max_state_history": 100
  }
}
```

### Hook Configuration (hooks/hooks.json)

The hooks registered with Claude Code are defined in `hooks/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_require_checkpoint.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse_log_tool.sh"
          }
        ]
      }
    ]
  }
}
```

- **PreToolUse hook**: Fires before `Write` or `Edit` tool invocations. Checks for `.claude/checkpoint.ok` marker file. Blocks the operation if the marker is absent.
- **PostToolUse hook**: Fires after `Skill` tool invocations. Extracts the skill name and arguments via `jq`, then appends a timestamped entry to `.claude/audit.log`.

---

## 5. Validation Commands

The project includes a suite of validation tools under `tools/` and `scripts/`. Run these after any changes to the ontology, workflows, profiles, or skill definitions.

### Validation Commands Table

| Command | Purpose | Expected Output |
|---------|---------|-----------------|
| `python tools/validate_workflows.py` | Validate workflow compositions against the ontology (checks run in the Rust core, so the package must be built: `pip install -e .`). Checks that all referenced capabilities exist, edge semantics hold, bindings and expressions are well-typed. Options: `--catalog PATH`, `--strict`, `--emit-patch`. | A `WARNINGS:` block if any, then `VALIDATION PASS` or `VALIDATION FAIL:` with lines `[workflow] step N (capability): CODE message — hint`. |
| `python tools/validate_ontology.py` | Check ontology graph integrity. Detects orphan nodes (capabilities with no edges), cycles in `requires`/`precedes` chains, asymmetry in bidirectional edge types, misuse of `mutation_overridable` and edges listed twice. | `VALIDATION PASSED` or errors listing the issues. |
| `python tools/validate_profiles.py` | Validate domain profiles (`schemas/profiles/*.yaml`) against the profile schema. Checks for required fields, valid capability references, and threshold ranges. | `PROFILE VALIDATION PASS: N profiles validated` or field-level errors identifying the failing profile. |
| `python tools/validate_skill_refs.py` | Check for phantom paths in skill files. Ensures all file references in SKILL.md documents point to files that actually exist in the repository. | `SKILL REFERENCE VALIDATION PASS: N skills validated` or list of broken references with file locations. |
| `python tools/sync_skill_schemas.py` | Regenerate skill-local files from their sources: `skills/<name>/schemas/output_schema.yaml` for each capability, the 17 vendored `reference/workflow_catalog.yaml` copies and their vendored schema copies; removes orphaned generated schemas. `--check` exits 1 on drift (run in CI); `--dry-run` lists changes. | `SYNC COMPLETE: X of N generated files changed, Y removed` (`SYNC CHECK PASS: ...` with `--check`). |
| `python scripts/run_conformance.py` | Run the validator on every fixture in `tests/fixtures/` (via `--catalog`) and check each against `tests/fixtures/EXPECTATIONS.json`: pass/fail and expected error and warning codes. | A `PASS:`/`FAIL:` line per fixture, then `Conformance PASSED` (or `Conformance FAILED (N failures)`). |
| `pytest tests/ -v` | Run SDK unit tests. Covers adapter, registry, mapper, checkpoint tracker, evidence store, and OASF adapter. | Standard pytest output with pass/fail per test. |
| `mypy grounded_agency/` | Run static type checking on the SDK package. Enforces `disallow_untyped_defs` and `warn_return_any`. | Type errors or `Success: no issues found`. |
| `ruff check .` | Run linting across the entire project. Checks pycodestyle, pyflakes, isort, bugbear, comprehensions, and pyupgrade rules. | Lint warnings or `All checks passed!`. |

### Generating Patch Suggestions

The workflow validator can emit machine-readable patch suggestions:

```bash
python tools/validate_workflows.py --emit-patch
# Writes tools/validator_patch.diff in addition to tools/validator_suggestions.json
```

`tools/validator_suggestions.json` is written on every run, pass or fail (keys `errors`, `warnings`, `structured_errors`, `structured_warnings`, `suggestions`); `--emit-patch` only adds the diff. Both files are in `.gitignore` and are meant for local use only.

### Full Validation Script

Run all validators in sequence to confirm a healthy project state:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Ontology Graph ==="
python tools/validate_ontology.py

echo "=== Workflow Compositions ==="
python tools/validate_workflows.py

echo "=== Domain Profiles ==="
python tools/validate_profiles.py

echo "=== Skill File References ==="
python tools/validate_skill_refs.py

echo "=== Generated Files In Sync ==="
python tools/sync_skill_schemas.py --check

echo "=== Rust Core ==="
(cd core && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test)

echo "=== Conformance Tests ==="
python scripts/run_conformance.py

echo "=== SDK Unit Tests ==="
pytest tests/ -v

echo "=== Type Checking ==="
mypy grounded_agency/

echo "=== Linting ==="
ruff check .

echo "All validations passed."
```

---

## 6. Project Structure

### Annotated Directory Tree

```
agent-capability-standard/
|
|-- .claude/                          # Claude Code local state (gitignored contents)
|   |-- audit.log                     #   Audit log written by PostToolUse hook
|   |-- settings.json                 #   Local settings overrides
|   +-- checkpoint.ok                 #   Checkpoint marker for PreToolUse hook
|
|-- .claude-plugin/                   # Claude Code plugin metadata
|   +-- plugin.json                   #   Plugin name, version, skill root, description
|
|-- .github/                          # GitHub configuration
|   +-- pull_request_template.md      #   PR template for contributors
|
|-- _archive/                         # Archived v1 files (99-capability model)
|                                     #   Excluded from mypy and ruff checks
|
|-- analysis/                         # Project analysis documents
|   |-- 01-architectural-analysis.md  #   Deep architectural analysis
|   |-- 02-system-diagrams-and-features.md
|   |-- 03-data-model-and-erd.md      #   Data model and entity-relationship diagrams
|   +-- 05-api-reference.md           #   API reference for SDK package
|
|-- benchmarks/                       # Performance and capability benchmarks
|   |-- runner.py                     #   Benchmark runner script
|   |-- scenarios/                    #   Benchmark scenario definitions
|   |-- fixtures/                     #   Test fixture data
|   |-- baselines/                    #   Baseline performance data
|   |-- results/                      #   Benchmark run results
|   +-- tests/                        #   Benchmark-specific tests
|
|-- docs/                             # User and methodology documentation
|   |-- FAQ.md                        #   Frequently asked questions
|   |-- GLOSSARY.md                   #   Key terms and definitions
|   |-- GROUNDED_AGENCY.md            #   Core philosophy deep dive
|   |-- QUICKSTART.md                 #   10-minute quickstart guide
|   |-- TUTORIAL.md                   #   30-minute tutorial
|   |-- WORKFLOW_PATTERNS.md          #   Reusable composition patterns
|   |-- WORKFLOW_ROADMAP.md           #   Workflow development roadmap
|   |-- domains/                      #   Domain-specific documentation
|   |-- guides/                       #   User guides
|   |   +-- MODALITY_HANDLING.md      #     Vision, audio, multimodal guidance
|   |-- integrations/                 #   Integration guides
|   |   +-- claude_agent_sdk.md       #     Claude Agent SDK integration
|   |-- methodology/                  #   Derivation and governance methodology
|   |   |-- FIRST_PRINCIPLES_REASSESSMENT.md  # How 36 capabilities were derived
|   |   |-- AGENT_ARCHITECTURE_RESEARCH.md    # Industry pattern research
|   |   |-- SKILLS_ALIGNMENT_EVALUATION.md    # Claude Skills validation
|   |   +-- EXTENSION_GOVERNANCE.md           # When to add capabilities
|   |-- proposals/                    #   Extension proposals
|   |   +-- OASF_SAFETY_EXTENSIONS.md #     OASF safety property integration
|   |-- research/                     #   Research notes and references
|   +-- reviews/                      #   Review documents
|
|-- core/                             # Rust crate acs-core: validator + executor,
|   |-- Cargo.toml                    #   compiled by maturin into grounded_agency._core
|   |-- src/                          #   yaml.rs, types.rs, refs.rs, schema.rs, expr/, validate/
|   +-- tests/                        #   cargo test suites
|
|-- examples/                         # Usage examples
|   |-- grounded_agent_demo.py        #   Full adapter usage demo
|   |-- checkpoint_enforcement_demo.py#   Checkpoint safety demo
|   |-- capability_skills_demo.py     #   Capability mapping demo
|   +-- digital_twin_sync_loop.workflow_catalog.yaml  # Workflow example
|
|-- grounded_agency/                  # Python SDK package (pip-installable)
|   |-- __init__.py                   #   Package exports, version, type aliases
|   |-- adapter.py                    #   GroundedAgentAdapter + GroundedAgentConfig
|   |-- adapters/                     #   Framework adapters
|   |   |-- __init__.py
|   |   +-- oasf.py                   #     OASF compatibility adapter
|   |-- capabilities/                 #   Capability system
|   |   |-- __init__.py
|   |   |-- registry.py              #     CapabilityRegistry (loads ontology)
|   |   +-- mapper.py                #     ToolCapabilityMapper (tool->capability)
|   |-- hooks/                        #   SDK hook implementations
|   |   |-- __init__.py
|   |   |-- evidence_collector.py    #     PostToolUse evidence collection
|   |   +-- skill_tracker.py         #     Skill invocation tracking
|   +-- state/                        #   State management
|       |-- __init__.py
|       |-- checkpoint_tracker.py    #     CheckpointTracker (lifecycle mgmt)
|       +-- evidence_store.py        #     EvidenceStore (anchor collection)
|
|-- hooks/                           # Claude Code shell hooks
|   |-- hooks.json                   #   Hook registration (PreToolUse, PostToolUse)
|   |-- pretooluse_require_checkpoint.sh  # Blocks Write/Edit without checkpoint
|   |-- posttooluse_log_tool.sh      #   Logs Skill invocations to audit.log
|   +-- README.md                    #   Hook documentation
|
|-- schemas/                         # Ontology, workflow, and data schemas
|   |-- capability_ontology.yaml     #   Master ontology (36 capabilities, edges, layers)
|   |-- workflow_catalog.yaml        #   12 composed workflow definitions
|   |-- world_state_schema.yaml      #   World state with provenance model
|   |-- authority_trust_model.yaml   #   Trust model with time decay
|   |-- entity_taxonomy.yaml         #   Entity type definitions
|   |-- event_schema.yaml            #   Event structure definitions
|   |-- identity_resolution_policy.yaml  # Entity identity resolution rules
|   |-- interop/                     #   Framework interoperability
|   |   +-- oasf_mapping.yaml        #     OASF skill-code-to-capability mapping
|   |-- profiles/                    #   Domain-specific profiles
|   |   +-- profile_schema.yaml      #     Schema for domain profiles
|   |-- transforms/                  #   Type coercion mappings
|   +-- workflows/                   #   Additional workflow definitions
|
|-- scripts/                         # Utility scripts
|   +-- run_conformance.py           #   Conformance test runner
|
|-- skills/                          # 36 atomic capability skills (flat structure)
|   |-- README.md                    #   Skills index and layer map
|   |-- retrieve/SKILL.md            #   PERCEIVE: retrieve information
|   |-- search/SKILL.md              #   PERCEIVE: search across sources
|   |-- observe/SKILL.md             #   PERCEIVE: observe system state
|   |-- receive/SKILL.md             #   PERCEIVE: receive external input
|   |-- detect/SKILL.md              #   UNDERSTAND: detect patterns/anomalies
|   |-- classify/SKILL.md            #   UNDERSTAND: classify entities
|   |-- compare/SKILL.md             #   UNDERSTAND: compare items
|   |-- discover/SKILL.md            #   UNDERSTAND: discover relationships
|   |-- measure/SKILL.md             #   UNDERSTAND: measure metrics
|   |-- predict/SKILL.md             #   UNDERSTAND: predict outcomes
|   |-- plan/SKILL.md                #   REASON: create action plans
|   |-- decompose/SKILL.md           #   REASON: break down problems
|   |-- critique/SKILL.md            #   REASON: evaluate quality
|   |-- explain/SKILL.md             #   REASON: explain reasoning
|   |-- state/SKILL.md               #   MODEL: represent world state
|   |-- transition/SKILL.md          #   MODEL: model state transitions
|   |-- attribute/SKILL.md           #   MODEL: assign attributes
|   |-- ground/SKILL.md              #   MODEL: ground claims in evidence
|   |-- simulate/SKILL.md            #   MODEL: simulate scenarios
|   |-- generate/SKILL.md            #   SYNTHESIZE: generate content
|   |-- transform/SKILL.md           #   SYNTHESIZE: transform data
|   |-- integrate/SKILL.md           #   SYNTHESIZE: integrate sources
|   |-- execute/SKILL.md             #   EXECUTE: execute actions
|   |-- mutate/SKILL.md              #   EXECUTE: mutate state (high-risk)
|   |-- send/SKILL.md                #   EXECUTE: send external messages (high-risk)
|   |-- verify/SKILL.md              #   VERIFY: verify correctness
|   |-- checkpoint/SKILL.md          #   VERIFY: create checkpoints
|   |-- rollback/SKILL.md            #   VERIFY: rollback to checkpoint
|   |-- constrain/SKILL.md           #   VERIFY: apply constraints
|   |-- audit/SKILL.md               #   VERIFY: audit actions
|   |-- persist/SKILL.md             #   REMEMBER: persist state
|   |-- recall/SKILL.md              #   REMEMBER: recall persisted state
|   |-- delegate/SKILL.md            #   COORDINATE: delegate to agents
|   |-- synchronize/SKILL.md         #   COORDINATE: synchronize agents
|   |-- invoke/SKILL.md              #   COORDINATE: invoke external services
|   |-- inquire/SKILL.md             #   COORDINATE: ask for information
|   |-- perspective-validation/      #   PVC: socio-technical review checklist
|   |-- capability-gap-analysis/     #   Workflow: identify missing capabilities
|   |-- debug-workflow/              #   Workflow: debug code changes
|   |-- digital-twin-bootstrap/      #   Workflow: initialize digital twin
|   +-- digital-twin-sync-loop/      #   Workflow: synchronize digital twin
|
|-- spec/                            # Formal specification documents
|   |-- STANDARD-v1.0.0.md           #   Formal specification
|   |-- WHITEPAPER.md                #   Design rationale and philosophy
|   |-- CONFORMANCE.md               #   Conformance levels and testing
|   |-- SECURITY.md                  #   Threat model and mitigations
|   |-- EDGE_TYPES.md                #   Ontology edge type documentation
|   |-- GOVERNANCE.md                #   RFC process
|   |-- ROADMAP.md                   #   Future plans
|   |-- CHANGELOG.md                 #   Version history
|   |-- CITATION.cff                 #   Citation metadata
|   |-- PRESS_KIT.md                 #   Media resources
|   +-- RFC-0001-*.md                #   Original proposal RFC
|
|-- templates/                       # Templates for creating new artifacts
|   |-- SKILL_TEMPLATE_ENHANCED.md   #   Template for new capability skills
|   |-- capability_atoms.md          #   Capability atom reference
|   |-- composition_patterns.md      #   Pattern composition reference
|   |-- output_contracts.md          #   Output contract summary
|   |-- output_contracts_full.md     #   Full output contract documentation
|   |-- verification_patterns.md     #   Verification pattern reference
|   +-- README.md                    #   Template documentation
|
|-- tests/                           # SDK unit and integration tests
|   |-- __init__.py
|   |-- test_sdk_integration.py      #   Adapter, registry, mapper tests
|   +-- test_oasf_adapter.py         #   OASF compatibility adapter tests
|
|-- tools/                           # Validation CLI tools
|   |-- validate_workflows.py        #   Workflow composition validator
|   |-- validate_ontology.py         #   Ontology graph integrity checker
|   |-- validate_profiles.py         #   Domain profile validator
|   |-- validate_skill_refs.py       #   Phantom path detector
|   +-- sync_skill_schemas.py        #   Skill schema generator
|
|-- pyproject.toml                   # Build config, dependencies, tool settings
|-- settings.json                    # Claude Code plugin settings
|-- CLAUDE.md                        # Claude Code project instructions
|-- README.md                        # Project readme
|-- CONTRIBUTING.md                  # Contribution guidelines
|-- CODE_OF_CONDUCT.md               # Community code of conduct
|-- LICENSE                          # Apache License 2.0
|-- NOTICE                           # Legal notices
|-- CHANGELOG.md                     # Project changelog
|-- CITATION.cff                     # Citation metadata
+-- build/conformance_results.json   # Latest conformance run output (gitignored)
```

### Key Structural Decisions

1. **Flat skill structure**: Skills are at `skills/<name>/SKILL.md` without layer-based subdirectories. This simplifies tool path resolution and avoids import ambiguity.

2. **Schema colocation**: Each skill can have a local `schemas/output_schema.yaml` generated by `sync_skill_schemas.py`, derived from the master `capability_ontology.yaml`.

3. **Hooks split**: Shell hooks (`hooks/`) are for Claude Code plugin integration; Python hooks (`grounded_agency/hooks/`) are for SDK integration. Both serve the same safety model but target different runtime environments.

4. **Archive isolation**: The `_archive/` directory contains the superseded 99-capability model. It is excluded from linting and type checking via `pyproject.toml` excludes.

---

## 7. Troubleshooting

### Python Version Too Old

**Symptom:**
```
SyntaxError: unsupported syntax (Python 3.9)
```
or
```
TypeError: dataclass() got an unexpected keyword argument 'slots'
```

**Cause:** The `grounded_agency` package requires Python 3.10+ for `str | None` union syntax and `@dataclass(slots=True)`.

**Fix:**
```bash
python --version  # Check current version
# Install Python 3.10+ via pyenv, brew, or system package manager
pyenv install 3.12.0 && pyenv local 3.12.0
# Or on macOS:
brew install python@3.12
```

### PyYAML Version Conflicts

**Symptom:**
```
ImportError: cannot import name 'CSafeLoader' from 'yaml'
```
or
```
yaml.scanner.ScannerError: while scanning a simple key
```

**Cause:** An older PyYAML version (< 6.0) may be installed system-wide or in a conflicting environment.

**Fix:**
```bash
pip install --upgrade pyyaml>=6.0
python -c "import yaml; print(yaml.__version__)"  # Should be 6.0+
```

If using system Python with a conflicting PyYAML, ensure your virtualenv is activated and does not inherit system packages:

```bash
python -m venv .venv --clear  # Recreate virtualenv
source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
```

### Missing jq (Audit Hook Fails Silently)

**Symptom:** The `posttooluse_log_tool.sh` hook exits silently without writing to the audit log. No errors are shown because the script is designed to degrade gracefully.

**Cause:** The hook script checks for `jq` and exits 0 if not found:

```bash
if ! command -v jq &> /dev/null; then
  exit 0
fi
```

**Fix:**
```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq

# Verify
jq --version
```

### SDK Not Found

**Symptom:**
```
ImportError: No module named 'claude_agent_sdk'
```

**Cause:** The core `grounded-agency` package does not include the Claude Agent SDK as a required dependency. It is an optional extra.

**Fix:**
```bash
pip install grounded-agency[sdk]
# Or from source:
pip install -e ".[sdk]"
```

Note: The adapter is designed to work without the SDK installed. It falls back to dict-based hook configuration and permission results. The `ImportError` only occurs if you explicitly import SDK types:

```python
# This works without SDK:
from grounded_agency import GroundedAgentAdapter  # OK

# This requires SDK:
from claude_agent_sdk import ClaudeSDKClient  # Requires [sdk] extra
```

### Ontology Path Resolution Failures

**Symptom:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'schemas/capability_ontology.yaml'
```
or
```
yaml.YAMLError: could not determine a constructor for the tag...
```

**Cause:** The three-level path resolution could not find the ontology file. This typically happens when:
- Running from a directory outside the project root
- The package was installed without the schemas directory
- An sdist was built without the `/schemas` include

**Fix:**

Option 1 -- Provide an explicit path:
```python
config = GroundedAgentConfig(
    ontology_path="/absolute/path/to/schemas/capability_ontology.yaml"
)
```

Option 2 -- Run from the project root:
```bash
cd /path/to/agent-capability-standard
python -c "from grounded_agency import GroundedAgentAdapter; print('OK')"
```

Option 3 -- Reinstall in editable mode to ensure the symlink:
```bash
pip install -e ".[dev]" -c constraints.txt
```

### Hook Script Permission Errors

**Symptom:**
```
Permission denied: hooks/pretooluse_require_checkpoint.sh
```

**Cause:** The shell scripts lost their executable bit, typically after extracting from a zip archive or on Windows filesystems.

**Fix:**
```bash
chmod +x hooks/pretooluse_require_checkpoint.sh
chmod +x hooks/posttooluse_log_tool.sh
```

### Validator Import Errors

**Symptom:**
```
ModuleNotFoundError: No module named 'yaml'
```
or
```
ModuleNotFoundError: No module named 'grounded_agency._core'
```
(or `ImportError: cannot import name '_core' from 'grounded_agency'`) when running `python tools/validate_workflows.py`, `python scripts/run_conformance.py` or importing `grounded_agency`.

**Cause:** Most validators under `tools/` are standalone scripts that need only PyYAML. `validate_workflows.py` (and therefore the conformance runner), `validate_benchmark_deps.py` and the `grounded_agency` package itself need the compiled Rust extension `grounded_agency._core`, which exists only after the package has been built and installed.

**Fix:**
```bash
# Ensure virtualenv is activated
source .venv/bin/activate

# Build the Rust core and install everything (needs rustc >= 1.86)
pip install -e ".[dev]" -c constraints.txt
```

If the build fails with `rustc` not found or a version error, install or update Rust (e.g. via `rustup`) to 1.86 or newer. After pulling changes to `core/`, re-run the same command: an editable install does not rebuild the extension automatically.

### Checkpoint Marker Not Found

**Symptom:**
```
Blocked: missing checkpoint marker (.claude/checkpoint.ok). Create a checkpoint first.
```

**Cause:** The `pretooluse_require_checkpoint.sh` hook detected a mutation operation (Write/Edit) but the checkpoint marker file `.claude/checkpoint.ok` does not exist.

**Fix:** Create a checkpoint before performing mutations:

```bash
# Manual marker creation (for testing)
mkdir -p .claude && touch .claude/checkpoint.ok

# Via the SDK adapter (programmatic)
adapter.create_checkpoint(scope=["*.py"], reason="Before changes")
```

In Claude Code sessions, invoke the `checkpoint` skill before any file modifications.

### Test Failures with Async Errors

**Symptom:**
```
RuntimeError: no running event loop
```
or
```
PytestUnraisableExceptionWarning: ...coroutine was never awaited
```

**Cause:** The `pytest-asyncio` package is missing or outdated.

**Fix:**
```bash
pip install pytest-asyncio>=0.21
```

The `pyproject.toml` configures `asyncio_mode = "auto"`, which requires `pytest-asyncio>=0.21` to function correctly. Earlier versions require explicit `@pytest.mark.asyncio` decorators.

### ruff or mypy Not Recognizing Project Structure

**Symptom:** ruff reports import errors for `grounded_agency` or mypy cannot find the package.

**Cause:** The package is not installed in the active environment. Both tools need the package to be importable to resolve first-party imports.

**Fix:**
```bash
pip install -e ".[dev]"
```

This installs the package in editable mode, making `grounded_agency` importable while also installing `mypy` and `ruff`.

---

*This document is part of the Agent Capability Standard analysis suite. For architectural details, see [01-architectural-analysis.md](01-architectural-analysis.md). For API reference, see [05-api-reference.md](05-api-reference.md).*
