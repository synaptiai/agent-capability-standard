---
name: act-plan
description: Execute a validated plan with checkpoints, verification, and rollback capability. Use when implementing changes, applying fixes, running multi-step mutations, or executing approved workflows.
argument-hint: "[plan] [checkpoint_ref] [dry_run]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit, Bash, Git
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: |
            SAFETY CHECK for act-plan execution.

            Command to execute: {{tool_input.command}}

            Verify ALL of the following:
            1. Command matches an action defined in the current plan
            2. Command is NOT destructive (no rm -rf, DROP TABLE, force push)
            3. Command is reversible OR a checkpoint exists
            4. Command does not access files outside the plan scope

            Reply ALLOW if all checks pass.
            Reply BLOCK with specific reason if any check fails.
          once: false
    - matcher: "Edit"
      hooks:
        - type: prompt
          prompt: |
            EDIT SAFETY CHECK for act-plan execution.

            File: {{tool_input.file_path}}
            Edit: {{tool_input.old_string}} -> {{tool_input.new_string}}

            Verify:
            1. File is in the plan's declared scope
            2. Edit matches a planned modification
            3. Checkpoint exists for rollback

            Reply ALLOW or BLOCK with reason.
          once: false
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: |
            echo "[ACT-PLAN] $(date -u +%Y-%m-%dT%H:%M:%SZ) Executed: {{tool_input.command}} | Exit: {{tool_output.exit_code}}" >> .checkpoints/act-plan-audit.log 2>/dev/null || true
---

## Intent

Execute a pre-validated plan by performing each step sequentially, creating checkpoints before mutations, verifying outcomes, and providing rollback capability on failure.

**Success criteria:**
- All plan steps executed successfully OR safely rolled back on failure
- Each mutation preceded by a checkpoint
- Verification checks pass for all completed steps
- Complete audit trail of changes produced

**Compatible schemas:**
- `docs/schemas/plan_schema.yaml`
- `docs/schemas/checkpoint_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `plan` | Yes | object | Validated plan from `plan` capability with steps, dependencies, and verification criteria |
| `checkpoint_ref` | Yes | string | ID of checkpoint created before execution (MANDATORY - execution blocked without this) |
| `dry_run` | No | boolean | If true, simulate execution without mutations (default: false) |
| `stop_on_warning` | No | boolean | Halt execution on non-critical issues (default: true) |
| `max_steps` | No | integer | Maximum steps to execute before pausing for review |

## Procedure

1) **Verify preconditions**: Confirm checkpoint exists and is valid
   - Check `checkpoint_ref` resolves to a valid checkpoint
   - Verify checkpoint was created recently (within session)
   - BLOCK execution if no valid checkpoint exists
   - Load plan and validate structure

2) **Validate plan structure**: Ensure plan has required fields
   - Each step must have: `id`, `action`, `target`, `verification_criteria`
   - Dependencies must form a DAG (no cycles)
   - Rollback actions should be defined for mutating steps

3) **Execute steps sequentially**: Process each step in dependency order
   - Log step start with timestamp
   - Execute action using appropriate tool (Edit, Bash, Git)
   - Capture output and any errors
   - Run step-level verification immediately after

4) **Verify each step**: Check verification criteria before proceeding
   - Run verification checks defined in the step
   - On PASS: proceed to next step
   - On FAIL: halt execution, prepare rollback

5) **Handle failures safely**: On any step failure
   - Stop further execution immediately
   - Log failure details and state
   - Prepare rollback recommendation
   - Return partial results with failure context

6) **Ground all claims**: Attach evidence to execution results
   - File paths with line numbers for changes
   - Command outputs for Bash executions
   - Git refs for version control operations

7) **Format output**: Structure results per output contract

## Output Contract

Return a structured object:

```yaml
plan_executed:
  id: string  # Plan identifier
  goal: string  # What the plan aimed to achieve
  steps:
    - id: string  # Step identifier
      action: string  # What was executed
      target: string  # File/resource affected
      result: success | failure | skipped  # Outcome
      checkpoint_id: string | null  # Checkpoint before this step
      output: string | null  # Execution output
changes:
  - file: string  # Path to modified file
    operation: create | modify | delete
    summary: string  # Brief description of change
    diff_anchor: string  # Reference to diff (git:hash or file:line)
verification:
  checks:
    - name: string  # Check identifier
      result: PASS | FAIL
      evidence: string  # How verified
  overall: PASS | FAIL
checkpoints:
  - id: string  # Checkpoint identifier
    type: git_stash | file_backup | state_snapshot
    restore_command: string  # How to restore
risks_encountered:
  - risk: string  # What risk was identified
    mitigation: string  # How it was handled
    outcome: string  # Result of mitigation
confidence: 0..1  # Numeric confidence score
evidence_anchors: ["file:line", "git:ref", "tool:bash:output"]
assumptions: []  # Explicit assumptions made
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `plan_executed` | object | Summary of plan execution including all steps |
| `changes` | array | All file/resource modifications made |
| `verification` | object | Results of all verification checks |
| `checkpoints` | array | Recovery points created during execution |
| `risks_encountered` | array | Risks identified and how they were handled |
| `confidence` | number | 0.0-1.0 based on verification results |
| `evidence_anchors` | array | File:line refs, git refs, tool outputs |
| `assumptions` | array | Explicit assumptions (e.g., "tests pass locally") |

## Examples

### Example 1: Bug Fix Execution

**Input:**
```yaml
plan:
  id: "fix-null-check-001"
  goal: "Add null check to prevent crash in UserService"
  steps:
    - id: "step-1"
      action: "edit"
      target: "src/services/UserService.ts"
      description: "Add null check before accessing user.email"
      verification_criteria: "File contains 'if (user != null)'"
      rollback_action: "git checkout src/services/UserService.ts"
    - id: "step-2"
      action: "bash"
      target: "npm test -- --grep UserService"
      description: "Run unit tests for UserService"
      verification_criteria: "Exit code 0"
      dependencies: ["step-1"]
checkpoint_ref: "checkpoint-2024-01-15-001"
dry_run: false
```

**Output:**
```yaml
plan_executed:
  id: "fix-null-check-001"
  goal: "Add null check to prevent crash in UserService"
  steps:
    - id: "step-1"
      action: "edit"
      target: "src/services/UserService.ts"
      result: success
      checkpoint_id: "checkpoint-2024-01-15-001"
      output: "Added null check at line 42"
    - id: "step-2"
      action: "bash"
      target: "npm test -- --grep UserService"
      result: success
      checkpoint_id: null
      output: "5 tests passed, 0 failed"
changes:
  - file: "src/services/UserService.ts"
    operation: modify
    summary: "Added null check before user.email access"
    diff_anchor: "git:a1b2c3d"
verification:
  checks:
    - name: "null-check-present"
      result: PASS
      evidence: "src/services/UserService.ts:42 contains 'if (user != null)'"
    - name: "tests-pass"
      result: PASS
      evidence: "npm test exit code 0, 5/5 tests passed"
  overall: PASS
checkpoints:
  - id: "checkpoint-2024-01-15-001"
    type: git_stash
    restore_command: "git stash pop"
risks_encountered: []
confidence: 0.95
evidence_anchors:
  - "src/services/UserService.ts:42"
  - "git:a1b2c3d"
  - "tool:bash:npm-test-output"
assumptions:
  - "Test environment matches production configuration"
```

**Evidence pattern:** File changes verified by reading modified file, test results verified by exit code and output parsing.

---

### Example 2: Failed Execution with Rollback Recommendation

**Input:**
```yaml
plan:
  id: "migrate-db-001"
  goal: "Update database schema"
  steps:
    - id: "step-1"
      action: "bash"
      target: "npx prisma migrate dev"
      verification_criteria: "Exit code 0"
      rollback_action: "npx prisma migrate reset"
checkpoint_ref: "checkpoint-2024-01-15-002"
```

**Output:**
```yaml
plan_executed:
  id: "migrate-db-001"
  goal: "Update database schema"
  steps:
    - id: "step-1"
      action: "bash"
      target: "npx prisma migrate dev"
      result: failure
      checkpoint_id: "checkpoint-2024-01-15-002"
      output: "Error: Foreign key constraint violation"
changes: []
verification:
  checks:
    - name: "migration-success"
      result: FAIL
      evidence: "Exit code 1, error message indicates constraint violation"
  overall: FAIL
checkpoints:
  - id: "checkpoint-2024-01-15-002"
    type: git_stash
    restore_command: "git stash pop"
risks_encountered:
  - risk: "Migration failed due to data constraint"
    mitigation: "Execution halted, no further steps attempted"
    outcome: "State preserved, rollback available"
confidence: 0.3
evidence_anchors:
  - "tool:bash:prisma-migrate-error"
assumptions:
  - "Database was in consistent state before migration"
next_actions:
  - "Review constraint error and fix migration"
  - "Consider data backfill before retry"
  - "Rollback using: git stash pop"
```

## Verification

- [ ] Checkpoint reference is valid and recent
- [ ] All executed steps have verification checks
- [ ] No step executed without prior checkpoint
- [ ] Failed executions preserved state for rollback
- [ ] All changes have evidence anchors

**Verification tools:** Git (for diff verification), Bash (for test execution)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: false
- `risk`: high

**Capability-specific rules:**
- NEVER execute without a valid checkpoint reference (CRITICAL)
- NEVER skip verification after any mutating step
- STOP immediately on first verification failure
- DO NOT proceed if checkpoint is missing or invalid
- Log all actions for audit trail
- Preserve original state information for rollback
- If confidence drops below 0.5, recommend manual review

**CRITICAL SAFETY PATTERN (CAVR):**
```
checkpoint -> act-plan -> verify -> (PASS: audit) | (FAIL: rollback)
```

## Composition Patterns

**Commonly follows:**
- `plan` - Provides the validated execution blueprint (REQUIRED)
- `checkpoint` - Creates recovery point before mutations (REQUIRED)
- `constrain` - Enforces policy limits on what can be executed
- `critique` - Identifies risks before execution

**Commonly precedes:**
- `verify` - Must verify all outcomes after execution
- `audit` - Record what was done and why
- `rollback` - Revert on failure (uses checkpoint)

**Anti-patterns:**
- NEVER call without prior `checkpoint` (CRITICAL - no recovery possible)
- NEVER skip `verify` after execution
- NEVER execute multiple act-plan calls without intermediate checkpoints
- NEVER proceed after FAIL verdict without rollback

**Workflow references:**
- See `composition_patterns.md#debug-code-change` for bug fix workflow
- See `composition_patterns.md#digital-twin-sync-loop` for sync context
- See `composition_patterns.md#cavr-pattern` for safety pattern
