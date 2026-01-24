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
    description: "100% remote work for all eligible employees"
  - id: "hybrid_3_2"
    description: "3 days remote, 2 days in office"
  - id: "office_first"
    description: "Office by default, remote by exception"
impact_dimensions:
  - "employee_satisfaction"
  - "productivity"
  - "real_estate_cost"
  - "collaboration_quality"
  - "talent_acquisition"
timeframe: "12 months"
stakeholders:
  - "employees"
  - "managers"
  - "finance"
  - "HR"
baseline:
  current_policy: "Pre-pandemic office-first"
  satisfaction_score: 72
  productivity_index: 100
  office_space: "50,000 sqft"
weights:
  employee_satisfaction: 0.25
  productivity: 0.25
  real_estate_cost: 0.15
  collaboration_quality: 0.2
  talent_acquisition: 0.15
```

**Output:**
```yaml
interventions:
  - id: "full_remote"
    summary: "Fully distributed workforce with no required office presence"
    type: policy
  - id: "hybrid_3_2"
    summary: "Flexible hybrid with 3 remote days and 2 office days weekly"
    type: policy
  - id: "office_first"
    summary: "Traditional office-centric with remote as exception"
    type: policy
comparison_dimensions:
  - name: "employee_satisfaction"
    weight: 0.25
    measurement: "Annual survey score (0-100)"
  - name: "productivity"
    weight: 0.25
    measurement: "Output per employee relative to baseline (index)"
  - name: "real_estate_cost"
    weight: 0.15
    measurement: "Annual cost in USD"
  - name: "collaboration_quality"
    weight: 0.2
    measurement: "Cross-team project success rate and survey"
  - name: "talent_acquisition"
    weight: 0.15
    measurement: "Offer acceptance rate and talent pool size"
baseline:
  description: "Pre-pandemic office-first policy"
  metrics:
    employee_satisfaction: 72
    productivity: 100
    real_estate_cost: "$2.4M/year"
    collaboration_quality: 78
    talent_acquisition: "85% acceptance, local pool only"
impact_matrix:
  - intervention_id: "full_remote"
    impacts:
      - dimension: "employee_satisfaction"
        direct_impact:
          direction: positive
          magnitude: high
          description: "Significant improvement from flexibility and no commute"
          estimate: "+18 points to 90"
          confidence_range:
            low: 85
            expected: 90
            high: 94
        indirect_impacts:
          - description: "Some employees may feel isolated"
            magnitude: medium
            timeframe: "6-12 months"
        time_to_realize: "immediate"
        evidence_anchor: "surveys/remote_work_study.pdf:42"
      - dimension: "productivity"
        direct_impact:
          direction: positive
          magnitude: medium
          description: "Fewer interruptions, focus time improved"
          estimate: "+8% to 108"
          confidence_range:
            low: 102
            expected: 108
            high: 112
        indirect_impacts:
          - description: "May decline for collaborative roles"
            magnitude: medium
            timeframe: "3-6 months"
        time_to_realize: "1-3 months"
        evidence_anchor: "studies/remote_productivity_meta.pdf"
      - dimension: "real_estate_cost"
        direct_impact:
          direction: positive
          magnitude: high
          description: "Can eliminate or drastically reduce office space"
          estimate: "-80% to $480K"
          confidence_range:
            low: "$400K"
            expected: "$480K"
            high: "$600K"
        indirect_impacts:
          - description: "May need co-working stipends"
            magnitude: low
            timeframe: "immediate"
        time_to_realize: "6-12 months (lease timing)"
        evidence_anchor: "finance/real_estate_analysis.xlsx"
      - dimension: "collaboration_quality"
        direct_impact:
          direction: negative
          magnitude: medium
          description: "Spontaneous collaboration and mentoring decline"
          estimate: "-12 points to 66"
          confidence_range:
            low: 60
            expected: 66
            high: 72
        indirect_impacts:
          - description: "New tools may partially compensate"
            magnitude: low
            timeframe: "6+ months"
        time_to_realize: "3-6 months"
        evidence_anchor: "surveys/collaboration_remote.pdf"
      - dimension: "talent_acquisition"
        direct_impact:
          direction: positive
          magnitude: high
          description: "Global talent pool, no geographic restrictions"
          estimate: "95% acceptance, national pool"
          confidence_range:
            low: "92%"
            expected: "95%"
            high: "97%"
        indirect_impacts: []
        time_to_realize: "immediate"
        evidence_anchor: "hr/talent_market_analysis.pdf"
  - intervention_id: "hybrid_3_2"
    impacts:
      - dimension: "employee_satisfaction"
        direct_impact:
          direction: positive
          magnitude: medium
          description: "Balance of flexibility and connection"
          estimate: "+10 points to 82"
          confidence_range:
            low: 78
            expected: 82
            high: 86
        indirect_impacts:
          - description: "Coordination overhead may frustrate some"
            magnitude: low
            timeframe: "1-3 months"
        time_to_realize: "1-3 months"
        evidence_anchor: "surveys/hybrid_satisfaction.pdf"
      - dimension: "productivity"
        direct_impact:
          direction: positive
          magnitude: medium
          description: "Best of both - focus and collaboration days"
          estimate: "+5% to 105"
          confidence_range:
            low: 102
            expected: 105
            high: 108
        indirect_impacts: []
        time_to_realize: "1-3 months"
        evidence_anchor: "studies/hybrid_productivity.pdf"
      - dimension: "real_estate_cost"
        direct_impact:
          direction: positive
          magnitude: medium
          description: "Can reduce to hoteling model"
          estimate: "-40% to $1.44M"
          confidence_range:
            low: "$1.2M"
            expected: "$1.44M"
            high: "$1.6M"
        indirect_impacts: []
        time_to_realize: "6-12 months"
        evidence_anchor: "finance/real_estate_analysis.xlsx"
      - dimension: "collaboration_quality"
        direct_impact:
          direction: neutral
          magnitude: low
          description: "Maintained through structured office days"
          estimate: "0 change, stays at 78"
          confidence_range:
            low: 74
            expected: 78
            high: 82
        indirect_impacts: []
        time_to_realize: "immediate"
        evidence_anchor: "surveys/hybrid_collaboration.pdf"
      - dimension: "talent_acquisition"
        direct_impact:
          direction: positive
          magnitude: medium
          description: "Expanded regional pool with hybrid flexibility"
          estimate: "90% acceptance, regional pool"
          confidence_range:
            low: "87%"
            expected: "90%"
            high: "93%"
        indirect_impacts: []
        time_to_realize: "immediate"
        evidence_anchor: "hr/talent_market_analysis.pdf"
  - intervention_id: "office_first"
    impacts:
      - dimension: "employee_satisfaction"
        direct_impact:
          direction: negative
          magnitude: medium
          description: "Perceived regression after pandemic flexibility"
          estimate: "-8 points to 64"
          confidence_range:
            low: 58
            expected: 64
            high: 68
        indirect_impacts:
          - description: "Possible attrition of flexibility-seeking talent"
            magnitude: high
            timeframe: "3-6 months"
        time_to_realize: "immediate"
        evidence_anchor: "surveys/return_to_office.pdf"
      - dimension: "productivity"
        direct_impact:
          direction: negative
          magnitude: low
          description: "Return to pre-pandemic levels"
          estimate: "0 change, stays at 100"
          confidence_range:
            low: 96
            expected: 100
            high: 102
        indirect_impacts:
          - description: "Commute fatigue may reduce engagement"
            magnitude: low
            timeframe: "3-6 months"
        time_to_realize: "immediate"
        evidence_anchor: "studies/office_productivity.pdf"
      - dimension: "real_estate_cost"
        direct_impact:
          direction: neutral
          magnitude: low
          description: "Maintain current office footprint"
          estimate: "0 change, stays at $2.4M"
          confidence_range:
            low: "$2.4M"
            expected: "$2.4M"
            high: "$2.5M"
        indirect_impacts: []
        time_to_realize: "immediate"
        evidence_anchor: "finance/real_estate_analysis.xlsx"
      - dimension: "collaboration_quality"
        direct_impact:
          direction: positive
          magnitude: medium
          description: "Spontaneous collaboration restored"
          estimate: "+8 points to 86"
          confidence_range:
            low: 82
            expected: 86
            high: 90
        indirect_impacts: []
        time_to_realize: "1-3 months"
        evidence_anchor: "surveys/office_collaboration.pdf"
      - dimension: "talent_acquisition"
        direct_impact:
          direction: negative
          magnitude: high
          description: "Limited to local candidates, many expect flexibility"
          estimate: "70% acceptance, local pool only"
          confidence_range:
            low: "65%"
            expected: "70%"
            high: "75%"
        indirect_impacts:
          - description: "May lose candidates to flexible competitors"
            magnitude: high
            timeframe: "immediate"
        time_to_realize: "immediate"
        evidence_anchor: "hr/talent_market_analysis.pdf"
stakeholder_analysis:
  - stakeholder: "employees"
    impacts_by_intervention:
      - intervention_id: "full_remote"
        net_impact: positive
        details: "High satisfaction, but some may miss social connection"
      - intervention_id: "hybrid_3_2"
        net_impact: positive
        details: "Good balance, some coordination overhead"
      - intervention_id: "office_first"
        net_impact: negative
        details: "Perceived loss of flexibility, potential attrition"
  - stakeholder: "managers"
    impacts_by_intervention:
      - intervention_id: "full_remote"
        net_impact: mixed
        details: "New management skills required, harder to assess performance"
      - intervention_id: "hybrid_3_2"
        net_impact: positive
        details: "Structured face time enables mentoring and oversight"
      - intervention_id: "office_first"
        net_impact: positive
        details: "Traditional management easier, but may face employee pushback"
  - stakeholder: "finance"
    impacts_by_intervention:
      - intervention_id: "full_remote"
        net_impact: positive
        details: "Major cost savings on real estate"
      - intervention_id: "hybrid_3_2"
        net_impact: positive
        details: "Moderate cost savings"
      - intervention_id: "office_first"
        net_impact: neutral
        details: "No change from current costs"
  - stakeholder: "HR"
    impacts_by_intervention:
      - intervention_id: "full_remote"
        net_impact: positive
        details: "Expanded talent pool, but equity challenges across locations"
      - intervention_id: "hybrid_3_2"
        net_impact: positive
        details: "Balanced approach, easier policy administration"
      - intervention_id: "office_first"
        net_impact: negative
        details: "Talent attraction challenges, potential attrition management"
recommendation:
  choice: "hybrid_3_2"
  rationale: "Best balance across all dimensions; avoids collaboration decline while improving satisfaction and costs"
  dominant_dimensions:
    - "collaboration_quality"
    - "employee_satisfaction"
    - "productivity"
  conditions:
    - "Organization values collaboration highly"
    - "Real estate flexibility is possible"
    - "Role mix includes both collaborative and individual work"
  risk_factors:
    - "Coordination overhead may frustrate some teams"
    - "Uneven implementation across departments"
tradeoffs:
  - intervention: "full_remote"
    positive_impacts:
      - "Highest employee satisfaction (+18)"
      - "Largest cost savings (-80% real estate)"
      - "Best talent acquisition (global pool)"
    negative_impacts:
      - "Collaboration quality decline (-12)"
      - "Management complexity increase"
    net_assessment: "Best for individual-work-heavy organizations"
  - intervention: "hybrid_3_2"
    positive_impacts:
      - "Good satisfaction improvement (+10)"
      - "Moderate cost savings (-40%)"
      - "Maintains collaboration quality"
    negative_impacts:
      - "Coordination overhead"
      - "Some scheduling complexity"
    net_assessment: "Best overall balance for most organizations"
  - intervention: "office_first"
    positive_impacts:
      - "Best collaboration quality (+8)"
      - "Simplest management model"
    negative_impacts:
      - "Satisfaction decline (-8)"
      - "Talent acquisition challenges"
      - "No cost savings"
    net_assessment: "Best for collaboration-intensive organizations willing to accept talent limitations"
uncertainty_summary:
  highest_uncertainty:
    - "Long-term productivity effects (study data limited)"
    - "Collaboration quality measurement reliability"
  key_assumptions:
    - "Market conditions for talent remain competitive"
    - "Technology enables effective remote collaboration"
    - "Real estate market allows flexibility"
  sensitivity_factors:
    - "Industry/competitor policies"
    - "Economic conditions affecting real estate"
    - "Technology improvements for collaboration"
confidence: 0.7
evidence_anchors:
  - "surveys/remote_work_study.pdf:42"
  - "studies/remote_productivity_meta.pdf"
  - "finance/real_estate_analysis.xlsx"
  - "surveys/collaboration_remote.pdf"
  - "hr/talent_market_analysis.pdf"
  - "surveys/hybrid_satisfaction.pdf"
  - "studies/hybrid_productivity.pdf"
  - "surveys/return_to_office.pdf"
assumptions:
  - "Employee preferences reflect broader market trends"
  - "Productivity measures are comparable across work modes"
  - "Real estate costs can be adjusted within 12 months"
  - "Current collaboration tools are representative"
```

**Evidence pattern:** Surveys + productivity studies + financial analysis + market research

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
