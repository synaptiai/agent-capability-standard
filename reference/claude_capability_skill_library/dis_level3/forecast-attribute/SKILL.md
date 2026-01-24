---
name: forecast-attribute
description: Predict how an entity's attribute will evolve over time. Use when projecting metrics, anticipating quality changes, or modeling property trajectories.
argument-hint: "[entity] [attribute] [--horizon <period>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Predict how an entity's attribute will change over a specified time horizon. This skill answers "what will attribute X of entity Y be in the future?" Unlike estimate-attribute (current value), this projects attribute evolution forward in time with trend analysis and scenario modeling.

**Success criteria:**
- Future attribute values are predicted with uncertainty bounds
- Trend direction and velocity are identified
- Factors driving attribute change are specified
- Scenarios explore different evolution paths

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entity` | Yes | string | The entity whose attribute is being forecasted |
| `attribute` | Yes | string | The attribute to forecast (e.g., "code quality score", "team velocity", "system latency") |
| `time_horizon` | Yes | string | How far ahead to forecast |
| `current_value` | No | object | Current attribute value and trend |
| `interventions` | No | array | Planned changes that will affect the attribute |

## Procedure

1) **Define the attribute and current state**: Establish what is being forecasted.
   - What is the attribute and how is it measured?
   - What is the current value?
   - What has been the recent trend?

2) **Analyze historical patterns**: Examine how the attribute has changed.
   - What is the trend direction? (increasing, decreasing, stable)
   - What is the rate of change?
   - Are there cyclical patterns?
   - What caused past inflection points?

3) **Identify change drivers**: List factors that will affect the attribute.
   - **Planned interventions**: Known changes that will impact attribute
   - **External factors**: Market, technology, regulatory changes
   - **Internal factors**: Resource changes, strategy shifts
   - **Natural evolution**: Organic growth or decay patterns

4) **Select forecasting model**: Choose approach based on attribute type.
   - **Linear trend**: Constant rate of change
   - **Exponential**: Compounding growth or decay
   - **Logistic**: Bounded growth toward ceiling
   - **Cyclical**: Repeating patterns with trend
   - **Step function**: Discrete changes from interventions

5) **Generate forecasts at time points**: Project attribute values.
   - Calculate values at key milestones
   - Apply intervention effects at appropriate times
   - Widen confidence intervals over time

6) **Create scenarios**: Model different evolution paths.
   - Optimistic: favorable conditions, interventions succeed
   - Expected: typical trajectory
   - Pessimistic: challenges emerge, interventions underperform

7) **Format output**: Structure with time-series predictions.

## Output Contract

Return a structured object:

```yaml
forecast:
  target_type: attribute
  entity: string            # What entity the attribute belongs to
  attribute: string         # The attribute being forecasted
  prediction: string | number  # Primary end-state prediction
  time_horizon: string      # Forecast period
  probability: number       # Confidence in primary prediction (0-1)
  trajectory:
    - timestamp: string     # Point in time
      value: number | string  # Predicted value
      confidence: number    # Confidence at this point
      notes: string         # What influences value here
  scenarios:
    - name: string
      probability: number
      outcome:
        final_value: string | number
        trajectory: string  # Evolution description
drivers:
  - factor: string          # What influences attribute
    direction: positive | negative | neutral
    magnitude: low | medium | high
interventions:
  - event: string           # Planned change
    timing: string
    expected_effect: string
confidence: number          # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.trajectory` | array | Attribute values at multiple time points |
| `drivers` | array | Factors shaping attribute evolution |
| `interventions` | array | Planned changes with expected effects |
| `scenarios` | array | Alternative evolution paths |
| `confidence` | number | Decreases with longer horizons |

## Examples

### Example 1: Forecasting Code Quality Score

**Input:**
```yaml
entity: "payment-service"
attribute: "maintainability index"
time_horizon: "6 months"
current_value:
  value: 62
  scale: "0-100"
  trend: "-1.5 points per month"
interventions:
  - "refactoring sprint in month 2"
  - "new linting rules in month 3"
```

**Output:**
```yaml
forecast:
  target_type: attribute
  entity: "payment-service"
  attribute: "maintainability index"
  prediction: 68
  time_horizon: "6 months"
  probability: 0.60
  trajectory:
    - timestamp: "month 1"
      value: 60
      confidence: 0.85
      notes: "Continued decline at current rate"
    - timestamp: "month 2"
      value: 65
      confidence: 0.75
      notes: "Refactoring sprint adds +8 points, offsetting natural decline"
    - timestamp: "month 3"
      value: 66
      confidence: 0.70
      notes: "New linting rules prevent further decline, minor improvement"
    - timestamp: "month 4"
      value: 67
      confidence: 0.65
      notes: "New code follows better patterns"
    - timestamp: "month 6"
      value: 68
      confidence: 0.55
      notes: "Gradual improvement as codebase stabilizes"
  scenarios:
    - name: "improvement_accelerates"
      probability: 0.25
      outcome:
        final_value: 75
        trajectory: "Refactoring culture takes hold; team prioritizes quality"
    - name: "moderate_improvement"
      probability: 0.50
      outcome:
        final_value: 68
        trajectory: "Interventions succeed as planned; gradual improvement"
    - name: "stagnation"
      probability: 0.25
      outcome:
        final_value: 58
        trajectory: "Refactoring sprint descoped; feature pressure continues"
drivers:
  - factor: "feature development velocity"
    direction: negative
    magnitude: medium
  - factor: "refactoring sprint"
    direction: positive
    magnitude: high
  - factor: "linting automation"
    direction: positive
    magnitude: medium
  - factor: "team expertise"
    direction: positive
    magnitude: low
interventions:
  - event: "refactoring sprint"
    timing: "month 2"
    expected_effect: "+8 points immediate improvement"
  - event: "linting rules activation"
    timing: "month 3"
    expected_effect: "prevents future decline, +1 point/month improvement"
confidence: 0.58
evidence_anchors:
  - "sonar/maintainability_trend:12m"
  - "project/refactoring_plan.md"
  - "engineering/linting_proposal.md"
assumptions:
  - "Refactoring sprint is not descoped"
  - "Linting rules are adopted by team"
  - "Feature pressure doesn't override quality focus"
  - "No major new complexity added"
```

**Evidence pattern:** Trend extrapolation with intervention impact modeling.

---

### Example 2: Forecasting Team Velocity

**Input:**
```yaml
entity: "platform-team"
attribute: "sprint velocity"
time_horizon: "Q2 (3 months)"
current_value:
  value: 45
  unit: "story points per sprint"
  trend: "stable (43-47 range)"
interventions:
  - "2 new developers joining in month 1"
  - "new CI/CD pipeline in month 2"
```

**Output:**
```yaml
forecast:
  target_type: attribute
  entity: "platform-team"
  attribute: "sprint velocity"
  prediction: 58
  time_horizon: "end of Q2 (3 months)"
  probability: 0.55
  trajectory:
    - timestamp: "sprint 1 (month 1)"
      value: 42
      confidence: 0.80
      notes: "Initial dip as new developers onboard, team adjusts"
    - timestamp: "sprint 2"
      value: 44
      confidence: 0.75
      notes: "Recovery to baseline; new team members ramping"
    - timestamp: "sprint 3 (month 2)"
      value: 50
      confidence: 0.70
      notes: "New CI/CD reduces friction; new devs productive"
    - timestamp: "sprint 4"
      value: 55
      confidence: 0.65
      notes: "Team hitting stride with full capacity"
    - timestamp: "sprint 6 (month 3)"
      value: 58
      confidence: 0.55
      notes: "Full velocity with expanded team"
  scenarios:
    - name: "rapid_integration"
      probability: 0.20
      outcome:
        final_value: 65
        trajectory: "New hires exceptionally strong fit; CI/CD exceeds expectations"
    - name: "typical_growth"
      probability: 0.55
      outcome:
        final_value: 58
        trajectory: "Standard ramp-up curve; interventions deliver as planned"
    - name: "integration_challenges"
      probability: 0.25
      outcome:
        final_value: 48
        trajectory: "Cultural friction with new hires; CI/CD has issues"
drivers:
  - factor: "team expansion (2 developers)"
    direction: positive
    magnitude: high
  - factor: "onboarding overhead"
    direction: negative
    magnitude: medium
  - factor: "CI/CD improvements"
    direction: positive
    magnitude: medium
  - factor: "sprint planning maturity"
    direction: positive
    magnitude: low
interventions:
  - event: "new developers join"
    timing: "month 1"
    expected_effect: "-10% velocity initially, then +30% at full capacity"
  - event: "CI/CD pipeline launch"
    timing: "month 2"
    expected_effect: "+15% velocity from reduced deployment friction"
confidence: 0.55
evidence_anchors:
  - "jira/velocity_history:12_sprints"
  - "hr/onboarding_timeline.md"
  - "devops/cicd_project_plan.md"
  - "benchmarks/team_rampup_data.csv"
assumptions:
  - "New hires have expected skill level"
  - "Existing team remains stable"
  - "CI/CD launches on schedule"
  - "No major scope changes to sprint work"
```

**Evidence pattern:** Capacity-based forecasting with intervention effects.

## Verification

- [ ] Entity and attribute are clearly specified
- [ ] Trajectory includes multiple time points
- [ ] Confidence decreases over time
- [ ] Interventions are mapped to expected effects
- [ ] Scenarios cover optimistic, expected, and pessimistic cases

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Note when historical data is insufficient for reliable forecasting
- Distinguish between trend-driven and intervention-driven changes
- Widen uncertainty for longer time horizons

## Composition Patterns

**Commonly follows:**
- `estimate-attribute` - Current value is baseline for projection
- `retrieve` - Historical attribute data for trend analysis
- `inspect` - Entity structure informs attribute dynamics

**Commonly precedes:**
- `compare` - To compare attribute trajectories across entities
- `plan` - When attribute forecast informs decisions
- `forecast-outcome` - When attribute is component of outcome

**Anti-patterns:**
- Never assume linear trends continue indefinitely
- Avoid forecasting without understanding historical patterns

**Workflow references:**
- See `workflow_catalog.json#capacity_planning` for attribute forecasting context
