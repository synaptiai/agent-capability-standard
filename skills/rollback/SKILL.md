---
name: rollback
description: Safely undo changes by restoring to a checkpoint. Use when verify fails, errors occur, or explicit undo is requested. Essential for the CAVR pattern recovery.
argument-hint: "[checkpoint_id] [scope]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Bash, Git
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: |
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            ROLLBACK SAFETY VALIDATION

            The tool call follows this prompt as JSON; the rollback command is tool_input.command.

            The safety layer checks the restore command: `git stash apply <sha>`,
            with the full id of the commit a checkpoint recorded, is a
            `rollback` call (a checkpoint taken earlier, F503); applying any
            other commit, and the skill's own restore, a `git restore
            --source=<sha> ...` line, is a `mutate` call (a fresh checkpoint,
            F501, and approval, F502). An expired or used checkpoint can still
            be restored (STANDARD 1.2.0 §5.2.2).

            Before executing rollback, verify:
            1. Current state has been captured (for audit)
            2. Rollback scope matches intended restore scope
            3. No ongoing operations that would conflict

            CRITICAL CHECKS:
            - Is checkpoint integrity verified (hash match)?
            - Will any data be irreversibly lost?
            - Are there uncommitted changes that would be overwritten?

            Return ok: true if rollback is safe to execute.
            Return ok: false, with the reason, if:
            - Checkpoint is missing or corrupted
            - Rollback would cause data loss beyond intended scope
            - Current state needs to be preserved first
          once: false
        - type: command
          command: |
            # A restore in this skill restores a checkpoint taken in the project
            # (STANDARD 1.2.0 §5.18.6, F503): each `git stash pop` or `git stash
            # apply` must name, as its one argument, the full id of a commit a
            # checkpoint marker recorded (.claude/checkpoint.ok, or one filed under
            # .claude/checkpoints/used/ or ended/), as the plugin's pre-tool-use
            # hook reads it; valid or not, used or not. Claude Code passes the tool
            # call as JSON on stdin; exit 2 blocks the call and the reason on stderr
            # is shown to Claude. A call that cannot be read is blocked (R407).
            CMD="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then DIR="$CLAUDE_PROJECT_DIR/.claude"
            elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then DIR="$CLAUDE_PLUGIN_ROOT/.claude"
            else DIR="$(pwd)/.claude"; fi
            while IFS= read -r RESTORE; do
              [ -n "$RESTORE" ] || continue
              ARG="$(printf '%s\n' "$RESTORE" | sed -E 's/^git[[:space:]]+stash[[:space:]]+(pop|apply)//; s/^[[:space:]]+//; s/[[:space:]]+$//')"
              FOUND=""
              if printf '%s\n' "$ARG" | grep -qE '^([0-9a-f]{40}|[0-9a-f]{64})$'; then
                for F in "$DIR/checkpoint.ok" "$DIR"/checkpoints/used/* "$DIR"/checkpoints/ended/*; do
                  if [ -f "$F" ] && [ ! -L "$F" ] && [ "$(jq -r 'if type == "object" then (.commit // "" | strings) else "" end' "$F" 2>/dev/null)" = "$ARG" ]; then FOUND=1; break; fi
                done
              fi
              if [ -z "$FOUND" ]; then
                printf "F503 ROLLBACK_FAILED: '%s' restores no checkpoint taken in this project. Restore with git stash apply <sha>, the full commit id a checkpoint recorded.\n" "$RESTORE" >&2
                exit 2
              fi
            done <<EOF
            $(printf '%s\n' "$CMD" | grep -oE 'git[[:space:]]+stash[[:space:]]+(pop|apply)([[:space:]][^;&|<>()]*)?' || true)
            EOF
            exit 0
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: |
            # Log the call without its input. Claude Code passes the tool call as
            # JSON on stdin; a SHA-256 digest of tool_input stands in for it.
            DIGEST=""
            INPUT="$(jq -cS '.tool_input' 2>/dev/null)" &&
              DIGEST="$(printf '%s' "$INPUT" | { sha256sum 2>/dev/null || shasum -a 256 2>/dev/null || openssl dgst -sha256 -r 2>/dev/null; } | cut -c1-64)"
            mkdir -p .audit 2>/dev/null || true
            echo "[ROLLBACK] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Bash | input_sha256: ${DIGEST:-unavailable}" >> .audit/rollback-operations.log 2>/dev/null || true
---

## Intent

Execute **rollback** to restore system state to a previously created checkpoint. This is the recovery mechanism in the CAVR (Checkpoint-Act-Verify-Rollback) pattern - used when mutations fail or produce undesired outcomes.

**Success criteria:**
- State fully restored to checkpoint state
- Post-rollback hash matches checkpoint hash
- No orphaned artifacts remain from failed mutation
- Audit trail of what was reverted

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `checkpoint_id` | Yes | string | ID of checkpoint to restore to |
| `scope` | No | string | Specific files/keys to rollback (default: all in checkpoint) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Validate checkpoint**: Confirm checkpoint exists and is valid
   - Look up checkpoint by ID in `.checkpoints/` or git stash
   - Verify checkpoint integrity (hash check)
   - An expired or used checkpoint can still be restored: validity limits what a checkpoint authorises, not what it restores (STANDARD 1.2.0 §5.2.2)
   - If checkpoint missing: FAIL immediately with clear error

2) **Capture current state**: Record what will be reverted
   - List all files/state that differ from checkpoint
   - Compute hash of current state for audit
   - Document changes that will be undone

3) **Execute restoration**: Apply the restore command
   - For a git checkpoint: `git stash apply <sha>`, with the full commit id the checkpoint recorded; a bare `git stash pop` or `git stash apply`, or any other revision, restores no checkpoint and is refused (F503)
   - For file_backup: Copy from `.checkpoints/<id>/` to original locations
   - For state_snapshot: Restore state variables
   - Handle any conflicts or errors gracefully

4) **Verify restoration**: Confirm state matches checkpoint
   - Recompute hash of restored state
   - Compare with checkpoint's pre_mutation_state.hash
   - Check for orphaned files created during failed mutation
   - Clean up orphaned artifacts if present

5) **Ground claims**: Attach evidence of successful rollback
   - Format: `tool:bash:<restore_command>`, comparison output
   - Include before/after state hashes

6) **Format output**: Return rollback results per contract

## Output Contract

Return a structured object:

```yaml
restored: boolean  # Whether state was restored to the checkpoint
previous_state:  # State before rollback
  hash: string
  summary: string
restored_state:  # State after rollback
  hash: string
  summary: string
restored_to:
  checkpoint_id: string
  checkpoint_type: string
  timestamp: string  # When checkpoint was created
changes_reverted:
  - file: string
    operation: string  # What was undone (create, modify, delete)
    summary: string  # Brief description of change reverted
verification:
  checkpoint_hash: string  # Expected hash from checkpoint
  match: boolean  # restored_state.hash == checkpoint_hash
warnings: array[string]  # Any issues encountered
next_actions: array[string]  # Suggested follow-up
confidence: number  # probability that the state now matches the checkpoint (§4.1.1)
evidence_anchors: [{ref: "rollback:<checkpoint_id>", kind: record}, {ref: "tool:bash:...", kind: tool}, {ref: "file:...", kind: file}]  # the restore's own record grounds the output (STANDARD v1.2 §3.1)
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `restored` | boolean | Whether rollback was successful (workflows gate on `${<step>.restored}`) |
| `previous_state` | any | State before rollback (hash and summary) |
| `restored_state` | any | State after rollback (hash and summary) |
| `restored_to` | object | Checkpoint that was restored to |
| `changes_reverted` | array | List of changes that were undone |
| `verification.match` | boolean | Whether restored state matches checkpoint |
| `warnings` | array | Issues like orphaned files or partial restore |
| `next_actions` | array | What to do next (re-plan, investigate, etc.) |
| `confidence` | number | Probability, 0.0-1.0, that the state now matches the checkpoint (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Proof of restoration |
| `assumptions` | array | Explicit assumptions made |

## Examples

### Example 1: Git Stash Rollback After Failed Tests

**Input:**
```yaml
checkpoint_id: "chk_20240115_143022_a7b3c9"
```

Reason for the rollback: tests failed after refactoring.

**Output:**
```yaml
restored: true
previous_state:
  hash: "sha256:deadbeef..."
  summary: "2 handler files with refactored, failing code"
restored_state:
  hash: "sha256:e3b0c442..."
  summary: "Handlers as of checkpoint"
restored_to:
  checkpoint_id: "chk_20240115_143022_a7b3c9"
  checkpoint_type: git_stash
  timestamp: "2024-01-15T14:30:22Z"
changes_reverted:
  - file: "src/api/handlers/user.py"
    operation: modify
    summary: "Reverted refactored get_user() function"
  - file: "src/api/handlers/auth.py"
    operation: modify
    summary: "Reverted auth token validation changes"
verification:
  checkpoint_hash: "sha256:e3b0c442..."
  match: true
warnings: []
next_actions:
  - "critique: Analyze why refactoring broke tests"
  - "plan: Create new plan with smaller incremental changes"
confidence: 1.0
evidence_anchors:
  - {ref: "rollback:chk_20240115_143022_a7b3c9", kind: record}
  - {ref: "tool:bash:git stash pop stash@{0}", kind: tool}
  - {ref: "tool:bash:git diff --stat HEAD", kind: tool}
  - {ref: "tool:bash:sha256sum src/api/handlers/*.py", kind: tool}
assumptions:
  - "No other changes made to stashed files since checkpoint"
```

**Evidence pattern:** Git stash pop output, diff showing restored state, hash verification.

---

### Example 2: File Backup Rollback with Orphaned Files

**Input:**
```yaml
checkpoint_id: "chk_20240115_150000_config"
```

Reason for the rollback: the config migration caused a service failure.

**Output:**
```yaml
restored: true
previous_state:
  hash: "sha256:newconfig..."
  summary: "Migrated database connection string"
restored_state:
  hash: "sha256:abc123..."
  summary: "Original production config"
restored_to:
  checkpoint_id: "chk_20240115_150000_config"
  checkpoint_type: file_backup
  timestamp: "2024-01-15T15:00:00Z"
changes_reverted:
  - file: "config/production.yaml"
    operation: modify
    summary: "Reverted database connection string changes"
verification:
  checkpoint_hash: "sha256:abc123..."
  match: true
warnings:
  - "Orphaned file detected: config/production.yaml.bak (removed)"
next_actions:
  - "audit: Record failed migration attempt"
  - "plan: Investigate migration script issue"
confidence: 0.95
evidence_anchors:
  - {ref: "rollback:chk_20240115_150000_config", kind: record}
  - {ref: "tool:bash:cp .checkpoints/chk_20240115_150000_config/production.yaml config/", kind: tool}
  - {ref: "tool:bash:rm config/production.yaml.bak", kind: tool}
  - {ref: "file:config/production.yaml:1", kind: file}
assumptions:
  - "Checkpoint backup file is not corrupted"
```

## Verification

Apply the following verification patterns:

- [ ] **Rollback Verification**: restored_state.hash == checkpoint_hash (CRITICAL)
- [ ] **State Assertion**: No unexpected files remain after rollback
- [ ] **Evidence Grounding**: Restore command execution is captured
- [ ] **Clean Git State**: git status shows no unexpected changes

**Verification tools:** Bash (for restore and hash), Git (for stash operations)

## Safety Constraints

- `mutation`: true (modifies files to restore state)
- `requires_checkpoint`: false (but a `checkpoint` MUST precede it: the ontology's `checkpoint` → `rollback` `requires` edge, else V102)
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- CRITICAL: Never rollback without a checkpoint_id that exists
- CRITICAL: Always verify state hash matches after restore
- Clean up orphaned files created by failed mutation
- An expired or used checkpoint can be restored (STANDARD 1.2.0 §5.2.2); the safety layer refuses a restore only when no checkpoint was ever taken (F503)
- Preserve audit trail of what was reverted
- If verification fails, STOP and alert - do not proceed

## Composition Patterns

**Commonly follows:**
- `verify` - When verify returns `passed: false`, trigger rollback (CAVR pattern)
- `mutate` / `execute` - If the side effect fails or verify returns `passed: false`, rollback
- `checkpoint` - Rollback requires prior checkpoint (dependency)

**Commonly precedes:**
- `critique` - After rollback, analyze what went wrong
- `plan` - Create new plan after understanding failure
- `audit` - Record the rollback event

**Anti-patterns:**
- CRITICAL: Never rollback without existing checkpoint
- CRITICAL: Never continue mutations after rollback without new checkpoint
- Never skip verification after rollback
- Never delete checkpoint until rollback verification passes

**Workflow references:**
- See `reference/composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
- See `reference/verification_patterns.md#pattern-4-rollback-verification` for rollback verification
- See `reference/composition_patterns.md#debug-code-change` for rollback-then-critique flow
