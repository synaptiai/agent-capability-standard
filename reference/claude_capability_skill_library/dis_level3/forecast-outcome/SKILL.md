---
name: forecast-outcome
description: Predict future outcome values or probabilities given current trajectory. Use when projecting results, predicting success rates, or modeling future states.
argument-hint: "[outcome] [--horizon <period>] [--scenarios]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Predict the future value, state, or probability of an outcome based on current conditions, trends, and influencing factors. This skill answers "what will the outcome be in the future?" Unlike estimate-outcome (current state), this projects forward in time with scenario analysis.

**Success criteria:**
- Future outcome is predicted with probability and confidence bounds
- Multiple scenarios explore different possible futures
- Key drivers and their influence direction are identified
- Uncertainty increases appropriately with time horizon

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `outcome` | Yes | string | The outcome to forecast (e.g., "quarterly revenue", "user retention", "project success") |
| `time_horizon` | Yes | string | How far ahead to forecast (e.g., "30 days", "Q2 2024", "end of year") |
| `current_state` | No | object | Current outcome value or trajectory |
| `factors` | No | array | Known factors that will influence the outcome |

## Procedure

1) **Define the outcome and time horizon**: Clarify what is being predicted and when.
   - What is the measurable outcome?
   - What is the forecast horizon?
   - What is the current baseline value?

2) **Assess current trajectory**: Analyze the trend toward this outcome.
   - What is the current value or progress?
   - What is the trend direction and velocity?
   - How stable is the trend?

3) **Identify influencing factors**: List what will affect the outcome.
   - What known events will occur in the forecast period?
   - What external factors could change?
   - What interventions are planned?

4) **Select forecasting approach**: Choose method based on data and outcome type.
   - **Trend extrapolation**: Continue current trajectory
   - **Regression model**: Use predictive variables
   - **Scenario modeling**: Define distinct future paths
   - **Bayesian updating**: Incorporate new information as it arrives
   - **Simulation**: Monte Carlo with uncertain inputs

5) **Generate scenario forecasts**: Create multiple outcome predictions.
   - **Base case**: Most likely trajectory continues
   - **Upside scenario**: Positive factors materialize
   - **Downside scenario**: Negative factors materialize
   - Assign probabilities to each scenario

6) **Quantify uncertainty**: Wider bounds for longer horizons.
   - Account for compounding uncertainty
   - Note what could invalidate the forecast
   - Identify leading indicators to monitor

7) **Format output**: Structure with predictions and confidence.

## Output Contract

Return a structured object:

```yaml
forecast:
  target_type: outcome
  outcome: string           # What is being forecasted
  prediction: string | number  # Primary outcome prediction
  time_horizon: string      # Forecast period
  probability: number       # Confidence in primary prediction (0-1)
  scenarios:
    - name: string          # base, upside, downside
      probability: number   # Probability of this scenario
      outcome:
        value: string | number
        rationale: string
drivers:
  - factor: string          # What influences outcome
    direction: positive | negative | neutral
    magnitude: low | medium | high
leading_indicators:
  - indicator: string       # What to monitor
    current_value: string
    threshold: string       # Signal that forecast is off-track
confidence: number          # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.prediction` | string/number | The most likely future outcome value |
| `scenarios` | array | Alternative outcomes with probabilities |
| `drivers` | array | Factors that push outcome positive or negative |
| `leading_indicators` | array | Early warning signals for forecast accuracy |
| `confidence` | number | Decreases with longer horizons and fewer data points |

## Examples

### Example 1: Forecasting Quarterly Conversion Rate

**Input:**
```yaml
outcome: "trial-to-paid conversion rate"
time_horizon: "Q2 2024"
current_state:
  current_rate: "12.5%"
  trend: "increasing 0.3% per month"
factors:
  - "new onboarding flow launching Feb 15"
  - "competitor pricing decrease announced"
  - "marketing spend increasing 20%"
```

**Output:**
```yaml
forecast:
  target_type: outcome
  outcome: "trial-to-paid conversion rate"
  prediction: "14.2%"
  time_horizon: "Q2 2024 (end of June)"
  probability: 0.55
  scenarios:
    - name: "upside"
      probability: 0.25
      outcome:
        value: "16.0%"
        rationale: "New onboarding flow exceeds expectations (+2%), marketing drives high-quality leads"
    - name: "base"
      probability: 0.50
      outcome:
        value: "14.2%"
        rationale: "Current trend continues (+0.3%/month), onboarding adds +1%, competitor pressure neutralized by marketing"
    - name: "downside"
      probability: 0.25
      outcome:
        value: "11.8%"
        rationale: "Competitor pricing draws away price-sensitive segment, onboarding issues cause drop"
drivers:
  - factor: "new onboarding flow"
    direction: positive
    magnitude: high
  - factor: "competitor pricing decrease"
    direction: negative
    magnitude: medium
  - factor: "increased marketing spend"
    direction: positive
    magnitude: medium
  - factor: "economic conditions"
    direction: negative
    magnitude: low
leading_indicators:
  - indicator: "onboarding completion rate"
    current_value: "67%"
    threshold: "<60% signals onboarding issues"
  - indicator: "trial signup volume"
    current_value: "2,400/month"
    threshold: "<2,000 signals demand issues"
  - indicator: "time-to-first-value"
    current_value: "3.2 days"
    threshold: ">5 days signals UX problems"
confidence: 0.62
evidence_anchors:
  - "analytics/conversion_trends:12m"
  - "product/onboarding_redesign.md:expected_impact"
  - "competitive/pricing_analysis.xlsx"
  - "marketing/q2_plan.md:budget"
assumptions:
  - "New onboarding flow launches on schedule"
  - "Marketing spend translates to qualified leads"
  - "No major product outages during Q2"
  - "Economic conditions remain stable"
```

**Evidence pattern:** Trend extrapolation with intervention adjustments.

---

### Example 2: Forecasting Project Success Probability

**Input:**
```yaml
outcome: "project delivered on-time and on-budget"
time_horizon: "project end (8 weeks)"
current_state:
  schedule_status: "1 week behind"
  budget_consumed: "55% (of 50% expected)"
  scope_changes: 2
```

**Output:**
```yaml
forecast:
  target_type: outcome
  outcome: "project delivered on-time and on-budget"
  prediction: "60% probability of success"
  time_horizon: "8 weeks"
  probability: 0.60
  scenarios:
    - name: "success"
      probability: 0.60
      outcome:
        value: "on-time and on-budget"
        rationale: "Team recovers 1 week delay through overtime, no additional scope changes, budget overrun absorbed by contingency"
    - name: "partial_success"
      probability: 0.25
      outcome:
        value: "on-time but over-budget by 10-15%"
        rationale: "Recovery requires additional resources, depletes contingency and exceeds by moderate amount"
    - name: "failure"
      probability: 0.15
      outcome:
        value: "late and over-budget"
        rationale: "Additional scope changes or technical issues compound delays, recovery not possible"
drivers:
  - factor: "scope stability"
    direction: positive
    magnitude: high
  - factor: "current schedule delay"
    direction: negative
    magnitude: medium
  - factor: "team experience"
    direction: positive
    magnitude: medium
  - factor: "technical risk in remaining work"
    direction: negative
    magnitude: medium
leading_indicators:
  - indicator: "weekly velocity"
    current_value: "28 story points"
    threshold: "<25 signals continued slippage"
  - indicator: "open blockers"
    current_value: "2"
    threshold: ">4 signals systemic issues"
  - indicator: "scope change requests"
    current_value: "2 approved"
    threshold: ">3 total signals scope creep"
confidence: 0.55
evidence_anchors:
  - "project/status_report_week6.md"
  - "jira/burndown:sprint_history"
  - "finance/project_budget.xlsx:current"
assumptions:
  - "No major scope changes in remaining 8 weeks"
  - "Team availability remains stable"
  - "Technical approach is sound (no major rework)"
  - "Stakeholder priorities don't shift"
```

**Evidence pattern:** Project health indicators with probability modeling.

## Verification

- [ ] Outcome is measurable and clearly defined
- [ ] Time horizon is explicit
- [ ] Scenarios cover optimistic, likely, and pessimistic cases
- [ ] Scenario probabilities sum to approximately 1.0
- [ ] Leading indicators are actionable and monitorable

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Clearly state that forecasts are predictions, not guarantees
- Increase uncertainty bounds for longer time horizons
- Note when forecast depends on external factors outside control

## Composition Patterns

**Commonly follows:**
- `estimate-outcome` - Current state is baseline for projection
- `retrieve` - Historical data for trend analysis
- `estimate-world` - World state provides context for forecast

**Commonly precedes:**
- `compare` - To compare forecast outcomes across options
- `plan` - When forecast informs strategy
- `forecast-risk` - When outcome affects risk profile

**Anti-patterns:**
- Never present forecasts as certainties
- Avoid forecasting outcomes with no historical baseline

**Workflow references:**
- See `workflow_catalog.json#strategic_planning` for outcome forecasting context
