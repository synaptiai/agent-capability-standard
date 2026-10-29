---
name: verify
description: Check correctness against tests, specs, or invariants; produce pass/fail evidence. Use when validating changes, testing hypotheses, checking invariants, or confirming behavior matches expectations.
argument-hint: "[conditions] [target] [strict]"
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
- Clear pass/fail result (`passed`) with supporting evidence
- Every check is grounded to observable output or file content
- Failures include actionable fix suggestions
- All assumptions about expected behavior are explicit

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | No | any | What to verify |
| `conditions` | Yes | array | Conditions to check |
| `strict` | No | boolean | Fail on first violation |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Load conditions**: Read the test/invariant definitions in `conditions`
   - Identify testable assertions from the conditions
   - Parse test commands or invariant expressions
   - Note any preconditions required for verification

2) **Examine target**: Inspect the target being verified
   - Read relevant code, config, or state
   - Identify the specific behavior/properties to check
   - Check preconditions are met before running tests

3) **Execute checks**: Run each verification check systematically
   - For test suites: execute via Bash, capture stdout/stderr
   - For invariants: evaluate conditions, record boolean results
   - For schema validation: compare structure against schema
   - Record timing and resource usage if relevant

4) **Analyze results**: Determine `passed` from check outcomes
   - `passed: true`: All checks succeed
   - `passed: false`: One or more checks fail (each listed in `violations`)
   - Inconclusive (errors or missing data): `passed: false` with `inconclusive: true`

5) **Ground claims**: Attach evidence anchors to all findings
   - Format: `file:line`, `tool:bash:<command>`, or `test:<test_name>`
   - Include exact error messages and stack traces for failures

6) **Format output**: Structure results per output contract
   - Include fix suggestions for each failure
   - Calculate coverage metrics if applicable

## Output Contract

Return a structured object:

```yaml
passed: boolean  # true only when every check passed
inconclusive: boolean  # true when checks could not run (passed is then false)
results:  # Per-condition results
  - name: string  # Check identifier
    type: assertion | invariant | regression | schema
    target: string  # What was checked
    passed: boolean
    evidence: string  # Output or file reference
violations:  # Failed conditions
  - check: string  # Which check failed
    expected: string  # What was expected
    actual: string  # What was observed
    severity: low | medium | high | critical
fix_suggestions:
  - violation_ref: string  # Which violation (by check name)
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
| `passed` | boolean | Overall result: true only when every check passed |
| `inconclusive` | boolean | True when checks could not be run; `passed` is then false |
| `results` | array | Per-condition results for every check executed |
| `violations` | array | Failed conditions with expected vs. actual |
| `fix_suggestions` | array | Actionable suggestions to fix violations |
| `coverage` | object | Metrics about verification coverage |
| `confidence` | number | 0.0-1.0 based on evidence quality and check coverage |
| `evidence_anchors` | array | File:line, URLs, or tool output references |
| `assumptions` | array | Explicit assumptions about expected behavior |

## Examples

### Example 1: Unit Test Verification

**Input:**
```yaml
target: "src/calculator.py"
conditions:
  - "pytest tests/test_calculator.py -v passes"
```

**Output:**
```yaml
passed: false
inconclusive: false
results:
  - name: test_add_positive
    type: assertion
    target: Calculator.add
    passed: true
    evidence: "tool:bash:pytest - PASSED"
  - name: test_divide_by_zero
    type: assertion
    target: Calculator.divide
    passed: false
    evidence: "tool:bash:pytest - AssertionError: Expected ZeroDivisionError"
violations:
  - check: test_divide_by_zero
    expected: "ZeroDivisionError raised"
    actual: "Returns infinity"
    severity: high
fix_suggestions:
  - violation_ref: test_divide_by_zero
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
target: "config/production.yaml"
conditions:
  - type: schema
    schema_path: "schemas/config.json"
```

**Output:**
```yaml
passed: true
inconclusive: false
results:
  - name: schema_validation
    type: schema
    target: config/production.yaml
    passed: true
    evidence: "All 12 required fields present, types valid"
violations: []
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

- [ ] **Evidence Grounding**: All results anchored to test output or file content
- [ ] **Contract Validation**: Output matches schema with required fields
- [ ] **Idempotency Check**: Re-running verify produces the same `passed` result (given unchanged inputs)
- [ ] **Coverage Tracking**: results.length == coverage.total

**Verification tools:** Bash (for test execution), Read (for evidence files)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not modify the artifact being verified
- Do not skip failing tests or mask errors
- Stop and clarify if conditions are ambiguous or missing
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
- `constrain` - Provides the invariants/spec to verify against
- `execute` / `mutate` - Verify the outcome of executed changes (they must precede verify)
- `plan` - Provides expected postconditions to verify

**Commonly precedes:**
- `audit` - Record verification results for compliance
- `rollback` - If `passed` is false, trigger rollback (CAVR pattern)
- `critique` - Analyze root cause of failures

**Anti-patterns:**
- Never verify without a spec (`constrain` invariants or explicit `conditions`)
- Never modify artifact during verification (breaks idempotency)
- Never ignore `passed: false` and proceed with mutations

**Workflow references:**
- See `reference/composition_patterns.md#debug-code-change` for CAVR pattern
- See `reference/composition_patterns.md#digital-twin-sync-loop` for verify-after-act usage
