---
name: recall
description: Retrieve prior decisions, rationale, and learned patterns from memory to apply consistently. Use when needing context from previous interactions, looking up past decisions, or ensuring consistency with prior reasoning.
argument-hint: "[query] [memory_scope session|project|global] [time_range]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Execute **recall** to retrieve relevant prior decisions, rationale, and patterns from memory to maintain consistency and learn from past interactions.

**Success criteria:**
- Relevant memories are retrieved based on query
- Prior decisions and their rationale are surfaced
- Consistency with past reasoning is maintained
- Retrieved information is grounded with timestamps and context

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `query` | Yes | string | What to recall: topic, decision type, or pattern name |
| `memory_scope` | No | enum | Where to search: `session` (current), `project` (CLAUDE.md), `global` (all). Default: `project` |
| `time_range` | No | object | Filter by time: `{ after: "2024-01-01", before: "2024-01-31" }` |
| `include_rationale` | No | boolean | Whether to include decision rationale. Default: true |
| `similarity_threshold` | No | number | Minimum relevance score (0.0-1.0). Default: 0.5 |

## Procedure

1) **Parse query intent**: Understand what is being recalled
   - Identify if query is about a decision, pattern, fact, or context
   - Extract key terms for memory search
   - Determine if exact match or semantic similarity needed

2) **Scope memory search**: Identify which memory stores to query
   - `session`: Current conversation context
   - `project`: CLAUDE.md, knowledge files, local docs
   - `global`: All accessible memory stores

3) **Search memory stores**: Query relevant sources
   - CLAUDE.md for project-level decisions and patterns
   - Session context for recent interactions
   - Knowledge files for domain-specific learnings
   - Use Grep for exact term matches, Read for context

4) **Rank by relevance**: Score and filter results
   - Relevance to query terms
   - Recency (more recent = higher weight unless historical needed)
   - Authority (explicit decisions > implicit patterns)
   - Filter below similarity_threshold

5) **Extract rationale**: For each recalled item, capture reasoning
   - Original decision context
   - Factors that influenced the decision
   - Constraints or assumptions at the time

6) **Check consistency**: Verify recalled items are internally consistent
   - Flag contradictions between recalled items
   - Note if context has changed since original decision

7) **Format output**: Structure results according to output contract

## Output Contract

Return a structured object:

```yaml
recalled:
  - id: string  # Unique identifier for this memory
    type: decision | pattern | fact | context
    content: string  # The recalled information
    rationale: string | null  # Why this decision was made
    source: string  # Where this was found (CLAUDE.md:42, session, etc.)
    timestamp: string | null  # When originally recorded
    relevance_score: number  # 0.0-1.0 match to query
    context:
      project: string | null
      conversation_id: string | null
      original_query: string | null
query_interpretation: string  # How the query was understood
search_scope:
  stores_searched: array[string]
  time_range_applied: object | null
total_matches: integer  # Total before filtering
returned_matches: integer  # After relevance filtering
consistency_check:
  consistent: boolean
  contradictions: array[object] | null
confidence: number  # 0.0-1.0 based on match quality
evidence_anchors: array[string]  # Sources for recalled items
assumptions: array[string]  # Assumptions about memory validity
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `recalled` | array[object] | List of retrieved memories |
| `recalled[].type` | enum | Kind of memory: decision, pattern, fact, or context |
| `recalled[].rationale` | string | Explanation for why decision was made |
| `recalled[].relevance_score` | number | How well this matches the query |
| `consistency_check` | object | Whether recalled items contradict each other |
| `confidence` | number | Overall confidence in recall quality |

## Examples

### Example 1: Recalling a Project Decision

**Input:**
```yaml
query: "error handling approach"
memory_scope: project
include_rationale: true
```

**Output:**
```yaml
recalled:
  - id: "decision_err_001"
    type: decision
    content: "Use Result<T, Error> pattern for all fallible operations; avoid exceptions"
    rationale: "Explicit error handling improves debuggability and makes failure paths visible in types"
    source: "CLAUDE.md:127"
    timestamp: "2024-01-10T09:15:00Z"
    relevance_score: 0.95
    context:
      project: "api-service"
      conversation_id: "conv_abc123"
      original_query: "How should we handle errors in this codebase?"
  - id: "pattern_err_001"
    type: pattern
    content: "Wrap external API errors with domain-specific error types before propagating"
    rationale: "Prevents leaking implementation details; enables consistent error messages"
    source: "CLAUDE.md:134"
    timestamp: "2024-01-10T09:20:00Z"
    relevance_score: 0.88
    context:
      project: "api-service"
      conversation_id: "conv_abc123"
      original_query: null
query_interpretation: "Looking for decisions and patterns related to error handling in the codebase"
search_scope:
  stores_searched: ["CLAUDE.md", "docs/architecture.md"]
  time_range_applied: null
total_matches: 5
returned_matches: 2
consistency_check:
  consistent: true
  contradictions: null
confidence: 0.92
evidence_anchors:
  - "CLAUDE.md:127"
  - "CLAUDE.md:134"
assumptions:
  - "CLAUDE.md reflects current project decisions"
  - "No conflicting decisions recorded elsewhere"
```

**Evidence pattern:** Each recalled item traced to specific file:line; rationale extracted from surrounding context.

---

### Example 2: Recalling Session Context

**Input:**
```yaml
query: "user's preferred output format"
memory_scope: session
time_range:
  after: "2024-01-16T00:00:00Z"
```

**Output:**
```yaml
recalled:
  - id: "ctx_fmt_001"
    type: context
    content: "User prefers YAML output over JSON for configuration files"
    rationale: "User stated 'I find YAML more readable' in earlier message"
    source: "session:message_42"
    timestamp: "2024-01-16T10:30:00Z"
    relevance_score: 0.97
    context:
      project: null
      conversation_id: "current_session"
      original_query: "Can you output this as YAML instead?"
query_interpretation: "Looking for user preferences about output formatting from current session"
search_scope:
  stores_searched: ["session"]
  time_range_applied:
    after: "2024-01-16T00:00:00Z"
    before: null
total_matches: 1
returned_matches: 1
consistency_check:
  consistent: true
  contradictions: null
confidence: 0.97
evidence_anchors:
  - "session:message_42"
assumptions:
  - "User preference still valid within session"
  - "No subsequent preference change"
```

---

### Example 3: Detecting Contradictory Memories

**Input:**
```yaml
query: "database choice"
memory_scope: project
include_rationale: true
```

**Output:**
```yaml
recalled:
  - id: "decision_db_001"
    type: decision
    content: "Use PostgreSQL for all persistent storage"
    rationale: "Strong ACID guarantees, mature ecosystem"
    source: "CLAUDE.md:45"
    timestamp: "2024-01-05T14:00:00Z"
    relevance_score: 0.94
    context:
      project: "backend-service"
      conversation_id: "conv_xyz789"
      original_query: "Which database should we use?"
  - id: "decision_db_002"
    type: decision
    content: "Use SQLite for local development and testing"
    rationale: "Faster setup, no external dependencies"
    source: "docs/dev-setup.md:23"
    timestamp: "2024-01-12T11:30:00Z"
    relevance_score: 0.85
    context:
      project: "backend-service"
      conversation_id: "conv_def456"
      original_query: "How to speed up local dev?"
query_interpretation: "Looking for decisions about database selection"
search_scope:
  stores_searched: ["CLAUDE.md", "docs/"]
  time_range_applied: null
total_matches: 2
returned_matches: 2
consistency_check:
  consistent: false
  contradictions:
    - items: ["decision_db_001", "decision_db_002"]
      attribute: "database"
      resolution_hint: "Different contexts: production vs development"
confidence: 0.75
evidence_anchors:
  - "CLAUDE.md:45"
  - "docs/dev-setup.md:23"
assumptions:
  - "Both decisions are currently valid"
  - "Context difference (prod vs dev) resolves contradiction"
next_actions:
  - "Clarify if query refers to production or development"
  - "Document environment-specific database strategy"
```

## Verification

- [ ] Query intent correctly interpreted
- [ ] All relevant memory stores searched within scope
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
- Do not fabricate memories; return empty if nothing found

## Composition Patterns

**Commonly follows:**
- `receive` - After receiving a request, recall relevant context
- `search` - Search results may trigger memory lookup for similar past queries

**Commonly precedes:**
- `decide` - Recalled decisions inform new decision-making
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
