---
name: estimate-impact
description: Approximate the current or immediate impact of an intervention, change, or choice. Use when assessing effects, measuring consequences, or quantifying influence.
argument-hint: "[intervention] [--on <target>] [--scope <boundary>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce a quantitative or qualitative estimate of the impact that an intervention, change, or decision has on a target system or outcome. This skill answers "what is the approximate effect of X on Y right now or immediately?" It focuses on current or realized impacts, not future projections.

**Success criteria:**
- Impact is expressed in measurable terms with uncertainty bounds
- Causal pathway from intervention to impact is articulated
- Counterfactual baseline (what would happen without intervention) is considered
- Both direct and indirect impacts are addressed where relevant

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `intervention` | Yes | string | The change, action, or choice whose impact is being estimated |
| `target` | No | string | What is being impacted (metric, system, outcome) |
| `scope` | No | object | Boundaries of the impact analysis (time, geography, population) |
| `baseline` | No | object | Counterfactual or pre-intervention state for comparison |

## Procedure

1) **Define the intervention and target**: Clarify what change occurred and what it affects.
   - What exactly changed? (action, policy, code, configuration)
   - What is the target of impact? (metric, behavior, system state)
   - What scope boundaries apply?

2) **Establish the baseline**: Determine the counterfactual or pre-intervention state.
   - What was the state before the intervention?
   - What would the state be without the intervention?
   - Are there control groups or comparison periods available?

3) **Identify impact pathways**: Map how the intervention affects the target.
   - What is the direct causal mechanism?
   - Are there intermediate effects?
   - What indirect or second-order effects might occur?

4) **Gather impact evidence**: Collect data on observed or expected effects.
   - Look for before/after measurements
   - Find comparison data (with/without intervention)
   - Identify leading indicators of impact

5) **Compute impact magnitude**: Estimate the size and direction of the effect.
   - Calculate absolute impact (difference from baseline)
   - Calculate relative impact (percentage change)
   - Determine confidence interval based on data quality

6) **Assess confounders and sensitivity**: Identify factors that might bias the estimate.
   - What other changes occurred simultaneously?
   - How sensitive is the estimate to assumptions?
   - What would change the impact significantly?

7) **Format output with grounding**: Structure results per contract with evidence.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: impact
  value: number | string  # Impact magnitude
  unit: string | null     # Unit of measurement
  range:
    low: number           # Conservative impact estimate
    high: number          # Optimistic impact estimate
  direction: positive | negative | mixed  # Impact direction
methodology: string       # How impact was isolated and measured
inputs_used:
  - string                # Data sources and measurements
sensitivity:
  - factor: string        # Confounder or assumption
    impact: low | medium | high
baseline:
  value: number | string  # Counterfactual or pre-intervention state
  source: string          # Where baseline came from
confidence: number        # 0.0-1.0
evidence_anchors:
  - string                # file:line, url, or tool reference
assumptions:
  - string                # Causal and measurement assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.value` | number/string | The estimated impact magnitude |
| `estimate.direction` | enum | Whether impact is positive, negative, or mixed |
| `baseline` | object | The counterfactual state for comparison |
| `methodology` | string | How the impact was isolated from other factors |
| `confidence` | number | Reflects causal certainty and measurement quality |

## Examples

### Example 1: Estimating Performance Impact of Code Change

**Input:**
```yaml
intervention: "database query optimization in user-list endpoint"
target: "API response time"
scope:
  endpoint: "/api/users"
  environment: "production"
baseline:
  value: "450ms p95 response time"
  period: "week before deployment"
```

**Output:**
```yaml
estimate:
  target_type: impact
  value: -180
  unit: "milliseconds (p95 response time reduction)"
  range:
    low: -150
    high: -220
  direction: positive  # Reduction in latency is positive
methodology: "Before/after comparison of p95 response times, controlling for traffic volume and time of day. Measured 48 hours post-deployment vs 48 hours pre-deployment at equivalent traffic levels."
inputs_used:
  - "APM metrics: p95 response time pre-deploy (450ms)"
  - "APM metrics: p95 response time post-deploy (270ms)"
  - "Traffic volume: comparable (within 5%)"
  - "No other deployments to this endpoint in window"
sensitivity:
  - factor: "traffic pattern differences"
    impact: low
  - factor: "database load from other services"
    impact: medium
  - factor: "cache warm-up effects"
    impact: low
baseline:
  value: 450
  source: "APM dashboard, 7-day average pre-deployment"
confidence: 0.85
evidence_anchors:
  - "apm/endpoint_metrics.json:user_list_p95"
  - "deployments/changelog_2024-01.md:line_47"
  - "grafana/dashboard/api_latency:panel_3"
assumptions:
  - "No confounding infrastructure changes during measurement window"
  - "Query optimization is the only change to this endpoint"
  - "p95 is representative of user experience impact"
```

**Evidence pattern:** Controlled before/after measurement with confound identification.

---

### Example 2: Estimating Impact of Pricing Change on Conversion

**Input:**
```yaml
intervention: "10% price reduction on premium tier"
target: "conversion rate from trial to paid"
scope:
  segment: "trial users exposed to new pricing"
  time_window: "first 2 weeks of change"
```

**Output:**
```yaml
estimate:
  target_type: impact
  value: 2.3
  unit: "percentage points increase in conversion rate"
  range:
    low: 1.1
    high: 3.8
  direction: positive
methodology: "A/B comparison between users who saw new pricing (treatment) vs original pricing (control). Conversion tracked over 14-day trial period. Statistical significance p<0.05."
inputs_used:
  - "control_group: 12.4% conversion (n=2,340)"
  - "treatment_group: 14.7% conversion (n=2,285)"
  - "experiment_duration: 14 days"
  - "statistical_test: chi-square, p=0.023"
sensitivity:
  - factor: "user segment composition"
    impact: medium
  - factor: "seasonal effects"
    impact: low
  - factor: "feature awareness during trial"
    impact: medium
baseline:
  value: 12.4
  source: "control group conversion rate"
confidence: 0.78
evidence_anchors:
  - "analytics/ab_test_results_pricing_v2.csv:summary"
  - "experiments/pricing_test_config.json:groups"
  - "stats/significance_tests.py:output"
assumptions:
  - "Random assignment was properly implemented"
  - "No cross-contamination between groups"
  - "14-day window captures full conversion decision"
  - "Revenue impact not considered (only conversion rate)"
```

**Evidence pattern:** Randomized A/B experiment with statistical testing.

## Verification

- [ ] Intervention is clearly defined and isolated
- [ ] Baseline is explicitly stated with source
- [ ] Impact direction matches the value sign
- [ ] Confounders are acknowledged in sensitivity or assumptions
- [ ] Evidence anchors support the before/after or treatment/control data

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Clearly distinguish correlation from causation when causal inference is weak
- If no baseline is available, state that impact is absolute observation, not relative
- Do not claim causal impact without controlled comparison or strong theory

## Composition Patterns

**Commonly follows:**
- `detect-anomaly` - When anomaly triggered investigation of impact
- `retrieve` - To gather before/after metrics
- `inspect` - To understand what the intervention changed

**Commonly precedes:**
- `compare` - To compare impacts across interventions
- `plan` - When impact informs next steps
- `forecast-impact` - To project future impact trajectory

**Anti-patterns:**
- Never use for future impact projections (use forecast-impact instead)
- Avoid when intervention is ongoing and impact is still evolving

**Workflow references:**
- See `workflow_catalog.json#change_analysis` for impact estimation in deployment context
