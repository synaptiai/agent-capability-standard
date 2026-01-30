---
name: verify
description: Check correctness against tests, specs, or invariants; produce pass/fail evidence. Use when validating changes, testing hypotheses, checking invariants, or confirming behavior matches expectations.
argument-hint: "[spec|tests] [artifact|target] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Bash, Grep
context: fork
agent: general-purpose
---

## Live Context

Before verification, gather current state:

- Working directory: !`pwd`
- Git status: !`git status --short 2>/dev/null || echo "Not a git repo"`
- Recent commits: !`git log --oneline -5 2>/dev/null || echo "No git history"`
- Last modified files: !`find . -type f -mmin -30 -not -path './.git/*' 2>/dev/null | head -10 || echo "None"`

## Intent

Execute **verify** to determine whether an artifact (code, configuration, state, output) conforms to a specification, passes tests, or satisfies declared invariants.

**Success criteria:**
- Clear PASS or FAIL verdict with supporting evidence
- Every check is grounded to observable output or file content
- Failures include actionable fix suggestions
- All assumptions about expected behavior are explicit

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `spec` | Yes | string\|object | The specification, test suite, or invariants to check against |
| `artifact` | Yes | string\|object | The target being verified (file path, function, API endpoint, state) |
| `constraints` | No | object | Verification constraints: timeout, test filter, coverage threshold |
| `check_types` | No | array | Types of checks: assertion, invariant, regression, schema |

## Procedure

1) **Load specification**: Read the spec/test/invariant definition
   - Identify testable assertions from the spec
   - Parse test commands or invariant expressions
   - Note any preconditions required for verification

2) **Examine artifact**: Inspect the target being verified
   - Read relevant code, config, or state
   - Identify the specific behavior/properties to check
   - Check preconditions are met before running tests

3) **Execute checks**: Run each verification check systematically
   - For test suites: execute via Bash, capture stdout/stderr
   - For invariants: evaluate conditions, record boolean results
   - For schema validation: compare structure against schema
   - Record timing and resource usage if relevant

4) **Analyze results**: Determine verdict from check outcomes
   - PASS: All checks succeed
   - FAIL: One or more checks fail
   - INCONCLUSIVE: Unable to determine due to errors or missing data

5) **Ground claims**: Attach evidence anchors to all findings
   - Format: `file:line`, `tool:bash:<command>`, or `test:<test_name>`
   - Include exact error messages and stack traces for failures

6) **Format output**: Structure results per output contract
   - Include fix suggestions for each failure
   - Calculate coverage metrics if applicable

## Output Contract

Return a structured object:

```yaml
verdict: PASS | FAIL | INCONCLUSIVE
checks_run:
  - name: string  # Check identifier
    type: assertion | invariant | regression | schema
    target: string  # What was checked
    result: PASS | FAIL
    evidence: string  # Output or file reference
failures:
  - check: string  # Which check failed
    expected: string  # What was expected
    actual: string  # What was observed
    severity: low | medium | high | critical
fix_suggestions:
  - failure_ref: string  # Reference to failure
    suggestion: string  # How to fix
    confidence: number  # 0.0-1.0 for suggestion quality
coverage:
  checked: integer  # Number of checks run
  total: integer  # Total checks possible
  percentage: number  # Coverage percentage
confidence: number  # 0.0-1.0
evidence_anchors: ["file:line", "tool:bash:...", "test:..."]
assumptions: []  # Explicit assumptions made
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `verdict` | enum | Overall verification result |
| `checks_run` | array | List of all checks executed with results |
| `failures` | array | Details of failed checks |
| `fix_suggestions` | array | Actionable suggestions to fix failures |
| `coverage` | object | Metrics about verification coverage |
| `confidence` | number | 0.0-1.0 based on evidence quality and check coverage |
| `evidence_anchors` | array | File:line, URLs, or tool output references |
| `assumptions` | array | Explicit assumptions about expected behavior |

## Examples

### Example 1: Unit Test Verification

**Input:**
```yaml
spec: "pytest tests/test_calculator.py -v"
artifact: "src/calculator.py"
constraints:
  timeout: "60s"
  check_types: ["regression", "assertion"]
```

**Output:**
```yaml
verdict: FAIL
checks_run:
  - name: test_add_positive
    type: assertion
    target: Calculator.add
    result: PASS
    evidence: "tool:bash:pytest - PASSED"
  - name: test_divide_by_zero
    type: assertion
    target: Calculator.divide
    result: FAIL
    evidence: "tool:bash:pytest - AssertionError: Expected ZeroDivisionError"
failures:
  - check: test_divide_by_zero
    expected: "ZeroDivisionError raised"
    actual: "Returns infinity"
    severity: high
fix_suggestions:
  - failure_ref: test_divide_by_zero
    suggestion: "Add check for divisor == 0 before division in Calculator.divide()"
    confidence: 0.9
coverage:
  checked: 5
  total: 5
  percentage: 100.0
confidence: 0.95
evidence_anchors:
  - "tool:bash:pytest tests/test_calculator.py -v"
  - "src/calculator.py:42"
assumptions:
  - "Test environment has pytest installed"
  - "Tests are deterministic"
```

**Evidence pattern:** Test output captured from pytest execution, line numbers from stack traces.

---

### Example 2: Schema Validation

**Input:**
```yaml
spec:
  type: schema
  schema_path: "schemas/config.json"
artifact: "config/production.yaml"
```

**Output:**
```yaml
verdict: PASS
checks_run:
  - name: schema_validation
    type: schema
    target: config/production.yaml
    result: PASS
    evidence: "All 12 required fields present, types valid"
failures: []
fix_suggestions: []
coverage:
  checked: 1
  total: 1
  percentage: 100.0
confidence: 1.0
evidence_anchors:
  - "config/production.yaml:1-45"
  - "schemas/config.json:1"
assumptions:
  - "JSON Schema draft-07 validation semantics"
```

## Verification

Apply the following verification patterns:

- [ ] **Evidence Grounding**: All verdicts anchored to test output or file content
- [ ] **Contract Validation**: Output matches schema with required fields
- [ ] **Idempotency Check**: Re-running verify produces same verdict (given unchanged inputs)
- [ ] **Coverage Tracking**: checks_run.length == coverage.total

**Verification tools:** Bash (for test execution), Read (for evidence files)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- Do not modify the artifact being verified
- Do not skip failing tests or mask errors
- Stop and clarify if spec is ambiguous or missing
- Timeout all external test execution (default 5 minutes)
- Do not access paths outside the workspace for verification

## Bundled Scripts

This skill includes utility scripts for automated verification:

### verify-state.sh

Located at: `scripts/verify-state.sh`

**Usage:**
```bash
./scripts/verify-state.sh [--git] [--files] [--tests] [--all]
```

**Options:**
- `--git` - Verify git state (uncommitted changes, branch status)
- `--files` - Verify file integrity (broken symlinks, empty files)
- `--tests` - Execute project tests (auto-detects npm/pytest/rspec)
- `--all` - Run all verification checks (default)

**Output:**
- Console output with color-coded PASS/FAIL results
- JSON report saved to `.verification-report.json`

**Example:**
```bash
# Run all checks
./scripts/verify-state.sh --all

# Check only git and file integrity
./scripts/verify-state.sh --git --files
```

## Composition Patterns

**Commonly follows:**
- `model-schema` - Provides the invariants/spec to verify against (REQUIRED)
- `act-plan` - Verify the outcome of executed changes
- `plan` - Provides expected postconditions to verify

**Commonly precedes:**
- `audit` - Record verification results for compliance
- `rollback` - If verify FAIL, trigger rollback (CAVR pattern)
- `critique` - Analyze root cause of failures

**Anti-patterns:**
- Never verify without a spec (model-schema is required dependency)
- Never modify artifact during verification (breaks idempotency)
- Never ignore FAIL verdicts and proceed with mutations

**Workflow references:**
- See `reference/composition_patterns.md#debug-code-change` for CAVR pattern
- See `reference/composition_patterns.md#digital-twin-sync-loop` for verify-after-act usage
