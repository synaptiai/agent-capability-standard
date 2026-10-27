# Testing Guide

## Document Metadata

| Field           | Value                                      |
|-----------------|--------------------------------------------|
| Document        | `analysis/08-testing-guide.md`             |
| Project         | Agent Capability Standard                  |
| Version         | 0.2.0                                      |
| Last Updated    | 2026-02-01                                 |
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

**Location:** `scripts/run_conformance.py`, `tests/fixtures/EXPECTATIONS.json`, `tests/fixtures/*.workflow_catalog.yaml`, `tests/conformance/expressions/{eval,check}.json`

Conformance tests validate that the workflow validator (the Rust core behind `tools/validate_workflows.py`) correctly accepts valid workflows and rejects invalid ones with the right diagnostics. The runner passes each fixture to the validator with `--catalog` (the production catalog is never swapped or modified) and checks the exit code and the emitted error and warning codes against `EXPECTATIONS.json`.

**Fixture files in `tests/fixtures/`:** 55 at the time of writing (`ls tests/fixtures/*.workflow_catalog.yaml | wc -l`), named `pass_*`, `fail_*` and `patch_*` and covering levels L1-L4. A sample:

| Fixture File                                         | Expected Result |
|------------------------------------------------------|-----------------|
| `pass_reference.workflow_catalog.yaml`               | PASS, no warnings |
| `pass_soft_requires_warn.workflow_catalog.yaml`      | PASS, warning W601 |
| `fail_unknown_capability.workflow_catalog.yaml`       | FAIL (V101)     |
| `fail_bad_binding_path.workflow_catalog.yaml`         | FAIL (B201)     |
| `fail_precedes_order.workflow_catalog.yaml`           | FAIL (V102)     |
| `fail_conflicts_parallel.workflow_catalog.yaml`       | FAIL (F504)     |
| `patch_string_to_number_coercion.workflow_catalog.yaml` | FAIL (B203), with suggestions |

The expression fixtures (`eval.json`, `check.json`) are exercised by the Rust tests and compared against cel-go in CI's `cel-differential` job.

---

## 2. pytest Configuration

The pytest configuration is defined in `pyproject.toml` under the `[tool.pytest.ini_options]` section:

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "benchmarks/tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-v"
```

### 2.1 Configuration Details

| Setting         | Value      | Effect                                                       |
|-----------------|------------|--------------------------------------------------------------|
| `testpaths`     | `["tests", "benchmarks/tests"]`| Restricts test discovery to `tests/` and `benchmarks/tests/` |
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
    "pytest>=7.0,<9",
    "pytest-asyncio>=0.21,<1",
    "mypy>=1.0,<2",
    "ruff>=0.16,<0.17",
    "types-PyYAML>=6.0,<7",
    "hypothesis>=6.0,<7",
    "jsonschema>=4.0,<5",
    "claude-agent-sdk>=0.1.25,<0.3",
]
```

Install with (builds the Rust core; `constraints.txt` pins the exact versions CI runs):
```bash
pip install -e ".[dev]" -c constraints.txt
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

The conformance runner (`scripts/run_conformance.py`) performs the following steps for each entry in `EXPECTATIONS.json`:

```
1. Locate tests/fixtures/<name>.workflow_catalog.yaml (missing file = failure)
2. Delete any stale tools/validator_suggestions.json
3. Run tools/validate_workflows.py --catalog <fixture>
4. Check exit code (0 = pass, non-zero = fail) against should_pass
5. Read tools/validator_suggestions.json and check expected_error_codes
   (structured_errors, for failing fixtures) and expected_warning_codes
   (structured_warnings)
```

The production `schemas/workflow_catalog.yaml` is never touched. Because the validator lives in the Rust core, the package must be built first (`pip install -e .`).

### 4.2 EXPECTATIONS.json Structure

```json
{
  "pass_reference": {
    "should_pass": true,
    "level": "L1",
    "category": "structural",
    "expected_warning_codes": []
  },
  "pass_soft_requires_warn": {
    "should_pass": true,
    "level": "L1",
    "category": "edges",
    "expected_warning_codes": ["W601"]
  },
  "fail_unknown_capability": {
    "should_pass": false,
    "level": "L1",
    "category": "structural",
    "expected_error_codes": ["V101"]
  },
  "patch_string_to_number_coercion": {
    "should_pass": false,
    "should_emit_suggestions": true,
    "level": "L4",
    "category": "patches",
    "expected_error_codes": ["B203"]
  }
}
```

Each key corresponds to a fixture file named `<key>.workflow_catalog.yaml` in `tests/fixtures/`. The `should_pass` field indicates whether the validator should exit with code 0 (pass) or non-zero (fail). `expected_error_codes` lists codes that must be emitted; `expected_warning_codes` lists warning codes that must be emitted, and an empty list means no warning may be emitted. `level` and `category` are informational; the optional `should_emit_suggestions` field indicates whether the validator is expected to produce suggestion output.

### 4.3 Fixture File Format

Fixture files are complete `workflow_catalog.yaml` documents, usually starting with a `# Standard version: 1.1.0` header. They follow the same schema as the production catalog but contain intentional errors for fail-case fixtures:

| Fixture                                | Injected Error                                  |
|----------------------------------------|-------------------------------------------------|
| `pass_reference`                       | None -- valid reference catalog                 |
| `fail_unknown_capability`              | References a nonexistent capability in a step (V101) |
| `fail_bad_binding_path`                | Invalid `${store.path}` references (B201)       |
| `fail_missing_store_ref`               | Reference to an undefined store (B202)          |
| `fail_precedes_order`                  | `classify` placed before `detect` (V102)        |
| `fail_conflicts_parallel`              | `conflicts_with` pair in one `parallel_group` (F504) |
| `pass_safety_flag_downgrade`           | Step flag weaker than the ontology (W602, still passes) |

### 4.4 Results Output

The runner writes `build/conformance_results.json` with details for each fixture:

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

Console output shows `PASS: <name>` or `FAIL: <name> ...` for each fixture, then `Conformance PASSED` or `Conformance FAILED (N failures)`. The exit code is 0 for full conformance and 1 for any failures.

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
| ToolCapabilityMapper   | 12+        | High           |
| CheckpointTracker      | 7+         | High           |
| EvidenceStore          | 5+         | High           |
| GroundedAgentAdapter   | 7+         | High           |
| Hook callbacks         | 3+         | Medium-High    |
| Hook pipeline (integration) | 5+    | Medium-High    |
| Shell hook scripts     | 8+         | Medium-High    |
| Integration workflows  | 4+         | Medium         |
| OASF Adapter           | 25         | High           |
| Benchmark scenarios    | 30+        | High           |
| Conformance fixtures   | 55    | High           |
| Regex fuzz testing     | 10+        | Medium         |
| Validator tools        | 7+         | Medium         |

### 7.2 Coverage Gaps (Updated 2026-02-01)

The following areas were identified as lacking test coverage in the initial assessment. Most have been addressed:

#### ~~No integration tests for hook pipeline~~ — **RESOLVED** (PR #92)

Integration tests now cover the dual-layer hook pipeline including pre-tool-use checkpoint enforcement and post-tool-use evidence collection. Tests validate that shell hooks and Python SDK hooks operate correctly when composed together.

#### ~~No tests for shell hook scripts~~ — **RESOLVED** (PR #91)

Shell hook scripts now have unit tests covering:
- `jq` query extraction from tool input payloads
- Checkpoint marker JSON validation with timestamp freshness
- Audit log HMAC chain integrity verification
- Exit code behavior (0 = allow, 1 = block)

#### ~~No performance or load tests for EvidenceStore at scale~~ — **RESOLVED** (PR #91)

Evidence store performance tests added covering:
- Priority-aware eviction with CRITICAL/NORMAL/LOW buckets at capacity
- O(1) eviction performance with 10,000+ anchors
- Benchmark: insert/evict cycle at scale

#### ~~No tests for validator tools~~ — **RESOLVED** (PR #92)

Validator tools are now tested both directly and via the expanded conformance suite (55 fixtures). The validation logic itself lives in the Rust core and is also covered by `cargo test` (CI `rust-core` job). All validators run in CI.

#### ~~No fuzz testing for regex patterns~~ — **RESOLVED** (PR #91)

Fuzz testing added for the `ToolCapabilityMapper` regex patterns covering:
- Edge cases in command detection
- Interpreter patterns (`python -c`, `ruby -e`, `node -e`)
- Process substitution patterns
- Compound command classification

#### No end-to-end tests with actual Claude Agent SDK — **PARTIALLY RESOLVED** (PR #92)

The adapter tests now include typed fallback tests that exercise the SDK integration path without the real SDK installed. Protocol types via `TYPE_CHECKING` ensure interface compatibility. Full end-to-end tests with the real SDK remain aspirational, as the SDK is an optional dependency.

#### ~~No test isolation for conformance runner~~ — **RESOLVED** (PR #92)

The conformance runner no longer touches the production catalog at all: it passes each fixture to the validator with `--catalog`. It uses a temporary directory for its build output and installs signal handlers for clean shutdown.

---

## 8. Running Tests

### 8.1 Prerequisites

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with development dependencies (builds the Rust core; needs rustc >= 1.86)
pip install -e ".[dev]" -c constraints.txt
```

The Rust core has its own test suite:

```bash
cd core && cargo test
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
PASS: pass_minimal_single_step
...
PASS: fail_unknown_capability
PASS: fail_bad_binding_path
...

Conformance PASSED
```

Note: a `PASS` for a `fail_*` fixture means the validator correctly rejected the invalid workflow with the expected error codes. Results are written to `build/conformance_results.json`.

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
python tools/sync_skill_schemas.py --check

# Rust core
(cd core && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test)
```

---

## 9. Continuous Integration

### 9.1 Current CI Pipeline (`.github/workflows/ci.yml`)

The CI pipeline runs these jobs in parallel on every PR and push to `main`. Every Python job installs a pinned Rust toolchain (`RUST_TOOLCHAIN`) and builds the package with `pip install -e`, since the validator lives in the Rust core:

```
validate-schemas: Validate YAML schemas
  - python tools/validate_ontology.py
  - python tools/validate_workflows.py
  - python tools/validate_profiles.py
  - python tools/validate_skill_refs.py
  - python tools/validate_canonical_schemas.py
  - python tools/validate_rfcs.py
  - python tools/validate_constraints.py
  - python tools/validate_doc_links.py
  - python tools/sync_skill_schemas.py --check

rust-core: Rust core (fmt, clippy, tests, MSRV)   [in core/]
  - cargo fmt --check
  - cargo clippy --locked --all-targets -- -D warnings
  - cargo clippy --locked --all-targets --features python -- -D warnings
  - cargo test --locked
  - cargo +1.86.0 check --locked --all-targets --features python   (MSRV)

cel-differential: Expressions stay a CEL-compatible profile   [Go]
  - go run . tests/conformance/expressions/eval.json .../check.json   (vs cel-go)

lint: Lint & type-check
  - ruff check grounded_agency/ tests/ tools/ scripts/ benchmarks/
  - ruff format --check grounded_agency/ tests/ benchmarks/
  - mypy grounded_agency/

test: Tests (Python 3.10, 3.11, 3.12)
  - pytest tests/ -v --tb=short

benchmarks: Benchmark validation
  - pytest benchmarks/tests/ -v --tb=short
  - python benchmarks/runner.py --report --format json --output benchmarks/results/benchmark_results.json
  - python tools/validate_benchmark_deps.py

conformance: Conformance tests
  - python scripts/run_conformance.py
```

### 9.2 Environment Matrix

From `pyproject.toml`:

```
Python versions: 3.10, 3.11, 3.12
Rust: pinned toolchain (RUST_TOOLCHAIN in ci.yml); MSRV 1.86 checked
Build: maturin>=1.9,<2
Required: pyyaml>=6.0,<7
Dev: pytest>=7.0,<9, pytest-asyncio>=0.21,<1, mypy>=1.0,<2, ruff>=0.16,<0.17 (exact versions in constraints.txt)
Optional: claude-agent-sdk>=0.1.25,<0.3
```

### 9.3 Artifacts to Preserve

- `build/conformance_results.json` -- Conformance test output (uploaded by the `conformance` job)
- `benchmarks/results/` -- Benchmark reports (Markdown or JSON; `benchmark_results.json` uploaded by the `benchmarks` job)
- `tools/validator_suggestions.json` -- Validator diagnostics and patch suggestions (written on every run)
- `tools/validator_patch.diff` -- Suggested patch (only with `--emit-patch`)

---

## 10. Troubleshooting

### 10.1 Common Issues

**`ModuleNotFoundError: No module named 'grounded_agency'`**

The package is not installed. Run `pip install -e ".[dev]" -c constraints.txt` from the repository root (needs a Rust toolchain, rustc >= 1.86).

**`ModuleNotFoundError: No module named 'grounded_agency._core'`** (or `cannot import name '_core'`)

The Rust extension has not been built, or the build is stale. Re-run `pip install -e ".[dev]" -c constraints.txt`; an editable install does not rebuild the extension when `core/` changes.

**`ModuleNotFoundError: No module named 'pytest_asyncio'`**

The dev dependencies are not installed. Run `pip install -e ".[dev]"`.

**Conformance fixture fails with "missing expected warning codes" or "expected no warning codes"**

The fixture's `expected_warning_codes` in `tests/fixtures/EXPECTATIONS.json` no longer matches what the validator emits. Run `python tools/validate_workflows.py --catalog tests/fixtures/<name>.workflow_catalog.yaml` to see the warnings, then fix the fixture or the expectation. (The runner never modifies `schemas/workflow_catalog.yaml`.)

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
