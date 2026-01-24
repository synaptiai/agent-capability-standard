---
name: prioritize
description: Rank tasks, options, or items by value, urgency, risk, and dependencies. Use when ordering backlogs, triaging issues, allocating resources, or sequencing work.
argument-hint: "[items] [criteria] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Rank a set of items (tasks, issues, features, options) according to explicit criteria, producing an ordered list with clear justification for each ranking decision.

**Success criteria:**
- All items ranked in clear order
- Criteria weights are explicit
- Dependencies are respected
- Ties are resolved with rationale
- Ranking is actionable

**Compatible schemas:**
- `docs/schemas/priority_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `items` | Yes | array | Items to prioritize |
| `criteria` | No | array | Ranking criteria with weights |
| `constraints` | No | object | Dependencies, blockers, deadlines |
| `capacity` | No | integer | How many items can be selected |
| `context` | No | object | Background for prioritization |

## Procedure

1) **Inventory items**: Ensure all items are understood
   - List all items to be prioritized
   - Clarify scope of each item
   - Note any missing information
   - Identify duplicates or overlaps

2) **Define criteria**: Establish ranking framework
   - Use provided criteria or standard framework
   - Common: value, urgency, effort, risk
   - Assign weights to each criterion
   - Define how to score each criterion

3) **Identify dependencies**: Map relationships
   - Which items block others?
   - Which items must go together?
   - Are there prerequisite items?
   - Create dependency graph

4) **Score items**: Evaluate each item
   - Score against each criterion
   - Document reasoning for scores
   - Note uncertainty in scores
   - Calculate weighted totals

5) **Apply constraints**: Respect hard rules
   - Items with deadlines may need priority boost
   - Blocked items cannot be first
   - Capacity limits selection
   - Dependencies order related items

6) **Resolve ties**: Make clear decisions
   - Document tie-breaker logic
   - Consider secondary criteria
   - Factor in strategic alignment
   - Avoid arbitrary ordering

7) **Produce ranked list**: Order by priority
   - Include rank and score
   - Group by priority tier if appropriate
   - Note items below cutoff
   - Explain top and bottom placements

## Output Contract

Return a structured object:

```yaml
prioritization:
  method: string  # Approach used
  total_items: integer
  capacity: integer | null
  timestamp: string
ranked_items:
  - rank: integer
    id: string
    name: string
    score: number
    tier: critical | high | medium | low
    scores:
      - criterion: string
        score: number
        rationale: string
    dependencies: array[string]
    blocked_by: array[string]
    deadline: string | null
criteria_used:
  - name: string
    weight: number
    description: string
dependencies:
  - item_id: string
    depends_on: array[string]
    blocks: array[string]
cutoff:
  position: integer | null  # Where capacity limit falls
  below_cutoff: array[string]  # Items that didn't make cut
tier_distribution:
  critical: integer
  high: integer
  medium: integer
  low: integer
rationale:
  top_items: string  # Why top items ranked highest
  bottom_items: string  # Why bottom items ranked lowest
  tie_breakers: array[string]  # How ties were resolved
confidence: 0..1
evidence_anchors: ["source:ref"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `prioritization` | object | Methodology summary |
| `ranked_items` | array | Ordered list with scores |
| `criteria_used` | array | Ranking framework |
| `dependencies` | array | Item relationships |
| `cutoff` | object | Capacity limit effects |
| `tier_distribution` | object | Count by priority tier |
| `rationale` | object | Explanation of key decisions |
| `confidence` | number | 0.0-1.0 based on information quality |

## Examples

### Example 1: Feature Backlog Prioritization

**Input:**
```yaml
items:
  - id: "F001"
    name: "User authentication rewrite"
    description: "Replace legacy auth with OAuth2"
  - id: "F002"
    name: "Dark mode"
    description: "Add dark theme option"
  - id: "F003"
    name: "Performance optimization"
    description: "Reduce page load time by 50%"
  - id: "F004"
    name: "Mobile app"
    description: "Native iOS/Android apps"
  - id: "F005"
    name: "API rate limiting"
    description: "Add rate limiting to public API"
criteria:
  - name: "business_value"
    weight: 0.4
  - name: "urgency"
    weight: 0.3
  - name: "effort"
    weight: 0.2
    inverse: true  # Lower effort = higher score
  - name: "risk"
    weight: 0.1
    inverse: true  # Lower risk = higher score
capacity: 3
```

**Output:**
```yaml
prioritization:
  method: "weighted_scoring"
  total_items: 5
  capacity: 3
  timestamp: "2024-01-15T10:00:00Z"
ranked_items:
  - rank: 1
    id: "F001"
    name: "User authentication rewrite"
    score: 8.5
    tier: critical
    scores:
      - criterion: "business_value"
        score: 9
        rationale: "Security requirement, blocks other features"
      - criterion: "urgency"
        score: 10
        rationale: "Security audit deadline in 6 weeks"
      - criterion: "effort"
        score: 6
        rationale: "6-week project, moderate complexity"
      - criterion: "risk"
        score: 7
        rationale: "Well-understood migration path"
    dependencies: []
    blocked_by: []
    deadline: "2024-03-01"
  - rank: 2
    id: "F005"
    name: "API rate limiting"
    score: 7.8
    tier: high
    scores:
      - criterion: "business_value"
        score: 7
        rationale: "Prevents abuse, enables paid tiers"
      - criterion: "urgency"
        score: 9
        rationale: "Recent abuse incidents"
      - criterion: "effort"
        score: 8
        rationale: "2-week project"
      - criterion: "risk"
        score: 8
        rationale: "Standard implementation"
    dependencies: []
    blocked_by: ["F001"]
    deadline: null
  - rank: 3
    id: "F003"
    name: "Performance optimization"
    score: 7.2
    tier: high
    scores:
      - criterion: "business_value"
        score: 8
        rationale: "Directly impacts user retention"
      - criterion: "urgency"
        score: 6
        rationale: "Important but not time-sensitive"
      - criterion: "effort"
        score: 7
        rationale: "4-week project"
      - criterion: "risk"
        score: 6
        rationale: "May require architectural changes"
    dependencies: []
    blocked_by: []
    deadline: null
  - rank: 4
    id: "F002"
    name: "Dark mode"
    score: 5.5
    tier: medium
    scores:
      - criterion: "business_value"
        score: 5
        rationale: "User-requested but not revenue-driving"
      - criterion: "urgency"
        score: 3
        rationale: "No deadline"
      - criterion: "effort"
        score: 9
        rationale: "1-week project"
      - criterion: "risk"
        score: 9
        rationale: "Well-defined scope"
    dependencies: []
    blocked_by: []
    deadline: null
  - rank: 5
    id: "F004"
    name: "Mobile app"
    score: 4.8
    tier: low
    scores:
      - criterion: "business_value"
        score: 7
        rationale: "New market segment"
      - criterion: "urgency"
        score: 2
        rationale: "Strategic, not urgent"
      - criterion: "effort"
        score: 2
        rationale: "16-week project"
      - criterion: "risk"
        score: 5
        rationale: "New platform, uncertain requirements"
    dependencies: ["F001", "F005"]
    blocked_by: ["F001"]
    deadline: null
criteria_used:
  - name: "business_value"
    weight: 0.4
    description: "Revenue and strategic impact"
  - name: "urgency"
    weight: 0.3
    description: "Time sensitivity and deadlines"
  - name: "effort"
    weight: 0.2
    description: "Development time (inverse: lower = better)"
  - name: "risk"
    weight: 0.1
    description: "Implementation risk (inverse: lower = better)"
dependencies:
  - item_id: "F004"
    depends_on: ["F001", "F005"]
    blocks: []
  - item_id: "F005"
    depends_on: []
    blocks: ["F004"]
cutoff:
  position: 3
  below_cutoff: ["F002", "F004"]
tier_distribution:
  critical: 1
  high: 2
  medium: 1
  low: 1
rationale:
  top_items: "F001 ranks first due to security deadline and blocking other work. F005 and F003 are high-value with reasonable effort."
  bottom_items: "F004 is strategic but high-effort and blocked by F001. F002 is low-urgency despite quick implementation."
  tie_breakers:
    - "F005 over F003 due to blocking relationship with F004"
confidence: 0.9
evidence_anchors:
  - "backlog:feature-list"
  - "deadline:security-audit"
assumptions:
  - "Security audit deadline is firm"
  - "Effort estimates are accurate"
  - "Capacity is 3 features per quarter"
```

**Evidence pattern:** Each item scored with rationale, dependencies mapped, capacity constraint applied.

## Verification

- [ ] All items ranked
- [ ] Dependencies respected
- [ ] Scores justified
- [ ] Ties resolved
- [ ] Cutoff documented

**Verification tools:** Read (for item details)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always document scoring rationale
- Never hide items below cutoff
- Respect hard dependencies
- Flag when information is missing
- Note if prioritization is time-sensitive

## Composition Patterns

**Commonly follows:**
- `retrieve` - Gather items to prioritize
- `evaluate` - Score items in detail
- `critique` - Assess risks for each item

**Commonly precedes:**
- `schedule` - Time-order prioritized items
- `plan` - Plan top priority items
- `delegate` - Assign prioritized work

**Anti-patterns:**
- Never prioritize without criteria
- Never ignore dependencies
- Never hide scoring logic

**Workflow references:**
- See `composition_patterns.md#capability-gap-analysis` for prioritization in planning
