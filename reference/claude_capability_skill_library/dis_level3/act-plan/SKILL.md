---
name: act-plan
description: Execute a structured plan using tools with checkpoints, verification, and rollback capability. Use when implementing multi-step changes, running deployment sequences, or performing coordinated file/system modifications.
argument-hint: "[plan] [verification_mode] [checkpoint_strategy]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit, Bash, Git
context: fork
agent: general-purpose
---

## Intent

Execute a pre-defined plan step by step, creating checkpoints before mutations, verifying outcomes after each step, and maintaining the ability to rollback if verification fails.

**Success criteria:**
- All plan steps execute in dependency order
- Checkpoints created before each mutating step
- Verification criteria checked after each step
- Rollback executed if any verification fails
- Complete audit trail of changes

**Hard dependencies:**
- Requires `plan` - Must have a structured plan to execute
- Uses `checkpoint` - For creating restore points
- Uses `verify` - For checking step outcomes
- Uses `rollback` - For reverting on failure

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `plan` | Yes | object | Structured plan with steps, dependencies, and verification criteria |
| `checkpoint_strategy` | No | string | When to checkpoint: `every_step`, `before_mutation`, `critical_only` (default: `before_mutation`) |
| `verification_mode` | No | string | How to verify: `strict` (fail on any issue), `lenient` (warn only), `none` |
| `dry_run` | No | boolean | If true, simulate execution without making changes |
| `stop_on_failure` | No | boolean | If false, continue executing after failed steps (default: true) |

## Procedure

1) **Parse and validate plan**: Ensure plan has required structure
   - Verify each step has: id, action, target, verification_criteria
   - Build dependency graph to determine execution order
   - Identify which steps are mutations vs read-only
   - Check that all referenced targets exist

2) **Initialize execution state**: Prepare for plan execution
   - Create execution log with timestamp
   - Record initial world state hash
   - Initialize checkpoint registry
   - Set up rollback stack

3) **Execute steps in order**: For each step in topological order
   - **Pre-step**: Check preconditions, create checkpoint if mutating
   - **Execute**: Run the action using appropriate tool (Edit, Bash, Git)
   - **Verify**: Run verification criteria against outcome
   - **Post-step**: Update execution log, record changes

4) **Handle failures**: When verification fails
   - Log failure details with evidence
   - If `stop_on_failure`: initiate rollback to last checkpoint
   - If continuing: mark step as failed, proceed to independent steps
   - Accumulate failure information for final report

5) **Verify final state**: After all steps complete
   - Run any cross-step verification criteria
   - Compare final state hash to expected state
   - Verify no unintended side effects

6) **Generate execution report**: Compile complete audit trail
   - List all actions taken with timestamps
   - Document all changes with diff anchors
   - Summarize verification results
   - Include checkpoint references for potential future rollback

## Output Contract

Return a structured object:

```yaml
plan_executed:
  id: string
  goal: string
  started_at: string  # ISO timestamp
  completed_at: string
  status: success | partial | failed | rolled_back
steps:
  - id: string
    action: string
    target: string
    started_at: string
    completed_at: string
    result: success | failure | skipped
    checkpoint_id: string | null
    output: string | null
    error: string | null
changes:
  - file: string
    operation: create | modify | delete
    summary: string
    diff_anchor: string  # file:line or git commit
verification:
  checks:
    - step_id: string
      name: string
      result: PASS | FAIL
      evidence: string
  overall: PASS | FAIL
  failures: array[string]
checkpoints:
  - id: string
    step_id: string
    type: git_stash | file_backup | state_snapshot
    created_at: string
    restore_command: string
risks_encountered:
  - risk: string
    step_id: string
    mitigation: string
    outcome: resolved | unresolved | accepted
rollback_info:
  rolled_back: boolean
  restored_to: string | null
  reason: string | null
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `plan_executed.status` | enum | Final execution status |
| `steps[].checkpoint_id` | string | Reference to restore point before this step |
| `changes[].diff_anchor` | string | Location of change evidence |
| `verification.overall` | enum | Aggregate verification result |
| `rollback_info` | object | Details if rollback was performed |

## Examples

### Example 1: Database Migration Execution

**Input:**
```yaml
plan:
  id: "migrate-db-v2"
  goal: "Migrate database schema to v2"
  steps:
    - id: "backup"
      action: "pg_dump production > backup.sql"
      target: "database"
      verification_criteria: "backup.sql exists and size > 0"
      dependencies: []
    - id: "apply-migration"
      action: "psql -f migration_v2.sql"
      target: "database"
      verification_criteria: "SELECT version FROM schema_info returns 'v2'"
      dependencies: ["backup"]
    - id: "verify-data"
      action: "run data_integrity_check.py"
      target: "database"
      verification_criteria: "exit code 0"
      dependencies: ["apply-migration"]
checkpoint_strategy: before_mutation
verification_mode: strict
```

**Output:**
```yaml
plan_executed:
  id: "migrate-db-v2"
  goal: "Migrate database schema to v2"
  started_at: "2024-01-15T10:30:00Z"
  completed_at: "2024-01-15T10:35:22Z"
  status: success
steps:
  - id: "backup"
    action: "pg_dump production > backup.sql"
    target: "database"
    started_at: "2024-01-15T10:30:00Z"
    completed_at: "2024-01-15T10:32:15Z"
    result: success
    checkpoint_id: null
    output: "Backup completed: 156MB"
    error: null
  - id: "apply-migration"
    action: "psql -f migration_v2.sql"
    target: "database"
    started_at: "2024-01-15T10:32:16Z"
    completed_at: "2024-01-15T10:34:45Z"
    result: success
    checkpoint_id: "chk-001"
    output: "Migration applied successfully"
    error: null
  - id: "verify-data"
    action: "run data_integrity_check.py"
    target: "database"
    started_at: "2024-01-15T10:34:46Z"
    completed_at: "2024-01-15T10:35:22Z"
    result: success
    checkpoint_id: null
    output: "All integrity checks passed"
    error: null
changes:
  - file: "backup.sql"
    operation: create
    summary: "Database backup created"
    diff_anchor: "tool:Bash:backup_output"
  - file: "database schema"
    operation: modify
    summary: "Applied migration_v2.sql"
    diff_anchor: "tool:Bash:migration_output"
verification:
  checks:
    - step_id: "backup"
      name: "backup.sql exists and size > 0"
      result: PASS
      evidence: "ls -la backup.sql: 156MB"
    - step_id: "apply-migration"
      name: "schema version check"
      result: PASS
      evidence: "SELECT version: 'v2'"
    - step_id: "verify-data"
      name: "exit code 0"
      result: PASS
      evidence: "data_integrity_check.py returned 0"
  overall: PASS
  failures: []
checkpoints:
  - id: "chk-001"
    step_id: "apply-migration"
    type: file_backup
    created_at: "2024-01-15T10:32:16Z"
    restore_command: "psql < backup.sql"
risks_encountered:
  - risk: "Schema migration may fail"
    step_id: "apply-migration"
    mitigation: "Created backup before migration"
    outcome: resolved
rollback_info:
  rolled_back: false
  restored_to: null
  reason: null
confidence: 0.95
evidence_anchors:
  - "tool:Bash:backup_output"
  - "tool:Bash:migration_output"
  - "tool:Bash:integrity_check"
assumptions:
  - "Database connection available"
  - "User has necessary permissions"
```

**Evidence pattern:** Each step's output captured via Bash tool, verification queries run after mutations.

---

### Example 2: Failed Execution with Rollback

**Input:**
```yaml
plan:
  id: "refactor-auth"
  goal: "Refactor authentication module"
  steps:
    - id: "update-imports"
      action: "Edit auth.py imports"
      target: "src/auth.py"
      verification_criteria: "python -c 'import src.auth'"
      dependencies: []
    - id: "update-handlers"
      action: "Edit request handlers"
      target: "src/handlers.py"
      verification_criteria: "pytest tests/test_handlers.py"
      dependencies: ["update-imports"]
checkpoint_strategy: before_mutation
verification_mode: strict
stop_on_failure: true
```

**Output:**
```yaml
plan_executed:
  id: "refactor-auth"
  goal: "Refactor authentication module"
  started_at: "2024-01-15T14:00:00Z"
  completed_at: "2024-01-15T14:02:30Z"
  status: rolled_back
steps:
  - id: "update-imports"
    action: "Edit auth.py imports"
    target: "src/auth.py"
    result: success
    checkpoint_id: "chk-auth-001"
    output: "Imports updated"
  - id: "update-handlers"
    action: "Edit request handlers"
    target: "src/handlers.py"
    result: failure
    checkpoint_id: "chk-auth-002"
    error: "pytest failed: 3 tests failed"
verification:
  overall: FAIL
  failures:
    - "update-handlers: pytest tests/test_handlers.py failed"
rollback_info:
  rolled_back: true
  restored_to: "chk-auth-001"
  reason: "Verification failed for step update-handlers"
confidence: 0.9
evidence_anchors:
  - "src/auth.py:1-15"
  - "tool:Bash:pytest_output"
assumptions:
  - "Tests accurately validate changes"
```

## Verification

- [ ] Plan structure validated before execution starts
- [ ] Checkpoint created before each mutating step
- [ ] Each step's verification criteria evaluated
- [ ] Rollback successful when triggered
- [ ] All changes documented with evidence anchors
- [ ] Final state matches expected outcome

**Verification tools:** Bash (for running tests), Git (for state comparison)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: false (but recommended for production systems)
- `risk`: high

**Capability-specific rules:**
- Always create checkpoint before mutating step (unless dry_run)
- Never skip verification in `strict` mode
- Stop immediately if checkpoint creation fails
- Preserve all rollback information even after successful completion
- Do not execute steps with unmet dependencies
- Log all actions for audit trail

## Composition Patterns

**Commonly follows:**
- `plan` - Execute a plan that was just created
- `verify` - Execute after verifying current state is safe
- `checkpoint` - Manual checkpoint before starting execution

**Commonly precedes:**
- `verify` - Verify final state after execution
- `audit` - Generate audit report of execution
- `rollback` - If manual rollback needed later

**Anti-patterns:**
- Never use without a checkpoint strategy on production systems
- Avoid `verification_mode: none` for mutating plans
- Do not combine with `generate-plan` in same operation (plan first, then execute)

**Workflow references:**
- See `workflow_catalog.json#safe-deployment` for production deployment pattern
- See `workflow_catalog.json#database-migration` for data migration pattern
