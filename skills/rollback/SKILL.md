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

Execute **rollback** to return what a checkpoint captured to the state it had when the checkpoint was taken, whoever changed it since (STANDARD v1.2 §4.4.1). This is the recovery mechanism in the CAVR (Checkpoint-Act-Verify-Rollback) pattern, used when mutations fail or produce undesired outcomes.

A rollback changes the world back, not the account of it: the record of what happened (the audit log, `.claude/`, the host's checkpoint and approval state, the trace, the transcript) is never rolled back. It reaches only what its checkpoint captured: a transmission a `send` made since is reported as `not_covered` (`transmitted`), as is a delegate's change outside the checkpoint (`delegated`).

**Success criteria:**
- Everything the rollback concerns is back in its checkpointed state, and `restored` says so
- What could not be restored is listed in `unrestored`, with a reason
- The restored content's digest matches the checkpoint's (`verification`)

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `checkpoint_id` | Yes | string | ID of checkpoint to restore to |
| `scope` | No | string | Part of what the checkpoint captured to restore, in the host's naming (default: all of it). An item it names that the checkpoint did not capture is `unrestored` (`not_captured`) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Find the checkpoint**: Look it up by ID where the host keeps checkpoint content
   - An expired or used checkpoint can still be restored while its content is kept: validity limits what a checkpoint authorises, not what it restores (STANDARD 1.2.0 §4.4.1, §5.2.2)
   - If its content is gone, report `restored: false` with `{item: "*", reason: discarded}`

2) **Read what changed** (read-only): `git diff --name-status <sha> -- <paths>` (tracked changes, for `changes_reverted`) and `git ls-files --others --exclude-standard -- <paths>`; files **created since** are the untracked ones not in the checkpoint's `excluded`

3) **Restore by mechanism**. The git form is one line, a gated `mutate` (a fresh checkpoint and an approval: it overwrites the current state):
   - `restore_kind: stash`: `git restore --source=<sha> --worktree -- <paths> && git restore --source=<sha>^2 --staged -- <paths>`; `restore_kind: head`: `git restore --source=<sha> --staged --worktree -- <paths>`
   - Then, only when files were created since, `&& rm -f -- <created paths>`; never `git clean` with an empty path list
   - `git stash apply <sha>` aborts once a file it touches changed since the checkpoint; a bare `git stash pop` or `apply` is refused (F503)
   - `file_copy`: copy each file back from the manifest, and remove the files created in scope since
   - Never touch `.claude/`, the audit log or the host's state

4) **Verify** (read-only): `git diff --quiet <sha> -- <paths>` and the untracked list again, for `verification`

5) **Report**: `unrestored` for what failed (`failed`), was never captured (`not_captured`) or is gone (`discarded`); `not_covered` for changes the checkpoint never covered (`outside_scope`, `transmitted`, and `HEAD` when commits were made since). `restored` is true only if `unrestored` is empty; the step completes either way

6) **Ground claims**: the rollback's own record, the restore and the verification commands

## Output Contract

Return a structured object:

```yaml
restored: boolean  # true only if everything the rollback concerns is back; the step completes either way (§4.4.1)
unrestored:  # what the rollback concerns that is not back; empty exactly when restored is true
  - item: string
    reason: failed | conflict | discarded | not_captured | x-...
    detail: string
not_covered:  # changes since the checkpoint that it never covered; they do not make restored false
  - item: string
    reason: transmitted | delegated | outside_scope | x-...
    detail: string
changes_reverted:
  - item: string
    operation: create | modify | delete | other  # what was undone
    summary: string
verification:
  digest: string  # digest of the restored content, computed as the checkpoint's was
  match: boolean  # whether it matches the checkpoint's digest
previous_state:  # state before rollback
  summary: string
restored_state:  # state after rollback
  summary: string
next_actions: array[string]  # Suggested follow-up
confidence: number  # probability that the state now matches the checkpoint (§4.1.1)
evidence_anchors: [{ref: "rollback:<checkpoint_id>", kind: record}, {ref: "tool:bash:...", kind: tool}, {ref: "file:...", kind: file}]  # the restore's own record grounds the output (STANDARD v1.2 §3.1)
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `restored` | boolean | True only if everything the rollback concerns is back (workflows gate on `${<step>.restored}`, §12.5 Checked Rollback) |
| `unrestored` | array | Items not back, each with `failed`, `conflict`, `discarded`, `not_captured` or an `x-` reason |
| `not_covered` | array | Changes the checkpoint never covered: `transmitted`, `delegated`, `outside_scope` or an `x-` reason |
| `changes_reverted` | array | Each `item` and the `operation` undone |
| `verification` | object | The restored content's `digest`, and whether it `match`es the checkpoint's |
| `previous_state` | any | State before rollback |
| `restored_state` | any | State after rollback |
| `next_actions` | array | What to do next (re-plan, investigate, etc.) |
| `confidence` | number | Probability, 0.0-1.0, that the state now matches the checkpoint (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Proof of restoration |
| `assumptions` | array | Explicit assumptions made |

An item holds no secret (§6.7): name a file, not its content, and redact a URL's credentials.

## Examples

### Example 1: Git Rollback After Failed Tests

**Input:**
```yaml
checkpoint_id: "chk_20240115_143022_a7b3c9"
```

Reason for the rollback: tests failed after refactoring. The checkpoint's restore point is a stash commit; one file was created since.

**Output:**
```yaml
restored: true
unrestored: []
not_covered: []
changes_reverted:
  - item: "src/api/handlers/user.py"
    operation: modify
    summary: "Reverted refactored get_user() function"
  - item: "src/api/handlers/auth.py"
    operation: modify
    summary: "Reverted auth token validation changes"
  - item: "src/api/handlers/tokens.py"
    operation: create
    summary: "Removed a file the refactoring added"
verification:
  digest: "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  match: true
previous_state:
  summary: "3 handler files with refactored, failing code"
restored_state:
  summary: "Handlers as of the checkpoint"
next_actions:
  - "critique: Analyze why refactoring broke tests"
  - "plan: Create new plan with smaller incremental changes"
confidence: 1.0
evidence_anchors:
  - {ref: "rollback:chk_20240115_143022_a7b3c9", kind: record}
  - {ref: "tool:bash:git diff --name-status 4f1d2c3b5a6978877665544332211009988aabbc -- src/api/handlers", kind: tool}
  - {ref: "tool:bash:git restore --source=4f1d2c3b5a6978877665544332211009988aabbc --worktree -- src/api/handlers", kind: tool}
  - {ref: "tool:bash:git diff --quiet 4f1d2c3b5a6978877665544332211009988aabbc -- src/api/handlers", kind: tool}
assumptions:
  - "No commit was made since the checkpoint"
```

**Evidence pattern:** the changes read before the restore, the restore line, and the verification diff.

---

### Example 2: Partial Rollback After a Send

**Input:**
```yaml
checkpoint_id: "chk_20240115_150000_config"
scope: "config/production.yaml config/secrets.env"
```

Reason for the rollback: the config migration caused a service failure, after a notification was sent.

**Output:**
```yaml
restored: false
unrestored:
  - item: "config/secrets.env"
    reason: not_captured
    detail: "excluded from the checkpoint: it holds secrets"
not_covered:
  - item: "send to https://hooks.example.com/deploys (run-7:12)"
    reason: transmitted
changes_reverted:
  - item: "config/production.yaml"
    operation: modify
    summary: "Reverted database connection string changes"
verification:
  digest: "sha256:9b74c9897bac770ffc029102a200c5de0b1d5e5d3c1b0e2f4a6c8e0a2b4c6d8e"
  match: true
previous_state:
  summary: "Migrated database connection string"
restored_state:
  summary: "Original production config; secrets.env as it is now"
next_actions:
  - "inquire: secrets.env was never captured; ask how to restore it"
  - "send: tell the deploy channel the migration was rolled back"
confidence: 0.9
evidence_anchors:
  - {ref: "rollback:chk_20240115_150000_config", kind: record}
  - {ref: "tool:bash:git restore --source=1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d --staged --worktree -- config/production.yaml", kind: tool}
  - {ref: "file:config/production.yaml:1", kind: file}
assumptions:
  - "The notification cannot be recalled; a new send corrects it"
```

## Verification

Apply the following verification patterns:

- [ ] **Rollback Verification**: `verification.match` is true for what was restored (CRITICAL)
- [ ] **Report Complete**: `restored` is true exactly when `unrestored` is empty
- [ ] **State Assertion**: No file created since remains in scope
- [ ] **Evidence Grounding**: Restore command execution is captured

**Verification tools:** Bash (for restore and hash), Git (for the diff and the restore)

## Safety Constraints

- `mutation`: true (modifies files to restore state)
- `requires_checkpoint`: false (but a `checkpoint` MUST precede it: the ontology's `checkpoint` → `rollback` `requires` edge, else V102)
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- CRITICAL: Never rollback without a checkpoint_id that exists
- CRITICAL: Never report `restored: true` for a rollback that did not complete
- Clean up the files created in scope since the checkpoint
- An expired or used checkpoint can be restored (STANDARD 1.2.0 §5.2.2); the safety layer refuses a restore only when no checkpoint was ever taken (F503)
- Never roll back the record of what happened: `.claude/`, the audit log, the host's checkpoint and approval state
- A transmission is not undone: report it `transmitted`, and compensate in a step of its own
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
