# Testing Guide

## Document Metadata

| Field           | Value                                      |
|-----------------|--------------------------------------------|
| Document        | `analysis/08-testing-guide.md`             |
| Project         | Agent Capability Standard                  |
| Version         | 0.1.0                                      |
| Last Updated    | 2026-01-30                                 |
| Status          | Active                                     |

---

## 1. Three-Layer Test Architecture

The Agent Capability Standard project organizes its test infrastructure into three distinct layers. Each layer validates different aspects of the system at different granularities.

```
+-------------------------------------------------------+
|                    Layer 3: Conformance                 |
|  scripts/run_conformance.py + tests/*.workflow_catalog |
|  Schema compliance / fixture-based validation          |
+-------------------------------------------------------+
|                    Layer 2: Benchmarks                  |
|  benchmarks/runner.py + benchmarks/scenarios/          |
|  Performance, correctness, and GA vs baseline          |
+-------------------------------------------------------+
|                    Layer 1: Unit Tests                  |
|  tests/test_sdk_integration.py                         |
|  tests/test_oasf_adapter.py                            |
|  SDK classes tested in isolation                       |
+-------------------------------------------------------+
```

### 1.1 Unit Tests (Layer 1)

**Location:** `tests/test_sdk_integration.py`, `tests/test_oasf_adapter.py`

Unit tests validate the SDK classes in isolation using pytest. They cover the five core components of the `grounded_agency` package (CapabilityRegistry, ToolCapabilityMapper, CheckpointTracker, EvidenceStore, GroundedAgentAdapter) plus the OASF adapter, hooks, and integration workflows. These tests run quickly without any external dependencies.

**Key characteristics:**
- All tests import from the `grounded_agency` package directly
- Fixtures use the real `capability_ontology.yaml` and `oasf_mapping.yaml` from the `schemas/` directory
- Async tests are annotated with `@pytest.mark.asyncio` and handled via pytest-asyncio
- Mock SDK types (`MockClaudeAgentOptions`) replace actual Claude Agent SDK dependencies
- No network calls, no file system mutations outside test scope

### 1.2 Benchmark Scenarios (Layer 2)

**Location:** `benchmarks/runner.py`, `benchmarks/scenarios/`, `benchmarks/tests/test_scenarios.py`

Benchmark scenarios compare a naive (baseline) approach against the Grounded Agency (GA) approach across five scenarios, measuring quantitative improvement:

| Scenario               | What It Measures                                 | Primary Metric          |
|------------------------|--------------------------------------------------|-------------------------|
| `conflicting_sources`  | Conflict resolution with trust-weighted evidence | Accuracy                |
| `mutation_recovery`    | Checkpoint/rollback data preservation            | Recovery rate           |
| `decision_audit`       | Explanation faithfulness and evidence grounding   | Faithfulness            |
| `workflow_type_error`  | Design-time vs runtime type error detection       | Detection rate          |
| `capability_gap`       | Pre-execution capability blocking                | Compute savings         |

Each scenario extends the abstract `BenchmarkScenario` base class defined in `benchmarks/scenarios/base.py`, which requires four methods:

```python
class BenchmarkScenario(ABC):
    @abstractmethod
    def setup(self) -> None: ...
    @abstractmethod
    def run_baseline(self) -> dict[str, Any]: ...
    @abstractmethod
    def run_ga(self) -> dict[str, Any]: ...
    @abstractmethod
    def compare(self, baseline_result, ga_result) -> dict[str, float]: ...
```

The runner supports multiple iterations with seed-based reproducibility and can generate reports in both Markdown and JSON formats.

### 1.3 Conformance Tests (Layer 3)

**Location:** `scripts/run_conformance.py`, `tests/EXPECTATIONS.json`, `tests/*.workflow_catalog.yaml`

Conformance tests validate that the workflow validator (`tools/validate_workflows.py`) correctly accepts valid workflows and rejects invalid ones. They work by temporarily swapping `schemas/workflow_catalog.yaml` with fixture files and checking the validator's exit code against expected pass/fail outcomes.

**Fixture files in `tests/`:**

| Fixture File                                         | Expected Result |
|------------------------------------------------------|-----------------|
| `pass_reference.workflow_catalog.yaml`               | PASS            |
| `fail_unknown_capability.workflow_catalog.yaml`       | FAIL            |
| `fail_bad_binding_path.workflow_catalog.yaml`         | FAIL            |
| `fail_ambiguous_untyped.workflow_catalog.yaml`        | FAIL            |
| `fail_consumer_contract_mismatch.workflow_catalog.yaml` | FAIL          |

---

## 2. pytest Configuration

The pytest configuration is defined in `pyproject.toml` under the `[tool.pytest.ini_options]` section:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v"
```

### 2.1 Configuration Details

| Setting         | Value      | Effect                                                       |
|-----------------|------------|--------------------------------------------------------------|
| `testpaths`     | `["tests"]`| Restricts test discovery to the `tests/` directory           |
| `asyncio_mode`  | `"auto"`   | Automatically handles async test functions without explicit event loop setup |
| `addopts`       | `"-v"`     | Enables verbose output by default for all test runs          |

### 2.2 Async Mode

The `asyncio_mode = "auto"` setting means pytest-asyncio automatically treats any `async def test_*` function as an asyncio test. Combined with `@pytest.mark.asyncio`, this eliminates the need for manual event loop management. This is used extensively in the permission callback tests and hook tests.

### 2.3 Markers Used

| Marker              | Usage                                                   |
|----------------------|---------------------------------------------------------|
| `@pytest.mark.asyncio` | Marks async test functions for pytest-asyncio execution |

### 2.4 Dependencies

From `pyproject.toml` `[project.optional-dependencies]`:

```toml
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "mypy>=1.0",
    "ruff>=0.1.0",
]
```

Install with:
```bash
pip install -e ".[dev]"
```

---

## 3. Test Fixtures and Patterns

### 3.1 SDK Integration Tests (`tests/test_sdk_integration.py`)

This file contains 726 lines across 7 test classes and approximately 50 individual test methods. All tests import from the `grounded_agency` package.

#### Fixtures Defined

```python
@pytest.fixture
def ontology_path() -> str:
    """Path to the capability ontology YAML file."""

@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    """Fresh CapabilityRegistry loaded from real ontology."""

@pytest.fixture
def mapper() -> ToolCapabilityMapper:
    """Fresh ToolCapabilityMapper instance."""

@pytest.fixture
def checkpoint_tracker() -> CheckpointTracker:
    """Fresh CheckpointTracker instance."""

@pytest.fixture
def evidence_store() -> EvidenceStore:
    """Fresh EvidenceStore instance."""

@pytest.fixture
def adapter(ontology_path: str) -> GroundedAgentAdapter:
    """Fresh GroundedAgentAdapter in strict mode."""
```

All fixtures create fresh instances per test, preventing state leakage between tests. The `adapter` fixture initializes with `strict_mode=True`, which means mutations without a valid checkpoint will be blocked.

#### TestCapabilityRegistry (16 tests)

Tests the `CapabilityRegistry` class, which loads and queries `capability_ontology.yaml`:

| Test Method                                    | What It Validates                                          |
|------------------------------------------------|------------------------------------------------------------|
| `test_load_ontology`                           | Ontology loads with `nodes`, `edges`, and `layers` keys    |
| `test_get_capability`                          | Retrieves `mutate` with correct layer, risk, mutation flag |
| `test_get_nonexistent_capability`              | Returns `None` for unknown capability IDs                  |
| `test_get_high_risk_capabilities`              | Finds all high-risk capabilities (includes `mutate`, `send`) |
| `test_get_checkpoint_required_capabilities`    | Finds all capabilities requiring checkpoints               |
| `test_get_edges`                               | Retrieves edges for `checkpoint` capability                |
| `test_get_required_capabilities`               | `mutate` requires `checkpoint`                             |
| `test_get_layer`                               | Gets EXECUTE layer metadata with `mutate` listed           |
| `test_version`                                 | Version string starts with `2.`                            |
| `test_capability_count`                        | Exactly 36 atomic capabilities                             |
| `test_get_preceding_capabilities`              | `mutate` is preceded by `checkpoint` and `plan`            |
| `test_get_preceding_capabilities_no_predecessors` | `observe` has no predecessors                           |
| `test_get_conflicting_capabilities`            | `rollback` conflicts with `persist` and `mutate`           |
| `test_get_conflicting_capabilities_symmetric`  | Conflict relationships are bidirectional                   |
| `test_get_alternatives`                        | `search` is alternative to `retrieve` (symmetric)          |
| `test_get_specialized_by`                      | `detect` is specialized by `classify`                      |

#### TestToolCapabilityMapper (12 tests)

Tests the mapping of Claude Code tools to capability metadata:

| Test Method                        | Tool Input             | Expected Capability | Risk  |
|------------------------------------|------------------------|---------------------|-------|
| `test_map_read_tool`              | `Read` with path       | `retrieve`          | low   |
| `test_map_write_tool`             | `Write` with file_path | `mutate`            | high  |
| `test_map_edit_tool`              | `Edit` with file_path  | `mutate`            | high  |
| `test_map_grep_tool`             | `Grep` with pattern    | `search`            | low   |
| `test_map_bash_read_only`        | `Bash` with `ls -la`   | `observe`           | low   |
| `test_map_bash_destructive`      | `Bash` with `rm -rf`   | `mutate`            | high  |
| `test_map_bash_git_push`         | `Bash` with `git push` | `mutate`            | high  |
| `test_map_bash_curl_post`        | `Bash` with `curl -X POST` | `send`          | high  |
| `test_map_unknown_tool`          | `UnknownTool`          | `observe`           | medium |
| `test_is_high_risk`              | Helper method          | Boolean check       | --    |
| `test_requires_checkpoint`       | Helper method          | Boolean check       | --    |

The mapper uses pattern matching on Bash command strings to determine intent (read vs. destructive vs. network).

#### TestCheckpointTracker (7 tests)

Tests the checkpoint lifecycle:

| Test Method                               | What It Validates                                     |
|-------------------------------------------|-------------------------------------------------------|
| `test_create_checkpoint`                  | Returns ID starting with `chk_`, tracker shows valid  |
| `test_has_valid_checkpoint_false_initially`| No checkpoint exists before any creation              |
| `test_consume_checkpoint`                 | Consuming removes the checkpoint from active state    |
| `test_checkpoint_scope_matching`          | `src/*.py` matches `src/main.py` but not `tests/test.py` |
| `test_wildcard_scope`                     | `*` scope matches any file path                       |
| `test_get_active_checkpoint`              | Returns checkpoint object with scope and reason       |
| `test_checkpoint_history`                 | History tracks consumed checkpoints                   |

#### TestEvidenceStore (5 tests)

Tests evidence collection and querying:

| Test Method                        | What It Validates                                          |
|------------------------------------|------------------------------------------------------------|
| `test_add_anchor`                 | Adding an anchor increments store length                   |
| `test_get_recent`                 | Returns N most recent evidence references                  |
| `test_get_by_kind`               | Filters by `tool_output`, `file`, or `mutation` kinds      |
| `test_get_for_capability`        | Associates evidence with capability ID for later query     |
| `test_evidence_anchor_from_command` | Creates command-type anchors with exit code metadata     |

#### TestGroundedAgentAdapter (7 tests)

Tests the main adapter that wraps SDK options:

| Test Method                                        | What It Validates                                    |
|----------------------------------------------------|------------------------------------------------------|
| `test_adapter_initialization`                      | All sub-components initialized                       |
| `test_wrap_options`                                | Injects `Skill` tool, enables checkpointing, adds hook |
| `test_wrap_options_preserves_existing`              | Existing tools preserved when wrapping               |
| `test_create_checkpoint_convenience`               | Convenience method delegates to tracker              |
| `test_get_evidence`                                | Returns evidence from internal store                 |
| `test_permission_callback_blocks_without_checkpoint` | Writes blocked when no checkpoint (strict mode)    |
| `test_permission_callback_allows_with_checkpoint`  | Writes allowed when checkpoint exists                |
| `test_permission_callback_allows_read_always`      | Read operations always permitted                     |

#### TestHooks (3 tests)

Tests the hook callbacks:

| Test Method                             | What It Validates                                        |
|-----------------------------------------|----------------------------------------------------------|
| `test_evidence_collector_hook`         | Hook collects evidence and returns empty dict (passive)  |
| `test_skill_tracker_hook`              | Checkpoint skill invocation creates checkpoint in tracker |
| `test_skill_tracker_ignores_non_skill` | Non-Skill tools do not trigger checkpoint creation       |

#### TestIntegration (4 tests)

End-to-end workflow tests:

| Test Method                                 | What It Validates                                        |
|---------------------------------------------|----------------------------------------------------------|
| `test_full_checkpoint_mutation_flow`       | Complete block -> checkpoint -> allow -> consume -> block |
| `test_evidence_collection_during_workflow` | Evidence accumulated during multi-tool workflow          |
| `test_ontology_version_accessible`         | Version accessible through adapter                       |
| `test_capability_count_correct`            | 36 capabilities accessible through adapter               |

### 3.2 OASF Adapter Tests (`tests/test_oasf_adapter.py`)

This file contains 187 lines across 5 test classes and approximately 25 individual test methods.

#### Fixture

```python
@pytest.fixture
def adapter() -> OASFAdapter:
    """Create an adapter with the real mapping and ontology files."""
    registry = CapabilityRegistry(ONTOLOGY_PATH)
    return OASFAdapter(MAPPING_PATH, registry=registry)
```

Uses real `oasf_mapping.yaml` and `capability_ontology.yaml` files.

#### TestOASFAdapterLoading (5 tests)

| Test Method                                  | What It Validates                                 |
|----------------------------------------------|---------------------------------------------------|
| `test_loads_mapping_file`                    | Category count equals 15                          |
| `test_oasf_version`                          | OASF version is `0.8.0`                          |
| `test_mapping_version`                       | Mapping version is `1.0.0`                        |
| `test_total_mappings_includes_subcategories` | Total mappings exceed 15 (subcategories included) |
| `test_missing_file_raises`                   | `FileNotFoundError` for nonexistent path          |

#### TestOASFTranslation (8 tests)

Tests skill code translation across all mapping types:

| Mapping Type    | Example Code | Skill Name            | Expected Capabilities       |
|-----------------|-------------|-----------------------|-----------------------------|
| `direct`        | `109`       | Text Classification   | `classify`                  |
| `domain`        | `111`       | Token Classification  | `detect` (domain=token)     |
| `composition`   | `101`       | NLU                   | `detect`, `classify`        |
| `workflow`      | `6`         | RAG                   | workflow=`rag_pipeline`     |
| category-level  | `2`         | Computer Vision       | `detect` (domain=image)     |
| subcategory     | `801`       | Threat Detection      | `detect` (domain=security)  |
| aggregate       | `1`         | NLP                   | `classify` + others         |
| unknown         | `99999`     | --                    | raises `UnknownSkillError`  |

#### TestSafetyMetadata (6 tests)

Tests that risk and checkpoint properties propagate correctly from the ontology through the OASF mapping layer.

#### TestReverseLookup (4 tests)

Tests bidirectional mapping: given a capability ID, find all OASF skill codes that map to it. Verifies coverage by checking that every capability in the forward mapping appears in the reverse mapping.

#### TestListOperations (4 tests)

Tests enumeration: listing categories, listing all mappings, and single-mapping retrieval.

---

## 4. Conformance Testing System

### 4.1 How Conformance Tests Work

The conformance runner (`scripts/run_conformance.py`) performs the following steps for each fixture:

```
1. Read the real schemas/workflow_catalog.yaml (backup)
2. Replace it with the fixture file content
3. Run tools/validate_workflows.py --emit-patch
4. Check exit code (0 = pass, non-zero = fail)
5. Compare against expected result from EXPECTATIONS.json
6. Restore the original workflow_catalog.yaml
```

This swap-and-restore pattern allows the validator to run against modified workflow catalogs without permanent changes.

### 4.2 EXPECTATIONS.json Structure

```json
{
  "pass_reference": {
    "should_pass": true
  },
  "fail_unknown_capability": {
    "should_pass": false
  },
  "fail_bad_binding_path": {
    "should_pass": false
  },
  "fail_ambiguous_untyped": {
    "should_pass": false
  },
  "fail_consumer_contract_mismatch": {
    "should_pass": false,
    "should_emit_suggestions": true
  }
}
```

Each key corresponds to a fixture file named `<key>.workflow_catalog.yaml` in `tests/`. The `should_pass` field indicates whether the validator should exit with code 0 (pass) or non-zero (fail). The optional `should_emit_suggestions` field indicates whether the validator is expected to produce suggestion output.

### 4.3 Fixture File Format

Fixture files are complete `workflow_catalog.yaml` documents. They follow the same schema as the production catalog but contain intentional errors for fail-case fixtures:

| Fixture                                | Injected Error                                  |
|----------------------------------------|-------------------------------------------------|
| `pass_reference`                       | None -- valid reference catalog                 |
| `fail_unknown_capability`              | References `nonexistent-capability` in a step   |
| `fail_bad_binding_path`                | Invalid `${store.path}` references              |
| `fail_ambiguous_untyped`               | Ambiguous untyped binding that cannot be inferred |
| `fail_consumer_contract_mismatch`      | Consumer capability input schema type mismatch  |

### 4.4 Results Output

The runner writes `conformance_results.json` to the project root with details for each fixture:

```json
[
  {
    "name": "pass_reference",
    "ok": true,
    "stdout": "...",
    "stderr": "..."
  },
  {
    "name": "fail_unknown_capability",
    "ok": false,
    "stdout": "...",
    "stderr": "..."
  }
]
```

Console output shows `PASS` or `FAIL` for each fixture, with a summary line indicating overall conformance status. The exit code is 0 for full conformance and 1 for any failures.

---

## 5. Benchmark Testing System

### 5.1 Scenario Architecture

All benchmark scenarios inherit from `BenchmarkScenario` in `benchmarks/scenarios/base.py`:

```python
@dataclass
class BenchmarkResult:
    scenario_name: str
    baseline_metrics: dict[str, Any]
    ga_metrics: dict[str, Any]
    improvement: dict[str, float]
    execution_time_ms: float
    metadata: dict[str, Any] | None = None
```

The `run()` method orchestrates the full lifecycle:
1. Call `setup()` to prepare fixtures
2. For each iteration: call `run_baseline()` then `run_ga()`
3. Average numeric metrics across iterations
4. Call `compare()` to compute improvement deltas
5. Return `BenchmarkResult`

### 5.2 Available Scenarios

| Scenario                | Class                         | Key Metrics                                    |
|-------------------------|-------------------------------|------------------------------------------------|
| `conflicting_sources`   | `ConflictingSourcesScenario`  | accuracy, evidence_completeness                |
| `mutation_recovery`     | `MutationRecoveryScenario`    | recovery_rate, data_integrity_rate, lines_lost |
| `decision_audit`        | `DecisionAuditScenario`       | faithfulness, confabulation_rate               |
| `workflow_type_error`   | `WorkflowTypeErrorScenario`   | design_time_detection_rate, suggestion_accuracy|
| `capability_gap`        | `CapabilityGapScenario`       | compute_saved, identification_accuracy         |

### 5.3 Benchmark Tests (`benchmarks/tests/test_scenarios.py`)

The benchmark test suite in `benchmarks/tests/test_scenarios.py` contains 531 lines across 12 test classes and approximately 30 test methods. It validates:

- All 5 scenarios are registered in the `SCENARIOS` dict
- Each scenario produces metrics within expected ranges
- Seed-based reproducibility: same seed produces identical results
- Different seeds produce different test cases
- Edge cases: single test case, single decision
- Full benchmark run returns proper `BenchmarkResult`
- Multi-iteration runs average results correctly
- Cleanup behavior for temp directories
- `_average_metrics` helper handles numeric and non-numeric values
- `compare()` method output includes expected improvement keys

---

## 6. Writing New Tests

### 6.1 Test Class Organization

Follow the established pattern of organizing tests into classes by component:

```python
class TestNewComponent:
    """Tests for NewComponent."""

    def test_basic_behavior(self, fixture_name: Type):
        """Test description."""
        # Arrange
        component = fixture_name

        # Act
        result = component.do_something()

        # Assert
        assert result is not None
```

### 6.2 Fixture Usage

Create fixtures at module level or in `conftest.py`:

```python
@pytest.fixture
def my_component() -> MyComponent:
    """Create a fresh MyComponent."""
    return MyComponent()
```

Fixtures in the test files use pytest's dependency injection pattern. When one fixture depends on another, pytest resolves the chain automatically:

```python
@pytest.fixture
def registry(ontology_path: str) -> CapabilityRegistry:
    # ontology_path fixture is automatically resolved first
    return CapabilityRegistry(ontology_path)
```

### 6.3 Async Test Patterns

For testing async functions (hooks, permission callbacks):

```python
@pytest.mark.asyncio
async def test_async_operation(self, adapter: GroundedAgentAdapter):
    """Test async behavior."""
    callback = adapter._make_permission_callback()

    result = await callback("Write", {"file_path": "test.txt"}, None)

    if isinstance(result, dict):
        assert result.get("allowed") is False
```

The `asyncio_mode = "auto"` setting in pyproject.toml means pytest-asyncio automatically handles the event loop for any test function declared with `async def`. The `@pytest.mark.asyncio` decorator is still used to make intent explicit.

### 6.4 Mocking Strategies

The project uses two mocking approaches:

**1. Mock dataclasses for SDK types:**

```python
@dataclass
class MockClaudeAgentOptions:
    """Mock ClaudeAgentOptions for testing."""
    allowed_tools: list = field(default_factory=list)
    permission_mode: str = "default"
    hooks: dict = field(default_factory=dict)
    setting_sources: list = field(default_factory=lambda: ["project"])
    enable_file_checkpointing: bool = False
    can_use_tool: object = None
```

This approach is used because the actual `claude-agent-sdk` package is an optional dependency. The mock replicates the interface the adapter expects.

**2. `unittest.mock.patch` for selective method replacement:**

```python
from unittest.mock import patch

def test_warning_logged_for_missing_capability(self, adapter, caplog):
    with patch.object(adapter._registry, "get_capability", return_value=None):
        with caplog.at_level(logging.WARNING):
            result = adapter.translate("109")
    assert "not found in registry" in caplog.text
```

### 6.5 Assertion Patterns

The test suite uses several assertion styles:

```python
# Exact equality
assert registry.capability_count == 36

# Membership
assert "mutate" in ids
assert "classify" in result.mapping.capabilities

# Property checks
assert mutate.risk == "high"
assert mutate.mutation is True

# Type checks
assert isinstance(result, BenchmarkResult)

# Range checks (benchmarks)
assert 0.40 <= result["accuracy"] <= 0.65

# Exception checking
with pytest.raises(UnknownSkillError):
    adapter.translate("99999")

# Log capture
with caplog.at_level(logging.WARNING):
    result = adapter.translate("109")
assert "not found in registry" in caplog.text
```

### 6.6 Adding a New Benchmark Scenario

To add a new benchmark scenario:

1. Create `benchmarks/scenarios/my_scenario.py` extending `BenchmarkScenario`:

```python
class MyScenario(BenchmarkScenario):
    name = "my_scenario"
    description = "Description of what this measures"

    def setup(self) -> None: ...
    def run_baseline(self) -> dict[str, Any]: ...
    def run_ga(self) -> dict[str, Any]: ...
    def compare(self, baseline, ga) -> dict[str, float]: ...
```

2. Register in `benchmarks/scenarios/__init__.py`:

```python
from .my_scenario import MyScenario

SCENARIOS = {
    # ... existing scenarios ...
    "my_scenario": MyScenario,
}
```

3. Add tests in `benchmarks/tests/test_scenarios.py`.

---

## 7. Test Coverage Analysis

### 7.1 Well-Tested Areas

| Component              | Test Count | Coverage Level |
|------------------------|------------|----------------|
| CapabilityRegistry     | 16         | High           |
| ToolCapabilityMapper   | 12         | High           |
| CheckpointTracker      | 7          | High           |
| EvidenceStore          | 5          | Medium-High    |
| GroundedAgentAdapter   | 7          | High           |
| Hook callbacks         | 3          | Medium         |
| Integration workflows  | 4          | Medium         |
| OASF Adapter           | 25         | High           |
| Benchmark scenarios    | 30+        | High           |
| Conformance fixtures   | 5          | Medium         |

### 7.2 Coverage Gaps

The following areas have been identified as lacking test coverage:

#### No integration tests for hook pipeline

The shell-based hooks defined in `hooks/` are not tested:
- `hooks/pretooluse_require_checkpoint.sh` -- Pre-mutation checkpoint enforcement
- `hooks/posttooluse_log_tool.sh` -- Audit logging after tool use
- `hooks/hooks.json` -- Hook configuration binding

These hooks are executed by the Claude Code runtime and would require integration testing with the actual CLI to validate.

#### No tests for shell hook scripts

The `.sh` hook scripts use `jq` for JSON parsing and shell logic for enforcement. There are no tests that verify:
- Correct `jq` query extraction from tool input
- Checkpoint marker detection in file content
- Audit log file writing and format
- Exit code behavior (0 = allow, 1 = block)

#### No performance or load tests for EvidenceStore at scale

The `EvidenceStore` tests use small datasets (1-5 anchors). There are no tests for:
- FIFO eviction behavior when the store reaches its maximum capacity
- Query performance with thousands of evidence anchors
- Memory usage patterns under sustained evidence collection
- Concurrent access patterns (if applicable)

#### No tests for validator tools

The Python validator scripts in `tools/` are tested indirectly through conformance tests (which invoke `validate_workflows.py` via subprocess), but there are no direct unit tests for:
- `tools/validate_workflows.py` -- The workflow validator's internal functions
- `tools/validate_profiles.py` -- Domain profile validation
- `tools/validate_skill_refs.py` -- Skill file reference validation
- `tools/validate_ontology.py` -- Ontology graph validation (orphans, cycles, symmetry)
- `tools/sync_skill_schemas.py` -- Schema synchronization logic

#### No fuzz testing for regex patterns

The `ToolCapabilityMapper` uses regex pattern matching to classify Bash commands as read-only, destructive, or network operations. There is no fuzz testing to verify:
- Edge cases in command detection (`rm` inside a string vs. as a command)
- Aliased or obfuscated destructive commands
- Complex piped commands with mixed read/write intent
- Unicode or special character handling

#### No end-to-end tests with actual Claude Agent SDK

All adapter tests use `MockClaudeAgentOptions`. There are no tests that:
- Import from the real `claude-agent-sdk` package
- Verify actual SDK compatibility
- Test the full `can_use_tool` callback signature with real SDK types
- Validate hook registration with the actual SDK hook system

This is partially by design -- the SDK is an optional dependency (`pip install -e ".[sdk]"`), so tests must work without it.

#### No test isolation for conformance runner

The conformance runner (`scripts/run_conformance.py`) swaps the production `schemas/workflow_catalog.yaml` during execution. If the process is interrupted, the production file could be left in a corrupted state. There are no tests for:
- Interrupted execution recovery
- Concurrent conformance test runs
- File permission errors during swap

---

## 8. Running Tests

### 8.1 Prerequisites

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"
```

### 8.2 Unit Tests

```bash
# Run all unit tests with verbose output
pytest tests/ -v

# Run only SDK integration tests
pytest tests/test_sdk_integration.py -v

# Run only OASF adapter tests
pytest tests/test_oasf_adapter.py -v

# Run a specific test class
pytest tests/test_sdk_integration.py::TestCapabilityRegistry -v

# Run a specific test method
pytest tests/test_sdk_integration.py::TestCheckpointTracker::test_create_checkpoint -v

# Run only async tests
pytest tests/ -v -k "async"
```

**Expected output (all tests passing):**

```
tests/test_sdk_integration.py::TestCapabilityRegistry::test_load_ontology PASSED
tests/test_sdk_integration.py::TestCapabilityRegistry::test_get_capability PASSED
tests/test_sdk_integration.py::TestCapabilityRegistry::test_get_nonexistent_capability PASSED
...
tests/test_oasf_adapter.py::TestOASFAdapterLoading::test_loads_mapping_file PASSED
tests/test_oasf_adapter.py::TestOASFTranslation::test_direct_mapping PASSED
...
========================= XX passed in X.XXs =========================
```

### 8.3 Benchmark Tests

```bash
# Run benchmark scenario tests
pytest benchmarks/tests/test_scenarios.py -v

# Run benchmark scenarios directly (performance comparison)
python benchmarks/runner.py

# Run a specific benchmark scenario
python benchmarks/runner.py --scenario conflicting_sources

# Run with multiple iterations for averaging
python benchmarks/runner.py --iterations 5

# Run with verbose output
python benchmarks/runner.py --verbose

# Generate a Markdown report
python benchmarks/runner.py --report --output benchmarks/results/report.md

# Generate a JSON report
python benchmarks/runner.py --report --format json --output benchmarks/results/report.json

# Set custom seed for reproducibility
python benchmarks/runner.py --seed 123
```

### 8.4 Conformance Tests

```bash
# Run conformance test suite
python scripts/run_conformance.py
```

**Expected output:**

```
PASS: pass_reference
PASS: fail_unknown_capability
PASS: fail_bad_binding_path
PASS: fail_ambiguous_untyped
PASS: fail_consumer_contract_mismatch

Conformance PASSED
```

Note: a `PASS` for a `fail_*` fixture means the validator correctly rejected the invalid workflow. Results are written to `conformance_results.json`.

### 8.5 Static Analysis

```bash
# Type checking with mypy
mypy grounded_agency/

# Linting with ruff
ruff check .

# Auto-fix linting issues
ruff check . --fix
```

### 8.6 Validation Tools

```bash
# Validate workflows against the ontology
python tools/validate_workflows.py

# Validate domain profiles against schema
python tools/validate_profiles.py

# Validate skill file references (no phantom paths)
python tools/validate_skill_refs.py

# Validate ontology graph (orphans, cycles, symmetry)
python tools/validate_ontology.py
```

### 8.7 Full Validation Pipeline

To run the complete test and validation suite:

```bash
# Unit tests
pytest tests/ -v

# Benchmark tests
pytest benchmarks/tests/test_scenarios.py -v

# Conformance tests
python scripts/run_conformance.py

# Static analysis
mypy grounded_agency/
ruff check .

# Schema and ontology validation
python tools/validate_workflows.py
python tools/validate_profiles.py
python tools/validate_skill_refs.py
python tools/validate_ontology.py
```

---

## 9. Continuous Integration Considerations

### 9.1 Recommended CI Steps

A CI pipeline for this project should execute the following stages in order:

```
Stage 1: Lint + Type Check
  - ruff check .
  - mypy grounded_agency/

Stage 2: Unit Tests
  - pytest tests/ -v

Stage 3: Benchmark Tests
  - pytest benchmarks/tests/test_scenarios.py -v

Stage 4: Conformance Tests
  - python scripts/run_conformance.py

Stage 5: Schema Validation
  - python tools/validate_workflows.py
  - python tools/validate_profiles.py
  - python tools/validate_skill_refs.py
  - python tools/validate_ontology.py
```

### 9.2 Environment Matrix

From `pyproject.toml`:

```
Python versions: 3.10, 3.11, 3.12
Required: pyyaml>=6.0
Dev: pytest>=7.0, pytest-asyncio>=0.21, mypy>=1.0, ruff>=0.1.0
Optional: claude-agent-sdk>=0.1.0
```

### 9.3 Artifacts to Preserve

- `conformance_results.json` -- Conformance test output
- `benchmarks/results/` -- Benchmark reports (Markdown or JSON)
- `tools/validator_suggestions.json` -- Validator patch suggestions (when `--emit-patch` is used)

---

## 10. Troubleshooting

### 10.1 Common Issues

**`ModuleNotFoundError: No module named 'grounded_agency'`**

The package is not installed. Run `pip install -e ".[dev]"` from the repository root.

**`ModuleNotFoundError: No module named 'pytest_asyncio'`**

The dev dependencies are not installed. Run `pip install -e ".[dev]"`.

**Conformance tests leave `workflow_catalog.yaml` in a corrupted state**

If the conformance runner is interrupted, restore the file from git:
```bash
git checkout schemas/workflow_catalog.yaml
```

**Benchmark tests fail with `AssertionError: setup() must be called`**

Some scenarios (e.g., `MutationRecoveryScenario`) require `setup()` to be called before `run_baseline()` or `run_ga()`. The `run()` method handles this automatically, but direct method calls must follow the lifecycle.

**Async tests hang or timeout**

Ensure `pytest-asyncio>=0.21` is installed and `asyncio_mode = "auto"` is set in `pyproject.toml`.

### 10.2 Debugging Test Failures

```bash
# Run with full traceback
pytest tests/ -v --tb=long

# Run with print output visible
pytest tests/ -v -s

# Run a single failing test
pytest tests/test_sdk_integration.py::TestCheckpointTracker::test_create_checkpoint -v -s

# Run with pdb on failure
pytest tests/ -v --pdb
```
