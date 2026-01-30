---
name: audit
description: Produce a comprehensive audit trail of actions, tools used, changes made, and decision rationale. Use when recording compliance evidence, tracking changes, or documenting decision lineage.
argument-hint: "[scope] [time_window] [actor] [detail_level]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
hooks:
  PostToolUse:
    - matcher: "Read"
      hooks:
        - type: command
          command: |
            # Record audit data access for meta-audit
            mkdir -p .audit 2>/dev/null || true
            echo "[AUDIT-READ] $(date -u +%Y-%m-%dT%H:%M:%SZ) | File: {{tool_input.file_path}} | Accessed for audit" >> .audit/audit-meta.log
    - matcher: "Grep"
      hooks:
        - type: command
          command: |
            # Record audit search operations
            mkdir -p .audit 2>/dev/null || true
            echo "[AUDIT-SEARCH] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Pattern: {{tool_input.pattern}} | Searched for audit" >> .audit/audit-meta.log
---

## Live Context

Current audit context:

- Recent git commits: !`git log --oneline -10 2>/dev/null || echo "No git history"`
- Git authors today: !`git log --since="midnight" --format="%an" 2>/dev/null | sort | uniq -c || echo "None"`
- Uncommitted changes: !`git status --short 2>/dev/null || echo "Not a git repo"`
- Recent file modifications: !`find . -type f -mtime -1 -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' '` files in last 24h
- Audit log exists: !`ls -la .audit/ 2>/dev/null | head -5 || echo "No .audit/ directory"`
- Checkpoint log exists: !`ls -la .checkpoints/ 2>/dev/null | head -5 || echo "No .checkpoints/ directory"`

## Intent

Execute **audit** to create a structured record of actions taken, tools invoked, changes made, and the reasoning behind decisions. This provides accountability, enables investigation of issues, and supports compliance requirements.

**Success criteria:**
- Complete chronological record of relevant actions
- Every action linked to actor, timestamp, and rationale
- Changes documented with before/after state
- Provenance chain for all outputs

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `scope` | Yes | string\|array | What to audit: file paths, action types, or "session" for all |
| `time_window` | No | object | Start/end timestamps to bound the audit |
| `actor` | No | string | Filter by specific actor (agent, user, tool) |
| `detail_level` | No | enum | summary, standard, verbose (default: standard) |
| `include_diffs` | No | boolean | Whether to include actual change diffs (default: false) |

## Procedure

1) **Define audit scope**: Determine what to include in the audit
   - Parse scope parameter to identify targets
   - Apply time_window filter if provided
   - Identify relevant log sources (git log, tool invocations, file changes)

2) **Collect action records**: Gather all actions within scope
   - Read git log for commits and their messages
   - Review tool invocation history if available
   - Identify file changes (created, modified, deleted)
   - Record timestamps for each action

3) **Extract decision rationale**: Document the "why" for each action
   - Link actions to plans or goals that motivated them
   - Capture assumptions stated before action
   - Record any constraints that influenced decisions

4) **Build provenance chain**: Track inputs to outputs
   - For each output, identify its source inputs
   - Document transformations applied
   - List dependencies between artifacts

5) **Ground claims**: Attach evidence for all audit entries
   - Format: `file:line`, `tool:git:commit_hash`, `timestamp`
   - Include actual command outputs where relevant

6) **Format output**: Structure per audit contract

## Output Contract

Return a structured object:

```yaml
audit_record:
  id: string  # Unique audit record ID
  timestamp: string  # When audit was generated
  actor: string  # Who/what performed audited actions
  action_type: string  # Category of actions
  targets: array[string]  # What was affected
  outcome: success | failure | partial
changes:
  - type: string  # create, modify, delete, execute
    before: string | null  # Previous state/value
    after: string | null  # New state/value
    location: string  # File path or identifier
    timestamp: string  # When change occurred
tool_usage:
  - tool: string  # Tool name
    invocation_count: integer
    success_rate: number  # 0.0-1.0
    commands: array[string]  # Actual commands if verbose
decision_rationale: string  # Why these actions were taken
provenance:
  inputs: array[string]  # Source data/files
  outputs: array[string]  # Produced artifacts
  dependencies: array[string]  # External dependencies used
confidence: number  # 0.0-1.0 (completeness of audit)
evidence_anchors: ["tool:git:...", "file:..."]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `audit_record.id` | string | Unique identifier for this audit |
| `audit_record.actor` | string | Who performed the actions |
| `audit_record.outcome` | enum | Overall result of audited actions |
| `changes` | array | List of all changes with before/after |
| `tool_usage` | array | Summary of tools invoked |
| `decision_rationale` | string | Explanation of why actions were taken |
| `provenance` | object | Input/output/dependency lineage |
| `confidence` | number | 0.0-1.0 completeness of audit trail |
| `evidence_anchors` | array | References to source evidence |
| `assumptions` | array | What was assumed during audit collection |

## Examples

### Example 1: Audit Code Change Session

**Input:**
```yaml
scope: "session"
time_window:
  start: "2024-01-15T14:00:00Z"
  end: "2024-01-15T16:00:00Z"
detail_level: standard
include_diffs: false
```

**Output:**
```yaml
audit_record:
  id: "audit_20240115_160000_session"
  timestamp: "2024-01-15T16:00:00Z"
  actor: "claude-agent"
  action_type: "code_modification"
  targets:
    - "src/api/handlers/user.py"
    - "src/api/handlers/auth.py"
    - "tests/test_handlers.py"
  outcome: success
changes:
  - type: modify
    before: "get_user() with inline SQL"
    after: "get_user() with parameterized query"
    location: "src/api/handlers/user.py:45-62"
    timestamp: "2024-01-15T14:45:00Z"
  - type: modify
    before: "5 test cases"
    after: "7 test cases (added SQL injection tests)"
    location: "tests/test_handlers.py"
    timestamp: "2024-01-15T15:15:00Z"
tool_usage:
  - tool: Read
    invocation_count: 12
    success_rate: 1.0
  - tool: Edit
    invocation_count: 4
    success_rate: 1.0
  - tool: Bash
    invocation_count: 3
    success_rate: 1.0
    commands: ["pytest tests/", "git diff", "git commit"]
decision_rationale: "Refactored to prevent SQL injection vulnerability identified in security audit. Added parameterized queries and corresponding test coverage."
provenance:
  inputs:
    - "security_audit_report.md"
    - "src/api/handlers/user.py (original)"
  outputs:
    - "src/api/handlers/user.py (modified)"
    - "tests/test_handlers.py (modified)"
  dependencies:
    - "pytest>=7.0"
    - "psycopg2"
confidence: 0.95
evidence_anchors:
  - "tool:git:abc123def456"
  - "tool:bash:pytest tests/ - 7 passed"
  - "file:src/api/handlers/user.py:45"
assumptions:
  - "Git log accurately reflects all changes"
  - "No manual edits outside of tracked session"
```

**Evidence pattern:** Git commit history, tool invocation logs, file diffs.

---

### Example 2: Audit Specific File Changes

**Input:**
```yaml
scope: "config/production.yaml"
detail_level: verbose
include_diffs: true
```

**Output:**
```yaml
audit_record:
  id: "audit_20240115_config"
  timestamp: "2024-01-15T17:00:00Z"
  actor: "claude-agent"
  action_type: "configuration_change"
  targets:
    - "config/production.yaml"
  outcome: failure
changes:
  - type: modify
    before: |
      database:
        host: db.internal
        port: 5432
    after: |
      database:
        host: db.external
        port: 5433
    location: "config/production.yaml:12-15"
    timestamp: "2024-01-15T15:30:00Z"
  - type: rollback
    before: "(modified config)"
    after: "(original config)"
    location: "config/production.yaml"
    timestamp: "2024-01-15T16:00:00Z"
tool_usage:
  - tool: Edit
    invocation_count: 2
    success_rate: 0.5
decision_rationale: "Attempted database migration to external host. Rollback triggered after connection test failed."
provenance:
  inputs:
    - "migration_plan.md"
    - "config/production.yaml (original)"
  outputs:
    - "config/production.yaml (restored to original)"
  dependencies: []
confidence: 1.0
evidence_anchors:
  - "file:.checkpoints/chk_20240115_150000_config/manifest.json"
  - "tool:bash:rollback command output"
assumptions: []
```

## Verification

Apply the following verification patterns:

- [ ] **Evidence Grounding**: All changes linked to evidence_anchors
- [ ] **Contract Validation**: Output matches audit_record schema
- [ ] **Completeness Check**: No gaps in timeline for specified time_window
- [ ] **Provenance Valid**: All inputs and outputs are verifiable

**Verification tools:** Read (for log files), Grep (for searching history)

## Safety Constraints

- `mutation`: false (audit is read-only observation)
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- Never modify audited artifacts during audit
- Preserve original timestamps (do not alter history)
- Include failed actions, not just successes
- Redact sensitive information (credentials, PII) from audit output
- Store audit records in append-only manner when persisting

## Composition Patterns

**Commonly follows:**
- `verify` - After verify PASS, audit the successful changes (CAVR pattern)
- `act-plan` - Audit what was executed
- `rollback` - Audit the rollback event itself

**Commonly precedes:**
- `summarize` - Summarize audit for stakeholder reporting
- `persist` - Store audit record for compliance

**Anti-patterns:**
- Never skip audit after act-plan (breaks accountability)
- Never modify artifacts during audit (breaks integrity)
- Never omit failed actions from audit trail

**Workflow references:**
- See `reference/composition_patterns.md#debug-code-change` for audit-after-verify
- See `reference/composition_patterns.md#digital-twin-sync-loop` for audit in loops
