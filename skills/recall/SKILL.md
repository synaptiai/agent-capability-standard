---
name: recall
description: Retrieve prior decisions, rationale, and learned patterns from memory to apply consistently. Use when needing context from previous interactions, looking up past decisions, or ensuring consistency with prior reasoning.
argument-hint: "[key] [default]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Execute **recall** to read back what `persist` stored under a key in a memory scope (STANDARD v1.2 §4.5), and, beside it, the prior decisions, rationale and patterns related to it, to keep consistent with past reasoning.

**Success criteria:**
- The entry stored under the key in the scope is returned exactly, when a live one exists
- Related memories are surfaced separately, grounded with their sources and times
- Nothing is reported found that was not stored under the key

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `key` | Yes | string | Storage key, compared by code point |
| `default` | No | any | Default if not found |
| `scope` | No | string | The scope to read, as for `persist`: `run`, `session`, `user`, `project`, `global` or an `x-` name; the host's default (`session`) when absent (§4.5) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Resolve the scope** (§4.5): the store of the scope asked for
   - `session` (the default): this conversation
   - `user`: what the host keeps for this principal across sessions
   - `project`: CLAUDE.md, knowledge files, the project's memory file
   - `global`: every store the host serves
   - `run`: the run the host started and every run nested in it
   - A scope this host does not provide: look nothing up, and answer `unsupported_scope`

2) **Look up the exact key first**: an entry stored under exactly `key` in the scope
   - An entry whose `expires_at` has passed has ended: it is not found
   - `found` is true only for a live entry with exactly this key; `data` is then its data, unchanged, with its `stored_at` (and `expires_at`)

3) **Search for related memories** (optional): topical matches for the key's terms
   - CLAUDE.md for project-level decisions and patterns; session context for recent interactions; knowledge files for domain learnings
   - Use Grep for term matches, Read for context
   - Rank by relevance, recency and authority (explicit decisions over implicit patterns)
   - They go in `x-related`, never in `data`: with no exact entry, `found` is false and `data` is the `default` (or null)

4) **Extract rationale and check consistency** for what was found
   - Original decision context, the factors and constraints of the time
   - Flag contradictions between items, and context that changed since

5) **Format output**: Structure results according to output contract

## Output Contract

Return a structured object:

```yaml
found: boolean  # true only when a live entry has exactly the key in the scope (§4.5)
data: any  # that entry's data, unchanged; otherwise the `default` input (or null)
scope: string  # The scope used (§4.5)
stored_at: string | null  # When the entry was stored
expires_at: string | null  # When the entry ends, for an entry with a ttl
x-related:  # Topical matches beside the exact key, best first (not the entry)
  - id: string
    type: decision | pattern | fact | context
    content: string
    rationale: string | null
    source: string  # Where this was found (CLAUDE.md:42, session, etc.)
    timestamp: string | null
    relevance_score: number  # 0.0-1.0 match to the key's terms
consistency_check:
  consistent: boolean
  contradictions: array[object] | null
confidence: number  # probability that the returned memories are correct for the query (§4.1.1)
evidence_anchors: array[EvidenceAnchor]  # Sources for recalled items; each {ref, kind} (STANDARD v1.2 §6.5)
assumptions: array[string]  # Assumptions about memory validity
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `found` | boolean | Whether a live entry has exactly the key in the scope |
| `data` | any | The entry's data, or the `default` input when none is found |
| `scope` | string | The scope used; a step of a 1.2 workflow that binds `scope` fails unless this echoes it (R402, `unsupported_scope`) |
| `stored_at` | string | ISO 8601 date-time the entry was stored |
| `expires_at` | string | When the entry ends, for an entry with a `ttl` |
| `x-related` | array | Related memories, best match first; never the entry itself |
| `consistency_check` | object | Whether recalled items contradict each other |
| `confidence` | number | Probability, 0.0-1.0, that the returned memories are correct for the query (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Sources for recalled items |
| `assumptions` | array | Assumptions about memory validity |

## Examples

### Example 1: Recalling a Stored Decision by Its Key

**Input:**
```yaml
key: "decision:error-handling"
scope: project
```

**Output:**
```yaml
found: true
data:
  decision: "Use Result<T, Error> for all fallible operations; avoid exceptions"
  rationale: "Explicit error handling makes failure paths visible in types"
scope: project
stored_at: "2024-01-10T09:15:00Z"
expires_at: null
x-related:
  - id: "pattern_err_001"
    type: pattern
    content: "Wrap external API errors with domain-specific error types before propagating"
    rationale: "Prevents leaking implementation details"
    source: "CLAUDE.md:134"
    timestamp: "2024-01-10T09:20:00Z"
    relevance_score: 0.88
consistency_check:
  consistent: true
  contradictions: null
confidence: 0.95
evidence_anchors:
  - {ref: "memory:project:decision:error-handling", kind: record}
  - {ref: "file:CLAUDE.md:134", kind: file}
assumptions:
  - "CLAUDE.md reflects current project decisions"
```

**Evidence pattern:** the entry's own record, and each related item traced to a file and line.

---

### Example 2: No Entry under the Key, Related Memories Found

**Input:**
```yaml
key: "database choice"
default: null
```

**Output:**
```yaml
found: false
data: null
scope: session
stored_at: null
expires_at: null
x-related:
  - id: "decision_db_001"
    type: decision
    content: "Use PostgreSQL for all persistent storage"
    rationale: "Strong ACID guarantees, mature ecosystem"
    source: "CLAUDE.md:45"
    timestamp: "2024-01-05T14:00:00Z"
    relevance_score: 0.94
  - id: "decision_db_002"
    type: decision
    content: "Use SQLite for local development and testing"
    rationale: "Faster setup, no external dependencies"
    source: "docs/dev-setup.md:23"
    timestamp: "2024-01-12T11:30:00Z"
    relevance_score: 0.85
consistency_check:
  consistent: false
  contradictions:
    - items: ["decision_db_001", "decision_db_002"]
      attribute: "database"
      resolution_hint: "Different contexts: production vs development"
confidence: 0.75
evidence_anchors:
  - {ref: "file:CLAUDE.md:45", kind: file}
  - {ref: "file:docs/dev-setup.md:23", kind: file}
assumptions:
  - "Context difference (prod vs dev) resolves the contradiction"
next_actions:
  - "Clarify if the key refers to production or development"
```

## Verification

- [ ] The exact key was looked up first, in the scope asked for
- [ ] `found` is true only for a live entry with exactly the key
- [ ] relevance_score reflects actual match quality
- [ ] Contradictions detected and flagged
- [ ] evidence_anchors provide traceable source references

**Verification tools:** Read (to validate memory file contents), Grep (to search across memory stores)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not recall or expose credentials, secrets, or PII from memory
- Respect memory scope boundaries; do not access global when session requested
- Flag stale memories (>30 days) with lower confidence
- Do not fabricate memories; if no live entry has the key return `found: false` with `data` set to the `default` input (or null), and topical matches only in `x-related`

## Composition Patterns

**Commonly follows:**
- `receive` - After receiving a request, recall relevant context
- `search` - Search results may trigger memory lookup for similar past queries

**Commonly precedes:**
- `compare` - Recalled decisions inform new comparisons and choices
- `plan` - Past patterns guide new plan creation
- `explain` - Recalled rationale used to explain current approach
- `persist` - New decisions should be consistent with recalled ones

**Anti-patterns:**
- Never override recalled decisions without explicit user request
- Never recall without checking for contradictions
- Avoid recalling from stale sources without flagging age

**Workflow references:**
- Memory recall is implicit in many workflows as context loading
- Pairs with `persist` for the remember/recall cycle
