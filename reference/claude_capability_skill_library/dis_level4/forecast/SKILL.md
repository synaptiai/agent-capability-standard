---
name: forecast
description: Predict a future state, value, or outcome over a time horizon with probability and scenario analysis. Use when projecting trends, anticipating changes, or modeling future states.
argument-hint: "[target] [time-horizon] [scenarios]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Project the future state of a system, metric, or entity based on current observations, historical trends, and identified drivers. Forecasting extends estimation into the temporal domain with explicit scenario modeling.

**Success criteria:**
- Prediction with associated probability
- Time horizon clearly specified
- Multiple scenarios with probabilities
- Key drivers and uncertainties identified

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | What to forecast (metric, state, event) |
| `time_horizon` | Yes | string | Forecast period (e.g., "7 days", "Q2 2025", "next sprint") |
| `historical_data` | No | array\|string | Past observations for trend analysis |
| `drivers` | No | array | Known factors that influence the target |
| `scenarios` | No | array[string] | Specific scenarios to analyze |

## Procedure

1) **Define forecast target**: Clarify exactly what is being predicted
   - Quantitative: numeric value at future time
   - Qualitative: state or category at future time
   - Event: whether something will occur by deadline

2) **Analyze historical patterns**: Examine past data for trends
   - Trend direction: increasing, decreasing, stable, cyclic
   - Rate of change: linear, exponential, logarithmic
   - Volatility: stable vs. highly variable

3) **Identify drivers**: Determine factors that influence the target
   - Positive drivers: push toward higher/better outcomes
   - Negative drivers: push toward lower/worse outcomes
   - Neutral factors: affect variance but not direction

4) **Model scenarios**: Construct plausible future paths
   - Base case: continuation of current trends
   - Optimistic: favorable driver assumptions
   - Pessimistic: unfavorable driver assumptions
   - Wild card: low-probability high-impact events

5) **Assign probabilities**: Estimate likelihood of each scenario
   - Use reference class forecasting when possible
   - Adjust for identified drivers
   - Sum of all scenario probabilities should approximate 1.0

6) **Quantify uncertainties**: Document what could invalidate the forecast
   - Known unknowns: identified factors with uncertain values
   - Unknown unknowns: acknowledge model limitations

7) **Ground claims**: Attach evidence anchors to all inputs and reasoning
   - Historical data sources
   - Driver identification rationale

## Output Contract

Return a structured object:

```yaml
forecast:
  prediction: string | object  # The forecasted outcome
  time_horizon: string  # When the forecast applies
  probability: number  # 0.0-1.0 likelihood of base prediction
  scenarios:
    - name: string  # Scenario identifier
      probability: number  # Scenario likelihood
      outcome: string | object  # What happens in this scenario
drivers:
  - factor: string  # Driver name
    direction: positive | negative | neutral
    magnitude: low | medium | high
uncertainties: array[string]  # Major sources of forecast uncertainty
confidence: number  # 0.0-1.0 confidence in forecast methodology
evidence_anchors: array[string]  # References to historical data, drivers
assumptions: array[string]  # Conditions that must hold for forecast validity
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.prediction` | string\|object | Primary predicted outcome |
| `forecast.time_horizon` | string | When prediction applies |
| `forecast.probability` | number | Likelihood of base prediction |
| `forecast.scenarios` | array | Alternative outcomes with probabilities |
| `drivers` | array | Factors influencing the forecast |
| `uncertainties` | array | Major sources of forecast error |
| `confidence` | number | 0.0-1.0 methodology confidence |
| `evidence_anchors` | array[string] | References to supporting data |
| `assumptions` | array[string] | Conditions required for validity |

## Examples

### Example 1: Forecast Sprint Completion

**Input:**
```yaml
target: "sprint story point completion"
time_horizon: "end of current sprint (10 days)"
historical_data: "last 6 sprints velocity data"
drivers:
  - "team availability"
  - "technical complexity"
  - "external dependencies"
```

**Output:**
```yaml
forecast:
  prediction: "42 of 50 story points completed"
  time_horizon: "Sprint 23 end (2025-02-15)"
  probability: 0.65
  scenarios:
    - name: "full completion"
      probability: 0.25
      outcome:
        points_completed: 50
        on_time: true
    - name: "partial completion"
      probability: 0.50
      outcome:
        points_completed: 42
        on_time: true
    - name: "significant shortfall"
      probability: 0.20
      outcome:
        points_completed: 35
        on_time: false
    - name: "blocked by dependency"
      probability: 0.05
      outcome:
        points_completed: 28
        blocked_stories: 3
drivers:
  - factor: "developer PTO mid-sprint"
    direction: negative
    magnitude: medium
  - factor: "similar stories to last sprint"
    direction: positive
    magnitude: low
  - factor: "API migration dependency"
    direction: negative
    magnitude: high
uncertainties:
  - "External API availability for integration testing"
  - "Accuracy of story point estimates for new technology"
confidence: 0.70
evidence_anchors:
  - "jira:velocity-report:sprints-17-22"
  - "calendar:team-pto:2025-02"
  - "confluence:api-migration-timeline"
assumptions:
  - "No emergency production incidents"
  - "Story point estimates are calibrated to team average"
  - "No scope changes after sprint start"
```

**Evidence pattern:** Read sprint history for velocity trends, check calendar for availability, review dependency status.

---

### Example 2: Forecast API Performance Degradation

**Input:**
```yaml
target: "API p99 latency"
time_horizon: "30 days"
historical_data: "monitoring data from past 90 days"
drivers:
  - "traffic growth"
  - "database size"
  - "cache hit rate"
```

**Output:**
```yaml
forecast:
  prediction: "p99 latency increases from 250ms to 320ms"
  time_horizon: "30 days (2025-03-01)"
  probability: 0.60
  scenarios:
    - name: "stable"
      probability: 0.30
      outcome:
        p99_latency_ms: 260
        action_required: false
    - name: "gradual degradation"
      probability: 0.50
      outcome:
        p99_latency_ms: 320
        action_required: true
    - name: "rapid degradation"
      probability: 0.15
      outcome:
        p99_latency_ms: 500
        sla_breach: true
    - name: "improvement"
      probability: 0.05
      outcome:
        p99_latency_ms: 200
        action_required: false
drivers:
  - factor: "10% monthly traffic growth"
    direction: negative
    magnitude: medium
  - factor: "database approaching index limits"
    direction: negative
    magnitude: high
  - factor: "new caching layer deployment"
    direction: positive
    magnitude: medium
uncertainties:
  - "Actual traffic growth rate"
  - "Effectiveness of new caching layer"
  - "Database maintenance window impact"
confidence: 0.65
evidence_anchors:
  - "datadog:latency-dashboard:90d"
  - "postgres:table-stats:users"
  - "jira:INFRA-1234:caching-epic"
assumptions:
  - "No major feature releases changing traffic patterns"
  - "Database hardware unchanged"
```

## Verification

- [ ] Time horizon is specific and unambiguous
- [ ] Scenario probabilities sum to approximately 1.0
- [ ] Each driver has direction and magnitude
- [ ] Uncertainties are distinct from assumptions
- [ ] Historical data sources are referenced in evidence_anchors
- [ ] Prediction is falsifiable at forecast horizon

**Verification tools:** Read (historical data), external monitoring tools if available

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always include multiple scenarios, not just point prediction
- Document uncertainties that could invalidate the forecast
- Flag forecasts beyond reliable prediction horizon
- Do not forecast without historical data - request data first

## Composition Patterns

**Commonly follows:**
- `estimate` - Current estimates feed into future projections
- `detect-anomaly` - Anomaly detection triggers risk forecasting
- `identify` - Identified trends inform forecasts

**Commonly precedes:**
- `plan` - Forecasts inform contingency and capacity planning
- `compare` - Forecast outcomes enable option comparison
- `act` - Forecasts may trigger preemptive actions

**Anti-patterns:**
- Never use forecast for current state (use `estimate`)
- Avoid forecast without historical context (results are unreliable)
- Do not forecast beyond data reliability horizon

**Workflow references:**
- See `composition_patterns.md#digital-twin-sync-loop` for forecast-risk usage
- See `composition_patterns.md#risk-assessment` for forecast in risk workflows
