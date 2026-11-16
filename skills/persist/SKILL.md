---
name: persist
description: Write stable learnings, decisions, and patterns to durable storage like CLAUDE.md or knowledge files. Use when saving project decisions, recording patterns, or updating long-term memory.
argument-hint: "[data] [key] [ttl]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Edit"
      hooks:
        - type: prompt
          prompt: |
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            PERSIST DATA VALIDATION CHECK

            The tool call follows this prompt as JSON; the target file is
            tool_input.file_path and the content to write is tool_input.new_string.

            Verify before persisting:
            1. NO credentials, API keys, or secrets in content
            2. NO personally identifiable information (PII)
            3. NO executable code that could be malicious
            4. File is within project scope (not system files)
            5. Content is stable knowledge (not ephemeral data)

            Also check:
            - Is this a duplicate of existing content?
            - Does this contradict existing persisted facts?

            Return ok: true if content is safe to persist.
            Return ok: false, with the specific reason, if validation fails.
          once: false
        - type: command
          command: |
            # Code-decided checks (STANDARD 1.2.0 §5.18.10): the target file is not
            # a system or credential file, and the content holds no credential
            # (§6.7). Claude Code passes the tool call as JSON on stdin, read once
            # here; exit 2 blocks the call and the reason on stderr is shown to
            # Claude. A call that cannot be read is blocked.
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            TARGET="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            case "$TARGET" in
              "~/"*) TARGET="${HOME}/${TARGET#??}" ;;
            esac
            # A path with '//', '.' or '..' segments is not compared as written
            # (/tmp/../etc/passwd is /etc/passwd), so it is blocked
            case "$TARGET" in
              *//*|*/./*|*/.|*/../*|*/..|../*|..)
                echo "F504 CONSTRAINT_VIOLATED: Cannot persist to a path with '//', '.' or '..' segments; give the normalised path" >&2
                exit 2
                ;;
            esac
            # Block writes to system directories and to credential directories under the home directory
            case "$TARGET" in
              /etc/*|/usr/*|/bin/*|/sbin/*|"${HOME}"/.ssh/*|"${HOME}"/.aws/*|"${HOME}"/.config/*)
                echo "F504 CONSTRAINT_VIOLATED: Cannot persist to system or credential directories" >&2
                exit 2
                ;;
            esac
            # Block writes to credential files
            if printf '%s\n' "$TARGET" | grep -qiE "(\.env|credentials|secrets|password|\.pem|\.key)$"; then
              echo "F504 CONSTRAINT_VIOLATED: Cannot persist to credential files" >&2
              exit 2
            fi
            # The content written: an Edit's new_string, or a whole file's content
            CONTENT="$(printf '%s' "$INPUT" | jq -r '[.tool_input.new_string, .tool_input.content] | map(select(type == "string")) | join("\n")' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            # BEGIN secret-scan (source: hooks/secret_scan.sh; tests/test_skill_hooks.py keeps every copy equal)
            # secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7).
            SECRET_ERE='-----BEGIN [A-Z ]*PRIVATE KEY-----|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
            SECRET_KEY='(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)'
            secret_in() {
              printf '%s' "$1" | grep -Eq -- "$SECRET_ERE" && return 0
              # A quoted value with no whitespace, 8 or more characters
              printf '%s' "$1" | grep -Eiq -- "$SECRET_KEY[\"']?[[:space:]]*[:=][[:space:]]*[\"'][^[:space:]\"']{8,}[\"']" && return 0
              # The password of a URL's userinfo, unless it is a placeholder
              printf '%s' "$1" | grep -Eo -- '[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/:@]+:[^[:space:]/@]+@' |
                sed -E 's#^[^/]*//[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
              # An Authorization header's value, 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization[\"']?[[:space:]]*[:=][[:space:]]*[\"']?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
                sed -E "s/^[^:=]*[:=][[:space:]]*[\"']?//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # An unquoted value of 12 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "$SECRET_KEY[\"']?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
                sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]'
            }
            # END secret-scan
            # Memory is read back as fact, so a credential is refused, not redacted
            if secret_in "$CONTENT"; then
              echo "F504 CONSTRAINT_VIOLATED: the content holds what looks like a credential; persist where the secret is kept, not the secret (STANDARD 1.2.0 §6.7)" >&2
              exit 2
            fi
            exit 0
  PostToolUse:
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
            echo "[PERSIST] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Edit | input_sha256: ${DIGEST:-unavailable}" >> .audit/persist-operations.log 2>/dev/null || true
---

## Intent

Execute **persist** to write stable learnings, decisions, and patterns to durable storage for future recall and consistency.

**Success criteria:**
- Content is written to the correct destination
- Existing content is preserved or properly merged
- New content follows established structure/format
- Metadata (timestamp, source) is recorded
- Write is verified successfully

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data` | Yes | any | Data to store |
| `key` | No | string | Storage key |
| `ttl` | No | string | Time to live |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Validate content**: Ensure content is appropriate for persistence
   - Check content is non-empty and meaningful
   - Verify content type classification
   - Ensure no sensitive data (credentials, PII) is being persisted: data that holds a secret is refused, not redacted, since memory is read back as fact (STANDARD v1.2 §6.7). Persist where the secret is kept (an environment variable's name, a vault path), not the secret
   - Validate content structure if object

2) **Determine destination**: Select where to write (from `key`, if given)
   - `CLAUDE.md`: Project-level decisions and patterns
   - Specific file: Domain or feature-specific knowledge
   - `auto`: Choose based on content type and scope

3) **Read existing content**: Load current state of destination
   - Parse structure and sections
   - Identify target section for new content
   - Note existing entries to avoid duplicates

4) **Check for duplicates/conflicts**: Compare new vs existing
   - Exact duplicate: Skip or update timestamp only
   - Similar content: Flag for review
   - Contradiction: Stop and request clarification

5) **Format new content**: Structure for persistence
   - Add timestamp and source metadata
   - Format according to destination conventions
   - Include rationale if decision/pattern

6) **Apply merge strategy**:
   - `append`: Add to end of section
   - `replace`: Overwrite matching existing entry
   - `merge`: Intelligently combine with existing

7) **Write to destination**: Execute the write operation
   - Use Edit tool for file modifications
   - Preserve file formatting and structure
   - Add section headers if needed

8) **Verify write**: Confirm content was persisted correctly
   - Re-read destination file
   - Confirm new content present
   - Validate structure integrity

## Output Contract

Return a structured object:

```yaml
stored: boolean  # true when the data is in the store after this step (written, merged, or already present)
key: string  # Storage key (destination and section, e.g. "CLAUDE.md#Patterns")
timestamp: string  # ISO 8601 date-time of persistence
persisted:
  content_type: decision | pattern | fact | context
  content_id: string  # Unique identifier for this persisted item
  destination: string  # File path where content was written
  section: string | null  # Section within file
write_operation:
  strategy: append | replace | merge
  bytes_written: integer
  lines_added: integer
  lines_modified: integer
verification:
  write_confirmed: boolean
  content_present: boolean
  structure_valid: boolean
metadata:
  source: string  # Where this knowledge came from
  related_entries: array[string]  # IDs of related persisted items
  expiry: string | null  # When this knowledge should be reviewed
duplicates_found:
  - existing_id: string
    similarity: number
    action_taken: skipped | updated | merged
confidence: number  # probability that the data was stored as reported (§4.1.1)
evidence_anchors: array[EvidenceAnchor]  # References to verification; each {ref, kind} (STANDARD v1.2 §6.5)
assumptions: array[string]  # Explicit assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `stored` | boolean | Whether the data is in the store after this step (written, merged, or already present as a duplicate) |
| `key` | string | Storage key the data lives under (destination and section) |
| `timestamp` | string | ISO 8601 date-time of persistence |
| `persisted.content_id` | string | Unique ID for retrieval with `recall` |
| `persisted.destination` | string | File path of storage location |
| `write_operation` | object | Details of the write performed |
| `verification.write_confirmed` | boolean | Whether write was verified |
| `duplicates_found` | array | Any duplicate/similar entries detected |
| `confidence` | number | Probability, 0.0-1.0, that the data was stored as reported (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | References to the written location and its verification |
| `assumptions` | array | Explicit assumptions |

## Examples

### Example 1: Persisting a Project Decision

**Input:**
```yaml
data:
  content_type: decision
  decision: "Use PostgreSQL for all persistent storage"
  rationale: "Strong ACID guarantees, mature ecosystem, team familiarity"
  context: "Evaluated PostgreSQL, MySQL, and MongoDB for new backend service"
  constraints:
    - "Must support complex queries"
    - "Team has PostgreSQL experience"
key: "CLAUDE.md#Architecture Decisions"
```

**Output:**
```yaml
stored: true
key: "CLAUDE.md#Architecture Decisions"
timestamp: "2024-01-16T10:00:00Z"
persisted:
  content_type: decision
  content_id: "decision_db_20240116"
  destination: "CLAUDE.md"
  section: "Architecture Decisions"
write_operation:
  strategy: append
  bytes_written: 256
  lines_added: 8
  lines_modified: 0
verification:
  write_confirmed: true
  content_present: true
  structure_valid: true
metadata:
  source: "conversation:conv_abc123"
  related_entries: []
  expiry: null
duplicates_found: []
confidence: 1.0
evidence_anchors:
  - {ref: "memory:CLAUDE.md#Architecture Decisions", kind: record}
  - {ref: "file:CLAUDE.md:45-52", kind: file}
  - {ref: "verification:re-read:success", kind: tool}
assumptions:
  - "CLAUDE.md is the correct location for architecture decisions"
  - "No conflicting database decisions exist"
```

**What was written to CLAUDE.md:**
```markdown
### Architecture Decisions

#### Database: PostgreSQL [2024-01-16]

**Decision:** Use PostgreSQL for all persistent storage

**Rationale:** Strong ACID guarantees, mature ecosystem, team familiarity

**Context:** Evaluated PostgreSQL, MySQL, and MongoDB for new backend service

**Constraints:**
- Must support complex queries
- Team has PostgreSQL experience
```

---

### Example 2: Detecting Duplicate

**Input:**
```yaml
data:
  content_type: pattern
  pattern: "Wrap external API errors with domain-specific error types"
  rationale: "Prevents leaking implementation details"
key: "CLAUDE.md#Patterns"
```

**Output:**
```yaml
stored: true  # Already present as pattern_err_001; nothing new written
key: "CLAUDE.md#Patterns"
timestamp: "2024-01-16T11:00:00Z"
persisted:
  content_type: pattern
  content_id: null
  destination: "CLAUDE.md"
  section: "Patterns"
write_operation:
  strategy: append
  bytes_written: 0
  lines_added: 0
  lines_modified: 0
verification:
  write_confirmed: false
  content_present: true
  structure_valid: true
metadata:
  source: "conversation:conv_def456"
  related_entries: ["pattern_err_001"]
  expiry: null
duplicates_found:
  - existing_id: "pattern_err_001"
    similarity: 0.95
    action_taken: skipped
confidence: 0.9
evidence_anchors:
  - {ref: "file:CLAUDE.md:134", kind: file}
assumptions:
  - "High similarity indicates same pattern"
  - "Skipping to avoid duplicate"
next_actions:
  - "Consider updating existing pattern if new rationale is better"
```

---

### Example 3: Merging with Existing Content

**Input:**
```yaml
data:
  content_type: fact
  fact: "API rate limit is 1000 requests per minute"
  source: "API documentation v2.3"
key: "docs/api-notes.md#Rate Limits"
```

Merge with the existing entry rather than appending a duplicate.

**Output:**
```yaml
stored: true
key: "docs/api-notes.md#Rate Limits"
timestamp: "2024-01-16T12:00:00Z"
persisted:
  content_type: fact
  content_id: "fact_rate_limit_20240116"
  destination: "docs/api-notes.md"
  section: "Rate Limits"
write_operation:
  strategy: merge
  bytes_written: 64
  lines_added: 1
  lines_modified: 1
verification:
  write_confirmed: true
  content_present: true
  structure_valid: true
metadata:
  source: "API documentation v2.3"
  related_entries: ["fact_rate_limit_20231201"]
  expiry: "2024-07-16"
duplicates_found:
  - existing_id: "fact_rate_limit_20231201"
    similarity: 0.8
    action_taken: merged
confidence: 1.0
evidence_anchors:
  - {ref: "memory:docs/api-notes.md#Rate Limits", kind: record}
  - {ref: "file:docs/api-notes.md:23", kind: file}
  - {ref: "source:API documentation v2.3", kind: x-doc}
assumptions:
  - "New rate limit supersedes previous"
  - "6-month expiry for review"
```

## Verification

- [ ] Content validated for appropriateness (no secrets/PII)
- [ ] Destination file exists or can be created
- [ ] Write operation completed without error
- [ ] Content present in destination after write
- [ ] File structure/formatting preserved

**Verification tools:** Read (to verify write), Edit (to perform write)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- NEVER persist credentials, API keys, or secrets. Code enforces it: the skill's PreToolUse command hook blocks an `Edit` whose content holds what looks like a credential (`F504 CONSTRAINT_VIOLATED:`, STANDARD v1.2 §6.7, §5.18.10). It matches credential shapes (key and token formats, PEM private keys, bearer tokens, a URL's userinfo password that is not a placeholder, an `Authorization` header's value mixing letters and digits) and assignments to a credential name (`password`, `token`, `api_key`, ...) whose value is quoted with no whitespace and 8 or more characters, or unquoted, 12 or more characters, mixing letters and digits; prose such as `token: rotate monthly` passes. The scan is `hooks/secret_scan.sh`, copied into the hook
- NEVER persist PII without explicit user consent
- Validate content does not contain executable code
- Preserve existing file structure and formatting
- Create backup before replacing existing content
- Stop if destination is a system or configuration file

## Composition Patterns

**Commonly follows:**
- `compare` - Persist the option a comparison selected for future reference
- `discover` - Save discovered patterns or relationships
- `recall` - Update existing memories with new context
- `generate` - Save a generated summary as durable knowledge

**Commonly precedes:**
- `recall` - Persisted content becomes available for recall
- `verify` - Verify persisted content is correct
- `audit` - Record what was persisted for compliance

**Anti-patterns:**
- Never persist without checking for duplicates
- Never persist contradictory information without flagging
- Never persist to files outside project scope without approval
- Avoid persisting ephemeral/temporary information

**Workflow references:**
- Pairs with `recall` for the remember/recall cycle
- Final step in many learning workflows
