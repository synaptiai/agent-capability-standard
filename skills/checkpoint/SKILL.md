---
name: checkpoint
description: Create a safety checkpoint marker before mutation or execution steps. Use when about to modify files, execute plans, or perform any irreversible action. Essential for the CAVR pattern.
argument-hint: "[scope] [reason] [checkpoint_type]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Bash, Edit
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: |
            CHECKPOINT CREATION VALIDATION

            Checkpoint command: {{tool_input.command}}

            Verify checkpoint creation is appropriate:
            1. Scope includes all files that will be mutated
            2. No sensitive files (.env, credentials) being checkpointed
            3. Checkpoint reason is documented
            4. Checkpoint type matches the operation (git_stash, file_backup, etc.)

            Reply ALLOW to create checkpoint.
            Reply BLOCK if:
            - Scope is incomplete (missing files)
            - Sensitive data would be captured
            - Checkpoint storage location is invalid
          once: false
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: |
            # Log checkpoint creation for audit trail
            mkdir -p .checkpoints .audit 2>/dev/null || true
            echo "[CHECKPOINT] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Command: {{tool_input.command}} | Exit: {{tool_output.exit_code}}" >> .audit/checkpoint-operations.log
            # Record checkpoint metadata
            if [ "{{tool_output.exit_code}}" = "0" ]; then
              echo "$(date -u +%Y-%m-%dT%H:%M:%SZ): Checkpoint created successfully" >> .checkpoints/checkpoint-manifest.log
            fi
    - matcher: "Edit"
      hooks:
        - type: command
          command: |
            echo "[CHECKPOINT] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Manifest updated: {{tool_input.file_path}}" >> .audit/checkpoint-operations.log 2>/dev/null || true
---

## Intent

Execute **checkpoint** to create a restorable state marker before any mutating operation. This is the foundation of safe agentic execution - enabling rollback if subsequent actions fail.

**Success criteria:**
- Checkpoint successfully created with unique identifier
- All files/state in scope are captured
- Restore command is documented and tested
- Expiry policy set if applicable

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `scope` | Yes | string\|array | Files, directories, or state keys to checkpoint |
| `reason` | No | string | Why this checkpoint is being created (for audit trail) |
| `checkpoint_type` | No | enum | Type: git_stash, file_backup, state_snapshot, database_savepoint |
| `expiry` | No | string | When checkpoint can be garbage collected (e.g., "24h", "never") |

## Procedure

1) **Identify scope**: Determine exactly what needs to be checkpointed
   - List all files that will be modified by upcoming mutation
   - Include related configuration or state files
   - Check for uncommitted git changes in scope

2) **Select checkpoint type**: Choose appropriate mechanism
   - `git_stash`: For git-tracked files (preferred for code changes)
   - `file_backup`: For non-git files, copy to `.checkpoints/`
   - `state_snapshot`: For in-memory or runtime state
   - `database_savepoint`: For database transactions

3) **Capture pre-mutation state**: Execute the checkpoint
   - For git: `git stash push -m "checkpoint:<id>:<reason>"`
   - For files: Copy to `.checkpoints/<id>/` with manifest
   - Record hashes of all captured content
   - Verify checkpoint integrity immediately after creation

4) **Generate restore command**: Document how to rollback
   - Exact command(s) to restore state
   - Any prerequisites for restoration
   - Order of operations if multiple systems involved

5) **Ground claims**: Attach evidence of checkpoint creation
   - Format: `tool:bash:<command>`, `file:<checkpoint_path>`
   - Include hash verification output

6) **Format output**: Return checkpoint metadata per contract

## Output Contract

Return a structured object:

```yaml
checkpoint_created: boolean
checkpoint:
  id: string  # Unique identifier (e.g., "chk_20240115_143022_abc123")
  type: git_stash | file_backup | state_snapshot | database_savepoint
  created_at: string  # ISO timestamp
  scope:
    files: array[string]  # File paths included
    state_keys: array[string]  # State keys included (if applicable)
  restore_command: string  # Exact command to restore
  expiry: string | null  # When checkpoint expires
pre_mutation_state:
  hash: string | null  # Combined hash of all checkpointed content
  summary: string  # Human-readable state summary
next_safe_actions: array[string]  # What can now safely proceed
confidence: number  # 0.0-1.0
evidence_anchors: ["tool:bash:...", "file:..."]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint_created` | boolean | Whether checkpoint was successfully created |
| `checkpoint.id` | string | Unique identifier for this checkpoint |
| `checkpoint.type` | enum | Mechanism used for checkpointing |
| `checkpoint.scope` | object | What was included in the checkpoint |
| `checkpoint.restore_command` | string | Exact command to restore state |
| `pre_mutation_state.hash` | string | Integrity hash of captured state |
| `next_safe_actions` | array | Actions that can now safely proceed |
| `confidence` | number | 0.0-1.0 based on checkpoint integrity verification |
| `evidence_anchors` | array | Proof of checkpoint creation |
| `assumptions` | array | Explicit assumptions (e.g., "git available") |

## Examples

### Example 1: Git Stash Checkpoint

**Input:**
```yaml
scope:
  - "src/api/handlers/*.py"
  - "tests/test_handlers.py"
reason: "Before refactoring API handlers"
checkpoint_type: git_stash
```

**Output:**
```yaml
checkpoint_created: true
checkpoint:
  id: "chk_20240115_143022_a7b3c9"
  type: git_stash
  created_at: "2024-01-15T14:30:22Z"
  scope:
    files:
      - "src/api/handlers/user.py"
      - "src/api/handlers/auth.py"
      - "tests/test_handlers.py"
    state_keys: []
  restore_command: "git stash pop stash@{0}"
  expiry: null
pre_mutation_state:
  hash: "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  summary: "3 files, 342 lines total, last modified 2024-01-15"
next_safe_actions:
  - "act-plan: Proceed with handler refactoring"
  - "edit: Modify files in scope"
confidence: 1.0
evidence_anchors:
  - "tool:bash:git stash push -m 'checkpoint:chk_20240115_143022_a7b3c9:Before refactoring API handlers'"
  - "tool:bash:git stash list | head -1"
assumptions:
  - "Git repository is initialized and clean"
  - "No merge conflicts in working tree"
```

**Evidence pattern:** Git stash creation command output, stash list verification.

---

### Example 2: File Backup Checkpoint

**Input:**
```yaml
scope: "config/production.yaml"
reason: "Before config migration"
checkpoint_type: file_backup
expiry: "24h"
```

**Output:**
```yaml
checkpoint_created: true
checkpoint:
  id: "chk_20240115_150000_config"
  type: file_backup
  created_at: "2024-01-15T15:00:00Z"
  scope:
    files:
      - "config/production.yaml"
    state_keys: []
  restore_command: "cp .checkpoints/chk_20240115_150000_config/production.yaml config/production.yaml"
  expiry: "2024-01-16T15:00:00Z"
pre_mutation_state:
  hash: "sha256:abc123..."
  summary: "1 file, 89 lines, production database config"
next_safe_actions:
  - "act-plan: Apply config migration"
confidence: 0.95
evidence_anchors:
  - "file:.checkpoints/chk_20240115_150000_config/manifest.json"
  - "tool:bash:sha256sum config/production.yaml"
assumptions:
  - ".checkpoints directory exists and is writable"
```

## Verification

Apply the following verification patterns:

- [ ] **State Assertion**: pre_mutation_state.hash can be recomputed and matches
- [ ] **Restore Command Valid**: restore_command executes without error (dry-run if possible)
- [ ] **Scope Complete**: All files in scope are captured in checkpoint
- [ ] **Evidence Grounding**: checkpoint.id appears in evidence_anchors

**Verification tools:** Bash (for hash verification), Read (for manifest)

## Safety Constraints

- `mutation`: true (creates checkpoint artifacts)
- `requires_checkpoint`: false (this IS the checkpoint operation)
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- NEVER skip checkpoint before act-plan (CRITICAL)
- NEVER delete checkpoints until explicitly requested
- ALWAYS verify checkpoint integrity immediately after creation
- Do not checkpoint sensitive files (.env, credentials) - warn and exclude
- Store checkpoint metadata in `.checkpoints/` within workspace
- Include reason in checkpoint for audit trail

## Composition Patterns

**Commonly follows:**
- `plan` - After creating a plan, checkpoint before execution
- `critique` - After reviewing risks, checkpoint before proceeding
- `constrain` - After policy check passes, checkpoint before mutation

**Commonly precedes:**
- `act-plan` - REQUIRED: Never act-plan without prior checkpoint (CAVR pattern)
- `improve` - Checkpoint before iterative improvement cycles
- `send` - Checkpoint before external communications

**Anti-patterns:**
- CRITICAL: Never call `act-plan` without prior `checkpoint`
- CRITICAL: Never call `rollback` without valid checkpoint reference
- Never checkpoint after mutation has started
- Never delete checkpoint before verify confirms success

**Workflow references:**
- See `composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
- See `composition_patterns.md#debug-code-change` for checkpoint placement
- See `composition_patterns.md#digital-twin-sync-loop` for checkpoint in loops
