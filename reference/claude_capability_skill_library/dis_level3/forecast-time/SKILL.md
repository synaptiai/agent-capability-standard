---
name: forecast-time
description: Predict when an event or state transition will occur in the future. Use when estimating completion dates, predicting timing, or scheduling based on projections.
argument-hint: "[event] [--horizon <period>] [--scenarios]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Predict the timing of a future event or state transition based on current conditions, historical patterns, and relevant factors. This skill answers "when will X happen?" or "by what date will Y be achieved?" It produces time-based predictions with probability distributions and scenario analysis.

**Success criteria:**
- Predicted time is expressed with confidence intervals
- Multiple scenarios with different probabilities are considered
- Factors that could accelerate or delay timing are identified
- Historical patterns or reference class data is used when available

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `event` | Yes | string | The event or transition to forecast (e.g., "project completion", "feature release", "threshold breach") |
| `horizon` | No | string | Maximum time horizon to consider (e.g., "30 days", "Q2 2024") |
| `current_state` | No | object | Current progress or state toward the event |
| `constraints` | No | array | Fixed dates, dependencies, or deadlines |

## Procedure

1) **Define the event and its completion criteria**: Clarify what constitutes the event occurring.
   - What marks the event as complete or occurred?
   - What is the starting point for measurement?
   - Are there intermediate milestones?

2) **Assess current state and progress**: Determine how far along the process is.
   - What has been completed so far?
   - What is the current rate of progress?
   - Are there blockers or accelerators?

3) **Gather historical and reference data**: Find comparable past events.
   - How long did similar events take historically?
   - What is the distribution of completion times?
   - What factors predicted faster or slower outcomes?

4) **Model time-to-completion**: Apply appropriate forecasting method.
   - **Linear extrapolation**: Current velocity to remaining work
   - **Distribution fitting**: Historical times to probability distribution
   - **Simulation**: Monte Carlo with variable factors
   - **Expert estimation**: Delphi method or reference class

5) **Generate scenarios**: Create multiple time forecasts for different conditions.
   - **Optimistic**: Favorable conditions, no delays
   - **Most likely**: Expected conditions
   - **Pessimistic**: Adverse conditions, typical delays

6) **Identify timing drivers**: List factors that influence the forecast.
   - What would accelerate completion?
   - What are the main delay risks?
   - What dependencies must complete first?

7) **Format output**: Structure with time predictions and probabilities.

## Output Contract

Return a structured object:

```yaml
forecast:
  target_type: time
  event: string             # What is being forecasted
  prediction: string        # Primary time prediction (date or duration)
  time_horizon: string      # Forecast window
  probability: number       # Confidence in primary prediction (0-1)
  scenarios:
    - name: string          # optimistic, most_likely, pessimistic
      probability: number   # Probability of this scenario
      outcome:
        date: string        # Predicted date or timeframe
        duration: string    # Time from now
        rationale: string   # Why this scenario
drivers:
  - factor: string          # What influences timing
    direction: accelerates | delays | neutral
    magnitude: low | medium | high
dependencies:
  - event: string           # What must happen first
    estimated_completion: string
confidence: number          # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.prediction` | string | The most likely timing (date or duration) |
| `scenarios` | array | Alternative timing outcomes with probabilities |
| `drivers` | array | Factors that accelerate or delay the event |
| `dependencies` | array | Prerequisites and their expected timing |
| `confidence` | number | Certainty in the timing prediction |

## Examples

### Example 1: Forecasting Feature Release Date

**Input:**
```yaml
event: "v2.5 feature release to production"
horizon: "60 days"
current_state:
  development: "80% complete"
  testing: "40% complete"
  remaining_tasks: 12
constraints:
  - "code freeze: 2024-02-15"
  - "release window: Tuesdays only"
```

**Output:**
```yaml
forecast:
  target_type: time
  event: "v2.5 feature release to production"
  prediction: "2024-02-20"
  time_horizon: "60 days"
  probability: 0.65
  scenarios:
    - name: "optimistic"
      probability: 0.20
      outcome:
        date: "2024-02-13"
        duration: "18 days"
        rationale: "No blockers, reviews pass first time, testing completes early"
    - name: "most_likely"
      probability: 0.55
      outcome:
        date: "2024-02-20"
        duration: "25 days"
        rationale: "Normal velocity continues, typical review cycles, one minor issue found in testing"
    - name: "pessimistic"
      probability: 0.25
      outcome:
        date: "2024-03-05"
        duration: "38 days"
        rationale: "Testing reveals significant issue, requires additional development sprint"
drivers:
  - factor: "testing team availability"
    direction: delays
    magnitude: medium
  - factor: "feature complexity of remaining items"
    direction: delays
    magnitude: low
  - factor: "team familiarity with codebase"
    direction: accelerates
    magnitude: medium
dependencies:
  - event: "infrastructure migration"
    estimated_completion: "2024-02-01"
  - event: "security review"
    estimated_completion: "2024-02-10"
confidence: 0.68
evidence_anchors:
  - "jira/sprint_velocity:last_6_sprints"
  - "project/milestone_plan.md:v2.5"
  - "calendar/release_windows.ics"
assumptions:
  - "Current team velocity continues (no sick leave or departures)"
  - "No scope changes to remaining features"
  - "Infrastructure migration completes on schedule"
  - "Code freeze date is firm"
```

**Evidence pattern:** Velocity-based projection with scenario modeling.

---

### Example 2: Forecasting System Capacity Exhaustion

**Input:**
```yaml
event: "database storage capacity exhaustion (>95%)"
horizon: "90 days"
current_state:
  current_usage: "72%"
  growth_rate: "1.2% per week"
```

**Output:**
```yaml
forecast:
  target_type: time
  event: "database storage capacity exhaustion (>95%)"
  prediction: "19 weeks from now (approximately May 2024)"
  time_horizon: "90 days"
  probability: 0.72
  scenarios:
    - name: "optimistic"
      probability: 0.15
      outcome:
        date: "beyond 90 days"
        duration: ">24 weeks"
        rationale: "Growth rate slows due to data cleanup or usage optimization"
    - name: "most_likely"
      probability: 0.60
      outcome:
        date: "May 2024"
        duration: "19 weeks"
        rationale: "Current growth rate (1.2%/week) continues linearly"
    - name: "pessimistic"
      probability: 0.25
      outcome:
        date: "March 2024"
        duration: "11 weeks"
        rationale: "Growth rate accelerates due to new feature launch or data migration"
drivers:
  - factor: "new feature launches"
    direction: accelerates
    magnitude: high
  - factor: "data retention policy changes"
    direction: delays
    magnitude: medium
  - factor: "user growth rate"
    direction: accelerates
    magnitude: medium
  - factor: "storage optimization efforts"
    direction: delays
    magnitude: low
dependencies:
  - event: "Q1 feature launch"
    estimated_completion: "2024-03-01"
confidence: 0.65
evidence_anchors:
  - "monitoring/storage_trends:30d"
  - "analytics/data_growth_model.py:projections"
  - "planning/feature_roadmap.md:Q1"
assumptions:
  - "No sudden data spikes from external events"
  - "Growth rate follows recent trend, not seasonal pattern"
  - "Storage capacity limit is current allocation, not expandable"
```

**Evidence pattern:** Trend extrapolation with growth rate modeling.

## Verification

- [ ] Event completion criteria is clearly defined
- [ ] Multiple scenarios with distinct probabilities are provided
- [ ] Probabilities across scenarios sum to approximately 1.0
- [ ] Drivers are identified with direction and magnitude
- [ ] Dependencies are listed with their own timing estimates

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Express uncertainty clearly; avoid false precision
- Note when historical data is insufficient for reliable forecasting
- Distinguish between deadlines (fixed) and forecasts (predictions)

## Composition Patterns

**Commonly follows:**
- `estimate-activity` - Current progress rate informs timing
- `estimate-world` - Current state is starting point for projection
- `retrieve` - Historical data for reference class forecasting

**Commonly precedes:**
- `plan` - Timing forecasts inform project planning
- `compare` - To compare timing across scenarios or options
- `forecast-risk` - When timing affects risk exposure

**Anti-patterns:**
- Never claim certainty about future timing
- Avoid single-point forecasts without ranges

**Workflow references:**
- See `workflow_catalog.json#project_planning` for timing forecast context
