---
name: forecast-impact
description: Predict the future impact of an intervention or change over time. Use when projecting consequences, modeling downstream effects, or planning impact trajectories.
argument-hint: "[intervention] [--on <target>] [--horizon <period>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Predict how the impact of an intervention, change, or decision will evolve over time. This skill answers "what will be the effect of X on Y over the coming weeks/months?" Unlike estimate-impact (current/immediate), this projects impact trajectories into the future with temporal dynamics.

**Success criteria:**
- Impact trajectory over time is modeled
- Peak impact timing and magnitude are identified
- Decay or growth patterns are specified
- Scenarios explore different impact evolution paths

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `intervention` | Yes | string | The change or action whose future impact is being forecasted |
| `target` | Yes | string | What is being impacted |
| `time_horizon` | Yes | string | How far ahead to forecast impact |
| `current_impact` | No | object | Current or initial observed impact |
| `dynamics` | No | string | Expected pattern: sustained, decaying, compounding, delayed |

## Procedure

1) **Define the intervention and target**: Clarify what change is being analyzed.
   - What is the intervention? (new feature, policy change, code optimization)
   - What is the target of impact? (metric, behavior, system state)
   - When did/will the intervention occur?

2) **Assess initial impact**: Establish the starting point for projection.
   - What is the current or expected immediate impact?
   - How was this initial impact measured?
   - What is the baseline (without intervention)?

3) **Determine impact dynamics**: Model how impact evolves over time.
   - **Sustained**: Impact persists at stable level
   - **Decaying**: Impact diminishes over time (novelty effects, adaptation)
   - **Compounding**: Impact grows through feedback loops
   - **Delayed**: Impact takes time to materialize fully
   - **Phased**: Impact occurs in stages

4) **Identify temporal factors**: Consider what changes over time.
   - Will the intervention continue or is it one-time?
   - What feedback loops affect impact over time?
   - Are there saturation or ceiling effects?
   - Will external factors change?

5) **Generate time-series forecast**: Project impact at multiple time points.
   - Model impact trajectory curve
   - Identify peak impact timing
   - Determine long-term steady state

6) **Create scenarios**: Alternative impact evolution paths.
   - Best case: favorable dynamics, impact compounds
   - Expected: typical pattern for this type of intervention
   - Worst case: impact decays rapidly or reverses

7) **Format output**: Structure with time-based predictions.

## Output Contract

Return a structured object:

```yaml
forecast:
  target_type: impact
  intervention: string      # What is causing the impact
  target: string            # What is being impacted
  prediction: string        # Primary impact trajectory description
  time_horizon: string      # Forecast period
  probability: number       # Confidence in primary prediction (0-1)
  trajectory:
    initial: object         # Impact at start
    peak: object            # Maximum impact point
    steady_state: object    # Long-term stable impact
  scenarios:
    - name: string
      probability: number
      outcome:
        trajectory: string  # Description of impact evolution
        final_impact: string | number
drivers:
  - factor: string          # What influences impact trajectory
    direction: positive | negative | neutral
    magnitude: low | medium | high
uncertainties:
  - string                  # Key unknowns
confidence: number          # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.trajectory` | object | Impact at key time points (initial, peak, steady-state) |
| `scenarios` | array | Alternative impact evolution paths |
| `drivers` | array | Factors that shape the impact trajectory |
| `uncertainties` | array | Key unknowns that affect confidence |
| `confidence` | number | Certainty in trajectory prediction |

## Examples

### Example 1: Forecasting Impact of Performance Optimization

**Input:**
```yaml
intervention: "API response time optimization (200ms reduction)"
target: "user engagement metrics"
time_horizon: "6 months"
current_impact:
  sessions_per_user: "+3% after 1 week"
  bounce_rate: "-8% after 1 week"
```

**Output:**
```yaml
forecast:
  target_type: impact
  intervention: "API response time optimization (200ms reduction)"
  target: "user engagement metrics"
  prediction: "Sustained +2-4% engagement improvement, with gradual decay to +2% steady state"
  time_horizon: "6 months"
  probability: 0.68
  trajectory:
    initial:
      timing: "week 1"
      impact: "+3% sessions, -8% bounce rate"
      notes: "Immediate response to faster experience"
    peak:
      timing: "weeks 2-4"
      impact: "+5% sessions, -10% bounce rate"
      notes: "Full effect as users experience improvement across multiple visits"
    steady_state:
      timing: "month 3+"
      impact: "+2% sessions, -5% bounce rate"
      notes: "New baseline established; novelty effect faded but core improvement persists"
  scenarios:
    - name: "compounding"
      probability: 0.20
      outcome:
        trajectory: "Impact grows as faster experience drives SEO improvement and word-of-mouth"
        final_impact: "+6% sessions, -12% bounce rate"
    - name: "sustained"
      probability: 0.55
      outcome:
        trajectory: "Impact stabilizes after initial peak, modest decay to new baseline"
        final_impact: "+2% sessions, -5% bounce rate"
    - name: "decay"
      probability: 0.25
      outcome:
        trajectory: "Impact fades as users adapt; other factors dominate engagement"
        final_impact: "+0.5% sessions, -2% bounce rate"
drivers:
  - factor: "user expectation adaptation"
    direction: negative
    magnitude: medium
  - factor: "SEO ranking improvement from speed"
    direction: positive
    magnitude: medium
  - factor: "competitor performance changes"
    direction: negative
    magnitude: low
  - factor: "mobile user segment growth"
    direction: positive
    magnitude: medium
uncertainties:
  - "How much of initial impact is novelty effect"
  - "Whether SEO benefits will materialize"
  - "Competitor response timeline"
confidence: 0.62
evidence_anchors:
  - "analytics/engagement_post_optimization.csv:week1"
  - "research/speed_impact_studies.md"
  - "industry/google_core_web_vitals.md"
assumptions:
  - "No other major changes to user experience"
  - "Performance improvement is maintained (no regressions)"
  - "User base composition remains stable"
  - "Mobile traffic proportion continues increasing"
```

**Evidence pattern:** Initial observed impact with dynamics modeling from research.

---

### Example 2: Forecasting Impact of Pricing Change

**Input:**
```yaml
intervention: "15% price increase on enterprise tier"
target: "revenue and churn"
time_horizon: "12 months"
dynamics: "phased"
```

**Output:**
```yaml
forecast:
  target_type: impact
  intervention: "15% price increase on enterprise tier"
  target: "revenue and churn"
  prediction: "Net +8-12% revenue increase, with 3-5% churn spike in months 2-4"
  time_horizon: "12 months"
  probability: 0.60
  trajectory:
    initial:
      timing: "months 1-2"
      impact: "Revenue +15% from renewals at new price; churn at baseline"
      notes: "Contracts renewing see immediate price; new customers unchanged"
    peak:
      timing: "months 2-4"
      impact: "Churn spike to +3-5% above baseline as price-sensitive customers leave"
      notes: "Lagged churn as customers reach renewal date and evaluate alternatives"
    steady_state:
      timing: "month 6+"
      impact: "Net revenue +10% vs pre-increase; churn returns to baseline +0.5%"
      notes: "Customer base rebalanced toward value-focused segments"
  scenarios:
    - name: "revenue_wins"
      probability: 0.35
      outcome:
        trajectory: "Minimal churn; customers accept price as value justified"
        final_impact: "Revenue +14%, churn +1%"
    - name: "balanced"
      probability: 0.45
      outcome:
        trajectory: "Moderate churn offset by higher revenue per customer"
        final_impact: "Revenue +10%, churn +3%"
    - name: "churn_dominates"
      probability: 0.20
      outcome:
        trajectory: "Significant churn erodes revenue gains"
        final_impact: "Revenue +2%, churn +7%"
drivers:
  - factor: "perceived value vs. alternatives"
    direction: positive
    magnitude: high
  - factor: "customer price sensitivity"
    direction: negative
    magnitude: high
  - factor: "contract lock-in periods"
    direction: positive
    magnitude: medium
  - factor: "competitor pricing response"
    direction: negative
    magnitude: medium
uncertainties:
  - "Actual price elasticity of enterprise customers"
  - "Competitor response timeline and magnitude"
  - "Customer perception of value justifying increase"
confidence: 0.55
evidence_anchors:
  - "finance/pricing_elasticity_study.pdf"
  - "sales/enterprise_tier_analysis.xlsx"
  - "competitive/pricing_benchmark.md"
assumptions:
  - "No new product features offset price perception"
  - "Competitors maintain current pricing for 3+ months"
  - "Economic conditions remain stable"
  - "Sales team executes value messaging effectively"
```

**Evidence pattern:** Phased impact modeling with revenue and churn dynamics.

## Verification

- [ ] Intervention and target are clearly defined
- [ ] Trajectory includes initial, peak, and steady-state points
- [ ] Dynamics (sustained, decaying, compounding, phased) are specified
- [ ] Scenarios cover range of possible impact evolutions
- [ ] Uncertainties acknowledge key unknowns

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Note when impact dynamics are highly uncertain
- Distinguish between causal impact and correlated changes
- Be explicit about novelty vs. sustained effects

## Composition Patterns

**Commonly follows:**
- `estimate-impact` - Current impact is starting point for projection
- `forecast-outcome` - When outcome forecast needs impact decomposition
- `retrieve` - Historical impact data from similar interventions

**Commonly precedes:**
- `compare` - To compare impact trajectories across options
- `plan` - When impact forecast informs strategy
- `forecast-risk` - When impact affects risk exposure over time

**Anti-patterns:**
- Never assume impact remains constant over time
- Avoid forecasting impact without understanding dynamics type

**Workflow references:**
- See `workflow_catalog.json#change_management` for impact forecasting context
