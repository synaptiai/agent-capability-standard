---
name: estimate-activity
description: Approximate the current intensity, duration, or likelihood of an activity. Use when quantifying activity levels, measuring engagement, or assessing ongoing processes.
argument-hint: "[activity] [--unit <metric>] [--confidence-interval]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce a quantitative or semi-quantitative estimate of an activity's current state, including intensity, duration, frequency, or participation level. This skill answers "approximately how much/how often/how intense is this activity right now?" rather than predicting future states.

**Success criteria:**
- Estimate includes a central value with meaningful range bounds
- Methodology for deriving the estimate is explicit and reproducible
- Sensitivity factors that could shift the estimate are identified
- All numerical claims are grounded in observable evidence

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `activity` | Yes | string | The activity to estimate (e.g., "user login frequency", "API call volume") |
| `scope` | No | object | Boundaries for the estimate (time window, user segment, system) |
| `unit` | No | string | Desired unit of measurement (e.g., "per hour", "percentage", "count") |
| `precision` | No | string | Required precision level: rough, moderate, precise |

## Procedure

1) **Identify the activity and its measurable dimensions**: Determine what aspect of the activity is being estimated (intensity, duration, frequency, participation rate). Clarify the scope boundaries.
   - What time window applies?
   - What entities are involved?
   - What constitutes one "instance" of the activity?

2) **Gather observable evidence**: Collect data points that inform the estimate.
   - Search for metrics, logs, or recorded observations
   - Look for historical baselines or reference values
   - Identify proxy indicators if direct measurement is unavailable

3) **Select estimation methodology**: Choose the appropriate technique based on available data.
   - **Direct observation**: If data is available, aggregate and compute
   - **Sampling**: If partial data exists, extrapolate with stated assumptions
   - **Proxy-based**: If no direct data, use correlated indicators with conversion factors
   - **Expert heuristic**: If no data available, apply domain knowledge with high uncertainty

4) **Compute the estimate with range**: Derive the central estimate and confidence bounds.
   - Calculate point estimate from available evidence
   - Determine range based on data variability and measurement uncertainty
   - Specify distribution type if known (normal, uniform, skewed)

5) **Analyze sensitivity factors**: Identify what could shift the estimate significantly.
   - Which inputs have the highest impact on the result?
   - What assumptions, if wrong, would invalidate the estimate?

6) **Ground claims and format output**: Attach evidence anchors to all assertions and structure according to the output contract.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: activity
  value: number | string  # Central estimate
  unit: string | null     # Unit of measurement
  range:
    low: number           # Lower bound (e.g., 10th percentile)
    high: number          # Upper bound (e.g., 90th percentile)
methodology: string       # How the estimate was derived
inputs_used:
  - string                # Data sources or observations used
sensitivity:
  - factor: string        # What could change the estimate
    impact: low | medium | high
confidence: number        # 0.0-1.0
evidence_anchors:
  - string                # file:line, url, or tool:<name>:<ref>
assumptions:
  - string                # Explicit assumptions made
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.value` | number/string | The central or most likely value for the activity measure |
| `estimate.range` | object | Low and high bounds representing uncertainty |
| `methodology` | string | Description of how the estimate was computed |
| `sensitivity` | array | Factors that would significantly change the estimate if adjusted |
| `confidence` | number | 0.0-1.0 based on evidence quality and methodology robustness |

## Examples

### Example 1: Estimating Current User Login Activity

**Input:**
```yaml
activity: "daily active user logins"
scope:
  system: "web application"
  time_window: "current day"
unit: "logins per hour"
```

**Output:**
```yaml
estimate:
  target_type: activity
  value: 1250
  unit: "logins per hour"
  range:
    low: 980
    high: 1480
methodology: "Sampled login events from auth logs for past 4 hours, extrapolated to full day pattern using historical hourly distribution weights"
inputs_used:
  - "auth_service.log entries 08:00-12:00 (4,892 events)"
  - "historical_patterns.csv hourly weights"
sensitivity:
  - factor: "time of day (peak vs off-peak)"
    impact: high
  - factor: "marketing campaign running"
    impact: medium
  - factor: "weekend vs weekday"
    impact: high
confidence: 0.75
evidence_anchors:
  - "logs/auth_service.log:1-4892"
  - "data/historical_patterns.csv:12"
assumptions:
  - "Today's login pattern follows historical weekday distribution"
  - "No major service disruptions affecting login availability"
  - "Sample period is representative of full day activity"
```

**Evidence pattern:** Direct sampling from auth logs with extrapolation using historical baseline patterns.

---

### Example 2: Estimating Code Review Activity Intensity

**Input:**
```yaml
activity: "code review engagement"
scope:
  repository: "main-app"
  time_window: "current sprint"
unit: "reviews per developer per week"
precision: "moderate"
```

**Output:**
```yaml
estimate:
  target_type: activity
  value: 4.2
  unit: "reviews per developer per week"
  range:
    low: 2.8
    high: 6.1
methodology: "Counted PR review comments and approvals from GitHub API, normalized by active developer count from commit authors"
inputs_used:
  - "GitHub PR review events (87 reviews)"
  - "Unique commit authors this sprint (21 developers)"
  - "Sprint duration (2 weeks elapsed of 3 total)"
sensitivity:
  - factor: "developer availability (PTO, meetings)"
    impact: medium
  - factor: "PR size and complexity"
    impact: low
  - factor: "end-of-sprint review surge"
    impact: high
confidence: 0.68
evidence_anchors:
  - "tool:GitHub API:pulls/reviews"
  - "tool:GitHub API:commits/authors"
assumptions:
  - "All developers are expected to participate in reviews"
  - "Review activity will continue at similar rate for remainder of sprint"
  - "Bot-generated PRs excluded from count"
```

**Evidence pattern:** API-based measurement with normalization by team size.

## Verification

- [ ] Estimate includes both central value and range bounds
- [ ] Methodology is explicit and could be reproduced
- [ ] At least one sensitivity factor is identified
- [ ] All numerical claims have evidence anchors
- [ ] Assumptions do not contradict the evidence

**Verification tools:** Read, Grep (to validate referenced files/data)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not access credentials or authentication tokens when reading logs
- If confidence is below 0.3, recommend data collection before acting on estimate
- Clearly distinguish between measured values and extrapolated values

## Composition Patterns

**Commonly follows:**
- `search` - To locate relevant data sources for the activity
- `inspect` - To understand the structure of activity logs or metrics

**Commonly precedes:**
- `compare` - To compare activity levels across periods or segments
- `forecast-activity` - When current estimate is needed as baseline for prediction
- `plan` - When activity estimate informs resource planning

**Anti-patterns:**
- Never use estimate-activity for future predictions (use forecast-* instead)
- Avoid when exact counts are available and required (use retrieve instead)

**Workflow references:**
- See `workflow_catalog.json#capacity_planning` for usage in resource allocation
