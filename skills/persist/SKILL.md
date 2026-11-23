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
    - matcher: "Edit|Write|MultiEdit|NotebookEdit"
      hooks:
        - type: prompt
          prompt: |
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            PERSIST DATA VALIDATION CHECK

            The tool call follows this prompt as JSON; the target file is
            tool_input.file_path (tool_input.notebook_path for NotebookEdit) and the
            content to write is tool_input.new_string (Edit), tool_input.content
            (Write), each tool_input.edits[].new_string (MultiEdit) or
            tool_input.new_source (NotebookEdit).

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
          timeout: 30
          onFailure: block
          command: |
            # Code-decided checks (STANDARD 1.2.0 §5.18.10): the target file is not
            # a system or credential file, and the content holds no credential
            # (§6.7). Claude Code passes the tool call (Edit, Write, MultiEdit or
            # NotebookEdit) as JSON on stdin, read once here; exit 2 blocks the call and the
            # reason on stderr is shown to Claude. A call that cannot be read is
            # blocked.
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            TARGET="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            case "$TARGET" in
              "~/"*) TARGET="${HOME}/${TARGET#??}" ;;
            esac
            # The file the write reaches: symbolic links followed. The deepest
            # directory of the path that exists, as `cd -P` resolves it, then the
            # rest of the path; a target that is itself a link is followed (at
            # most 8 links). Fails on a link it cannot read.
            resolve() {
              R_PATH="$1"
              R_LINKS=0
              while :; do
                case "$R_PATH" in /*) ;; *) R_PATH="$(pwd -P)/$R_PATH" ;; esac
                R_DIR="${R_PATH%/*}"
                R_REST="${R_PATH##*/}"
                while [ -n "$R_DIR" ] && [ ! -d "$R_DIR" ]; do
                  R_REST="${R_DIR##*/}/$R_REST"
                  R_DIR="${R_DIR%/*}"
                done
                R_DIR="$(cd -P "${R_DIR:-/}" 2>/dev/null && pwd -P)" || return 1
                R_PATH="${R_DIR%/}/$R_REST"
                [ -L "$R_PATH" ] || break
                R_LINKS=$((R_LINKS + 1))
                [ "$R_LINKS" -le 8 ] || return 1
                R_TO="$(readlink "$R_PATH" 2>/dev/null)" || return 1
                case "$R_TO" in /*) R_PATH="$R_TO" ;; *) R_PATH="${R_PATH%/*}/$R_TO" ;; esac
              done
              printf '%s\n' "$R_PATH"
            }
            REAL="$TARGET"
            if [ -n "$TARGET" ]; then
              REAL="$(resolve "$TARGET")" || { echo "F504 CONSTRAINT_VIOLATED: Cannot persist through a symbolic link that cannot be followed" >&2; exit 2; }
            fi
            HOME_REAL="$(cd -P "${HOME:-/}" 2>/dev/null && pwd -P)" || HOME_REAL="${HOME:-}"
            # Each check reads the path as written and the file it reaches
            for P in "$TARGET" "$REAL"; do
              # A path with '//', '.' or '..' segments is not compared as written
              # (/tmp/../etc/passwd is /etc/passwd), so it is blocked
              case "$P" in
                *//*|*/./*|*/.|*/../*|*/..|../*|..)
                  echo "F504 CONSTRAINT_VIOLATED: Cannot persist to a path with '//', '.' or '..' segments; give the normalised path" >&2
                  exit 2
                  ;;
              esac
              # Block writes to system directories (/private/etc is macOS's /etc),
              # to credential directories under the home directory, and to Claude
              # Code's own settings there
              case "$P" in
                /etc/*|/private/etc/*|/usr/*|/bin/*|/sbin/*|"${HOME}"/.ssh/*|"${HOME}"/.aws/*|"${HOME}"/.config/*|"${HOME}"/.claude/*|"${HOME_REAL}"/.ssh/*|"${HOME_REAL}"/.aws/*|"${HOME_REAL}"/.config/*|"${HOME_REAL}"/.claude/*)
                  echo "F504 CONSTRAINT_VIOLATED: Cannot persist to system or credential directories" >&2
                  exit 2
                  ;;
              esac
              # Block writes to credential files
              if printf '%s\n' "$P" | grep -qiE "(\.env|credentials|secrets|password|\.pem|\.key)$"; then
                echo "F504 CONSTRAINT_VIOLATED: Cannot persist to credential files" >&2
                exit 2
              fi
            done
            # What the call stores (§5.18.10, §6.7): the text it carries (an Edit's
            # new_string, a Write's content, each new_string of a MultiEdit's edits,
            # a NotebookEdit's new_source), and the lines of the file as it will be
            # after the call that the file does not hold now (the edits applied in
            # order, replace_all honoured, curly quotes read as straight ones when an
            # old_string is found only so), so a credential whose key, or whose other
            # half, is already in the file, or that two edits or calls build, is read
            # whole; and each again with the escapes a reader resolves (\uXXXX,
            # \UXXXXXXXX, \xXX, \/ and \") decoded. The file is read only when it is
            # a regular file of at most 8 MB; any other existing target is refused.
            BEFORE=/dev/null
            if [ -n "$REAL" ] && { [ -e "$REAL" ] || [ -L "$REAL" ]; }; then
              [ -f "$REAL" ] || { echo "F504 CONSTRAINT_VIOLATED: Cannot persist to something that is not a regular file" >&2; exit 2; }
              SIZE="$(wc -c < "$REAL" 2>/dev/null | tr -d ' ')" || SIZE=""
              case "$SIZE" in ''|*[!0-9]*) echo "R407 SAFETY_CHECK_FAILED: cannot read the file the call writes" >&2; exit 2 ;; esac
              [ "$SIZE" -le 8388608 ] || { echo "F504 CONSTRAINT_VIOLATED: the file is over 8 MB, more than this check reads; persist to a smaller file" >&2; exit 2; }
              BEFORE="$REAL"
            fi
            CONTENT="$(printf '%s' "$INPUT" | jq -r --rawfile before "$BEFORE" '
              def hexval: reduce explode[] as $c (0; . * 16 + (if $c >= 97 then $c - 87 elif $c >= 65 then $c - 55 else $c - 48 end));
              def ishex: explode | all(. >= 48 and . <= 57 or . >= 65 and . <= 70 or . >= 97 and . <= 102);
              def unescape($mark; $n):
                if index($mark) == null then . else
                  split($mark) as $p
                  | $p[0] + ([$p[1:][] | .[:$n] as $h
                      | (if ($h | length) == $n and ($h | ishex) then $h | hexval else -1 end) as $v
                      | if $v >= 32 and ($v < 55296 or ($v > 57343 and $v < 1114112))
                        then ([$v] | implode) + .[$n:] else $mark + . end] | join(""))
                end;
              def decoded: unescape("\\u"; 4) | unescape("\\U"; 8) | unescape("\\x"; 2)
                | split("\\/") | join("/") | split("\\\"") | join("\"");
              def straight: split("\u2018") | join("\u0027") | split("\u2019") | join("\u0027")
                | split("\u201c") | join("\"") | split("\u201d") | join("\"");
              def replaced($o; $n; $all):
                split($o) as $p
                | if ($p | length) < 2 then null
                  elif $all then $p | join($n)
                  else $p[0] + $n + ($p[1:] | join($o)) end;
              def apply($e):
                ($e.old_string) as $o | ($e.new_string) as $n
                | if ($o | type) != "string" or ($n | type) != "string" then .
                  elif $o == "" then $n + .
                  else replaced($o; $n; $e.replace_all == true)
                    // (straight | replaced($o | straight; $n; $e.replace_all == true))
                    // . end;
              def counts: reduce (split("\n")[]) as $l ({}; .[$l] += 1);
              def added($b; $a):
                ($b | counts) as $had
                | $a | counts | to_entries | map(select(.value > ($had[.key] // 0)) | .key) | join("\n");
              .tool_input as $t
              | ([$t.new_string, $t.content, $t.new_source,
                  (($t.edits | if type == "array" then .[] else empty end) | objects | .new_string)]
                 | map(select(type == "string")) | join("\n")) as $carried
              | (if ($t.content | type) == "string" then $t.content
                 elif ($t.edits | type) == "array" then reduce ($t.edits[] | objects) as $e ($before; apply($e))
                 elif ($t.old_string | type) == "string" then $before | apply($t)
                 else $before end) as $after
              | ($carried + "\n" + added($before | straight; $after | straight)) as $text
              | ($text + "\n" + ($text | decoded)) | split("\u0000") | join(" ")
            ' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call or the file it writes (jq is required)" >&2; exit 2; }
            # BEGIN secret-scan (source: hooks/secret_scan.sh; tests/test_skill_hooks.py keeps every copy equal)
            # secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7).
            SECRET_ERE='-----BEGIN [A-Z ]*PRIVATE KEY-----|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
            SECRET_KEY='(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)'
            # A quote, or an escaped one (\" in JSON text inside a JSON string)
            SECRET_Q="\\\\*[\"']"
            # A command's option named for a credential (--password, --api-key), and a user option (curl -u user:password)
            SECRET_OPT="(^|[^A-Za-z0-9_-])--([A-Za-z0-9]+[_-])*$SECRET_KEY"
            SECRET_SEP="([[:space:]]+($SECRET_Q)?|=($SECRET_Q)?|($SECRET_Q)?[[:space:]]*,[[:space:]]*$SECRET_Q)"
            SECRET_USER="(^|[^A-Za-z0-9_-])(-[uU]$SECRET_SEP?|--(proxy-)?user$SECRET_SEP)[^[:space:]:\"'\\\\]*:"
            secret_in() {
              printf '%s' "$1" | grep -Eq -- "$SECRET_ERE" && return 0
              # A quoted value with no whitespace, 8 or more characters, assigned or given to a credential option
              printf '%s' "$1" | grep -Eiq -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[^[:space:]\"']{8,}[\"']|$SECRET_OPT([[:space:]]+|($SECRET_Q)?[[:space:]]*,[[:space:]]*)$SECRET_Q[^-[:space:]\"'][^[:space:]\"']{7,}[\"']" && return 0
              # The password of a URL's userinfo, unless it is a placeholder
              printf '%s' "$1" | grep -Eo -- '[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/:@]*:[^[:space:]/@]+@' |
                sed -E 's#^[^/]*//[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
              # An Authorization header's value, 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
                sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # A header's or credential's value given as a name/value pair, or a tuple of exactly two, in text: 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
                sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*\\\\*[\"']//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # A user option's password (curl -u user:password), 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eo -- "$SECRET_USER[^[:space:]\"'\\\\]{8,}" |
                sed -E 's/^[^:]*://' | grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # An unquoted value of 12 or more characters with letters and digits, assigned or given to a credential option
              printf '%s' "$1" | grep -Eio -- "$SECRET_OPT[[:space:]]+[^-[:space:]\"'][^[:space:]\"']{11,}" |
                sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              printf '%s' "$1" | grep -Eio -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
                sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]'
            }
            # END secret-scan
            # Memory is read back as fact, so a credential is refused, not redacted
            if secret_in "$CONTENT"; then
              echo "F504 CONSTRAINT_VIOLATED: the content holds what looks like a credential; persist where the secret is kept, not the secret (STANDARD 1.2.0 §6.7)" >&2
              exit 2
            fi
            exit 0
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
| `data` | Yes | any | Data to store; it round-trips as I-JSON, and data holding a secret is refused (STANDARD v1.2 §4.5, §6.7) |
| `key` | No | string | Storage key; without one the host chooses it and returns it as `key` |
| `ttl` | No | string | Time to live, a duration (§5.10.1) longer than zero, e.g. `30d` or `PT12H`; the entry ends `ttl` after `stored_at` |
| `scope` | No | string | Who can read the entry and how long it lasts: `run`, `session`, `user`, `project`, `global` or an `x-` name (§4.5); the host's default (`session`) when absent |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Validate content**: Ensure content is appropriate for persistence
   - Check content is non-empty and meaningful
   - Verify content type classification
   - Ensure no sensitive data (credentials, PII) is being persisted: data that holds a secret is refused, not redacted, since memory is read back as fact (STANDARD v1.2 §6.7). Persist where the secret is kept (an environment variable's name, a vault path), not the secret
   - Validate content structure if object

2) **Determine scope and destination** (STANDARD v1.2 §4.5): the entry `{key, scope, data, stored_at, expires_at}` goes to the scope's store
   - `session` (the default): this conversation
   - `project`: a file the project keeps (`CLAUDE.md` for decisions and patterns, a specific file for domain knowledge)
   - `user`, `global`, `run`: the store the host provides for them
   - A scope this host does not provide: store nothing, and answer `unsupported_scope`; a `ttl` that is not a duration longer than zero: store nothing, and answer `unsupported_ttl`
   - Data that holds a secret: store nothing, and answer `secret_in_data`

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

6) **Apply the write**: A persist to a key that holds an entry replaces it
   - To combine with what is there, `recall` it first and persist the combined data
   - Within a file, `append` a new section, or `replace` the entry under the key

7) **Write to destination**: Execute the write operation
   - Use Edit tool for file modifications
   - Preserve file formatting and structure
   - Add section headers if needed

8) **Verify write** (read-after-write, §4.5): read the key back in the scope and compare
   - The data read back equals the data stored; then report `stored: true` with `stored_at` (and `expires_at` for a `ttl`)
   - `stored: false` means nothing was written or replaced: the step completes, and a workflow that depends on the write checks `stored`

## Output Contract

Return a structured object:

```yaml
stored: boolean  # true: a recall of the key in the scope returns the data until the entry ends; false: nothing was written (§4.5)
key: string  # Storage key (destination and section, e.g. "CLAUDE.md#Patterns")
scope: string  # The scope used (§4.5)
stored_at: string  # ISO 8601 date-time the entry was stored
expires_at: string | null  # When the entry ends, for an entry with a ttl
timestamp: string  # Deprecated: the same instant as stored_at
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
| `stored` | boolean | True: a later `recall` of the key in the scope returns the data until the entry ends (read-after-write, §4.5); false: nothing was written or replaced |
| `key` | string | Storage key the data lives under (destination and section) |
| `scope` | string | The scope used; a step of a 1.2 workflow that binds `scope` fails unless this echoes it (R402, `unsupported_scope`) |
| `stored_at` | string | ISO 8601 date-time the entry was stored |
| `expires_at` | string | When the entry ends, for an entry with a `ttl`; from then on a `recall` does not find it |
| `timestamp` | string | Deprecated: the same instant as `stored_at`; read `stored_at` (a reference to it is W603) |
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
scope: project
```

**Output:**
```yaml
stored: true
key: "CLAUDE.md#Architecture Decisions"
scope: project
stored_at: "2024-01-16T10:00:00Z"
expires_at: null
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
- NEVER persist credentials, API keys, or secrets. Code enforces it: the skill's PreToolUse command hook blocks an `Edit`, `Write`, `MultiEdit` or `NotebookEdit` whose content holds what looks like a credential (`F504 CONSTRAINT_VIOLATED:`, STANDARD v1.2 §6.7, §5.18.10): the text it carries, and the lines the file will hold after it that it does not hold now (so a key already in the file, or a token two edits build, counts), each also with its `\uXXXX`, `\xXX`, `\/` and `\"` escapes decoded. It matches credential shapes (key and token formats, PEM private keys, bearer tokens, a URL's userinfo password that is not a placeholder, an `Authorization` header's value mixing letters and digits, also given as a name/value pair or a two-element tuple, as a HAR or code writes headers, and a command's user option's password, `curl -u user:<password>`) and assignments to a credential name (`password`, `passphrase`, `token`, `secret_key`, `api_key`, ...), or values given to an option named for one (`--password <value>`), whose value is quoted with no whitespace and 8 or more characters, or unquoted, 12 or more characters, mixing letters and digits, quotes escaped or not; prose such as `token: rotate monthly` passes. The scan is `hooks/secret_scan.sh`, copied into the hook
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
