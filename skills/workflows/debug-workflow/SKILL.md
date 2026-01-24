---
name: debug-workflow
description: Execute the Debug Code Change workflow end-to-end with safety gates. Use when debugging code changes, investigating issues, or performing root cause analysis with audit trail.
argument-hint: "[goal] [scope] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent

Run the composed workflow **debug-workflow** using atomic capability skills to systematically debug code changes with full safety and audit capabilities.

**Success criteria:**
- Every step output is grounded with evidence anchors
- Safety gates are respected (checkpoint before any mutation)
- All issues are traced to root cause with supporting evidence
- Final result includes complete audit trail
- Rollback pathway documented and verified

**Compatible schemas:**
- `docs/schemas/workflow_catalog.yaml`
- `docs/schemas/audit_log.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `goal` | Yes | string | The debugging objective (e.g., "identify why tests fail after refactor") |
| `scope` | Yes | string\|array | Files, directories, or components to investigate |
| `constraints` | No | object | Hard limits (e.g., time budget, files to exclude, severity threshold) |
| `prior_context` | No | object | Previous debugging attempts or known information |

## Procedure

0) **Create checkpoint marker** if mutation might occur:
   - Create `.claude/checkpoint.ok` after confirming rollback strategy

1) **Invoke `/inspect`** and store output as `inspect_out`
   - Examine the scope for symptoms, error patterns, recent changes

2) **Invoke `/search`** and store output as `search_out`
   - Find related code, error messages, similar patterns

3) **Invoke `/map-relationships`** and store output as `map-relationships_out`
   - Map dependencies, call graphs, data flows

4) **Invoke `/model-schema`** and store output as `model-schema_out`
   - Model the expected vs actual behavior

5) **Invoke `/critique`** and store output as `critique_out`
   - Critically analyze hypotheses, identify weak points

6) **Invoke `/plan`** and store output as `plan_out`
   - Create remediation plan with verification criteria

7) **Invoke `/act-plan`** and store output as `act-plan_out`
   - Execute the fix with checkpoint protection

8) **Invoke `/verify`** and store output as `verify_out`
   - Confirm fix addresses root cause

9) **Invoke `/audit`** and store output as `audit_out`
   - Record all actions and evidence for audit trail

10) **Invoke `/rollback`** if needed and store output as `rollback_out`
    - Restore previous state if verification fails

## Output Contract

Return a structured object:

```yaml
workflow_id: string  # Unique workflow execution ID
goal: string  # The debugging objective
status: completed | failed | rolled_back
steps:
  inspect_out:
    summary: string
    findings: array[string]
    evidence_anchors: array[string]
  search_out:
    summary: string
    matches: array[string]
    evidence_anchors: array[string]
  map_relationships_out:
    summary: string
    dependencies: array[string]
    evidence_anchors: array[string]
  model_schema_out:
    summary: string
    evidence_anchors: array[string]
  critique_out:
    summary: string
    weaknesses: array[string]
    evidence_anchors: array[string]
  plan_out:
    summary: string
    actions: array[string]
    verification_criteria: array[string]
    evidence_anchors: array[string]
  act_plan_out:
    summary: string
    changes_made: array[string]
    evidence_anchors: array[string]
  verify_out:
    result: PASS | FAIL
    evidence_anchors: array[string]
  audit_out:
    log_path: string
    evidence_anchors: array[string]
  rollback_out:
    executed: boolean
    restore_point: string | null
    evidence_anchors: array[string]
root_cause:
  description: string
  evidence_anchors: array[string]
resolution:
  description: string
  files_changed: array[string]
verification: PASS | FAIL
audit_log_pointer: string  # Path to .claude/audit.log
rollback_available: boolean
rollback_command: string | null
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | Unique identifier for this workflow execution |
| `status` | enum | Final workflow status |
| `steps` | object | Summary and evidence from each workflow step |
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
goal: "Identify why user authentication tests fail after handler refactor"
scope:
  - "src/api/handlers/auth.py"
  - "tests/test_auth.py"
constraints:
  max_time: "30m"
  severity: "high"
```

**Output:**
```yaml
workflow_id: "debug_20240115_143022"
goal: "Identify why user authentication tests fail after handler refactor"
status: completed
steps:
  inspect_out:
    summary: "Test failure in test_login_success, line 45"
    findings:
      - "Expected status 200, got 401"
      - "Token validation logic changed in refactor"
    evidence_anchors:
      - "file:tests/test_auth.py:45"
      - "file:src/api/handlers/auth.py:78"
  search_out:
    summary: "Found 3 related token validation patterns"
    matches:
      - "src/api/handlers/auth.py:validate_token"
      - "src/utils/jwt.py:decode_token"
    evidence_anchors:
      - "tool:grep:validate_token"
  map_relationships_out:
    summary: "auth.py depends on jwt.py for token validation"
    dependencies:
      - "auth.py -> jwt.py"
      - "auth.py -> user_model.py"
    evidence_anchors:
      - "tool:ast:import_analysis"
  critique_out:
    summary: "Token validation order changed - signature check now after expiry"
    weaknesses:
      - "Signature validation moved after expiry check, causing premature rejection"
    evidence_anchors:
      - "file:src/api/handlers/auth.py:78-85"
  plan_out:
    summary: "Restore original validation order"
    actions:
      - "Move signature check before expiry check"
    verification_criteria:
      - "test_login_success passes"
      - "No regression in other auth tests"
    evidence_anchors:
      - "file:src/api/handlers/auth.py:78"
  act_plan_out:
    summary: "Reordered validation steps"
    changes_made:
      - "src/api/handlers/auth.py:78-85"
    evidence_anchors:
      - "tool:git:diff"
  verify_out:
    result: PASS
    evidence_anchors:
      - "tool:bash:pytest tests/test_auth.py"
  audit_out:
    log_path: ".claude/audit.log"
    evidence_anchors:
      - "file:.claude/audit.log"
  rollback_out:
    executed: false
    restore_point: "chk_20240115_143000"
    evidence_anchors: []
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
rollback_available: true
rollback_command: "git stash pop"
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

- [ ] **Step Completeness**: All 10 workflow steps executed with output
- [ ] **Evidence Grounding**: Every step output includes evidence_anchors
- [ ] **Checkpoint Created**: Mutation steps preceded by checkpoint
- [ ] **Root Cause Identified**: root_cause has specific description and evidence
- [ ] **Verification Passed**: verify_out.result is PASS before completion
- [ ] **Audit Trail**: audit_log_pointer points to valid log file
- [ ] **Rollback Ready**: rollback_command documented if changes made

**Verification tools:** Bash (for test execution), Git (for change verification), Read (for audit log)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: false
- `risk`: high

**Capability-specific rules:**
- NEVER proceed to `act-plan` without checkpoint and explicit plan
- STOP and request clarification if any step produces confidence < 0.3
- ALWAYS verify fix before marking workflow complete
- Document rollback command before any mutation
- Preserve original error state for comparison

## Composition Patterns

**Commonly follows:**
- `receive` - After receiving bug report or error notification
- `retrieve` - After fetching relevant context or logs

**Commonly precedes:**
- `summarize` - To create debug report for stakeholders
- `send` - To notify team of resolution

**Anti-patterns:**
- Never skip `/inspect` to jump directly to `/plan`
- Never proceed past `/critique` without addressing identified weaknesses
- Never execute `/act-plan` without prior `/checkpoint`
- Never mark complete without `/verify` confirmation

**Workflow references:**
- See `workflow_catalog.yaml#debug-workflow` for step definitions
- See `composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
