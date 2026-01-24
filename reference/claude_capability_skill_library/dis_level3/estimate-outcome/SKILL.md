---
name: estimate-outcome
description: Approximate the current value or likelihood of an outcome given known inputs. Use when assessing results, evaluating success probability, or quantifying achievement levels.
argument-hint: "[outcome] [--given <conditions>] [--confidence-interval]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce a quantitative estimate of an outcome's current state or probability based on available evidence. This skill answers "given what we know now, what is the approximate value/likelihood of this outcome?" It focuses on current or recently completed outcomes, not future predictions.

**Success criteria:**
- Outcome value or probability is expressed with meaningful uncertainty bounds
- Inputs and conditions used for the estimate are explicitly listed
- The relationship between inputs and outcome is articulated
- Estimate distinguishes between known facts and inferred values

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `outcome` | Yes | string | The outcome to estimate (e.g., "conversion rate", "test pass rate", "project success") |
| `given` | No | object | Known conditions or inputs that affect the outcome |
| `metric_type` | No | string | Type of estimate: probability, count, percentage, score, rating |
| `baseline` | No | number | Reference value for comparison |

## Procedure

1) **Define the outcome precisely**: Clarify what constitutes the outcome being estimated.
   - What is the success/failure criteria?
   - What is the unit of measurement?
   - What population or scope does this apply to?

2) **Identify conditioning factors**: List the known inputs that influence this outcome.
   - What variables affect the outcome?
   - Which conditions are fixed vs. variable?
   - Are there any constraints or boundary conditions?

3) **Gather evidence for each factor**: Collect data on the conditioning variables.
   - Search for historical outcome data under similar conditions
   - Find measurements of current input values
   - Identify any outcome indicators or leading signals

4) **Apply estimation logic**: Use appropriate method based on outcome type.
   - **Probability outcomes**: Use base rates, conditional probabilities, or Bayesian updating
   - **Continuous outcomes**: Use regression, interpolation, or weighted averages
   - **Categorical outcomes**: Use classification rules or decision trees
   - **Composite outcomes**: Decompose into sub-outcomes and aggregate

5) **Quantify uncertainty**: Determine the confidence interval around the estimate.
   - Account for measurement error in inputs
   - Consider model uncertainty
   - Factor in missing information

6) **Ground and format**: Attach evidence anchors and structure output per contract.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: outcome
  value: number | string  # Estimated outcome value or probability
  unit: string | null     # Unit (percentage, count, rating, etc.)
  range:
    low: number           # Lower confidence bound
    high: number          # Upper confidence bound
methodology: string       # How estimate was derived from inputs
inputs_used:
  - string                # Conditioning factors and their values
sensitivity:
  - factor: string        # Input that most affects outcome
    impact: low | medium | high
confidence: number        # 0.0-1.0
evidence_anchors:
  - string                # file:line, url, or tool reference
assumptions:
  - string                # Explicit assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.value` | number/string | The estimated outcome value (probability 0-1, or measured value) |
| `estimate.unit` | string | Unit of measurement (probability, %, count, score) |
| `methodology` | string | The logic connecting inputs to outcome estimate |
| `inputs_used` | array | List of conditions/factors used in the estimate |
| `confidence` | number | Reflects both data quality and model fit |

## Examples

### Example 1: Estimating Feature Release Success Probability

**Input:**
```yaml
outcome: "successful feature release"
given:
  test_coverage: "87%"
  code_review_approved: true
  staging_validation: "passed"
  similar_releases_succeeded: "8 of 10"
metric_type: "probability"
```

**Output:**
```yaml
estimate:
  target_type: outcome
  value: 0.82
  unit: "probability"
  range:
    low: 0.68
    high: 0.91
methodology: "Base rate from similar releases (0.80) adjusted upward for above-average test coverage (+0.02) and staging validation pass, with variance from historical release outcomes"
inputs_used:
  - "test_coverage: 87% (above team average of 75%)"
  - "code_review: approved by 2 reviewers"
  - "staging_validation: all 12 test scenarios passed"
  - "historical_base_rate: 8/10 similar releases succeeded"
sensitivity:
  - factor: "staging environment fidelity to production"
    impact: high
  - factor: "test coverage of edge cases"
    impact: medium
  - factor: "deployment timing (peak vs off-peak)"
    impact: low
confidence: 0.72
evidence_anchors:
  - "ci/test_report.xml:coverage_summary"
  - "github.com/repo/pull/1234:reviews"
  - "staging/validation_log.txt:1-45"
  - "metrics/release_history.csv:recent_10"
assumptions:
  - "Staging environment accurately represents production"
  - "Historical release conditions are comparable to current"
  - "No external dependencies have changed since staging test"
```

**Evidence pattern:** Base rate adjustment using current condition signals.

---

### Example 2: Estimating Current Customer Satisfaction Score

**Input:**
```yaml
outcome: "customer satisfaction score"
given:
  recent_tickets: 47
  resolution_rate: "91%"
  avg_response_time: "2.3 hours"
metric_type: "score"
baseline: 4.2  # Previous quarter CSAT
```

**Output:**
```yaml
estimate:
  target_type: outcome
  value: 4.35
  unit: "CSAT score (1-5 scale)"
  range:
    low: 4.15
    high: 4.55
methodology: "Regression model using ticket volume, resolution rate, and response time as predictors, calibrated against previous 4 quarters of CSAT data"
inputs_used:
  - "ticket_volume: 47 (12% below average, positive signal)"
  - "resolution_rate: 91% (above 85% target)"
  - "avg_response_time: 2.3h (within 4h SLA)"
  - "baseline_csat: 4.2 from Q3"
sensitivity:
  - factor: "sample representativeness of survey respondents"
    impact: high
  - factor: "resolution rate accuracy"
    impact: medium
  - factor: "seasonal expectations"
    impact: low
confidence: 0.65
evidence_anchors:
  - "support/ticket_summary_q4.json:stats"
  - "analytics/csat_regression_model.pkl:coefficients"
  - "reports/q3_csat_results.pdf:page_2"
assumptions:
  - "Ticket metrics are leading indicators of satisfaction"
  - "No major product issues since last survey"
  - "Customer expectations remain stable quarter-over-quarter"
```

**Evidence pattern:** Regression model with current operational metrics as inputs.

## Verification

- [ ] Outcome definition is unambiguous
- [ ] All conditioning inputs are listed in inputs_used
- [ ] Range bounds are consistent with stated confidence level
- [ ] Methodology explains the input-to-outcome logic
- [ ] Evidence anchors support key claims

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not estimate outcomes involving personal health or safety without domain expertise
- If base rate data is unavailable, clearly state that estimate is heuristic
- Distinguish between correlation and causation in methodology

## Composition Patterns

**Commonly follows:**
- `retrieve` - To gather outcome data and input values
- `search` - To find historical outcomes under similar conditions
- `detect-anomaly` - When unusual inputs require special handling

**Commonly precedes:**
- `compare` - To compare estimated vs. actual or across scenarios
- `plan` - When outcome estimate informs decision-making
- `forecast-outcome` - When current estimate serves as baseline for projection

**Anti-patterns:**
- Never use for future outcome predictions (use forecast-outcome instead)
- Avoid for outcomes with no measurable definition

**Workflow references:**
- See `workflow_catalog.json#risk_assessment` for outcome estimation in risk context
