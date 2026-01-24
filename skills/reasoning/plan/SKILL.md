---
name: plan
description: Create an executable plan with steps, dependencies, verification criteria, checkpoints, and rollback strategies. Use when preparing changes, designing workflows, or structuring multi-step operations before execution.
argument-hint: "[goal] [constraints] [context]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create a structured, executable plan that decomposes a goal into ordered steps with clear dependencies, verification criteria for each step, checkpoint placement for safety, and rollback strategies for recovery.

**This capability is the GATEWAY to all actions.** No mutating operation should proceed without a validated plan.

**Success criteria:**
- Goal is decomposed into atomic, verifiable steps
- Dependencies form a valid DAG (no cycles)
- Each mutating step has rollback strategy defined
- Checkpoints placed before high-risk operations
- Estimated risk level accurately reflects plan complexity

**Compatible schemas:**
- `docs/schemas/plan_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `goal` | Yes | string | Clear statement of what the plan should achieve |
| `context` | No | object | Current state, available resources, constraints |
| `constraints` | No | object | Time limits, resource bounds, policy restrictions |
| `risk_tolerance` | No | string | low, medium, high - affects checkpoint frequency |
| `max_steps` | No | integer | Maximum number of steps to generate |

## Procedure

1) **Understand the goal**: Parse and clarify the objective
   - Identify success criteria explicitly
   - Detect ambiguity and resolve or flag it
   - Determine scope boundaries

2) **Analyze context**: Gather relevant information
   - Read minimal files needed to understand current state
   - Identify existing patterns and conventions
   - Note constraints from environment or policy

3) **Decompose into steps**: Break goal into atomic operations
   - Each step should be independently verifiable
   - Prefer small, reversible changes
   - Order by logical dependencies
   - Use `decompose` capability patterns

4) **Define dependencies**: Map step relationships
   - Create DAG of step dependencies
   - Identify parallel-safe steps
   - Flag blocking dependencies

5) **Add verification criteria**: Specify how to check each step
   - Define concrete, testable conditions
   - Include expected outputs or state changes
   - Reference files or commands for verification

6) **Place checkpoints**: Identify recovery points
   - Before every mutating step (MANDATORY)
   - Before irreversible operations
   - At logical phase boundaries
   - More frequent for high-risk plans

7) **Define rollback strategies**: Plan recovery for each step
   - Specific commands or operations to undo
   - Order of rollback (reverse execution order)
   - Identify steps that cannot be rolled back

8) **Assess risk**: Evaluate overall plan risk
   - Count mutating operations
   - Consider blast radius of failures
   - Factor in rollback complexity

## Output Contract

Return a structured object:

```yaml
plan:
  id: string  # Unique plan identifier
  goal: string  # What this plan achieves
  steps:
    - id: string  # Step identifier (e.g., "step-1")
      action: string  # Type of action (edit, bash, git, etc.)
      target: string  # Resource being modified
      description: string  # Human-readable explanation
      dependencies: array[string]  # Step IDs this depends on
      verification_criteria: string  # How to verify success
      rollback_action: string | null  # How to undo (null if not reversible)
      estimated_risk: low | medium | high
  checkpoints:
    - after_step: string  # Step ID to checkpoint after
      type: git_stash | file_backup | state_snapshot
      reason: string  # Why checkpoint here
  estimated_risk: low | medium | high  # Overall plan risk
validation:
  preconditions: array[string]  # Must be true before execution
  postconditions: array[string]  # Must be true after execution
  invariants: array[string]  # Must remain true throughout
alternatives_considered: array[string]  # Other approaches evaluated
confidence: 0..1  # Confidence in plan correctness
evidence_anchors: ["file:line", "url"]
assumptions: []  # Explicit assumptions made
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `plan.id` | string | Unique identifier for this plan |
| `plan.goal` | string | Clear statement of objective |
| `plan.steps` | array | Ordered list of execution steps |
| `plan.checkpoints` | array | Recovery points in execution |
| `plan.estimated_risk` | enum | Overall risk assessment |
| `validation` | object | Pre/post conditions and invariants |
| `alternatives_considered` | array | Other approaches evaluated |
| `confidence` | number | 0.0-1.0 based on analysis completeness |
| `evidence_anchors` | array | References supporting the plan |
| `assumptions` | array | Explicit assumptions requiring validation |

## Examples

### Example 1: Bug Fix Plan

**Input:**
```yaml
goal: "Fix null pointer exception in UserService.getEmail()"
context:
  file: "src/services/UserService.ts"
  error: "TypeError: Cannot read property 'email' of null"
  stack_trace: "UserService.ts:42"
constraints:
  must_pass_tests: true
  no_api_changes: true
```

**Output:**
```yaml
plan:
  id: "fix-npe-userservice-001"
  goal: "Fix null pointer exception in UserService.getEmail()"
  steps:
    - id: "step-1"
      action: "edit"
      target: "src/services/UserService.ts"
      description: "Add null check before accessing user.email at line 42"
      dependencies: []
      verification_criteria: "File contains null check pattern 'if (user != null)' or 'user?.email'"
      rollback_action: "git checkout src/services/UserService.ts"
      estimated_risk: low
    - id: "step-2"
      action: "bash"
      target: "npm test -- --grep UserService"
      description: "Run UserService unit tests"
      dependencies: ["step-1"]
      verification_criteria: "Exit code 0, all tests pass"
      rollback_action: null
      estimated_risk: low
    - id: "step-3"
      action: "bash"
      target: "npm run lint src/services/UserService.ts"
      description: "Verify code style compliance"
      dependencies: ["step-1"]
      verification_criteria: "Exit code 0, no lint errors"
      rollback_action: null
      estimated_risk: low
  checkpoints:
    - after_step: "step-0"
      type: git_stash
      reason: "Preserve state before any file modifications"
  estimated_risk: low
validation:
  preconditions:
    - "src/services/UserService.ts exists"
    - "npm test command is available"
  postconditions:
    - "No null pointer exception on getEmail() with null user"
    - "All existing tests still pass"
  invariants:
    - "API signature of getEmail() unchanged"
alternatives_considered:
  - "Throw explicit error instead of returning null - rejected due to API change constraint"
  - "Add null check at caller sites - rejected as defensive coding in service is preferred"
confidence: 0.9
evidence_anchors:
  - "src/services/UserService.ts:42"
  - "tool:grep:null-access-pattern"
assumptions:
  - "Error only occurs when user object is null, not when email property is missing"
  - "Test suite covers the getEmail() method adequately"
```

**Evidence pattern:** Stack trace analysis identified exact location, code inspection revealed missing null check.

---

### Example 2: High-Risk Database Migration Plan

**Input:**
```yaml
goal: "Add new column to users table with default value"
context:
  database: "PostgreSQL 14"
  table: "users"
  column: "preferences JSONB DEFAULT '{}'"
  rows: "~1M"
constraints:
  max_downtime: "30s"
  must_be_reversible: true
```

**Output:**
```yaml
plan:
  id: "add-preferences-column-001"
  goal: "Add preferences JSONB column to users table"
  steps:
    - id: "step-1"
      action: "bash"
      target: "pg_dump users > backup_users.sql"
      description: "Create backup of users table"
      dependencies: []
      verification_criteria: "Backup file exists and is non-empty"
      rollback_action: null
      estimated_risk: low
    - id: "step-2"
      action: "bash"
      target: "psql -c 'ALTER TABLE users ADD COLUMN preferences JSONB DEFAULT '{}';'"
      description: "Add new column with default"
      dependencies: ["step-1"]
      verification_criteria: "Column exists in schema, no errors"
      rollback_action: "psql -c 'ALTER TABLE users DROP COLUMN preferences;'"
      estimated_risk: high
    - id: "step-3"
      action: "bash"
      target: "psql -c 'SELECT COUNT(*) FROM users WHERE preferences IS NOT NULL;'"
      description: "Verify default applied to all rows"
      dependencies: ["step-2"]
      verification_criteria: "Count matches total row count"
      rollback_action: null
      estimated_risk: low
  checkpoints:
    - after_step: "step-1"
      type: state_snapshot
      reason: "Backup created - recovery point before schema change"
    - after_step: "step-2"
      type: state_snapshot
      reason: "Schema modified - capture for validation"
  estimated_risk: high
validation:
  preconditions:
    - "users table exists"
    - "preferences column does not exist"
    - "Sufficient disk space for backup"
  postconditions:
    - "preferences column exists with JSONB type"
    - "All existing rows have default value"
  invariants:
    - "No data loss in existing columns"
    - "Application queries continue to work"
alternatives_considered:
  - "Add column without default, backfill separately - rejected due to NULL handling complexity"
  - "Create new table and migrate - rejected due to downtime constraints"
confidence: 0.75
evidence_anchors:
  - "tool:psql:schema-inspection"
assumptions:
  - "Database has sufficient resources for ALTER TABLE on 1M rows"
  - "No concurrent writes during migration window"
  - "Application handles new column gracefully"
```

## Verification

- [ ] All steps have unique IDs
- [ ] Dependencies form a valid DAG (no cycles)
- [ ] Every mutating step has verification_criteria
- [ ] Every high-risk step has rollback_action
- [ ] Checkpoints placed before mutations
- [ ] Preconditions are testable
- [ ] Postconditions match goal

**Verification tools:** Read (for file analysis), Grep (for pattern verification)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always include rollback strategies for mutating steps
- Place checkpoints before EVERY mutating operation
- Flag irreversible operations explicitly
- If estimated_risk is high, recommend human review before execution
- Never generate plans that bypass safety constraints
- Plans with confidence < 0.5 should request clarification

**CRITICAL: Plan is the gateway to act-plan**
- No `act-plan` execution should occur without a validated plan
- Plans must be complete before execution begins
- Incomplete plans should be marked as draft

## Composition Patterns

**Commonly follows:**
- `inspect` - Understand current state before planning
- `decompose` - Break complex goals into subgoals
- `critique` - Identify potential issues before finalizing
- `search` - Find relevant code/config to inform plan

**Commonly precedes:**
- `checkpoint` - Create safety checkpoint before execution
- `act-plan` - Execute the plan (REQUIRES this capability)
- `verify` - Validate plan structure before execution
- `constrain` - Apply policy limits to plan

**Anti-patterns:**
- Never call `act-plan` without a validated plan
- Never skip `critique` for high-risk plans
- Never execute plans with unresolved ambiguity

**Workflow references:**
- See `composition_patterns.md#debug-code-change` for bug fix workflow
- See `composition_patterns.md#capability-gap-analysis` for planning context
- See `composition_patterns.md#oma-pattern` for Observe-Model-Act flow
