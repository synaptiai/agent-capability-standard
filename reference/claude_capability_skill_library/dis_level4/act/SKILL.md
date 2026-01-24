---
name: act
description: Execute a plan by performing mutations (file edits, commands, git operations) with verification and rollback capability. Use when implementing changes, applying fixes, or modifying system state.
argument-hint: "[plan] [checkpoint-ref] [verification-criteria]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit, Bash, Git
context: fork
agent: general-purpose
---

## Intent

Execute a sequence of mutating actions according to a plan, with mandatory checkpointing, verification, and rollback capability. Act is the highest-risk capability and requires explicit safety protocols.

**Success criteria:**
- All planned actions executed successfully
- Changes verified against acceptance criteria
- Checkpoint created before mutations
- Rollback path documented and tested

**Compatible schemas:**
- `docs/schemas/action_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `plan` | Yes | object\|string | The plan to execute (steps, targets, verification criteria) |
| `checkpoint_ref` | Yes | string | Reference to checkpoint created before act (REQUIRED) |
| `verification_criteria` | No | array[string] | Conditions that must pass after execution |
| `dry_run` | No | boolean | If true, simulate without actual mutations |

## Procedure

1) **Verify checkpoint exists**: Confirm rollback capability before any mutation
   - Check checkpoint_ref is valid and restorable
   - Abort if checkpoint cannot be verified
   - NEVER proceed without valid checkpoint

2) **Parse plan steps**: Extract ordered actions from plan
   - Identify dependencies between steps
   - Flag any steps requiring approval
   - Validate all targets are accessible

3) **Execute steps sequentially**: Perform each action with verification
   - Log before/after state for each mutation
   - Run step-level verification where defined
   - Stop on first failure - do not continue

4) **Record all changes**: Document every mutation made
   - File changes: path, operation (create/modify/delete), diff
   - Commands: command string, exit code, output summary
   - Git operations: commits, branches, refs affected

5) **Run verification suite**: Validate post-execution state
   - Execute all verification_criteria checks
   - Collect pass/fail for each check
   - Compute overall PASS/FAIL verdict

6) **Handle failure path**: If verification fails
   - Document which checks failed and why
   - Prepare rollback command using checkpoint_ref
   - Do NOT automatically rollback - await confirmation

7) **Document side effects**: Note unintended or unexpected changes
   - Environment modifications
   - Generated files not in plan
   - Cache invalidation effects

8) **Produce audit trail**: Compile complete action record
   - Timeline of all operations
   - Evidence anchors for each change

## Output Contract

Return a structured object:

```yaml
actions_taken:
  - action: string  # What was done
    target: string  # What was affected
    result: success | failure | partial
    output: string | null  # Command output or operation result
changes:
  - file: string  # File path
    operation: create | modify | delete
    summary: string  # Brief description of change
    diff_anchor: string  # Reference to diff
verification:
  checks_run: array[string]  # Verification checks executed
  overall: PASS | FAIL
  failures: array[string]  # Failed check descriptions
side_effects: array[string]  # Unintended changes observed
checkpoints:
  - id: string  # Checkpoint identifier
    type: git_stash | file_backup | state_snapshot
    restore_command: string  # How to rollback
confidence: number  # 0.0-1.0 in execution correctness
evidence_anchors: array[string]  # References to changes
assumptions: array[string]  # Conditions assumed during execution
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `actions_taken` | array | Log of all actions executed |
| `changes` | array | Files modified with operation type |
| `verification` | object | Verification suite results |
| `side_effects` | array | Unintended changes observed |
| `checkpoints` | array | Rollback points available |
| `confidence` | number | 0.0-1.0 in execution success |
| `evidence_anchors` | array[string] | References to diffs and outputs |
| `assumptions` | array[string] | Conditions assumed |

## Examples

### Example 1: Apply Security Fix

**Input:**
```yaml
plan:
  goal: "Fix SQL injection vulnerability in user controller"
  steps:
    - id: "step1"
      action: "Replace string concatenation with parameterized query"
      target: "src/api/user_controller.py:47"
      verification: "grep for string concatenation returns empty"
    - id: "step2"
      action: "Add input validation import"
      target: "src/api/user_controller.py:1"
      verification: "import statement present"
    - id: "step3"
      action: "Run security linter"
      target: "src/api/"
      verification: "bandit returns 0 exit code"
checkpoint_ref: "git-stash:stash@{0}"
verification_criteria:
  - "All tests pass"
  - "No SQL injection warnings from bandit"
```

**Output:**
```yaml
actions_taken:
  - action: "Edit user_controller.py to use parameterized query"
    target: "src/api/user_controller.py:47"
    result: success
    output: null
  - action: "Add import statement for input validation"
    target: "src/api/user_controller.py:1"
    result: success
    output: null
  - action: "Run bandit security linter"
    target: "src/api/"
    result: success
    output: "No issues identified. Scanned 12 files."
changes:
  - file: "src/api/user_controller.py"
    operation: modify
    summary: "Replaced string concatenation (line 47) with cursor.execute parameterized query. Added import for validate_input."
    diff_anchor: "git:diff:HEAD~1:src/api/user_controller.py"
verification:
  checks_run:
    - "pytest src/api/tests/"
    - "bandit -r src/api/"
    - "grep 'f\"SELECT.*{' src/api/"
  overall: PASS
  failures: []
side_effects:
  - "Pytest cache updated (.pytest_cache/)"
checkpoints:
  - id: "stash@{0}"
    type: git_stash
    restore_command: "git stash pop stash@{0}"
confidence: 0.95
evidence_anchors:
  - "src/api/user_controller.py:47"
  - "tool:bandit:output"
  - "tool:pytest:output"
assumptions:
  - "Database driver supports parameterized queries"
  - "No other code paths use vulnerable pattern"
```

**Evidence pattern:** Edit files, run verification tools, capture all outputs for audit.

---

### Example 2: Execute Migration Script

**Input:**
```yaml
plan:
  goal: "Run database schema migration"
  steps:
    - id: "backup"
      action: "Create database backup"
      target: "production_db"
      verification: "backup file exists and is non-empty"
    - id: "migrate"
      action: "Run migration script"
      target: "migrations/20250120_add_user_roles.sql"
      verification: "migration table updated"
    - id: "verify"
      action: "Check schema matches expected"
      target: "production_db.users"
      verification: "role column exists with correct type"
checkpoint_ref: "db-backup:20250120_pre_migration.sql"
dry_run: false
```

**Output:**
```yaml
actions_taken:
  - action: "Create database backup"
    target: "production_db"
    result: success
    output: "Backup created: backups/20250120_pre_migration.sql (45MB)"
  - action: "Execute migration SQL"
    target: "migrations/20250120_add_user_roles.sql"
    result: success
    output: "ALTER TABLE users ADD COLUMN role VARCHAR(50); 1 row affected"
  - action: "Verify schema"
    target: "production_db.users"
    result: success
    output: "Column 'role' exists, type=varchar(50), nullable=true"
changes:
  - file: "production_db:schema"
    operation: modify
    summary: "Added 'role' column to users table"
    diff_anchor: "db:schema_diff:users:20250120"
verification:
  checks_run:
    - "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
    - "SELECT COUNT(*) FROM users WHERE role IS NOT NULL"
    - "Migration log entry exists"
  overall: PASS
  failures: []
side_effects:
  - "Database connections temporarily held during ALTER"
  - "Query cache invalidated"
checkpoints:
  - id: "20250120_pre_migration.sql"
    type: file_backup
    restore_command: "psql production_db < backups/20250120_pre_migration.sql"
confidence: 0.9
evidence_anchors:
  - "backups/20250120_pre_migration.sql"
  - "migrations/20250120_add_user_roles.sql"
  - "db:query_log:20250120"
assumptions:
  - "No active transactions on users table during migration"
  - "Backup is consistent (no in-flight transactions)"
```

## Verification

- [ ] checkpoint_ref exists and is restorable (CRITICAL)
- [ ] All actions_taken have result status
- [ ] All changes have diff_anchor references
- [ ] verification.overall is computed from checks_run
- [ ] At least one checkpoint is documented
- [ ] Side effects are explicitly listed (even if empty)

**Verification tools:** Bash (for restore tests), Git (for diff verification), Read (for file checks)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: false
- `risk`: high

**Capability-specific rules:**
- NEVER execute without valid checkpoint_ref - abort immediately
- Stop on first action failure - do not continue partial execution
- Do not modify files outside plan targets
- Request explicit approval for destructive operations (delete, drop)
- Log all commands and outputs for audit trail
- Prefer reversible operations over irreversible when possible

## Composition Patterns

**Commonly follows:**
- `checkpoint` - REQUIRED before act (see CAVR pattern)
- `plan` - Provides the execution blueprint
- `constrain` - Policy checks before execution

**Commonly precedes:**
- `verify` - REQUIRED after act (see CAVR pattern)
- `audit` - Record what was done
- `rollback` - If verification fails

**Anti-patterns:**
- NEVER call act without prior checkpoint (CRITICAL)
- NEVER skip verify after act
- NEVER continue past first failure
- NEVER act without clear plan

**Workflow references:**
- See `composition_patterns.md#cavr-pattern` for checkpoint-act-verify-rollback
- See `composition_patterns.md#debug-code-change` for act in fix workflows
- See `composition_patterns.md#digital-twin-sync-loop` for act in automation
