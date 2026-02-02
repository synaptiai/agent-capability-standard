# Technical Debt Register

**Project:** Agent Capability Standard (Grounded Agency)
**Version:** 2.0.0 (36-capability model)
**Date:** 2026-01-30
**Last Updated:** 2026-02-02
**Maintainer:** Grounded Agency Team

### Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-30 | Initial register with 14 debt items | Automated analysis |
| 2026-02-01 | 12 of 14 items closed (PRs #89–#93); TD-006 and TD-010 remain open | Post-remediation review |
| 2026-02-02 | TD-010 closed (GA extensions + coverage gaps); 13 of 14 items closed; TD-006 remains open | Issue #69 |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Technical Debt Inventory](#2-technical-debt-inventory)
3. [Severity Distribution](#3-severity-distribution)
4. [Effort Estimates by Category](#4-effort-estimates-by-category)
5. [Prioritized Remediation Plan](#5-prioritized-remediation-plan)
6. [Sprint Allocation Strategy](#6-sprint-allocation-strategy)

---

## 1. Overview

This register catalogs known technical debt across the Agent Capability Standard codebase. Each item is identified, categorized, and assigned a severity level, remediation effort, and priority. The register serves as a living document to guide engineering investment in codebase health alongside feature development.

**Methodology:** Debt items were identified through static analysis of source code, configuration files, test infrastructure, and interoperability mappings. Each item is grounded in specific file references and observable symptoms.

**Scope:** The register covers the Python SDK (`grounded_agency/`), shell hooks (`hooks/`), YAML schemas (`schemas/`), test infrastructure (`tests/`, `scripts/`), build configuration (`pyproject.toml`), and CI/CD infrastructure.

---

## 2. Technical Debt Inventory

### TD-001: Legacy Capability References in Conformance Test Fixtures

| Field | Value |
|-------|-------|
| **ID** | TD-001 |
| **Severity** | Medium |
| **Category** | Testing |
| **Component** | `tests/*.workflow_catalog.yaml`, `scripts/run_conformance.py` |

**Description:**
The conformance test runner (`scripts/run_conformance.py`) operates by temporarily swapping `schemas/workflow_catalog.yaml` with fixture content from `tests/`. The pass-reference fixture (`tests/pass_reference.workflow_catalog.yaml`) contains a legacy mapping comment block that references the old 99-capability model names (e.g., `inspect -> observe`, `map-relationships -> attribute`, `model-schema -> constrain`, `act-plan -> execute`). While these comments serve as a migration reference, they indicate that test fixtures may not have been fully modernized to validate the current 36-capability ontology independently.

Additionally, the conformance runner uses a destructive file-swap approach: it overwrites the production `schemas/workflow_catalog.yaml` with fixture content, runs validation, then restores the original. If the process crashes between the swap and the restore (lines 23-29 of `run_conformance.py`), the production file is left in a corrupted state.

**Impact:**
- Conformance tests may pass while not fully exercising the current ontology structure.
- A crash during test execution could corrupt the production workflow catalog.
- Legacy comments could mislead contributors into using deprecated capability names.

**Remediation:**
1. Update all test fixtures to use only 36-capability model names, removing legacy mapping comments.
2. Refactor `run_conformance.py` to use a temporary directory copy of the catalog rather than overwriting the production file in-place.
3. Add a signal handler or `atexit` callback to guarantee file restoration.

**Effort:** Medium (3-5 days)

**Status:** **Closed** (PRs #91, #92) -- Conformance fixtures expanded to 22; runner refactored to use temp directory; legacy comments removed.

---

### TD-002: Shell Hook Simplistic Pattern Matching

| Field | Value |
|-------|-------|
| **ID** | TD-002 |
| **Severity** | High |
| **Category** | Security |
| **Component** | `hooks/pretooluse_require_checkpoint.sh` |

**Description:**
The shell-based pre-tool-use hook uses a simple `grep -E -i` pattern to detect mutation operations:

```bash
if echo "$payload" | grep -E -i "(Edit\b|Bash\b|Git\b|rm\b|mv\b|sed\b|perl\b)" >/dev/null; then
```

This approach has several weaknesses compared to the Python SDK's regex-based classifier in `grounded_agency/capabilities/mapper.py`, which uses compiled regex patterns with verbose mode, separate detection for destructive operations, network sends, and shell injection attempts (`_DESTRUCTIVE_PATTERNS`, `_NETWORK_SEND_PATTERNS`, `_SHELL_INJECTION_PATTERNS`):

1. The shell hook does not detect `Write` operations (only `Edit`).
2. It does not detect network-sending tools (`curl --data`, `scp`, `rsync`).
3. It does not detect Docker mutations (`docker rm`, `docker push`), Kubernetes mutations (`kubectl delete`, `kubectl apply`), or npm publish operations.
4. It relies on `\b` word boundaries in `grep -E`, which may behave differently across shell environments (GNU grep vs. BSD grep on macOS).
5. There is no detection of shell injection patterns (command substitution, backticks, `eval`).

**Impact:**
- Mutation operations could bypass the shell checkpoint enforcement layer entirely.
- The dual-layer safety model (shell hook + Python SDK) has an asymmetric coverage gap at the shell layer.
- False sense of security: the hook exists but does not provide comprehensive coverage.

**Remediation:**
1. Align the shell hook's detection patterns with the Python mapper's pattern set.
2. Add `Write`, `MultiEdit`, `NotebookEdit`, `curl`, `docker`, `kubectl`, `npm publish` to the shell pattern.
3. Consider replacing the shell hook with a Python-based hook that imports from `grounded_agency.capabilities.mapper` for pattern consistency.
4. Add regression tests that verify the shell hook catches all patterns the Python mapper catches.

**Effort:** Medium (3-5 days)

**Status:** **Closed** (PRs #91, #93) -- Shell hook expanded to 21 patterns; two-pass compound classifier added; interpreter pattern detection included.

---

### TD-003: No Integration Tests for Hook Pipeline

| Field | Value |
|-------|-------|
| **ID** | TD-003 |
| **Severity** | High |
| **Category** | Testing |
| **Component** | `tests/`, `hooks/`, `grounded_agency/hooks/` |

**Description:**
The project implements a dual-layer safety enforcement model:

- **Layer 1 (Shell):** `hooks/pretooluse_require_checkpoint.sh` runs as a Claude Code hook to block mutations without a `.claude/checkpoint.ok` marker file.
- **Layer 2 (Python):** `grounded_agency/hooks/evidence_collector.py` and `grounded_agency/hooks/skill_tracker.py` provide SDK-level post-tool-use hooks for evidence collection.

There are no integration tests that verify:
- Both layers operate correctly when composed together.
- The shell hook's checkpoint file marker (`.claude/checkpoint.ok`) is consistent with the Python `CheckpointTracker`'s in-memory state.
- Evidence is correctly collected after a mutation is permitted by the shell hook.
- The fail-safe behavior when one layer allows and the other blocks.

**Impact:**
- The dual-layer enforcement assumption -- that shell hooks catch what Python misses and vice versa -- remains unvalidated.
- Regressions in either layer could silently break the safety model without detection.
- Contributors may modify one layer without understanding the interaction contract with the other.

**Remediation:**
1. Create an integration test suite under `tests/integration/` that exercises both hook layers.
2. Test scenarios: mutation with valid checkpoint (both layers pass), mutation without checkpoint (shell layer blocks), mutation with expired checkpoint, checkpoint file present but Python tracker expired.
3. Add a test helper that simulates the Claude Code hook invocation flow end-to-end.

**Effort:** Large (1-2 weeks)

**Status:** **Closed** (PR #92) -- Integration test suite added; dual-layer scenarios covered; hook pipeline tests included.

---

### TD-004: Evidence Store O(n) Eviction on Secondary Indexes

| Field | Value |
|-------|-------|
| **ID** | TD-004 |
| **Severity** | Medium |
| **Category** | Code Quality |
| **Component** | `grounded_agency/state/evidence_store.py` (lines 307-323) |

**Description:**
The `EvidenceStore` uses a `deque` with `maxlen` for the primary anchor list, providing O(1) append and automatic eviction. However, the `_evict_oldest_from_indexes` method performs O(n) linear scans on secondary indexes:

```python
def _evict_oldest_from_indexes(self) -> None:
    oldest = self._anchors[0]
    kind_list = self._by_kind.get(oldest.kind, [])
    if oldest in kind_list:
        kind_list.remove(oldest)  # O(n) scan
    for cap_list in self._by_capability.values():
        if oldest in cap_list:
            cap_list.remove(oldest)  # O(n) scan
            break
```

The `list.remove()` call is O(n) because it scans the list to find the element, then shifts subsequent elements. The `oldest in kind_list` membership check is also O(n). At the default `max_anchors=10000`, each eviction performs up to two O(n) scans across potentially large lists.

**Impact:**
- At scale (10,000+ anchors at steady-state churn), every `add_anchor` call triggers an O(n) eviction, degrading performance from amortized O(1) to O(n) per insertion.
- For long-running agent sessions with high tool-use frequency, this could introduce latency spikes during evidence collection.
- The `_by_capability` scan iterates all capability lists in the worst case (though the `break` mitigates for the found case).

**Remediation:**
1. Replace secondary index lists with `OrderedDict` or `deque` structures that support O(1) removal from the front.
2. Alternatively, use a `dict[str, deque[EvidenceAnchor]]` for `_by_kind` and `_by_capability`, with the same `maxlen` proportional to expected distribution.
3. For the capability index, store a reverse mapping from anchor ref to capability ID to avoid scanning all capability lists.

**Effort:** Small (1-2 days)

**Status:** **Closed** (PR #91) -- O(1) priority eviction with CRITICAL/NORMAL/LOW buckets replaces linear scan.

---

### TD-005: Missing Type Annotations (Any in Hook Wrappers)

| Field | Value |
|-------|-------|
| **ID** | TD-005 |
| **Severity** | Medium |
| **Category** | Code Quality |
| **Component** | `grounded_agency/adapter.py`, `grounded_agency/hooks/evidence_collector.py`, `grounded_agency/hooks/skill_tracker.py` |

**Description:**
Hook callback functions use `Any` for SDK types to avoid a hard dependency on `claude-agent-sdk`:

```python
# evidence_collector.py, line 55
async def collect_evidence(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,          # <-- Should be HookContext
) -> dict[str, Any]:
```

```python
# skill_tracker.py, line 50
async def track_skill(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,          # <-- Should be HookContext
) -> dict[str, Any]:
```

The `TYPE_CHECKING` guard is imported but only used for the `HookCallback` type alias (line 16-17 in `evidence_collector.py`). The `context` parameter, which should be typed as `HookContext` from the SDK, is left as `Any` in both hook implementations.

The `adapter.py` module similarly uses `Any` extensively for SDK option types (line 26: `from typing import Any`).

**Impact:**
- `mypy` cannot catch type errors in hook callbacks, despite `pyproject.toml` setting `disallow_untyped_defs = true`.
- IDE autocompletion and inline documentation are degraded for `context` usage.
- Contributors may misuse the `context` parameter without type checker warnings.

**Remediation:**
1. Expand the `TYPE_CHECKING` guard to include `HookContext` and other SDK types.
2. Use `if TYPE_CHECKING:` conditional import with string-based forward references for `context: "HookContext"`.
3. Create a `grounded_agency/_types.py` module with protocol classes that mirror SDK types for structural typing without runtime dependency.
4. Add `mypy --strict` to the CI validation pipeline (once CI exists, see TD-009).

**Effort:** Small (1-2 days)

**Status:** **Closed** (PR #93) -- Protocol types added via `TYPE_CHECKING` guard; typed fallback for SDK types; `mypy --strict` passes.

---

### TD-006: No Workflow Execution Engine (Declarative Only)

| Field | Value |
|-------|-------|
| **ID** | TD-006 |
| **Severity** | Low |
| **Category** | Architecture |
| **Component** | `schemas/workflow_catalog.yaml` |

**Description:**
The workflow catalog defines 12 composed workflow patterns (e.g., `debug_code_change`, `rag_pipeline`, `security_assessment`, `multi_agent_orchestration`) as declarative YAML structures specifying steps, bindings, and capability compositions. However, there is no runtime engine that:

1. Instantiates a workflow from its YAML definition.
2. Orchestrates step execution in dependency order.
3. Enforces binding contracts between steps (output of step N matches input of step N+1).
4. Manages checkpoint/rollback lifecycle within a workflow context.
5. Validates that all `requires` edge constraints from the ontology are satisfied at runtime.

The workflows currently serve as reference composition patterns -- they document how capabilities should be combined but rely entirely on the agent (or human operator) to follow the pattern manually.

**Impact:**
- Workflows are documentation artifacts, not executable pipelines. The gap between declared workflow intent and actual agent behavior is unmonitored.
- There is no runtime validation that an agent executing a "debug_code_change" workflow actually follows the declared step sequence.
- Binding type mismatches between steps cannot be caught at runtime.

**Remediation:**
1. Design a lightweight workflow execution engine that reads workflow YAML and orchestrates capability invocations.
2. Start with a "validation mode" that traces agent actions and verifies they match a declared workflow pattern (audit-only, no enforcement).
3. Extend to "enforcement mode" where the engine gates step transitions based on precondition satisfaction.
4. Integrate with `CheckpointTracker` for automatic checkpoint creation before high-risk workflow steps.

**Effort:** XL (2+ weeks)

**Status:** **Open** -- Workflow execution engine remains a strategic investment for v1.2.0+.

---

### TD-007: Transform Registry Path References

| Field | Value |
|-------|-------|
| **ID** | TD-007 |
| **Severity** | Low |
| **Category** | Infrastructure |
| **Component** | `schemas/transforms/` |

**Description:**
The `schemas/transforms/` directory contains 7 transform definition files:

- `transform_coercion_registry.yaml` (master registry)
- `transform_mapping_coerce_number_to_string.yaml`
- `transform_mapping_coerce_string_to_number.yaml`
- `transform_mapping_project_array_object_to_array_string.yaml`
- `transform_mapping_rawlog_to_observation.yaml`
- `transform_mapping_stringify_object.yaml`
- `transform_mapping_wrap_any_to_object.yaml`

These transforms are referenced by workflow steps in `schemas/workflow_catalog.yaml` using path-relative references. If the transforms directory is restructured (e.g., moved under a `schemas/interop/` prefix or split by domain), all workflow references would break. There is no validation tool that checks transform path references for correctness, unlike `tools/validate_skill_refs.py` which validates skill file references.

**Impact:**
- Directory restructuring could silently break transform references without immediate detection.
- No automated validation catches "phantom paths" in transform references (unlike skill references which have `validate_skill_refs.py`).
- Contributors may inadvertently create broken references when reorganizing the schema directory.

**Remediation:**
1. Add transform path validation to `tools/validate_skill_refs.py` or create a dedicated `tools/validate_transform_refs.py`.
2. Consider using a registry pattern where transforms are referenced by ID (from `transform_coercion_registry.yaml`) rather than by file path.
3. Add a pre-commit hook that validates all cross-file references in the schemas directory.

**Effort:** Small (1-2 days)

**Status:** **Closed** (PR #93) -- `validate_transform_refs.py` added; all transform `mapping_ref` paths validated.

---

### TD-008: License Mismatch Between pyproject.toml and Repository

| Field | Value |
|-------|-------|
| **ID** | TD-008 |
| **Severity** | Critical |
| **Category** | Infrastructure |
| **Component** | `pyproject.toml`, `LICENSE` |

**Description:**
There is a direct contradiction between the declared license in `pyproject.toml` and the actual license file in the repository:

- **`pyproject.toml` line 10:** `license = "MIT"`
- **`pyproject.toml` line 27:** `"License :: OSI Approved :: MIT License"` (trove classifier)
- **`LICENSE` file:** Apache License, Version 2.0, January 2004

The Python package metadata (which is published to PyPI and consumed by package managers, license scanners, and dependency auditors) declares MIT, while the repository's `LICENSE` file contains the full text of Apache 2.0. These are materially different licenses:

- MIT is a permissive 2-clause license with no patent grant.
- Apache 2.0 includes an explicit patent grant (Section 3), contributor license terms, and trademark restrictions.

**Impact:**
- **Legal ambiguity:** Enterprise adopters running license compliance scans (FOSSA, Snyk, WhiteSource) will see conflicting signals, potentially blocking adoption.
- **PyPI metadata:** If published, the package would be indexed as MIT, misleading users who rely on PyPI metadata.
- **Contributor confusion:** Contributors may be uncertain which license governs their contributions.

**Remediation:**
1. Determine the intended license (consult project leadership).
2. Update `pyproject.toml` to match the repository license:
   - If Apache 2.0 is intended: change `license = "Apache-2.0"` and update the classifier to `"License :: OSI Approved :: Apache Software License"`.
   - If MIT is intended: replace the `LICENSE` file with MIT license text.
3. Add a license consistency check to CI (see TD-009).

**Effort:** Small (1-2 days)

**Status:** **Closed** (PR #92) -- License harmonized to Apache-2.0; `pyproject.toml` updated; license check in CI.

---

### TD-009: No CI Pipeline (GitHub Actions)

| Field | Value |
|-------|-------|
| **ID** | TD-009 |
| **Severity** | Critical |
| **Category** | Infrastructure |
| **Component** | `.github/workflows/` (missing) |

**Description:**
The repository has a `.github/pull_request_template.md` but no GitHub Actions workflow files under `.github/workflows/`. There is no automated CI pipeline to run on pull requests or pushes. The project has multiple validation scripts that are designed to be run locally:

- `tools/validate_workflows.py` -- Validates workflows against the ontology.
- `tools/validate_profiles.py` -- Validates domain profiles against schema.
- `tools/validate_skill_refs.py` -- Validates skill file references (no phantom paths).
- `tools/validate_ontology.py` -- Validates ontology graph (orphans, cycles, symmetry).
- `scripts/run_conformance.py` -- Runs conformance tests.
- `pytest tests/` -- Runs SDK integration tests.
- `mypy grounded_agency/` -- Type checking.
- `ruff check grounded_agency/` -- Linting.

None of these are automated. Contributors must remember to run them manually before submitting PRs.

**Impact:**
- Regressions can be merged without detection. A PR could break ontology validation, introduce phantom skill references, or fail type checking with no automated gate.
- The validation tooling investment (5+ validation scripts) is underutilized since it is not enforced.
- New contributors have no automated feedback loop -- they must discover and run validation scripts themselves.
- No automated test reporting or status checks on PRs.

**Remediation:**
1. Create `.github/workflows/ci.yml` with jobs for:
   - Python matrix testing (3.10, 3.11, 3.12)
   - YAML validation (all 4 validators)
   - Conformance tests
   - `mypy --strict` type checking
   - `ruff check` linting
   - License consistency check
2. Configure branch protection rules requiring CI passage before merge.
3. Add a badge to `README.md` showing CI status.
4. Consider adding a CODEOWNERS file for review automation.

**Effort:** Medium (3-5 days)

**Status:** **Closed** (PR #92) -- `.github/workflows/ci.yml` created; runs all 7 validators, conformance tests, pytest, mypy, ruff; branch protection configured.

---

### TD-010: OASF Mapping Completeness Gaps

| Field | Value |
|-------|-------|
| **ID** | TD-010 |
| **Severity** | Medium |
| **Category** | Architecture |
| **Component** | `schemas/interop/oasf_mapping.yaml` |

**Description:**
The OASF-to-Grounded-Agency capability mapping (OASF v0.8.0) has documented coverage gaps in both directions:

**6 GA capabilities with NO OASF equivalent** (empty reverse mapping arrays):
1. `attribute` -- Causal reasoning/attribution
2. `integrate` -- Data merging
3. `recall` -- Stored data retrieval (agent memory)
4. `receive` -- Pushed data/event acceptance
5. `send` -- External data transmission
6. `transition` -- Dynamics modeling / state machine transitions

**7 GA capabilities with only PARTIAL OASF mappings:**
1. `checkpoint` -- State preservation (partial: categories 12, 1201, 1202, 1204)
2. `simulate` -- Counterfactual analysis (partial: categories 15, 1501, 1504)
3. `inquire` -- Structured clarification (partial: categories 10, 1004)
4. `synchronize` -- Multi-agent state agreement (partial: categories 10, 1004)
5. `state` -- World state representation (partial: categories 1, 15, 106, 1501, 1504)
6. `ground` -- Evidence anchoring (partial: categories 1, 6, 103)
7. `rollback` -- Recovery mechanism (partial: categories 12, 1202)

Additionally, several OASF-to-GA mappings use `composition` mapping type, meaning a single OASF skill category requires multiple GA capabilities working together. This is semantically valid but creates an N:M mapping that is harder to implement programmatically.

**Impact:**
- Tools built for the OASF ecosystem cannot fully interoperate with the 6 unmapped GA capabilities.
- Agents claiming OASF compliance cannot express safety-critical capabilities like `checkpoint`, `rollback`, and `ground` through standard OASF skill codes.
- The OASF Safety Extensions Proposal (`docs/proposals/OASF_SAFETY_EXTENSIONS.md`) exists but has not been adopted by the OASF standard body.

**Remediation:**
1. Continue advocacy for the OASF Safety Extensions Proposal to get `checkpoint`, `rollback`, and `ground` adopted as first-class OASF skill categories.
2. Create an OASF compatibility adapter that wraps unmapped GA capabilities as OASF "custom skill" extensions (using OASF's extensibility mechanism).
3. Document the 6 unmapped capabilities as "GA-native" capabilities that extend beyond OASF's scope, with clear guidance for OASF-aligned consumers.
4. Track OASF version updates (currently v0.8.0) and update mappings as the OASF standard evolves.

**Effort:** Large (1-2 weeks)

**Status:** **Closed** (Issue #69) -- GA extension mechanism wraps 6 unmapped capabilities with synthetic `GA-` codes; `coverage_gaps` section documents all gaps structurally; 4 new `OASFAdapter` methods for coverage introspection; 11 new tests.

---

### TD-011: Checkpoint Persistence (In-Memory Only)

| Field | Value |
|-------|-------|
| **ID** | TD-011 |
| **Severity** | High |
| **Category** | Architecture |
| **Component** | `grounded_agency/state/checkpoint_tracker.py` |

**Description:**
The `CheckpointTracker` stores all checkpoint state in memory (`_active_checkpoint` and `_checkpoint_history` instance attributes). Despite accepting a `checkpoint_dir` parameter (line 93: `checkpoint_dir: str | Path = ".checkpoints"`), no code writes checkpoint data to the filesystem. The `checkpoint_dir` path is stored but never used for persistence:

```python
def __init__(self, checkpoint_dir: str | Path = ".checkpoints", ...):
    self._checkpoint_dir = Path(checkpoint_dir)  # Stored but never used for I/O
    self._active_checkpoint: Checkpoint | None = None
    self._checkpoint_history: list[Checkpoint] = []
```

This means:
1. If the agent process crashes, all checkpoint state is lost.
2. Checkpoints cannot be shared across multiple agent processes.
3. The audit trail (checkpoint history) is non-durable; it exists only for the lifetime of the process.
4. The shell hook checks for `.claude/checkpoint.ok` (a file-based marker), but the Python tracker has no mechanism to write or read this marker, creating a disconnect between the two safety layers.

**Impact:**
- **Safety gap:** A crash during a mutation sequence could leave the system in a state where the mutation was partially applied but the checkpoint record is lost.
- **Audit failure:** Post-incident investigation cannot reconstruct checkpoint history if the process has restarted.
- **Cross-layer inconsistency:** The shell hook relies on file-based checkpoint markers (`.claude/checkpoint.ok`), but the Python `CheckpointTracker` does not manage this file, meaning the two safety layers operate independently.

**Remediation:**
1. Implement filesystem persistence in `CheckpointTracker`:
   - Write checkpoint metadata to `checkpoint_dir` as JSON files on creation.
   - Load existing checkpoints from `checkpoint_dir` on initialization.
   - Update checkpoint file on consume/expire.
2. Bridge the shell hook: have `CheckpointTracker.create_checkpoint()` also write `.claude/checkpoint.ok` and `consume_checkpoint()` delete it.
3. Add a `CheckpointStore` abstraction to allow pluggable backends (filesystem, SQLite, Redis) for different deployment scenarios.

**Effort:** Medium (3-5 days)

**Status:** **Closed** (PR #92) -- File-based persistence backend implemented; `CheckpointTracker` manages `.claude/checkpoint.ok` lifecycle; bridges shell and SDK layers.

---

### TD-012: No YAML Schema Validation (No JSON Schema)

| Field | Value |
|-------|-------|
| **ID** | TD-012 |
| **Severity** | Medium |
| **Category** | Documentation |
| **Component** | `schemas/` |

**Description:**
The YAML schema files (`capability_ontology.yaml`, `workflow_catalog.yaml`, `profiles/*.yaml`, `transforms/*.yaml`) define the project's core data structures but lack formal schema definitions. There is no JSON Schema, YAML Schema, or equivalent machine-readable schema that specifies:

1. Required fields and their types for capability definitions.
2. Allowed values for enums (risk levels, layer names, edge types).
3. Structural constraints (e.g., every capability must have `input` and `output` schemas).
4. Cross-reference integrity (e.g., edge targets must reference existing capabilities).

Validation is currently performed by bespoke Python scripts (`tools/validate_workflows.py`, `tools/validate_profiles.py`, `tools/validate_ontology.py`) that encode structural expectations in Python code. The `schemas/profiles/profile_schema.yaml` exists for domain profiles, but the main ontology and workflow catalog have no equivalent schema.

**Impact:**
- **Schema drift:** The implicit structure of `capability_ontology.yaml` can diverge from what validation scripts expect without clear error messages. A contributor could add a field in the wrong location and get a confusing Python traceback rather than a schema validation error.
- **IDE support:** Without JSON Schema, editors cannot provide autocompletion, inline validation, or hover documentation for YAML files.
- **External consumers:** Third-party tools that consume the ontology YAML must reverse-engineer the schema from examples rather than referencing a formal definition.

**Remediation:**
1. Create JSON Schema definitions for `capability_ontology.yaml` and `workflow_catalog.yaml`.
2. Register schemas in `$schema` header fields for IDE integration.
3. Add schema validation to CI (e.g., `ajv` or `check-jsonschema` CLI tool).
4. Consider publishing schemas to JSON Schema Store for community IDE support.

**Effort:** Large (1-2 weeks)

**Status:** **Closed** (PR #92) -- JSON Schema (Draft 2020-12) validation added for ontology and workflow catalog; IDE integration enabled.

---

### TD-013: Bash Command Classifier False Positives on Compound Commands

| Field | Value |
|-------|-------|
| **ID** | TD-013 |
| **Severity** | Low |
| **Category** | Code Quality |
| **Component** | `grounded_agency/capabilities/mapper.py` (lines 43-62) |

**Description:**
The `_SHELL_INJECTION_PATTERNS` regex in the Bash command classifier flags several patterns that are commonly benign in developer workflows:

```python
_SHELL_INJECTION_PATTERNS = re.compile(r"""
    \$\( |         # Command substitution $(...)
    ` |            # Backtick command substitution
    \$\{ |         # Variable expansion ${...}
    ;\s*[a-zA-Z] | # Command chaining with semicolon
    \|\| |         # OR chaining
    && |           # AND chaining
    ...
""")
```

This means common patterns like `git add . && git commit -m "msg"` or `echo $HOME` are classified as high-risk mutations requiring a checkpoint. While the fail-safe default (unknown = high-risk) is a sound security principle, it creates friction for routine compound commands that are standard in developer workflows.

The comment on line 52 acknowledges this: `# AND chaining (could be benign, but risky)`.

**Impact:**
- Excessive checkpoint requirements for benign operations, potentially causing "checkpoint fatigue" where users create perfunctory checkpoints that reduce the safety signal.
- Common CI/CD script patterns (`set -e && make test && make deploy`) would all be flagged as injection.
- Read-only compound commands like `ls && pwd && whoami` are unnecessarily elevated to high risk.

**Remediation:**
1. Implement a two-pass classifier: first check if the compound command's individual components are all read-only, then check for injection patterns.
2. Add a "known safe compound patterns" allowlist for common developer idioms.
3. Consider context-aware classification: `&&` chaining read-only commands should not trigger the injection detector.

**Effort:** Medium (3-5 days)

**Status:** **Closed** (PR #93) -- Two-pass compound classifier handles read-only chains correctly; `ls && pwd` classified as low-risk.

---

### TD-014: Conformance Runner Writes Results to Repository Root

| Field | Value |
|-------|-------|
| **ID** | TD-014 |
| **Severity** | Low |
| **Category** | Testing |
| **Component** | `scripts/run_conformance.py` (line 52) |

**Description:**
The conformance test runner writes its results file (`conformance_results.json`) directly to the repository root:

```python
(ROOT / "conformance_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
```

This file is not in `.gitignore`, meaning it could be accidentally committed. It also pollutes the repository root directory, which should contain only top-level project files.

**Impact:**
- Accidental commits of test artifacts to the repository.
- Repository root clutter from generated files.
- Potential merge conflicts if multiple developers run conformance tests.

**Remediation:**
1. Move the results output to a `build/` or `.conformance/` directory (and add to `.gitignore`).
2. Add `conformance_results.json` to `.gitignore` as an immediate mitigation.
3. Consider writing results to stdout instead of file, or use a `--output` flag.

**Effort:** Small (1-2 days)

**Status:** **Closed** (PR #92) -- Results written to `.conformance/` directory; `conformance_results.json` added to `.gitignore`.

---

## 3. Severity Distribution

### Summary Table (Original Assessment)

| Severity | Original | Closed | Remaining Open | Open Items |
|----------|----------|--------|---------------|------------|
| Critical | 2 | 2 | 0 | -- |
| High | 3 | 3 | 0 | -- |
| Medium | 5 | 5 | 0 | -- |
| Low | 4 | 3 | 1 | TD-006 |
| **Total** | **14** | **13** | **1** | |

**Debt reduction: 92.9% (13/14 items closed)**

### Distribution Chart (Remaining)

```
Critical  [-------------]  0 items   (0%)
High      [-------------]  0 items   (0%)
Medium    [-------------]  0 items   (0%)
Low       [#------------]  1 item    (100%)  TD-006 (workflow engine)
          +-+-+-+-+-+-+-+
          0 1 2 3 4 5 6
```

### By Category (Updated)

| Category | Original | Closed | Remaining | Open Items |
|----------|----------|--------|-----------|------------|
| Architecture | 3 | 2 | 1 | TD-006 |
| Code Quality | 3 | 3 | 0 | -- |
| Testing | 3 | 3 | 0 | -- |
| Infrastructure | 3 | 3 | 0 | -- |
| Security | 1 | 1 | 0 | -- |
| Documentation | 1 | 1 | 0 | -- |

---

## 4. Effort Estimates by Category

### Individual Effort Summary

| ID | Title | Effort | Est. Days | Status |
|----|-------|--------|-----------|--------|
| TD-001 | Legacy Conformance Fixtures | Medium | 3-5 | **Closed** |
| TD-002 | Shell Hook Pattern Matching | Medium | 3-5 | **Closed** |
| TD-003 | Hook Pipeline Integration Tests | Large | 5-10 | **Closed** |
| TD-004 | Evidence Store O(n) Eviction | Small | 1-2 | **Closed** |
| TD-005 | Missing Type Annotations | Small | 1-2 | **Closed** |
| TD-006 | No Workflow Execution Engine | XL | 10+ | Open |
| TD-007 | Transform Path References | Small | 1-2 | **Closed** |
| TD-008 | License Mismatch | Small | 1-2 | **Closed** |
| TD-009 | No CI Pipeline | Medium | 3-5 | **Closed** |
| TD-010 | OASF Mapping Completeness | Large | 5-10 | **Closed** |
| TD-011 | Checkpoint Persistence | Medium | 3-5 | **Closed** |
| TD-012 | No YAML Schema Validation | Large | 5-10 | **Closed** |
| TD-013 | Bash Classifier False Positives | Medium | 3-5 | **Closed** |
| TD-014 | Conformance Results Placement | Small | 1-2 | **Closed** |

### Aggregate by Effort Category

| Effort Level | Original | Closed | Remaining | Est. Days Remaining |
|--------------|----------|--------|-----------|---------------------|
| Small (1-2 days) | 5 | 5 | 0 | 0 |
| Medium (3-5 days) | 5 | 5 | 0 | 0 |
| Large (1-2 weeks) | 3 | 3 | 0 | 0 |
| XL (2+ weeks) | 1 | 0 | 1 (TD-006) | 10+ |
| **Total** | **14** | **13** | **1** | **~10+ days** |

---

## 5. Prioritized Remediation Plan

Items are grouped into sprints based on severity, dependency relationships, and strategic importance.

### Sprint 1 (P0): Foundation -- Legal & Automation -- **COMPLETED**

**Goal:** Eliminate legal risk and establish automated quality gates.
**Timeline:** Week 1-2
**Total Effort:** 4-7 days

| ID | Title | Effort | Rationale |
|----|-------|--------|-----------|
| TD-008 | License Mismatch | Small | **Blocking.** Legal ambiguity prevents enterprise adoption. Must resolve before any external distribution or PyPI publish. |
| TD-009 | No CI Pipeline | Medium | **Enabling.** All subsequent remediations benefit from automated validation. CI is the force multiplier for all other debt reduction. |
| TD-014 | Conformance Results Placement | Small | **Quick win.** Fix during CI setup since conformance tests will be integrated into the pipeline. |

**Acceptance Criteria:**
- [x] `pyproject.toml` license field matches `LICENSE` file.
- [x] `.github/workflows/ci.yml` exists and runs all validation scripts.
- [x] Branch protection rules require CI passage.
- [x] `conformance_results.json` is either written to `build/` or added to `.gitignore`.

---

### Sprint 2 (P1): Safety -- Integration Tests & Checkpoint Durability -- **COMPLETED**

**Goal:** Close safety model gaps and ensure mutation enforcement is tested and durable.
**Timeline:** Week 3-5
**Total Effort:** 8-15 days

| ID | Title | Effort | Rationale |
|----|-------|--------|-----------|
| TD-003 | Hook Pipeline Integration Tests | Large | **Safety-critical.** The dual-layer enforcement model is the project's core safety guarantee. It must be tested. |
| TD-011 | Checkpoint Persistence | Medium | **Safety-critical.** In-memory-only checkpoints undermine the safety model for any long-running or crash-prone agent session. |
| TD-001 | Legacy Conformance Fixtures | Medium | **Dependency.** Integration tests (TD-003) need clean test fixtures. Modernize fixtures first. |

**Acceptance Criteria:**
- [x] Integration test suite under `tests/integration/` covers all dual-layer scenarios.
- [x] `CheckpointTracker` persists state to filesystem.
- [x] Shell hook and Python `CheckpointTracker` share checkpoint state via filesystem.
- [x] All test fixtures reference only 36-capability model names.
- [x] Conformance runner uses temp directory, not file-swap.

---

### Sprint 3 (P2): Quality -- Type Safety, Performance, Hook Hardening -- **COMPLETED**

**Goal:** Improve code quality, developer experience, and close shell hook security gap.
**Timeline:** Week 6-8
**Total Effort:** 7-12 days

| ID | Title | Effort | Rationale |
|----|-------|--------|-----------|
| TD-005 | Missing Type Annotations | Small | **Developer experience.** Enables `mypy --strict` in CI (from TD-009). |
| TD-004 | Evidence Store O(n) Eviction | Small | **Performance.** Simple data structure change with measurable impact. |
| TD-002 | Shell Hook Pattern Matching | Medium | **Security.** Aligning shell patterns with Python patterns closes the asymmetric coverage gap. |
| TD-013 | Bash Classifier False Positives | Medium | **Usability.** Reduces checkpoint fatigue from benign compound commands. |

**Acceptance Criteria:**
- [x] `mypy --strict` passes on `grounded_agency/` package.
- [x] Evidence store secondary indexes use O(1) eviction.
- [x] Shell hook covers all patterns from Python `_DESTRUCTIVE_PATTERNS` and `_NETWORK_SEND_PATTERNS`.
- [x] Compound read-only commands (`ls && pwd`) are classified as low-risk.
- [x] Benchmark: 10,000 anchor insert/evict cycle completes in under 100ms.

---

### Sprint 4 (P3): Strategic -- Interop, Schemas & Workflow Engine -- **3 of 4 COMPLETE**

**Goal:** Address long-term architectural debt and standards interoperability.
**Timeline:** Week 9-14 (or ongoing backlog)
**Total Effort:** 20-30+ days (10+ days remaining)

| ID | Title | Effort | Rationale |
|----|-------|--------|-----------|
| TD-006 | Workflow Execution Engine | XL | **Strategic.** Transforms workflows from documentation to executable pipelines. Largest single investment. |
| TD-010 | OASF Mapping Completeness | Large | **Ecosystem.** Depends on external OASF standard evolution; focus on adapter patterns. |
| TD-012 | No YAML Schema Validation | Large | **Developer experience.** JSON Schema enables IDE support and external consumer tooling. |
| TD-007 | Transform Path References | Small | **Maintenance.** Low urgency but easy to address alongside schema work. |

**Acceptance Criteria:**
- [ ] Workflow engine MVP: validation mode traces agent actions against workflow definitions. **(TD-006 -- Open)**
- [x] OASF compatibility adapter wraps unmapped GA capabilities. **(TD-010 -- Closed)**
- [x] JSON Schema published for `capability_ontology.yaml` and `workflow_catalog.yaml`. **(TD-012 -- Closed)**
- [x] Transform references validated by existing or new validation tool. **(TD-007 -- Closed)**

---

## 6. Sprint Allocation Strategy

### Recommended Investment: 20% Engineering Time

Following the industry-standard technical debt management guideline, we recommend allocating **20% of engineering capacity** to debt reduction on an ongoing basis.

#### Rationale

| Allocation | Investment | Outcome |
|------------|------------|---------|
| 0% (ignore debt) | Zero | Debt compounds; velocity degrades over time; safety assumptions erode. |
| 10% (minimal) | ~1 day/week | Addresses quick wins but leaves structural debt untouched. |
| **20% (recommended)** | **~1 day/week per engineer** | **Steady debt reduction without impacting feature velocity. Completes P0-P2 in ~8 weeks.** |
| 30%+ (aggressive) | >1.5 days/week | Appropriate only for a dedicated "debt sprint" or pre-launch hardening phase. |

#### Implementation Model

**Dedicated Debt Days:** Reserve one day per week (e.g., every Friday) where the team works exclusively on technical debt items from this register. This creates predictable cadence and prevents debt work from being perpetually deprioritized.

**Sprint Integration:** Alternatively, include 1-2 debt items in each feature sprint. Pair debt items with related feature work (e.g., address TD-005 type annotations when adding new hook features).

#### Projected Timeline (20% allocation, 1 engineer)

| Sprint | Weeks | Items | Status | Cumulative Debt Reduced |
|--------|-------|-------|--------|-------------------------|
| Sprint 1 (P0) | 1-2 | TD-008, TD-009, TD-014 | **Completed** | 21% (3/14 items) |
| Sprint 2 (P1) | 3-5 | TD-003, TD-011, TD-001 | **Completed** | 43% (6/14 items) |
| Sprint 3 (P2) | 6-8 | TD-005, TD-004, TD-002, TD-013 | **Completed** | 71% (10/14 items) |
| Sprint 4 (P3) | 9-14 | TD-006, TD-010, TD-012, TD-007 | **Partial** (3/4) | 92.9% (13/14 items) |

#### Tracking & Governance

1. **Monthly review:** Re-assess severity of remaining items. New debt may be discovered; priorities may shift.
2. **Debt budget:** Each sprint may introduce new debt (marked `[NEW]` in this register). The debt budget tracks whether the register is growing or shrinking over time. Target: net debt count decreases by at least 1 item per sprint.
3. **Completion metric:** Track the "debt reduction velocity" -- number of items resolved per sprint. Initial target: 2-3 items per sprint.
4. **Escalation:** If any Critical item remains unresolved for more than 2 sprints, escalate to project leadership for resource allocation review.

---

*This register should be reviewed and updated at the start of each sprint. Items may be added, re-prioritized, or closed as the codebase evolves.*

*Last updated: 2026-02-02 | 92.9% debt reduction achieved (13/14 items closed)*
