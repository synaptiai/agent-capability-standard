---
name: compare-impact
description: Compare impacts of different interventions, decisions, or options to evaluate consequences. Use when assessing policy effects, change impacts, or decision outcomes.
argument-hint: "[intervention_a] [intervention_b] [impact_dimensions] [timeframe]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically compare the anticipated or measured impacts of different interventions, decisions, or options across multiple dimensions to support informed decision-making about consequences.

**Success criteria:**
- Impacts are assessed across all relevant dimensions
- Direct and indirect effects are distinguished
- Timeframes for impact realization are explicit
- Uncertainty in impact estimates is quantified

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `interventions` | Yes | array[object] | Options/decisions to compare impacts of |
| `impact_dimensions` | Yes | array[string] | Dimensions to assess (financial, operational, social, etc.) |
| `timeframe` | No | string | Time horizon for impact assessment (short/medium/long-term) |
| `stakeholders` | No | array[string] | Whose impacts to consider |
| `baseline` | No | object | Current state to measure impact against |
| `weights` | No | object | Relative importance of impact dimensions |

## Procedure

1) **Define impact dimensions**: Clarify what impacts to assess
   - Financial (cost, revenue, ROI)
   - Operational (efficiency, capacity, quality)
   - Human (employees, customers, community)
   - Technical (systems, infrastructure, security)
   - Strategic (competitive position, capabilities)

2) **Establish baseline**: Define current state
   - Metrics for each dimension
   - Trends without intervention
   - Existing constraints and dependencies

3) **Project impacts per intervention**: For each option
   - Direct impacts (immediate, certain)
   - Indirect impacts (cascading, secondary)
   - Magnitude and direction
   - Time to impact realization

4) **Assess by stakeholder**: If stakeholders specified
   - How each group is affected
   - Winners and losers
   - Mitigation needs for negative impacts

5) **Quantify uncertainty**: For each impact estimate
   - Confidence range (optimistic/pessimistic)
   - Key assumptions affecting estimate
   - Sensitivity to external factors

6) **Synthesize comparison**: Aggregate and weight
   - Apply dimension weights
   - Identify dominant option per dimension
   - Recommend based on overall impact profile

## Output Contract

Return a structured object:

```yaml
interventions:
  - id: string
    summary: string
    type: policy | decision | change | investment
comparison_dimensions:
  - name: string
    weight: number
    measurement: string  # How this dimension is measured
baseline:
  description: string
  metrics: object  # Current state per dimension
impact_matrix:
  - intervention_id: string
    impacts:
      - dimension: string
        direct_impact:
          direction: positive | negative | neutral
          magnitude: low | medium | high
          description: string
          estimate: string | number
          confidence_range: object  # low, expected, high
        indirect_impacts:
          - description: string
            magnitude: low | medium | high
            timeframe: string
        time_to_realize: string  # immediate, 3-6 months, 1+ year
        evidence_anchor: string
stakeholder_analysis:
  - stakeholder: string
    impacts_by_intervention:
      - intervention_id: string
        net_impact: positive | negative | mixed | neutral
        details: string
recommendation:
  choice: string
  rationale: string
  dominant_dimensions: array[string]  # Dimensions driving recommendation
  conditions: array[string]
  risk_factors: array[string]
tradeoffs:
  - intervention: string
    positive_impacts: array[string]
    negative_impacts: array[string]
    net_assessment: string
uncertainty_summary:
  highest_uncertainty: array[string]  # Which impacts are least certain
  key_assumptions: array[string]
  sensitivity_factors: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `interventions` | array | Options being compared |
| `comparison_dimensions` | array | Impact dimensions with weights |
| `baseline` | object | Current state reference |
| `impact_matrix` | array | Impacts per intervention-dimension |
| `stakeholder_analysis` | array | Per-stakeholder impact assessment |
| `recommendation` | object | Recommended option with rationale |
| `tradeoffs` | array | Positive/negative impacts per option |
| `uncertainty_summary` | object | Key uncertainties and sensitivities |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | Studies, data, or analysis cited |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Comparing Remote Work Policy Options

**Input:**
```yaml
interventions:
  - id: "full_remote"
    description: "100% remote work"
  - id: "hybrid_3_2"
    description: "3 days remote, 2 days office"
impact_dimensions: ["employee_satisfaction", "productivity", "cost"]
timeframe: "12 months"
stakeholders: ["employees", "finance"]
```

**Output:**
```yaml
interventions:
  - id: "full_remote"
    summary: "Fully distributed workforce"
    type: policy
  - id: "hybrid_3_2"
    summary: "Flexible hybrid model"
    type: policy
comparison_dimensions:
  - name: "employee_satisfaction"
    weight: 0.35
    measurement: "Survey score (0-100)"
  - name: "productivity"
    weight: 0.35
    measurement: "Output index"
  - name: "cost"
    weight: 0.30
    measurement: "Annual spend"
baseline:
  description: "Current office-first policy"
  metrics: { satisfaction: 72, productivity: 100, cost: "$2.4M" }
impact_matrix:
  - intervention_id: "full_remote"
    impacts:
      - dimension: "employee_satisfaction"
        direct_impact: { direction: positive, magnitude: high, estimate: "+18 pts" }
        confidence_range: { low: 85, expected: 90, high: 94 }
        time_to_realize: "3-6 months"
      - dimension: "productivity"
        direct_impact: { direction: positive, magnitude: low, estimate: "+5%" }
        indirect_impacts:
          - description: "Collaboration overhead"
            magnitude: medium
        time_to_realize: "6-12 months"
      - dimension: "cost"
        direct_impact: { direction: positive, magnitude: high, estimate: "-$1.9M" }
        time_to_realize: "immediate"
  - intervention_id: "hybrid_3_2"
    impacts:
      - dimension: "employee_satisfaction"
        direct_impact: { direction: positive, magnitude: medium, estimate: "+10 pts" }
        time_to_realize: "1-3 months"
      - dimension: "productivity"
        direct_impact: { direction: positive, magnitude: medium, estimate: "+8%" }
        time_to_realize: "3-6 months"
      - dimension: "cost"
        direct_impact: { direction: positive, magnitude: medium, estimate: "-$0.9M" }
        time_to_realize: "immediate"
stakeholder_analysis:
  - stakeholder: "employees"
    impacts_by_intervention:
      - intervention_id: "full_remote"
        net_impact: positive
        details: "High satisfaction, some miss social connection"
      - intervention_id: "hybrid_3_2"
        net_impact: positive
        details: "Good balance of flexibility and connection"
  - stakeholder: "finance"
    impacts_by_intervention:
      - intervention_id: "full_remote"
        net_impact: positive
        details: "Major cost savings"
      - intervention_id: "hybrid_3_2"
        net_impact: positive
        details: "Moderate savings"
recommendation:
  choice: "hybrid_3_2"
  rationale: "Best balance across dimensions"
  dominant_dimensions: ["productivity", "satisfaction"]
  conditions: ["Organization values collaboration"]
  risk_factors: ["Coordination overhead"]
tradeoffs:
  - intervention: "full_remote"
    positive_impacts: ["Highest satisfaction", "Max cost savings"]
    negative_impacts: ["Collaboration challenges"]
    net_assessment: "Best for individual-work-heavy orgs"
  - intervention: "hybrid_3_2"
    positive_impacts: ["Balanced approach", "Moderate savings"]
    negative_impacts: ["Scheduling complexity"]
    net_assessment: "Best overall for most organizations"
uncertainty_summary:
  highest_uncertainty: ["Long-term productivity effects"]
  key_assumptions: ["Market conditions stable"]
  sensitivity_factors: ["Competitor policies"]
confidence: 0.75
evidence_anchors:
  - "surveys/remote_work_study.pdf"
  - "finance/real_estate_analysis.xlsx"
assumptions:
  - "Employee preferences reflect market trends"
```

**Evidence pattern:** Multi-stakeholder surveys, financial analysis, and productivity studies.

## Verification

- [ ] All impact dimensions assessed for each intervention
- [ ] Direct and indirect impacts distinguished
- [ ] Confidence ranges provided for estimates
- [ ] Stakeholder impacts align with dimension analysis
- [ ] Recommendation consistent with weighted impact scores

**Verification tools:** Read (for studies and data), Grep (for searching evidence)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Distinguish factual impacts from projected impacts
- Flag when impact estimates are highly uncertain
- Do not present projections as certainties
- Stop and clarify when impact dimensions are ambiguous

## Bundled Scripts

This skill includes utility scripts for generating comparison tables:

### compare-table.sh

Located at: `scripts/compare-table.sh`

**Usage:**
```bash
./scripts/compare-table.sh <before_file> <after_file> [options]
```

**Options:**
- `--format markdown|csv|json` - Output format (default: markdown)
- `--output <file>` - Write to file instead of stdout
- `--help` - Show help message

**Features:**
- JSON diff with path-level change tracking
- Change type classification (added/removed/modified)
- Markdown tables for documentation
- CSV export for spreadsheet analysis
- JSON export for programmatic use

**Examples:**
```bash
# Generate markdown comparison table
./scripts/compare-table.sh state-v1.json state-v2.json

# Export as CSV
./scripts/compare-table.sh before.json after.json --format csv --output changes.csv

# Generate JSON diff
./scripts/compare-table.sh old-config.json new-config.json --format json
```

**Output Formats:**

*Markdown:*
| Path | Change Type | Before | After |
|------|-------------|--------|-------|
| `user.email` | Modified | `old@ex.com` | `new@ex.com` |

*JSON:*
```json
{"changes": [{"path": "user.email", "type": "modified", "before": "old@ex.com", "after": "new@ex.com"}]}
```

## Composition Patterns

**Commonly follows:**
- `estimate-impact` - to assess individual intervention impacts
- `retrieve` - to gather impact studies and data
- `forecast-outcome` - to project future impacts

**Commonly precedes:**
- `compare-plans` - using impact analysis to compare plans
- `generate-plan` - to plan mitigation for negative impacts
- `summarize` - to create impact summary for stakeholders

**Anti-patterns:**
- Never compare impacts without explicit time horizon
- Avoid single-dimension impact comparisons

**Workflow references:**
- See `workflow_catalog.json#policy_decision` for policy analysis workflows
