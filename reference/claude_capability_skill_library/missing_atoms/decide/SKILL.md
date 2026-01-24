---
name: decide
description: Choose among alternatives using explicit criteria, trade-off analysis, and evidence-based reasoning. Use when selecting options, making recommendations, or justifying choices.
argument-hint: "[options] [criteria] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Make a well-reasoned decision among alternatives by defining explicit criteria, evaluating each option, analyzing trade-offs, and documenting the rationale. Produce a defensible recommendation.

**Success criteria:**
- All options evaluated against same criteria
- Trade-offs explicitly identified
- Decision rationale is clear and documented
- Assumptions are stated
- Recommendation is actionable

**Compatible schemas:**
- `docs/schemas/decision_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `options` | Yes | array | Alternatives to choose from |
| `criteria` | No | array | Evaluation criteria with weights |
| `constraints` | No | object | Hard constraints (must-haves, deal-breakers) |
| `context` | No | object | Background information for decision |
| `risk_tolerance` | No | string | low, medium, high - affects weighting |

## Procedure

1) **Clarify decision scope**: Understand what is being decided
   - What is the goal of this decision?
   - What is NOT being decided?
   - Who are the stakeholders?
   - What is the timeline?

2) **Enumerate options**: Ensure all alternatives are considered
   - List all provided options
   - Identify any obvious missing options
   - Remove options that fail hard constraints
   - Note any option that was excluded and why

3) **Define criteria**: Establish evaluation framework
   - Use provided criteria or derive from context
   - Assign weights reflecting relative importance
   - Distinguish must-have vs nice-to-have
   - Ensure criteria are measurable

4) **Evaluate options**: Score each option against criteria
   - Gather evidence for each option/criterion pair
   - Assign scores (0-10 or qualitative)
   - Note confidence in each score
   - Document reasoning for scores

5) **Analyze trade-offs**: Understand what each option sacrifices
   - Identify pros and cons for each option
   - Find criteria where options differ most
   - Assess reversibility of each choice
   - Consider second-order effects

6) **Calculate recommendation**: Determine best option
   - Apply weighted scoring
   - Consider qualitative factors
   - Account for uncertainty
   - Check against gut/intuition

7) **Document rationale**: Explain the decision
   - State the recommendation clearly
   - Explain why it scored highest
   - Acknowledge what is being traded away
   - Note conditions that could change the decision

## Output Contract

Return a structured object:

```yaml
decision:
  question: string  # What was being decided
  recommendation: string  # Chosen option
  confidence: number  # 0.0-1.0
  rationale: string  # Why this option
options:
  - id: string
    name: string
    summary: string
    eliminated: boolean
    elimination_reason: string | null
criteria:
  - name: string
    weight: number  # 0.0-1.0
    type: must_have | nice_to_have
    description: string
evaluation:
  - option_id: string
    total_score: number
    scores:
      - criterion: string
        score: number  # 0-10
        rationale: string
        evidence: string | null
trade_offs:
  - option: string
    pros: array[string]
    cons: array[string]
    risk_level: low | medium | high
alternatives_if_rejected:
  - condition: string  # When this alternative applies
    recommendation: string
    reason: string
confidence: 0..1
evidence_anchors: ["source:ref"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `decision` | object | Final recommendation with rationale |
| `options` | array | All options considered |
| `criteria` | array | Evaluation framework |
| `evaluation` | array | Scored evaluations |
| `trade_offs` | array | Pros/cons for each option |
| `alternatives_if_rejected` | array | Backup recommendations |
| `confidence` | number | 0.0-1.0 overall decision confidence |

## Examples

### Example 1: Technology Selection

**Input:**
```yaml
options:
  - name: "PostgreSQL"
    description: "Relational database with strong ACID"
  - name: "MongoDB"
    description: "Document database with flexible schema"
  - name: "DynamoDB"
    description: "Managed NoSQL with auto-scaling"
criteria:
  - name: "consistency"
    weight: 0.4
  - name: "scalability"
    weight: 0.3
  - name: "operational_cost"
    weight: 0.3
constraints:
  must_have: ["ACID transactions"]
context:
  use_case: "User account data"
  scale: "10M users"
```

**Output:**
```yaml
decision:
  question: "Which database for user account data at 10M scale?"
  recommendation: "PostgreSQL"
  confidence: 0.85
  rationale: "User accounts require strong consistency and ACID transactions. PostgreSQL meets all must-haves and scores highest on weighted criteria. MongoDB eliminated due to eventual consistency concerns for auth data."
options:
  - id: "opt-postgres"
    name: "PostgreSQL"
    summary: "Strong ACID, proven at scale, relational model fits user data"
    eliminated: false
    elimination_reason: null
  - id: "opt-mongodb"
    name: "MongoDB"
    summary: "Flexible schema, eventual consistency"
    eliminated: true
    elimination_reason: "Does not meet must-have: ACID transactions for auth data"
  - id: "opt-dynamodb"
    name: "DynamoDB"
    summary: "Managed, auto-scaling, eventually consistent by default"
    eliminated: true
    elimination_reason: "Does not meet must-have: ACID transactions"
criteria:
  - name: "consistency"
    weight: 0.4
    type: must_have
    description: "Strong consistency for auth decisions"
  - name: "scalability"
    weight: 0.3
    type: nice_to_have
    description: "Handle 10M+ users with growth"
  - name: "operational_cost"
    weight: 0.3
    type: nice_to_have
    description: "Total cost of ownership including ops"
evaluation:
  - option_id: "opt-postgres"
    total_score: 8.2
    scores:
      - criterion: "consistency"
        score: 10
        rationale: "Full ACID transactions, serializable isolation"
        evidence: "PostgreSQL docs: transaction isolation"
      - criterion: "scalability"
        score: 7
        rationale: "Proven at 10M+ but requires manual sharding above 100M"
        evidence: "Case study: Instagram used PostgreSQL at 100M+"
      - criterion: "operational_cost"
        score: 7
        rationale: "No license cost, moderate ops complexity"
        evidence: "AWS RDS pricing, typical DBA requirements"
trade_offs:
  - option: "PostgreSQL"
    pros:
      - "Strong ACID compliance"
      - "Team has experience"
      - "Well-understood operational model"
    cons:
      - "Manual sharding required at very large scale"
      - "Schema migrations require planning"
    risk_level: low
alternatives_if_rejected:
  - condition: "If horizontal scaling becomes primary concern"
    recommendation: "CockroachDB"
    reason: "PostgreSQL-compatible with distributed transactions"
confidence: 0.85
evidence_anchors:
  - "doc:postgresql-transaction-isolation"
  - "case-study:instagram-postgres"
assumptions:
  - "10M users is stable target for 2 years"
  - "ACID requirement will not change"
  - "Team has PostgreSQL expertise"
```

**Evidence pattern:** Each criterion scored with rationale, eliminated options documented.

---

### Example 2: Process Decision

**Input:**
```yaml
options:
  - name: "Manual code review"
  - name: "AI-assisted review"
  - name: "Automated only"
criteria:
  - name: "bug_detection"
    weight: 0.5
  - name: "team_velocity"
    weight: 0.3
  - name: "knowledge_sharing"
    weight: 0.2
context:
  team_size: 5
  codebase: "100k LOC"
```

**Output:**
```yaml
decision:
  question: "What code review process to adopt?"
  recommendation: "AI-assisted review"
  confidence: 0.75
  rationale: "AI-assisted review balances thoroughness with velocity. Catches automated issues while preserving human oversight for logic and design. Maintains knowledge sharing through required human sign-off."
options:
  - id: "opt-manual"
    name: "Manual code review"
    summary: "Human reviewers only"
    eliminated: false
    elimination_reason: null
  - id: "opt-ai-assisted"
    name: "AI-assisted review"
    summary: "AI pre-review with human approval"
    eliminated: false
    elimination_reason: null
  - id: "opt-automated"
    name: "Automated only"
    summary: "No human review, linting only"
    eliminated: false
    elimination_reason: null
criteria:
  - name: "bug_detection"
    weight: 0.5
    type: must_have
    description: "Catch bugs before production"
  - name: "team_velocity"
    weight: 0.3
    type: nice_to_have
    description: "Not slow down development significantly"
  - name: "knowledge_sharing"
    weight: 0.2
    type: nice_to_have
    description: "Team learns from each other's code"
evaluation:
  - option_id: "opt-manual"
    total_score: 7.0
    scores:
      - criterion: "bug_detection"
        score: 8
        rationale: "Humans catch logic bugs AI might miss"
        evidence: null
      - criterion: "team_velocity"
        score: 5
        rationale: "Waiting for reviewers slows merges"
        evidence: "Average PR wait time: 4 hours"
      - criterion: "knowledge_sharing"
        score: 9
        rationale: "Direct knowledge transfer through comments"
        evidence: null
  - option_id: "opt-ai-assisted"
    total_score: 8.1
    scores:
      - criterion: "bug_detection"
        score: 9
        rationale: "AI catches style/pattern issues, humans catch logic"
        evidence: null
      - criterion: "team_velocity"
        score: 8
        rationale: "AI provides instant feedback, human review focused"
        evidence: null
      - criterion: "knowledge_sharing"
        score: 6
        rationale: "Reduced but still present with human sign-off"
        evidence: null
  - option_id: "opt-automated"
    total_score: 5.2
    scores:
      - criterion: "bug_detection"
        score: 5
        rationale: "Only catches pattern violations"
        evidence: null
      - criterion: "team_velocity"
        score: 9
        rationale: "Instant, no waiting"
        evidence: null
      - criterion: "knowledge_sharing"
        score: 1
        rationale: "No human interaction on PRs"
        evidence: null
trade_offs:
  - option: "AI-assisted review"
    pros:
      - "Fast initial feedback"
      - "Consistent checking"
      - "Preserves human oversight"
    cons:
      - "Less knowledge sharing than pure manual"
      - "New tooling to integrate"
    risk_level: low
alternatives_if_rejected:
  - condition: "If team strongly prefers manual process"
    recommendation: "Manual with AI suggestions"
    reason: "Human primary, AI as optional advisor"
confidence: 0.75
evidence_anchors:
  - "metric:pr-wait-time"
assumptions:
  - "AI tool has acceptable accuracy"
  - "Team is open to new tooling"
```

## Verification

- [ ] All options evaluated against same criteria
- [ ] Scores have rationale
- [ ] Trade-offs documented
- [ ] Eliminated options explained
- [ ] Recommendation is clear

**Verification tools:** Read (for evidence gathering)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always document criteria weights
- Never hide trade-offs
- Acknowledge uncertainty in scores
- If no clear winner, say so
- Document conditions that would change decision

## Composition Patterns

**Commonly follows:**
- `compare` - Compare options in detail
- `evaluate` - Score options
- `critique` - Identify risks in options
- `retrieve` - Gather decision inputs

**Commonly precedes:**
- `plan` - Plan implementation of decision
- `explain` - Justify decision to stakeholders
- `send` - Communicate decision

**Anti-patterns:**
- Never decide without evaluating all options
- Never hide eliminated options
- Never skip trade-off analysis

**Workflow references:**
- See `composition_patterns.md#capability-gap-analysis` for decision in planning
