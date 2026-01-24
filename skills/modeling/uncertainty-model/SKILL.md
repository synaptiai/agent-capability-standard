---
name: uncertainty-model
description: Quantify and represent uncertainty including distributions, confidence intervals, epistemic vs aleatoric uncertainty, and reduction opportunities. Use when assessing reliability of estimates, modeling risk, or identifying knowledge gaps.
argument-hint: "[target] [uncertainty_types] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Build an **uncertainty model** that explicitly quantifies what we know, what we don't know, and how sure we are about each claim. This is essential for honest modeling and informed decision-making.

**Success criteria:**
- Uncertainty type is classified (aleatoric vs. epistemic vs. model)
- Distributions are specified with parameters
- Confidence intervals are meaningful and calibrated
- Reduction opportunities are identified
- Uncertainty propagates correctly through the model

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | object\|array | World state, claims, or estimates to model uncertainty for |
| `uncertainty_types` | No | array | Types to consider: `aleatoric`, `epistemic`, `model` (default: all) |
| `quantification_method` | No | string | `parametric`, `empirical`, `expert` (default: infer) |
| `constraints` | No | object | Bounds, required precision, aggregation method |

## Procedure

1) **Identify uncertain quantities**: Extract what needs uncertainty modeling
   - **State variables**: Entity attributes, measurements
   - **Parameters**: Model inputs, configuration values
   - **Predictions**: Forecasts, estimates
   - **Relationships**: Strengths of causal/correlational links

2) **Classify uncertainty type**: For each quantity, determine the source
   - **Aleatoric** (irreducible): Inherent randomness in the system
     - Example: Coin flip outcome, quantum measurement
     - Cannot be reduced with more data
   - **Epistemic** (reducible): Uncertainty from incomplete knowledge
     - Example: Unknown parameter, missing data
     - Can be reduced with more information
   - **Model** (structural): Uncertainty about the model itself
     - Example: Wrong functional form, missing variables
     - Reduced by model comparison/validation

3) **Select distribution**: Choose appropriate probability distribution
   - **Continuous quantities**:
     - Normal: Symmetric around mean, unbounded
     - Log-normal: Positive, right-skewed
     - Beta: Bounded [0,1], good for proportions
     - Uniform: Equal probability within bounds
     - Triangular: Known min, max, mode
   - **Discrete quantities**:
     - Bernoulli: Binary outcome
     - Poisson: Count data
     - Categorical: Multiple discrete outcomes
   - **Unknown**: Use empirical distribution or bounds

4) **Estimate parameters**: Determine distribution parameters
   - From data: Maximum likelihood, Bayesian inference
   - From expert judgment: Elicit percentiles, bounds
   - From literature: Reference values, ranges
   - From sensitivity analysis: Observe range of outcomes

5) **Calculate derived quantities**: Propagate uncertainty
   - Point estimates: Mean, median, mode
   - Intervals: Confidence intervals, credible intervals
   - Extreme values: Tails, worst-case scenarios
   - Aggregation: Combined uncertainty from multiple sources

6) **Identify reduction opportunities**: How could uncertainty be decreased?
   - More data: Additional observations
   - Better measurements: Higher precision instruments
   - Model improvement: Include missing variables
   - Expert consultation: Domain knowledge

7) **Assess confidence in the uncertainty model itself**: Meta-uncertainty
   - How well-calibrated are our estimates?
   - What are we uncertain about the uncertainty?
   - Where might we be overconfident or underconfident?

8) **Ground uncertainty claims**: Link to evidence
   - Source of distribution choice
   - Basis for parameter estimates
   - Calibration data if available

## Output Contract

Return a structured object:

```yaml
uncertainties:
  - id: string  # Uncertainty ID
    entity_id: string | null  # Entity this applies to (null for global)
    attribute: string  # What quantity is uncertain
    type: aleatoric | epistemic | model
    distribution:
      family: string  # normal, uniform, beta, empirical, etc.
      parameters: object  # Distribution-specific parameters
      bounds: object | null  # {min, max} if bounded
    point_estimate:
      value: number | string
      estimator: string  # mean, median, mode, MAP
    intervals:
      - level: number  # e.g., 0.95 for 95%
        lower: number
        upper: number
        type: confidence | credible | prediction
    source: string  # Where uncertainty estimate came from
aggregated_uncertainty:
  method: string  # monte_carlo, analytical, worst_case, etc.
  result:
    combined_distribution: object | null
    summary_statistics: object
  correlation_assumptions: array[string]
reduction_opportunities:
  - uncertainty_id: string
    method: string  # How to reduce
    expected_reduction: number | string  # Quantified or qualitative
    cost: low | medium | high
    priority: low | medium | high
meta_uncertainty:
  calibration_assessment: string  # How well-calibrated are we?
  known_biases: array[string]  # Identified biases in estimates
  confidence_in_model: number  # 0.0-1.0
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `uncertainties` | array | Individual uncertainty specifications |
| `distribution` | object | Probability distribution and parameters |
| `intervals` | array | Confidence/credible intervals at various levels |
| `aggregated_uncertainty` | object | Combined uncertainty across multiple quantities |
| `reduction_opportunities` | array | Ways to reduce uncertainty |

## Examples

### Example 1: Service Latency Uncertainty

**Input:**
```yaml
target:
  world_state_ref: "ws_api_service"
  attribute: "response_latency_ms"
uncertainty_types: ["aleatoric", "epistemic"]
quantification_method: empirical
```

**Output:**
```yaml
uncertainties:
  - id: "u_latency_aleatoric"
    entity_id: "api_service"
    attribute: "response_latency_ms"
    type: aleatoric
    distribution:
      family: "log_normal"
      parameters:
        mu: 3.5
        sigma: 0.4
      bounds:
        min: 10
        max: 5000
    point_estimate:
      value: 45
      estimator: "median"
    intervals:
      - level: 0.5
        lower: 35
        upper: 58
        type: prediction
      - level: 0.95
        lower: 22
        upper: 150
        type: prediction
      - level: 0.99
        lower: 15
        upper: 350
        type: prediction
    source: "empirical from 7-day production metrics"
  - id: "u_latency_epistemic"
    entity_id: "api_service"
    attribute: "response_latency_ms.baseline"
    type: epistemic
    distribution:
      family: "normal"
      parameters:
        mean: 45
        std: 3
      bounds: null
    point_estimate:
      value: 45
      estimator: "mean"
    intervals:
      - level: 0.95
        lower: 39
        upper: 51
        type: confidence
    source: "uncertainty in baseline estimate due to traffic variation"
aggregated_uncertainty:
  method: "monte_carlo"
  result:
    combined_distribution:
      samples: 10000
      percentiles:
        p50: 45
        p90: 95
        p99: 200
    summary_statistics:
      mean: 52
      std: 35
  correlation_assumptions:
    - "Baseline uncertainty independent of aleatoric variation"
reduction_opportunities:
  - uncertainty_id: "u_latency_epistemic"
    method: "Collect more data across different traffic conditions"
    expected_reduction: "50% reduction in baseline uncertainty"
    cost: low
    priority: medium
  - uncertainty_id: "u_latency_aleatoric"
    method: "Implement request queuing to smooth demand"
    expected_reduction: "30% reduction in variance"
    cost: high
    priority: low
meta_uncertainty:
  calibration_assessment: "Good - log-normal fit validated on holdout data"
  known_biases:
    - "Metrics exclude failed requests (survivorship bias)"
    - "Nighttime traffic underrepresented"
  confidence_in_model: 0.8
confidence: 0.85
evidence_anchors:
  - "datadog:metrics/api.latency:7d"
  - "tool:distribution_fit:log_normal_test"
assumptions:
  - "Traffic patterns are stationary over the measurement period"
  - "Log-normal is appropriate for latency distribution"
```

**Evidence pattern:** Fit distribution to observed latency data, validated with goodness-of-fit test, separated aleatoric (request-to-request) from epistemic (baseline estimation).

---

### Example 2: Project Duration Uncertainty

**Input:**
```yaml
target:
  tasks:
    - id: "task_design"
      estimate_days: 5
    - id: "task_implement"
      estimate_days: 15
    - id: "task_test"
      estimate_days: 8
```

**Output:**
```yaml
uncertainties:
  - id: "u_design"
    entity_id: "task_design"
    attribute: "duration_days"
    type: epistemic
    distribution:
      family: "triangular"
      parameters:
        min: 3
        mode: 5
        max: 10
      bounds: { min: 3, max: 10 }
    point_estimate:
      value: 6
      estimator: "mean"
    intervals:
      - level: 0.9
        lower: 3.5
        upper: 9
        type: prediction
    source: "expert estimate with optimistic/pessimistic bounds"
  - id: "u_implement"
    entity_id: "task_implement"
    attribute: "duration_days"
    type: epistemic
    distribution:
      family: "triangular"
      parameters:
        min: 10
        mode: 15
        max: 30
      bounds: { min: 10, max: 30 }
    point_estimate:
      value: 18.3
      estimator: "mean"
    intervals:
      - level: 0.9
        lower: 11
        upper: 27
        type: prediction
    source: "expert estimate - higher uncertainty due to scope unknowns"
  - id: "u_test"
    entity_id: "task_test"
    attribute: "duration_days"
    type: epistemic
    distribution:
      family: "triangular"
      parameters:
        min: 5
        mode: 8
        max: 15
      bounds: { min: 5, max: 15 }
    point_estimate:
      value: 9.3
      estimator: "mean"
    intervals:
      - level: 0.9
        lower: 5.5
        upper: 14
        type: prediction
    source: "expert estimate based on similar past projects"
aggregated_uncertainty:
  method: "monte_carlo"
  result:
    combined_distribution:
      samples: 10000
      percentiles:
        p10: 24
        p50: 33
        p80: 42
        p90: 48
    summary_statistics:
      mean: 33.6
      std: 8.2
  correlation_assumptions:
    - "Tasks assumed independent (may underestimate if issues cascade)"
reduction_opportunities:
  - uncertainty_id: "u_implement"
    method: "Break down implementation into smaller, well-defined tasks"
    expected_reduction: "40% reduction in variance"
    cost: medium
    priority: high
  - uncertainty_id: "all"
    method: "Use historical data from similar completed projects"
    expected_reduction: "Better calibration of estimates"
    cost: low
    priority: high
meta_uncertainty:
  calibration_assessment: "Moderate - planning fallacy likely, estimates may be optimistic"
  known_biases:
    - "Experts tend to underestimate implementation complexity"
    - "Sequential task model ignores parallel work potential"
  confidence_in_model: 0.6
confidence: 0.7
evidence_anchors:
  - "project_plan:task_estimates"
  - "historical:similar_project_durations"
assumptions:
  - "Tasks are sequential (design -> implement -> test)"
  - "No scope changes during execution"
  - "Single-person work effort"
```

## Verification

- [ ] Distribution parameters are valid (e.g., std > 0, bounds consistent)
- [ ] Intervals nest properly (90% interval inside 95% interval)
- [ ] Point estimates are within distribution support
- [ ] Uncertainty type classification is justified
- [ ] Aggregation method is appropriate for correlation structure

**Verification tools:** Distribution validators, interval consistency checks

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not claim false precision (avoid 99.9% confidence without strong evidence)
- Mark when uncertainty is itself highly uncertain
- Distinguish between variability (aleatoric) and ignorance (epistemic)
- When data is insufficient, use conservative bounds

## Composition Patterns

**Commonly follows:**
- `world-state` - Attach uncertainty to state variables
- `estimate-*` - Quantify uncertainty in estimates
- `forecast-*` - Model forecast uncertainty

**Commonly precedes:**
- `simulation` - Use uncertainty in Monte Carlo simulations
- `plan` - Account for uncertainty in planning
- `decide` - Inform decisions with uncertainty

**Anti-patterns:**
- Never ignore uncertainty in downstream processing
- Avoid overconfident intervals without calibration

**Workflow references:**
- See `composition_patterns.md#world-model-build` for uncertainty in model construction
- See `composition_patterns.md#digital-twin-sync-loop` for updating uncertainty
