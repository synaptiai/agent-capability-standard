---
name: discover-outcome
description: Discover outcomes and emergent patterns from historical evidence and data analysis. Use when learning from past events, finding result patterns, or understanding what happened and why.
argument-hint: "[data_source] [event_type] [time_range]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Uncover outcomes, results, and emergent patterns from historical data to understand what happened, identify success/failure patterns, and extract actionable insights for future decisions.

**Success criteria:**
- Outcomes are identified with supporting evidence
- Patterns across multiple outcomes are detected
- Causal factors are distinguished from correlations
- Insights are actionable and specific

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data_source` | Yes | string\|object | Historical data to analyze |
| `event_type` | No | string | Type of events to analyze (deployments, experiments, incidents) |
| `time_range` | No | object | Period to analyze (start, end) |
| `outcome_definition` | No | object | How to measure success/failure |
| `grouping` | No | array[string] | Dimensions to group outcomes by |

## Procedure

1) **Scope the analysis**: Define what outcomes to discover
   - Identify event boundaries (start, end, result)
   - Define success/failure criteria
   - Establish relevant time range

2) **Extract outcome data**: Gather historical evidence
   - Event records with results
   - Metrics before/after events
   - Contextual factors at time of event

3) **Classify outcomes**: Categorize results
   - Success vs failure vs partial
   - Magnitude of outcome
   - Speed of outcome realization

4) **Pattern detection**: Find recurring themes
   - Common factors in successful outcomes
   - Common factors in failures
   - Surprising combinations

5) **Analyze contributing factors**: Understand causation
   - Strong predictors of outcome
   - Necessary conditions vs sufficient conditions
   - Confounding factors to control for

6) **Synthesize insights**: Generate actionable findings
   - What predicts success?
   - What should be avoided?
   - What warrants further investigation?

## Output Contract

Return a structured object:

```yaml
discoveries:
  - id: string
    type: outcome_pattern | success_factor | failure_mode | correlation
    description: string
    significance: low | medium | high
    novelty: known | suspected | surprising
    evidence_count: integer
    confidence_level: low | medium | high
    evidence:
      - event_id: string
        outcome: success | failure | partial
        relevant_factors: object
        location: string
outcomes_analyzed:
  total_events: integer
  success_rate: number
  failure_rate: number
  partial_rate: number
  by_category: object  # Outcomes grouped by specified dimensions
success_factors:
  - factor: string
    prevalence_in_success: number  # 0.0-1.0
    prevalence_in_failure: number
    correlation_strength: weak | moderate | strong
    causal_likelihood: unlikely | possible | likely
    evidence_anchors: array[string]
failure_modes:
  - mode: string
    frequency: number  # How often this failure mode occurs
    severity: low | medium | high | critical
    prevention_suggestions: array[string]
    evidence_anchors: array[string]
temporal_patterns:
  - pattern: string
    description: string
    period: string  # daily, weekly, monthly, etc.
insights:
  - insight: string
    actionability: low | medium | high
    confidence: number
    supporting_evidence: array[string]
recommendations:
  - action: string
    expected_impact: string
    priority: low | medium | high
    rationale: string
methodology: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `discoveries` | array | Individual patterns found |
| `outcomes_analyzed` | object | Summary statistics |
| `success_factors` | array | Factors correlated with success |
| `failure_modes` | array | Common failure patterns |
| `temporal_patterns` | array | Time-based patterns |
| `insights` | array | Actionable learnings |
| `recommendations` | array | Suggested actions |
| `confidence` | number | 0.0-1.0 based on data quality |
| `evidence_anchors` | array[string] | All evidence locations |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Discovering Deployment Outcome Patterns

**Input:**
```yaml
data_source: "deployment_records/"
event_type: "production_deployment"
time_range:
  start: "2023-07-01"
  end: "2023-12-31"
outcome_definition:
  success: "No rollback within 24 hours, no P1 incidents"
  failure: "Rollback required OR P1 incident within 24 hours"
grouping:
  - "team"
  - "day_of_week"
  - "deployment_size"
```

**Output:**
```yaml
discoveries:
  - id: "disc-001"
    type: outcome_pattern
    description: "Friday deployments fail 3.2x more often than Monday-Thursday average"
    significance: high
    novelty: suspected
    evidence_count: 47
    confidence_level: high
    evidence:
      - event_id: "deploy-2023-10-13"
        outcome: failure
        relevant_factors:
          day_of_week: "Friday"
          time: "16:45"
          size: "large"
        location: "deployment_records/2023-10.json:234"
      - event_id: "deploy-2023-11-17"
        outcome: failure
        relevant_factors:
          day_of_week: "Friday"
          time: "14:30"
          size: "medium"
        location: "deployment_records/2023-11.json:456"
  - id: "disc-002"
    type: success_factor
    description: "Deployments with >80% test coverage succeed 94% vs 67% for <80%"
    significance: high
    novelty: known
    evidence_count: 156
    confidence_level: high
    evidence:
      - event_id: "deploy-2023-08-15"
        outcome: success
        relevant_factors:
          test_coverage: 92
          tests_passed: true
        location: "deployment_records/2023-08.json:178"
  - id: "disc-003"
    type: failure_mode
    description: "Database migrations without dry-run cause 78% of data-related failures"
    significance: high
    novelty: surprising
    evidence_count: 23
    confidence_level: medium
    evidence:
      - event_id: "deploy-2023-09-22"
        outcome: failure
        relevant_factors:
          has_migration: true
          dry_run_performed: false
          failure_type: "data_corruption"
        location: "deployment_records/2023-09.json:567"
  - id: "disc-004"
    type: correlation
    description: "Team Alpha has 40% higher success rate than organization average"
    significance: medium
    novelty: suspected
    evidence_count: 34
    confidence_level: medium
    evidence:
      - event_id: "multiple (see aggregation)"
        outcome: "aggregated"
        relevant_factors:
          team: "Alpha"
          practices: ["feature_flags", "canary_releases", "automated_rollback"]
        location: "deployment_records/team_alpha/*.json"
outcomes_analyzed:
  total_events: 287
  success_rate: 0.78
  failure_rate: 0.15
  partial_rate: 0.07
  by_category:
    by_team:
      Alpha: { total: 34, success_rate: 0.94 }
      Beta: { total: 52, success_rate: 0.75 }
      Gamma: { total: 45, success_rate: 0.71 }
      Delta: { total: 61, success_rate: 0.77 }
      Platform: { total: 95, success_rate: 0.79 }
    by_day_of_week:
      Monday: { total: 58, success_rate: 0.83 }
      Tuesday: { total: 67, success_rate: 0.81 }
      Wednesday: { total: 72, success_rate: 0.79 }
      Thursday: { total: 61, success_rate: 0.80 }
      Friday: { total: 29, success_rate: 0.52 }
    by_deployment_size:
      small: { total: 145, success_rate: 0.87 }
      medium: { total: 98, success_rate: 0.76 }
      large: { total: 44, success_rate: 0.59 }
success_factors:
  - factor: "Test coverage > 80%"
    prevalence_in_success: 0.89
    prevalence_in_failure: 0.34
    correlation_strength: strong
    causal_likelihood: likely
    evidence_anchors:
      - "deployment_records/coverage_analysis.json"
  - factor: "Feature flag wrapping"
    prevalence_in_success: 0.72
    prevalence_in_failure: 0.23
    correlation_strength: strong
    causal_likelihood: likely
    evidence_anchors:
      - "deployment_records/feature_flag_usage.json"
  - factor: "Deployment before 14:00 local time"
    prevalence_in_success: 0.67
    prevalence_in_failure: 0.41
    correlation_strength: moderate
    causal_likelihood: possible
    evidence_anchors:
      - "deployment_records/timing_analysis.json"
  - factor: "Canary release (10% then 100%)"
    prevalence_in_success: 0.45
    prevalence_in_failure: 0.12
    correlation_strength: strong
    causal_likelihood: likely
    evidence_anchors:
      - "deployment_records/canary_analysis.json"
failure_modes:
  - mode: "Database migration without dry-run"
    frequency: 0.23
    severity: critical
    prevention_suggestions:
      - "Mandate dry-run for all migrations"
      - "Add CI check for migration validation"
      - "Require DBA review for schema changes"
    evidence_anchors:
      - "deployment_records/2023-09.json:567"
      - "deployment_records/2023-11.json:234"
  - mode: "Friday afternoon deployment"
    frequency: 0.16
    severity: high
    prevention_suggestions:
      - "Implement deployment freeze after Thursday 16:00"
      - "Require VP approval for Friday deploys"
    evidence_anchors:
      - "deployment_records/friday_analysis.json"
  - mode: "Large deployment without canary"
    frequency: 0.14
    severity: high
    prevention_suggestions:
      - "Require canary for deployments affecting >3 services"
      - "Mandate staged rollout for large changes"
    evidence_anchors:
      - "deployment_records/large_deploy_analysis.json"
temporal_patterns:
  - pattern: "End of sprint rush"
    description: "Deployment volume increases 2.5x in last 2 days of sprint, failure rate increases 1.4x"
    period: "bi-weekly"
  - pattern: "Holiday proximity"
    description: "Failure rate increases 1.8x in week before major holidays"
    period: "seasonal"
insights:
  - insight: "Team Alpha's practices (feature flags + canary + automated rollback) should be organization standard"
    actionability: high
    confidence: 0.85
    supporting_evidence:
      - "disc-004"
      - "success_factors analysis"
  - insight: "Friday deployments should be eliminated or require exceptional approval"
    actionability: high
    confidence: 0.9
    supporting_evidence:
      - "disc-001"
      - "by_day_of_week statistics"
  - insight: "Database migration process needs mandatory dry-run step"
    actionability: high
    confidence: 0.8
    supporting_evidence:
      - "disc-003"
      - "failure_modes analysis"
  - insight: "Deployment size is a lagging indicator - real factor is change scope without adequate safeguards"
    actionability: medium
    confidence: 0.7
    supporting_evidence:
      - "by_deployment_size statistics"
      - "canary correlation"
recommendations:
  - action: "Implement Friday deployment freeze"
    expected_impact: "Reduce overall failure rate by ~8%"
    priority: high
    rationale: "Friday failures are 3.2x higher; 10% of deploys but 22% of failures"
  - action: "Mandate migration dry-runs in CI pipeline"
    expected_impact: "Prevent ~78% of data-related failures"
    priority: high
    rationale: "Most severe failure mode with simple prevention"
  - action: "Standardize Team Alpha practices across organization"
    expected_impact: "Potentially improve success rate to 90%+"
    priority: high
    rationale: "Proven practices with measurable outcomes"
  - action: "Add deployment timing to CI checks (warn if >14:00)"
    expected_impact: "Reduce failure rate by 5-10%"
    priority: medium
    rationale: "Late deploys have less time for issue detection before EOD"
methodology: "Retrospective analysis of deployment records with outcome classification, factor correlation, and pattern mining"
confidence: 0.85
evidence_anchors:
  - "deployment_records/2023-07.json"
  - "deployment_records/2023-08.json"
  - "deployment_records/2023-09.json"
  - "deployment_records/2023-10.json"
  - "deployment_records/2023-11.json"
  - "deployment_records/2023-12.json"
  - "deployment_records/coverage_analysis.json"
  - "deployment_records/feature_flag_usage.json"
  - "deployment_records/timing_analysis.json"
assumptions:
  - "Deployment records are complete and accurate"
  - "24-hour window is appropriate for outcome assessment"
  - "Team practices are consistent within each team"
  - "External factors (infra issues) are evenly distributed"
```

**Evidence pattern:** Historical record analysis + statistical correlation + pattern mining

## Verification

- [ ] Outcome classifications are consistent and defensible
- [ ] Correlation vs causation is clearly distinguished
- [ ] Sample sizes support confidence levels claimed
- [ ] Recommendations are actionable and specific
- [ ] Temporal patterns account for confounding factors

**Verification tools:** Read (for record inspection), Grep (for pattern searching)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Distinguish correlation from causation explicitly
- Report sample sizes with all statistics
- Flag when data may be incomplete or biased
- Do not overfit patterns to small samples

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather historical data
- `search` - to locate relevant records
- `identify-entity` - to identify events and actors

**Commonly precedes:**
- `forecast-outcome` - using discovered patterns for prediction
- `generate-plan` - to plan improvements based on insights
- `summarize` - to create executive summary of findings

**Anti-patterns:**
- Never claim causation without experimental evidence
- Avoid single-factor explanations for complex outcomes

**Workflow references:**
- See `workflow_catalog.json#retrospective_analysis` for post-mortem workflows
- See `workflow_catalog.json#continuous_improvement` for process optimization
