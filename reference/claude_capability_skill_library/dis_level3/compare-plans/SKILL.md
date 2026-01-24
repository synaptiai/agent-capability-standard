---
name: compare-plans
description: Compare action plans by feasibility, risk, cost, speed, and quality to recommend optimal execution strategy. Use when choosing between implementation approaches, project timelines, or strategic alternatives.
argument-hint: "[plan_a] [plan_b] [criteria] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically compare multiple action plans against execution criteria to identify the optimal strategy, accounting for feasibility, risk, resource requirements, and expected outcomes.

**Success criteria:**
- Each plan is evaluated on consistent, relevant criteria
- Risks and dependencies are explicitly identified for each plan
- Recommendation considers both short-term execution and long-term implications
- Tradeoffs between plans are clearly articulated

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `plans` | Yes | array[object] | Plans to compare (each with steps, timeline, resources) |
| `criteria` | No | array[string] | Evaluation criteria (defaults: feasibility, risk, cost, speed, quality) |
| `constraints` | No | object | Hard constraints (budget, deadline, team size, etc.) |
| `weights` | No | object | Relative importance of each criterion |
| `context` | No | string | Decision context (urgency, risk tolerance, strategic goals) |

## Procedure

1) **Parse plan structures**: Extract comparable elements from each plan
   - Steps and dependencies
   - Resource requirements (time, money, people, tools)
   - Expected outcomes and milestones
   - Assumptions and prerequisites

2) **Evaluate feasibility**: For each plan
   - Check prerequisite availability
   - Assess team capability against required skills
   - Identify blocking dependencies
   - Rate execution complexity

3) **Assess risks**: Identify and score risks per plan
   - Technical risks (unknowns, complexity)
   - Schedule risks (dependencies, parallelization)
   - Resource risks (availability, contention)
   - External risks (vendor, market, regulatory)

4) **Calculate costs**: Total resource investment
   - Direct costs (budget, licenses, infrastructure)
   - Opportunity costs (what else could be done)
   - Hidden costs (maintenance, technical debt)

5) **Estimate timelines**: Compare execution speed
   - Critical path analysis
   - Parallelization opportunities
   - Buffer requirements for uncertainty

6) **Project quality**: Expected outcome quality
   - Completeness of solution
   - Maintainability and extensibility
   - User/stakeholder satisfaction likelihood

## Output Contract

Return a structured object:

```yaml
plans:
  - id: string
    summary: string
    steps_count: integer
    estimated_duration: string
    passes_constraints: boolean
criteria:
  - name: string  # feasibility, risk, cost, speed, quality
    weight: number
    description: string
comparison_matrix:
  - plan_id: string
    scores:
      - criterion: string
        score: number  # 0.0-1.0 (higher = better)
        rationale: string
        evidence_anchor: string
        key_factors: array[string]
risk_analysis:
  - plan_id: string
    risks:
      - type: technical | schedule | resource | external
        description: string
        probability: low | medium | high
        impact: low | medium | high
        mitigation: string | null
recommendation:
  choice: string
  rationale: string
  confidence: number
  conditions: array[string]  # When this recommendation holds
  alternatives_for: object  # Different contexts -> different recommendations
tradeoffs:
  - plan: string
    pros: array[string]
    cons: array[string]
    best_when: string  # Context where this plan excels
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `plans` | array | Plans being compared with summaries |
| `criteria` | array | Evaluation criteria with weights |
| `comparison_matrix` | array | Scores per plan-criterion pair |
| `risk_analysis` | array | Detailed risks per plan |
| `recommendation` | object | Recommended plan with conditions |
| `tradeoffs` | array | Pros/cons and ideal contexts per plan |
| `confidence` | number | 0.0-1.0 based on information completeness |
| `evidence_anchors` | array[string] | Plan documents, estimates, or analysis |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Comparing Migration Strategies

**Input:**
```yaml
plans:
  - id: "big_bang"
    description: "Complete system replacement over one weekend"
    steps:
      - "Freeze current system Friday 6pm"
      - "Run parallel data migration"
      - "Deploy new system"
      - "Validate and cutover"
      - "Go live Monday 8am"
  - id: "strangler_fig"
    description: "Gradual replacement over 6 months"
    steps:
      - "Deploy facade layer"
      - "Migrate module A (month 1-2)"
      - "Migrate module B (month 2-3)"
      - "Migrate module C (month 3-5)"
      - "Decommission legacy (month 6)"
  - id: "parallel_run"
    description: "Run both systems for 3 months, then switch"
    steps:
      - "Deploy new system alongside legacy"
      - "Route 10% traffic to new system"
      - "Gradually increase to 100%"
      - "Decommission legacy after 3 months"
criteria:
  - "feasibility"
  - "risk"
  - "cost"
  - "speed"
  - "quality"
constraints:
  budget: "$500,000"
  deadline: "6 months"
  downtime_tolerance: "4 hours max"
weights:
  risk: 0.3
  quality: 0.25
  cost: 0.2
  speed: 0.15
  feasibility: 0.1
```

**Output:**
```yaml
plans:
  - id: "big_bang"
    summary: "Complete replacement in single weekend cutover"
    steps_count: 5
    estimated_duration: "1 weekend (prep: 2 months)"
    passes_constraints: false  # Risk of exceeding downtime
  - id: "strangler_fig"
    summary: "Incremental replacement over 6 months"
    steps_count: 5
    estimated_duration: "6 months"
    passes_constraints: true
  - id: "parallel_run"
    summary: "Parallel operation with gradual traffic shift"
    steps_count: 4
    estimated_duration: "3 months"
    passes_constraints: true
criteria:
  - name: "feasibility"
    weight: 0.1
    description: "Can the plan be executed with available resources?"
  - name: "risk"
    weight: 0.3
    description: "Probability and impact of failure"
  - name: "cost"
    weight: 0.2
    description: "Total resource investment including hidden costs"
  - name: "speed"
    weight: 0.15
    description: "Time to complete migration"
  - name: "quality"
    weight: 0.25
    description: "Expected outcome quality and maintainability"
comparison_matrix:
  - plan_id: "big_bang"
    scores:
      - criterion: "feasibility"
        score: 0.6
        rationale: "Requires perfect execution under time pressure"
        evidence_anchor: "plans/big_bang.md:12"
        key_factors: ["weekend execution", "all-or-nothing"]
      - criterion: "risk"
        score: 0.3
        rationale: "High risk - single point of failure, rollback complex"
        evidence_anchor: "plans/big_bang.md:25"
        key_factors: ["no gradual validation", "rollback destroys data"]
      - criterion: "cost"
        score: 0.7
        rationale: "Lower total cost if successful, no dual maintenance"
        evidence_anchor: "estimates/big_bang_cost.xlsx"
        key_factors: ["$150K estimate", "overtime costs"]
      - criterion: "speed"
        score: 0.95
        rationale: "Fastest completion if successful"
        evidence_anchor: "plans/big_bang.md:timeline"
        key_factors: ["2 months prep + 1 weekend"]
      - criterion: "quality"
        score: 0.5
        rationale: "Quality depends on testing completeness pre-cutover"
        evidence_anchor: "plans/big_bang.md:testing"
        key_factors: ["limited production validation"]
  - plan_id: "strangler_fig"
    scores:
      - criterion: "feasibility"
        score: 0.9
        rationale: "Proven pattern, manageable increments"
        evidence_anchor: "plans/strangler.md:8"
        key_factors: ["incremental delivery", "reversible steps"]
      - criterion: "risk"
        score: 0.85
        rationale: "Low risk - failures isolated to modules"
        evidence_anchor: "plans/strangler.md:risk_analysis"
        key_factors: ["module isolation", "easy rollback"]
      - criterion: "cost"
        score: 0.5
        rationale: "Higher total cost due to dual maintenance"
        evidence_anchor: "estimates/strangler_cost.xlsx"
        key_factors: ["$400K estimate", "6 months dual ops"]
      - criterion: "speed"
        score: 0.4
        rationale: "Slowest option at 6 months"
        evidence_anchor: "plans/strangler.md:timeline"
        key_factors: ["sequential modules"]
      - criterion: "quality"
        score: 0.9
        rationale: "Highest quality - each module validated in production"
        evidence_anchor: "plans/strangler.md:validation"
        key_factors: ["production testing", "iterative improvement"]
  - plan_id: "parallel_run"
    scores:
      - criterion: "feasibility"
        score: 0.75
        rationale: "Requires infrastructure for dual systems"
        evidence_anchor: "plans/parallel.md:requirements"
        key_factors: ["double infrastructure", "sync complexity"]
      - criterion: "risk"
        score: 0.7
        rationale: "Medium risk - data sync issues possible"
        evidence_anchor: "plans/parallel.md:risks"
        key_factors: ["sync failures", "gradual exposure"]
      - criterion: "cost"
        score: 0.4
        rationale: "Highest cost - double infrastructure for 3 months"
        evidence_anchor: "estimates/parallel_cost.xlsx"
        key_factors: ["$480K estimate", "cloud costs"]
      - criterion: "speed"
        score: 0.7
        rationale: "Moderate speed - faster than strangler"
        evidence_anchor: "plans/parallel.md:timeline"
        key_factors: ["3 months total"]
      - criterion: "quality"
        score: 0.8
        rationale: "Good quality - real traffic validation"
        evidence_anchor: "plans/parallel.md:validation"
        key_factors: ["A/B testing", "gradual rollout"]
risk_analysis:
  - plan_id: "big_bang"
    risks:
      - type: technical
        description: "Data migration may fail or corrupt data"
        probability: medium
        impact: high
        mitigation: "Extensive pre-migration testing, backup strategy"
      - type: schedule
        description: "Weekend may not provide enough time"
        probability: medium
        impact: high
        mitigation: "None - plan assumes weekend sufficient"
      - type: external
        description: "Vendor support may not be available weekend"
        probability: low
        impact: medium
        mitigation: "Pre-arrange support contracts"
  - plan_id: "strangler_fig"
    risks:
      - type: technical
        description: "Module boundaries may not be clean"
        probability: medium
        impact: low
        mitigation: "Discovery phase to validate module boundaries"
      - type: resource
        description: "Team fatigue over 6 months"
        probability: medium
        impact: medium
        mitigation: "Rotate team members, celebrate milestones"
  - plan_id: "parallel_run"
    risks:
      - type: technical
        description: "Data synchronization between systems"
        probability: high
        impact: medium
        mitigation: "Event sourcing, reconciliation jobs"
      - type: resource
        description: "Double infrastructure costs"
        probability: high
        impact: low
        mitigation: "Budget approved, cloud autoscaling"
recommendation:
  choice: "strangler_fig"
  rationale: "Best risk-adjusted outcome given risk weight of 0.3; only plan with low risk and high quality"
  confidence: 0.75
  conditions:
    - "Risk tolerance is low to medium"
    - "Quality is prioritized over speed"
    - "Budget allows for extended timeline"
  alternatives_for:
    "time_critical": "parallel_run if deadline is 3 months"
    "budget_constrained": "big_bang if budget < $200K and risk acceptable"
tradeoffs:
  - plan: "big_bang"
    pros:
      - "Fastest completion (1 weekend)"
      - "Lowest cost if successful"
      - "Clean break from legacy"
    cons:
      - "Highest risk of catastrophic failure"
      - "May exceed downtime tolerance"
      - "No production validation before cutover"
    best_when: "Simple system, excellent test coverage, experienced team, rollback is easy"
  - plan: "strangler_fig"
    pros:
      - "Lowest risk"
      - "Highest quality outcome"
      - "Production-validated at each step"
    cons:
      - "Slowest (6 months)"
      - "Higher total cost (dual maintenance)"
      - "Requires clean module boundaries"
    best_when: "Risk averse, quality critical, complex system, uncertain requirements"
  - plan: "parallel_run"
    pros:
      - "Real traffic validation"
      - "Moderate timeline (3 months)"
      - "Gradual confidence building"
    cons:
      - "Highest infrastructure cost"
      - "Data sync complexity"
      - "Requires feature parity"
    best_when: "Need production validation, can afford infrastructure, clear feature parity"
confidence: 0.75
evidence_anchors:
  - "plans/big_bang.md:12"
  - "plans/big_bang.md:25"
  - "plans/strangler.md:8"
  - "plans/strangler.md:risk_analysis"
  - "plans/parallel.md:requirements"
  - "plans/parallel.md:risks"
  - "estimates/big_bang_cost.xlsx"
  - "estimates/strangler_cost.xlsx"
  - "estimates/parallel_cost.xlsx"
assumptions:
  - "Team has capacity for any plan"
  - "Budget figures are estimates with +/- 20% variance"
  - "No external regulatory deadlines"
  - "Legacy system can remain operational during transition"
```

**Evidence pattern:** Plan documents + cost estimates + risk analysis

## Verification

- [ ] All plans evaluated on same criteria
- [ ] Risk analysis covers all major risk categories
- [ ] Recommendation aligns with weighted scores
- [ ] Constraint violations correctly flagged
- [ ] Tradeoffs accurately reflect plan characteristics

**Verification tools:** Read (for plan documents), Grep (for searching requirements)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not recommend plans that violate hard constraints
- Flag when plans have incomplete information
- Highlight irreversible decisions in each plan
- Stop and clarify if plan descriptions are ambiguous

## Composition Patterns

**Commonly follows:**
- `generate-plan` - to create plans to compare
- `retrieve` - to gather plan documentation
- `estimate-risk` - to assess individual plan risks

**Commonly precedes:**
- `act-plan` - to execute the recommended plan
- `critique` - to stress-test the recommended plan
- `summarize` - to create executive summary

**Anti-patterns:**
- Never compare plans without understanding constraints
- Avoid recommending based on single criterion

**Workflow references:**
- See `workflow_catalog.json#project_planning` for project workflows
