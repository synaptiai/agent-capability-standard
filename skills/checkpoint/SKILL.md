---
name: checkpoint
description: Create a safety checkpoint marker before mutation or execution steps. Use when about to modify files, execute plans, or perform any irreversible action. Essential for the CAVR pattern.
argument-hint: "[scope] [label] [metadata]"
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
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            CHECKPOINT CREATION VALIDATION

            The tool call follows this prompt as JSON; the checkpoint command is tool_input.command.

            Verify checkpoint creation is appropriate:
            1. Scope includes all files that will be mutated
            2. No sensitive files (.env, credentials) being checkpointed
            3. Checkpoint reason is documented
            4. Checkpoint mechanism matches the operation (vcs_snapshot, file_copy, etc.)

            Return ok: true to create checkpoint.
            Return ok: false, with the reason, if:
            - Scope is incomplete (missing files)
            - Sensitive data would be captured
            - Checkpoint storage location is invalid
          once: false
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
            echo "[CHECKPOINT] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Bash | input_sha256: ${DIGEST:-unavailable}" >> .audit/checkpoint-operations.log 2>/dev/null || true
    - matcher: "Edit"
      hooks:
        - type: command
          command: |
            # Log the call without its input. Claude Code passes the tool call as
            # JSON on stdin; a SHA-256 digest of tool_input stands in for it.
            DIGEST=""
            INPUT="$(jq -cS '.tool_input' 2>/dev/null)" &&
              DIGEST="$(printf '%s' "$INPUT" | { sha256sum 2>/dev/null || shasum -a 256 2>/dev/null || openssl dgst -sha256 -r 2>/dev/null; } | cut -c1-64)"
            mkdir -p .audit 2>/dev/null || true
            echo "[CHECKPOINT] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Edit | input_sha256: ${DIGEST:-unavailable}" >> .audit/checkpoint-operations.log 2>/dev/null || true
---

## Intent

Execute **checkpoint** to take a copy of the state within a scope, kept where the host keeps it, from which that state can be restored before a mutating operation (STANDARD v1.2 §4.4.1). This is the foundation of safe agentic execution: a later `rollback` returns what the checkpoint captured to its saved state.

A checkpoint restores state, not effects: it cannot recall a transmission a later `send` makes (§4.4.2), and it reaches only what it captured. It never captures the record of what happened (the audit log, `.claude/`, the host's checkpoint and approval state): a scope that names those leaves them out and lists them in `excluded`.

**Success criteria:**
- The state in scope is captured, and what was left out is listed in `excluded`
- The restore point is recorded (a commit id, a manifest, a savepoint name)
- A `digest` of the captured content lets a rollback verify its restore

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `scope` | Yes | string | What to capture, in the host's naming (paths or patterns, keys, resource identifiers, separated by white space); `*` for everything the host can restore |
| `label` | No | string | Checkpoint name |
| `metadata` | No | object | Additional metadata |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Identify scope**: Determine exactly what needs to be captured
   - List the files, records or resources the upcoming change will touch
   - Include related configuration or state
   - Leave out what holds secrets (`.env`, keys, credentials): list it in `excluded`

2) **Select the mechanism** by what is in scope (reported as `mechanism`):
   - `vcs_snapshot`: tracked files in a version-control working tree
   - `file_copy`: files copied where the host keeps checkpoint content
   - `store_snapshot`: a key-value or document store's snapshot
   - `savepoint`: a database transaction savepoint
   - a provider snapshot (a volume, a VM image) as an `x-` name
   Keep checkpoint content where the host keeps it, outside the files in scope.

3) **Capture**. The git form (`vcs_snapshot`), each a separate plain Bash call: the safety layer counts exactly the plain `git stash create` as `checkpoint`, and a line with `$(`, `;` or `&&` as a gated `mutate`.
   1. `git stash create "checkpoint:<id>"`: saves the tracked state (worktree and index) as an unreferenced stash commit and prints its sha, leaving the working tree unchanged. **An empty output means a clean tree.**
   2. On a clean tree, `git rev-parse HEAD` (read-only): the restore point is `HEAD`. Record `restore_point` (the sha) and `restore_kind` (`stash` or `head`).
   3. `git ls-files --others --exclude-standard -- <paths>` (read-only): untracked files in scope, which `git stash create` does not capture. List them in `excluded`, or copy them (`file_copy`, a gated call of its own). Ignored files are outside the checkpoint.
   Do not run `git stash store` or `git update-ref`: either names a commit the caller chooses, which the safety layer does not count as a checkpoint, and as a gated `mutate` it would use up the checkpoint the `create` just took. Git keeps the unreferenced commit until `gc.pruneExpire` (two weeks by default); report no `expires_at` for it.
   For `file_copy`: copy each file in scope with a manifest of its path and SHA-256, into a private directory (0700) outside the scope.

4) **Generate the restore command**: how to roll back (skill-level aid, not contract)
   - For `vcs_snapshot`: the `rollback` skill's `git restore --source=<sha>` form
   - For `file_copy`: the copy back from the manifest

5) **Ground claims**: Attach evidence of the checkpoint
   - The checkpoint's own record: `{ref: "checkpoint:<id>", kind: record}`
   - The capture command: `tool:bash:<command>`

6) **Format output**: Return the checkpoint's report per contract

## Output Contract

Return a structured object:

```yaml
checkpoint_id: string  # Unique identifier (e.g., "chk_20240115_143022_abc123")
timestamp: string  # ISO 8601 date-time the checkpoint was taken
size: integer  # Size of the captured content in bytes (optional)
mechanism: vcs_snapshot | file_copy | store_snapshot | savepoint | x-...  # How it was taken (§4.4.1)
captured: array[string]  # What it holds, in the host's naming
excluded: array[string]  # What the scope named that it does not hold (secrets, untracked files, the host's own records)
digest: string  # "sha256:<hex>" of the captured content, which a rollback's verification compares
expires_at: string | null  # When the host may discard the content (retention), not its validity
restore_command: string  # Skill-level aid: how to restore
pre_mutation_state:
  summary: string  # Skill-level aid: human-readable state summary
next_safe_actions: array[string]  # What can now safely proceed
confidence: number  # probability that the checkpoint restores the state it reports (§4.1.1)
evidence_anchors: [{ref: "checkpoint:<checkpoint_id>", kind: record}, {ref: "tool:bash:...", kind: tool}, {ref: "file:...", kind: file}]  # the checkpoint's own record grounds the output (STANDARD v1.2 §3.1)
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint_id` | string | Unique identifier for this checkpoint (workflows bind `${<step>.checkpoint_id}`) |
| `timestamp` | string | ISO 8601 date-time the checkpoint was taken |
| `size` | integer | Size of the captured content in bytes (optional) |
| `mechanism` | string | `vcs_snapshot`, `file_copy`, `store_snapshot`, `savepoint`, or an `x-` name (§4.4.1) |
| `captured` | array | What the checkpoint holds |
| `excluded` | array | What the scope named that it does not hold |
| `digest` | string | Digest of the captured content, `<algorithm>:<lowercase hex>` |
| `expires_at` | string | When the content may be discarded; a used or no longer valid checkpoint can be restored until then |
| `restore_command` | string | Skill-level aid: how to restore |
| `next_safe_actions` | array | Actions that can now safely proceed |
| `confidence` | number | Probability, 0.0-1.0, that the checkpoint restores the state it reports (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Proof of the checkpoint |
| `assumptions` | array | Explicit assumptions (e.g., "git available") |

Validity and retention differ (§4.4.1): validity (§5.2.2) limits what a checkpoint authorises, one change, while it is fresh; retention limits what it can restore. A checkpoint that was used up or is no longer valid can still be restored while its content is kept.

## Examples

### Example 1: Git Checkpoint of a Dirty Tree

**Input:**
```yaml
scope: "src/api/handlers tests/test_handlers.py"
label: "Before refactoring API handlers"
```

**Output:**
```yaml
checkpoint_id: "chk_20240115_143022_a7b3c9"
timestamp: "2024-01-15T14:30:22Z"
mechanism: vcs_snapshot
captured:
  - "src/api/handlers/user.py"
  - "src/api/handlers/auth.py"
  - "tests/test_handlers.py"
excluded:
  - "src/api/handlers/scratch.py"
digest: "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
expires_at: null
restore_command: "git restore --source=4f1d2c3b5a6978877665544332211009988aabbc --worktree -- src/api/handlers tests/test_handlers.py && git restore --source=4f1d2c3b5a6978877665544332211009988aabbc^2 --staged -- src/api/handlers tests/test_handlers.py"
pre_mutation_state:
  summary: "3 tracked files with uncommitted changes; restore point is the stash commit"
next_safe_actions:
  - "mutate: Modify files in scope"
confidence: 1.0
evidence_anchors:
  - {ref: "checkpoint:chk_20240115_143022_a7b3c9", kind: record}
  - {ref: "tool:bash:git stash create checkpoint:chk_20240115_143022_a7b3c9", kind: tool}
  - {ref: "tool:bash:git ls-files --others --exclude-standard -- src/api/handlers tests/test_handlers.py", kind: tool}
assumptions:
  - "The untracked scratch.py is not needed to restore the handlers"
```

**Evidence pattern:** the stash commit `git stash create` printed (the restore point), and the untracked files it does not capture, listed in `excluded`.

---

### Example 2: Git Checkpoint of a Clean Tree

**Input:**
```yaml
scope: "config/production.yaml"
label: "Before config migration"
```

`git stash create` printed nothing: the tree is clean, so `git rev-parse HEAD` gives the restore point.

**Output:**
```yaml
checkpoint_id: "chk_20240115_150000_config"
timestamp: "2024-01-15T15:00:00Z"
mechanism: vcs_snapshot
captured:
  - "config/production.yaml"
excluded: []
digest: "sha256:9b74c9897bac770ffc029102a200c5de0b1d5e5d3c1b0e2f4a6c8e0a2b4c6d8e"
expires_at: null
restore_command: "git restore --source=1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d --staged --worktree -- config/production.yaml"
pre_mutation_state:
  summary: "1 tracked file, unchanged since HEAD"
next_safe_actions:
  - "mutate: Apply config migration"
confidence: 0.95
evidence_anchors:
  - {ref: "checkpoint:chk_20240115_150000_config", kind: record}
  - {ref: "tool:bash:git stash create checkpoint:chk_20240115_150000_config", kind: tool}
  - {ref: "tool:bash:git rev-parse HEAD", kind: tool}
assumptions:
  - "No commit is made between the checkpoint and the change"
```

## Verification

Apply the following verification patterns:

- [ ] **State Assertion**: `digest` can be recomputed from the captured content and matches
- [ ] **Scope Complete**: everything in scope is in `captured` or `excluded`
- [ ] **Nothing Secret Captured**: no secret-bearing file is in `captured`
- [ ] **Evidence Grounding**: checkpoint_id appears in evidence_anchors

**Verification tools:** Bash (for hash verification), Read (for manifest)

## Safety Constraints

- `mutation`: true (creates checkpoint artifacts)
- `requires_checkpoint`: false (this IS the checkpoint operation)
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- NEVER skip checkpoint before mutate or send (CRITICAL)
- NEVER delete checkpoint content until explicitly requested
- ALWAYS verify the capture immediately after creation
- Do not checkpoint sensitive files (.env, credentials): exclude them and list them in `excluded`
- Never capture the audit log, `.claude/`, or the host's checkpoint, approval or idempotency state (§4.4.1)
- Keep checkpoint content where the host keeps it, outside the files in scope
- Include the reason in the checkpoint's label for the audit trail

## Composition Patterns

**Commonly follows:**
- `plan` - After creating a plan, checkpoint before execution
- `critique` - After reviewing risks, checkpoint before proceeding
- `constrain` - After policy check passes, checkpoint before mutation

**Commonly precedes:**
- `mutate` - REQUIRED: Never mutate without prior checkpoint (CAVR pattern)
- `execute` - Checkpoint before a step that raises `requires_checkpoint`
- `send` - REQUIRED: Checkpoint before external communications; it restores the agent's own state, not the transmission (§4.4.2)
- `rollback` - REQUIRED: Rollback restores to a checkpoint

**Anti-patterns:**
- CRITICAL: Never call `mutate` or `send` without prior `checkpoint`
- CRITICAL: Never call `rollback` without valid checkpoint reference
- Never checkpoint after mutation has started
- Never delete checkpoint before verify confirms success

**Workflow references:**
- See `reference/composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
- See `reference/composition_patterns.md#debug-code-change` for checkpoint placement
- See `reference/composition_patterns.md#digital-twin-sync-loop` for checkpoint in loops
