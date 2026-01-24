---
name: compare-entities
description: Compare entities across explicit criteria to produce a structured recommendation. Use when evaluating options, making decisions between alternatives, or assessing tradeoffs between systems/tools/frameworks.
argument-hint: "[entity_a] [entity_b] [criteria] [weights]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically compare two or more entities (systems, tools, frameworks, products, concepts) against defined criteria to produce an evidence-based recommendation with explicit tradeoffs.

**Success criteria:**
- Comparison matrix covers all specified criteria with scores and rationale
- Recommendation is grounded in evidence with clear confidence level
- Tradeoffs for each option are explicitly stated
- All claims have evidence anchors

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entities` | Yes | array[string\|object] | The entities to compare (2 or more) |
| `criteria` | Yes | array[string] | Comparison criteria (e.g., performance, cost, maintainability) |
| `weights` | No | object | Relative importance of each criterion (0.0-1.0) |
| `context` | No | string | Use case or decision context influencing the comparison |
| `constraints` | No | object | Hard requirements that must be met (e.g., budget < $1000) |

## Procedure

1) **Enumerate entities**: List each entity with a brief summary of its identity and purpose
   - Gather key attributes for each entity from documentation, code, or provided context
   - Note version numbers, configurations, or variants if relevant

2) **Define evaluation criteria**: Formalize each criterion with measurement approach
   - For quantitative criteria: specify units and measurement method
   - For qualitative criteria: define rating scale (e.g., 1-5 or low/medium/high)
   - Apply weights (default to equal weights if not specified)

3) **Gather evidence per criterion**: For each entity-criterion pair
   - Search for benchmarks, documentation, or code evidence
   - Record specific evidence anchors (file:line, URL, or tool output)
   - Note when evidence is missing or weak

4) **Score and rationalize**: Assign scores with explicit rationale
   - Each score must cite at least one evidence anchor
   - Flag subjective assessments vs objective measurements

5) **Calculate recommendation**: Apply weighted scoring
   - Identify clear winner if scores diverge significantly
   - Provide conditional recommendation if context-dependent

6) **Document tradeoffs**: For each option, list what you gain and lose
   - Consider edge cases where the non-recommended option wins

## Output Contract

Return a structured object:

```yaml
options:
  - id: string  # Entity identifier
    type: string  # entity, system, tool, framework, etc.
    summary: string  # Brief description
criteria:
  - name: string  # Criterion name
    weight: number  # 0.0-1.0
    type: quantitative | qualitative
comparison_matrix:
  - option_id: string
    scores:
      - criterion: string
        score: number  # Normalized 0.0-1.0
        raw_value: string | number | null  # Original measurement
        rationale: string  # Why this score
        evidence_anchor: string  # file:line or URL
recommendation:
  choice: string  # Recommended entity ID
  rationale: string  # Why this recommendation
  conditions: array[string]  # When this recommendation applies
tradeoffs:
  - option: string
    pros: array[string]
    cons: array[string]
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `options` | array | Entities being compared with summaries |
| `criteria` | array | Evaluation criteria with weights |
| `comparison_matrix` | array | Scores for each entity-criterion pair |
| `recommendation` | object | Final choice with rationale and conditions |
| `tradeoffs` | array | Pros/cons for each option |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | All file:line refs, URLs, or tool outputs |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Comparing JavaScript Frameworks

**Input:**
```yaml
entities:
  - name: "React"
    version: "18.x"
  - name: "Vue"
    version: "3.x"
criteria:
  - "learning_curve"
  - "performance"
  - "ecosystem_size"
  - "typescript_support"
weights:
  learning_curve: 0.2
  performance: 0.3
  ecosystem_size: 0.25
  typescript_support: 0.25
context: "Building a medium-sized SPA for a team with mixed experience levels"
```

**Output:**
```yaml
options:
  - id: "react-18"
    type: "framework"
    summary: "Declarative UI library with component-based architecture and virtual DOM"
  - id: "vue-3"
    type: "framework"
    summary: "Progressive framework with reactive data binding and composition API"
criteria:
  - name: "learning_curve"
    weight: 0.2
    type: qualitative
  - name: "performance"
    weight: 0.3
    type: quantitative
  - name: "ecosystem_size"
    weight: 0.25
    type: quantitative
  - name: "typescript_support"
    weight: 0.25
    type: qualitative
comparison_matrix:
  - option_id: "react-18"
    scores:
      - criterion: "learning_curve"
        score: 0.6
        raw_value: "medium"
        rationale: "JSX requires understanding, hooks have gotchas"
        evidence_anchor: "https://react.dev/learn"
      - criterion: "performance"
        score: 0.85
        raw_value: "45ms TTI"
        rationale: "Concurrent rendering, automatic batching"
        evidence_anchor: "tool:benchmark:react-perf-001"
      - criterion: "ecosystem_size"
        score: 0.95
        raw_value: "2.1M npm dependents"
        rationale: "Largest ecosystem, most third-party libraries"
        evidence_anchor: "https://npmjs.com/package/react"
      - criterion: "typescript_support"
        score: 0.85
        raw_value: "native"
        rationale: "First-class TS support, strong type inference"
        evidence_anchor: "https://react.dev/learn/typescript"
  - option_id: "vue-3"
    scores:
      - criterion: "learning_curve"
        score: 0.85
        raw_value: "easy"
        rationale: "Template syntax familiar, gentle progression"
        evidence_anchor: "https://vuejs.org/guide/introduction.html"
      - criterion: "performance"
        score: 0.9
        raw_value: "42ms TTI"
        rationale: "Smaller bundle, fine-grained reactivity"
        evidence_anchor: "tool:benchmark:vue-perf-001"
      - criterion: "ecosystem_size"
        score: 0.7
        raw_value: "0.9M npm dependents"
        rationale: "Growing ecosystem, fewer ready-made solutions"
        evidence_anchor: "https://npmjs.com/package/vue"
      - criterion: "typescript_support"
        score: 0.9
        raw_value: "native"
        rationale: "Vue 3 written in TS, excellent inference"
        evidence_anchor: "https://vuejs.org/guide/typescript/overview.html"
recommendation:
  choice: "react-18"
  rationale: "Larger ecosystem compensates for steeper learning curve; more hiring options"
  conditions:
    - "Team has JavaScript experience"
    - "Long-term maintainability is priority"
    - "Third-party integrations needed"
tradeoffs:
  - option: "react-18"
    pros:
      - "Largest job market and community"
      - "Most third-party libraries available"
      - "Well-documented patterns for scale"
    cons:
      - "Steeper initial learning curve"
      - "More boilerplate for state management"
      - "Frequent ecosystem churn"
  - option: "vue-3"
    pros:
      - "Faster onboarding for beginners"
      - "Better out-of-box performance"
      - "More opinionated (less decision fatigue)"
    cons:
      - "Smaller ecosystem, may need custom solutions"
      - "Fewer senior Vue developers available"
confidence: 0.75
evidence_anchors:
  - "https://react.dev/learn"
  - "https://vuejs.org/guide/introduction.html"
  - "https://npmjs.com/package/react"
  - "https://npmjs.com/package/vue"
  - "tool:benchmark:react-perf-001"
  - "tool:benchmark:vue-perf-001"
assumptions:
  - "Team size is 3-8 developers"
  - "Project timeline is 6+ months"
  - "Performance benchmarks from standard SPA workload"
```

**Evidence pattern:** Documentation review + npm statistics + synthetic benchmarks

## Verification

- [ ] Each criterion has at least one score per entity
- [ ] All scores have evidence anchors
- [ ] Recommendation aligns with weighted scores (or deviation is explained)
- [ ] Tradeoffs cover both options
- [ ] Confidence reflects evidence completeness

**Verification tools:** Read, Grep (for searching documentation/code)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not make comparison claims without evidence
- Flag when comparison data is stale or version-specific
- Avoid bias toward familiar or popular options
- Stop and clarify if criteria are ambiguous or conflicting

## Composition Patterns

**Commonly follows:**
- `search` - to find entities to compare
- `identify-entity` - to clarify what is being compared
- `retrieve` - to gather comparison data

**Commonly precedes:**
- `plan` - to plan implementation using the chosen option
- `generate-plan` - to create action plan based on recommendation
- `explain` - to justify the comparison to stakeholders

**Anti-patterns:**
- Never compare without defined criteria (leads to bias)
- Avoid comparing more than 5 entities without narrowing first

**Workflow references:**
- See `workflow_catalog.json#technology_selection` for usage in tech decisions
