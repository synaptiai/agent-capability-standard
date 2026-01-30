---
name: explain
description: Produce clear reasoning with assumptions, causal chains, and evidence. Use when clarifying decisions, teaching concepts, justifying recommendations, or documenting rationale.
argument-hint: "[topic] [audience_level] [format]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Generate a clear, structured explanation of a topic, decision, or concept tailored to the audience level. Include explicit assumptions, causal reasoning, and supporting evidence.

**Success criteria:**
- Explanation is clear and understandable by target audience
- Assumptions are explicitly stated
- Causal chain shows logical progression
- Evidence supports key claims
- No unnecessary jargon or fluff
**Compatible schemas:**
- `schemas/output_schema.yaml`


## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `topic` | Yes | string or object | What to explain (concept, decision, code, etc.) |
| `audience_level` | No | string | beginner, intermediate, expert (default: intermediate) |
| `format` | No | string | prose, bullets, structured, diagram (default: structured) |
| `focus` | No | string | Specific aspect to emphasize |
| `max_length` | No | string | Length constraint (brief, standard, detailed) |

## Procedure

1) **Analyze the topic**: Understand what needs explaining
   - Identify the core concept or decision
   - Note the complexity level
   - Determine what background is needed
   - Identify potential confusion points

2) **Assess audience**: Calibrate explanation depth
   - Beginner: Define all terms, use analogies
   - Intermediate: Assume basic knowledge, focus on key points
   - Expert: Technical depth, skip fundamentals

3) **Extract key concepts**: Identify essential elements
   - Core idea or decision
   - Supporting concepts
   - Technical terms that need definition
   - Related concepts for context

4) **Build causal chain**: Show logical progression
   - Starting conditions or premises
   - Each step in reasoning
   - How each step leads to the next
   - Final conclusion

5) **State assumptions**: Make implicit knowledge explicit
   - What must be true for explanation to hold
   - Background knowledge assumed
   - Simplifications made
   - Edge cases not covered

6) **Add analogies**: Create relatable comparisons
   - Match complexity to audience
   - Use familiar domains
   - Highlight key similarities
   - Note where analogy breaks down

7) **Ground with evidence**: Support claims
   - Reference code, documentation, data
   - Link to authoritative sources
   - Provide examples

## Output Contract

Return a structured object:

```yaml
explanation:
  summary: string  # 1-2 sentence overview
  detailed: string  # Full explanation at appropriate depth
  level: beginner | intermediate | expert
  analogies: array[string]  # Helpful comparisons
key_concepts:
  - term: string  # Concept or term
    definition: string  # Clear definition
    relevance: string  # Why it matters here
causal_chain:
  - step: integer
    claim: string  # What is being claimed
    reasoning: string  # Why this follows
    evidence: string | null  # Supporting evidence
assumptions:
  - assumption: string  # What is assumed
    impact: string  # What happens if false
    testable: boolean  # Can this be verified
caveats:
  - caveat: string  # Limitation or exception
    severity: minor | moderate | significant
confidence: 0..1
evidence_anchors: ["file:line", "url", "doc:section"]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `explanation` | object | Main explanation content |
| `key_concepts` | array | Terms and definitions |
| `causal_chain` | array | Logical progression of reasoning |
| `assumptions` | array | Explicit assumptions with impact |
| `caveats` | array | Limitations and exceptions |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array | Supporting references |

## Examples

### Example 1: Explaining a Technical Decision

**Input:**
```yaml
topic: "Why we chose PostgreSQL over MongoDB for the user service"
audience_level: intermediate
format: structured
```

**Output:**
```yaml
explanation:
  summary: "PostgreSQL was selected for the user service due to strong ACID compliance, relational data patterns, and team expertise."
  detailed: |
    The user service manages core user data including profiles, authentication,
    and relationships between users. After evaluating PostgreSQL and MongoDB,
    we chose PostgreSQL for three primary reasons:

    1. **ACID Compliance**: User data requires strong consistency. When a user
       updates their email, all subsequent reads must see the new value. PostgreSQL's
       ACID transactions guarantee this; MongoDB's eventual consistency model would
       require additional application logic.

    2. **Relational Data Model**: User data is inherently relational - users have
       roles, roles have permissions, users have relationships with other users.
       PostgreSQL's foreign keys and JOINs model this naturally. MongoDB would
       require denormalization or multiple queries.

    3. **Team Expertise**: Our team has 5+ years of PostgreSQL experience.
       Estimated ramp-up time for MongoDB was 3 months, adding risk to the timeline.
  level: intermediate
  analogies:
    - "ACID transactions are like bank transfers - the money leaves one account and arrives in another atomically, never losing money in transit"
    - "Relational data is like a spreadsheet with linked tabs - change a value in one tab and lookups from other tabs reflect it automatically"
key_concepts:
  - term: "ACID"
    definition: "Atomicity, Consistency, Isolation, Durability - properties ensuring reliable database transactions"
    relevance: "Critical for user data where partial updates could corrupt state"
  - term: "Eventual Consistency"
    definition: "Data will become consistent across replicas eventually, but reads may see stale data temporarily"
    relevance: "Acceptable for analytics, problematic for auth data"
  - term: "Denormalization"
    definition: "Duplicating data across documents to avoid JOINs"
    relevance: "MongoDB pattern that increases storage and update complexity"
causal_chain:
  - step: 1
    claim: "User data requires strong consistency"
    reasoning: "Authentication and authorization decisions cannot tolerate stale data"
    evidence: "Security requirements doc section 2.3"
  - step: 2
    claim: "PostgreSQL provides stronger consistency than MongoDB"
    reasoning: "ACID transactions vs eventual consistency model"
    evidence: "PostgreSQL docs: transaction isolation; MongoDB docs: read concern"
  - step: 3
    claim: "User data is relational in nature"
    reasoning: "Users have roles, roles have permissions, users have social connections"
    evidence: "Data model diagram shows 12 foreign key relationships"
  - step: 4
    claim: "Team can deliver faster with PostgreSQL"
    reasoning: "Existing expertise reduces development and debugging time"
    evidence: "Team skills inventory shows 5/7 developers proficient in PostgreSQL"
  - step: 5
    claim: "PostgreSQL is the better choice for this use case"
    reasoning: "Meets consistency requirements, fits data model, leverages team skills"
    evidence: null
assumptions:
  - assumption: "User data consistency requirements will not relax"
    impact: "If relaxed, MongoDB's flexibility might become more attractive"
    testable: true
  - assumption: "Team composition remains stable"
    impact: "New hires might have MongoDB expertise, changing the calculus"
    testable: true
caveats:
  - caveat: "MongoDB would be better for highly variable schema data"
    severity: minor
  - caveat: "At massive scale, PostgreSQL horizontal scaling is harder than MongoDB"
    severity: moderate
confidence: 0.9
evidence_anchors:
  - "doc:security-requirements:section-2.3"
  - "doc:data-model-diagram"
  - "doc:team-skills-inventory"
```

**Evidence pattern:** Decision traced through causal chain with evidence at each step.

---

### Example 2: Explaining a Concept to Beginners

**Input:**
```yaml
topic: "What is a database index and why does it matter?"
audience_level: beginner
format: structured
```

**Output:**
```yaml
explanation:
  summary: "A database index is like a book's index - it helps find data quickly without reading everything."
  detailed: |
    Imagine you have a phonebook with millions of entries. To find "John Smith", you
    could start at page 1 and read every entry until you find him. That would take
    forever! Instead, you use the alphabetical ordering - jump to "S", then find
    "Smith", then find "John Smith". Much faster!

    A database index works the same way. Without an index, the database reads every
    row to find what you want (called a "table scan"). With an index on the right
    column, it can jump directly to matching rows.

    **When to use indexes:**
    - Columns you search frequently (WHERE clauses)
    - Columns you sort by (ORDER BY)
    - Columns used to join tables

    **The trade-off:**
    Indexes speed up reading but slow down writing. Each time you add or update data,
    all relevant indexes must also be updated. Like maintaining multiple indexes for
    a book - more work for the author, but readers find things faster.
  level: beginner
  analogies:
    - "A database index is like a book's index - it tells you exactly which page to turn to"
    - "Without an index, searching is like reading every page of a book to find one word"
    - "Creating too many indexes is like having a 100-page index for a 50-page book - the overhead outweighs the benefit"
key_concepts:
  - term: "Table Scan"
    definition: "Reading every row in a table to find matching data"
    relevance: "What happens without an index - slow for large tables"
  - term: "Index"
    definition: "A data structure that maps column values to row locations"
    relevance: "Enables fast lookups without reading all data"
  - term: "Trade-off"
    definition: "Gaining one thing by giving up another"
    relevance: "Faster reads but slower writes"
causal_chain:
  - step: 1
    claim: "Tables can have millions of rows"
    reasoning: "Real applications accumulate data over time"
    evidence: null
  - step: 2
    claim: "Finding specific rows requires checking each row without an index"
    reasoning: "Database has no other way to know which rows match"
    evidence: null
  - step: 3
    claim: "Indexes provide a shortcut to relevant rows"
    reasoning: "Like alphabetical ordering in a phonebook"
    evidence: null
  - step: 4
    claim: "Queries using indexed columns are much faster"
    reasoning: "Jump directly to matching rows instead of scanning all"
    evidence: "Query on indexed column: 5ms vs non-indexed: 2000ms"
assumptions:
  - assumption: "Reader understands what a database is"
    impact: "May need to explain databases first"
    testable: true
  - assumption: "Book/phonebook analogy is familiar"
    impact: "Digital natives may not relate to phonebooks"
    testable: true
caveats:
  - caveat: "Indexes are not always the answer - small tables may not benefit"
    severity: minor
  - caveat: "Choosing wrong columns to index wastes resources"
    severity: moderate
confidence: 0.95
evidence_anchors:
  - "example:query-timing-comparison"
```

## Verification

- [ ] Explanation matches audience level
- [ ] All key concepts are defined
- [ ] Causal chain is logically valid
- [ ] Assumptions are explicit
- [ ] Evidence supports claims

**Verification tools:** Read (for reference materials)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never invent facts - acknowledge uncertainty
- Clearly mark opinions vs facts
- Acknowledge when topic is outside expertise
- Do not oversimplify to the point of inaccuracy
- Flag where explanation is incomplete

## Composition Patterns

**Commonly follows:**
- `analyze` - Explain analysis results
- `decide` - Justify decision rationale
- `critique` - Explain findings
- Any capability that produces complex output

**Commonly precedes:**
- `summarize` - Condense explanation further
- `translate` - Convert to different register
- `validate` - Check explanation accuracy

**Anti-patterns:**
- Never explain without understanding first
- Avoid jargon without definition for beginners
- Never skip assumptions for complex topics

**Workflow references:**
- See any workflow needing human-readable output
