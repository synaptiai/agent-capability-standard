---
name: debug-workflow
description: Execute the Debug Code Change workflow end-to-end with safety gates. Use when debugging code changes, investigating issues, or performing root cause analysis with audit trail.
argument-hint: "[bug] [user_input]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent

Run the composed workflow **debug_code_change** (`reference/workflow_catalog.yaml`) using atomic capability skills to diagnose and fix a bug with full safety and audit capabilities.

**Success criteria:**
- Every step output is grounded with evidence anchors
- Safety gates are respected (checkpoint before any mutation)
- All issues are traced to root cause with supporting evidence
- Final result includes complete audit trail
- Rollback runs only when verification fails

**Compatible schemas:**
- `reference/workflow_catalog.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `bug` | Yes | object | The failure to diagnose and fix: `component` (where it is), `symptom` (what goes wrong), `fix_command` (the command that applies and tests the fix) |
| `user_input` | No | object | `domain` and `constraints` (e.g. time budget, files to exclude) |

## Procedure

0) **Create checkpoint marker** if mutation might occur:
   - Create `.claude/checkpoint.ok` after confirming rollback strategy

1) **Invoke `/observe`** on `bug.component` and store output as `observe_out`
   - Observe failing behavior, logs, and relevant code paths

2) **Invoke `/search`** for `bug.symptom` and store output as `search_out`
   - Find related code, configs, and error patterns

3) **Invoke `/attribute`** with `bug.symptom` as the effect and store output as `attribute_out`
   - Build the dependency graph and identify causal relationships around the failing component

4) **Invoke `/constrain`** on `bug.component` and store output as `constrain_out`
   - Define the invariants the fix must keep (existing tests pass, public interfaces unchanged)

5) **Invoke `/critique`** on `attribute_out.causes` and store output as `critique_out`
   - List likely failure modes and edge cases

6) **Invoke `/plan`** and store output as `plan_out`
   - Produce a minimal fix plan with checkpoints

7) **Invoke `/checkpoint`** on `bug.component` and store output as `checkpoint_out`
   - Save a restore point before mutation

8) **Invoke `/execute`** with `bug.fix_command` and store output as `execute_out`
   - Apply the fix, run tests, and produce a diff summary

9) **Invoke `/verify`** and store output as `verify_out`
   - Run targeted verification: tests pass and the symptom is resolved

10) **Invoke `/audit`** and store output as `audit_out`
    - Record what changed and why: the component, the plan, the verdict

11) **Invoke `/rollback`** to `checkpoint_out.checkpoint_id` if `verify_out.passed` is false, and store output as `rollback_out`
    - The step is skipped when verification passes

## Output Contract

Return a structured object:

```yaml
workflow_id: string  # Unique workflow execution ID
bug: object  # The bug as given
status: completed | failed | rolled_back
steps:
  observe_out:
    observation: object
    evidence_anchors: array[string]
  search_out:
    results: array[object]
    evidence_anchors: array[string]
  attribute_out:
    causes: array[object]
    strengths: object  # Causal strength per cause
    evidence_anchors: array[string]
  constrain_out:
    compliant: boolean
    violations: array[object]
    evidence_anchors: array[string]
  critique_out:
    issues: array[object]
    evidence_anchors: array[string]
  plan_out:
    steps: array[object]
    risks: array[object]
    evidence_anchors: array[string]
  checkpoint_out:
    checkpoint_id: string
    evidence_anchors: array[string]
  execute_out:
    result: any
    evidence_anchors: array[string]
  verify_out:
    passed: boolean
    violations: array[object]
    evidence_anchors: array[string]
  audit_out:
    audit_id: string
    evidence_anchors: array[string]
  rollback_out:  # null when verification passed and the step was skipped
    restored: boolean
    evidence_anchors: array[string]
root_cause:
  description: string
  evidence_anchors: array[string]
resolution:
  description: string
  files_changed: array[string]
verification: PASS | FAIL
audit_log_pointer: string  # Path to .claude/audit.log
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | Unique identifier for this workflow execution |
| `status` | enum | Final workflow status |
| `steps` | object | Each step's output, keyed by its `store_as` |
| `root_cause` | object | Identified root cause with evidence |
| `resolution` | object | What was done to fix the issue |
| `verification` | enum | Final PASS/FAIL after fix applied |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array | All evidence references collected |
| `assumptions` | array | Explicit assumptions made during debugging |

## Examples

### Example 1: Debug Failing Test After Refactor

**Input:**
```yaml
bug:
  component: "src/api/handlers/auth.py"
  symptom: "test_login_success fails with 401 after the handler refactor"
  fix_command: "git apply fix.patch && pytest tests/test_auth.py"
user_input:
  constraints:
    max_time: "30m"
```

**Output:**
```yaml
workflow_id: "debug_20240115_143022"
bug:
  component: "src/api/handlers/auth.py"
  symptom: "test_login_success fails with 401 after the handler refactor"
  fix_command: "git apply fix.patch && pytest tests/test_auth.py"
status: completed
steps:
  observe_out:
    observation:
      failing_test: "tests/test_auth.py::test_login_success"
      expected_status: 200
      actual_status: 401
    evidence_anchors:
      - "file:tests/test_auth.py:45"
      - "file:src/api/handlers/auth.py:78"
  search_out:
    results:
      - location: "src/api/handlers/auth.py:validate_token"
      - location: "src/utils/jwt.py:decode_token"
    evidence_anchors:
      - "tool:grep:validate_token"
  attribute_out:
    causes:
      - id: signature_after_expiry
        cause: "Signature check moved after the expiry check"
    strengths:
      signature_after_expiry: 0.9
    evidence_anchors:
      - "tool:git:blame"
  constrain_out:
    compliant: true
    violations: []
    evidence_anchors: []
  critique_out:
    issues:
      - issue: "Signature validation after the expiry check rejects valid tokens"
        location: "src/api/handlers/auth.py:78-85"
    evidence_anchors:
      - "file:src/api/handlers/auth.py:78-85"
  plan_out:
    steps:
      - action: "Move the signature check before the expiry check"
        verification: "test_login_success passes; no other auth test regresses"
    risks: []
    evidence_anchors:
      - "file:src/api/handlers/auth.py:78"
  checkpoint_out:
    checkpoint_id: "chk_20240115_143000"
    evidence_anchors:
      - "tool:git:stash"
  execute_out:
    result: "patch applied; 12 passed"
    evidence_anchors:
      - "tool:bash:git apply fix.patch && pytest tests/test_auth.py"
  verify_out:
    passed: true
    violations: []
    evidence_anchors:
      - "tool:bash:pytest tests/test_auth.py"
  audit_out:
    audit_id: "audit_20240115_143500"
    evidence_anchors:
      - "file:.claude/audit.log"
  rollback_out: null  # skipped: verification passed
root_cause:
  description: "Token signature validation was moved after expiry check during refactor, causing valid tokens to be rejected before signature verification"
  evidence_anchors:
    - "file:src/api/handlers/auth.py:78-85"
    - "tool:git:blame"
resolution:
  description: "Restored original validation order: signature check before expiry check"
  files_changed:
    - "src/api/handlers/auth.py"
verification: PASS
audit_log_pointer: ".claude/audit.log"
confidence: 0.95
evidence_anchors:
  - "file:tests/test_auth.py:45"
  - "file:src/api/handlers/auth.py:78-85"
  - "tool:bash:pytest"
  - "tool:git:diff"
assumptions:
  - "Test environment matches production configuration"
  - "No concurrent changes to auth module"
```

**Evidence pattern:** Combined code inspection, git blame for change attribution, test execution for verification.

## Verification

- [ ] **Step Completeness**: All 11 workflow steps executed with output (rollback skipped when verification passed)
- [ ] **Evidence Grounding**: Every step output includes evidence_anchors
- [ ] **Checkpoint Created**: Mutation steps preceded by checkpoint
- [ ] **Root Cause Identified**: root_cause has specific description and evidence
- [ ] **Verification Passed**: verify_out.passed is true before completion
- [ ] **Audit Trail**: audit_log_pointer points to valid log file
- [ ] **Rollback Ready**: checkpoint_out.checkpoint_id recorded before the fix ran

**Verification tools:** Bash (for test execution), Git (for change verification), Read (for audit log)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: true (the `execute` step that applies the fix)
- `risk`: high

**Capability-specific rules:**
- NEVER proceed to `execute` without checkpoint and explicit plan
- STOP and request clarification if any step produces confidence < 0.3
- ALWAYS verify fix before marking workflow complete
- Record the checkpoint before any mutation
- Preserve original error state for comparison

## Composition Patterns

**Commonly follows:**
- `receive` - After receiving bug report or error notification
- `retrieve` - After fetching relevant context or logs

**Commonly precedes:**
- `explain` - To create debug report for stakeholders
- `send` - To notify team of resolution

**Anti-patterns:**
- Never skip `/observe` to jump directly to `/plan`
- Never proceed past `/critique` without addressing identified weaknesses
- Never run `/execute` without prior `/checkpoint`
- Never mark complete without `/verify` confirmation

**Workflow references:**
- See `reference/workflow_catalog.yaml#debug_code_change` for step definitions
- See `reference/composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
