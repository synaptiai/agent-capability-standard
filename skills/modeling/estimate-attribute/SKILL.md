---
name: estimate-attribute
description: Approximate the current value of an attribute from indirect evidence. Use when measuring properties, inferring characteristics, or quantifying qualities that cannot be directly observed.
argument-hint: "[entity] [attribute] [--precision <level>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce a quantitative or qualitative estimate of an entity's attribute when direct measurement is unavailable or impractical. This skill answers "approximately what is the value of attribute X for entity Y right now?" It uses indirect evidence, proxies, or inference to derive attribute values.

**Success criteria:**
- Attribute value is estimated with appropriate precision and uncertainty
- Methodology for deriving the estimate from evidence is explicit
- Proxy indicators or inference chain is documented
- Difference between measured vs. inferred attributes is clear

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entity` | Yes | string | The entity whose attribute is being estimated |
| `attribute` | Yes | string | The attribute to estimate (e.g., "complexity", "quality", "size") |
| `evidence` | No | array | Available indicators or proxy data |
| `precision` | No | string | Required precision: rough, moderate, precise |
| `scale` | No | string | Measurement scale: continuous, ordinal, categorical |

## Procedure

1) **Define the attribute precisely**: Clarify what property is being estimated.
   - What does this attribute represent?
   - How would it be measured directly if possible?
   - What scale is appropriate? (continuous, ordinal, categorical)

2) **Identify available evidence**: List what can be observed or measured.
   - Direct indicators: partial measurements, samples
   - Proxy indicators: correlated observable properties
   - Comparative references: similar entities with known values
   - Expert assessments: documented evaluations

3) **Establish estimation method**: Choose approach based on evidence type.
   - **Direct extrapolation**: Sample to population inference
   - **Proxy-based**: Convert proxy values using known relationships
   - **Comparative**: Position relative to known reference points
   - **Composite**: Combine multiple indicators with weights

4) **Apply estimation logic**: Compute the attribute value.
   - Transform proxy values if needed
   - Aggregate multiple indicators
   - Calibrate against reference points
   - Quantify the estimation uncertainty

5) **Validate estimate plausibility**: Check for reasonableness.
   - Does the estimate fall within expected bounds?
   - Is it consistent with other known attributes?
   - Are there contradicting signals?

6) **Format output with grounding**: Structure per contract with evidence.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: attribute
  entity: string          # What entity the attribute belongs to
  attribute: string       # Name of the attribute
  value: number | string  # Estimated attribute value
  unit: string | null     # Unit or scale
  range:
    low: number           # Lower bound
    high: number          # Upper bound
  value_type: measured | inferred | proxy-based  # How value was obtained
methodology: string       # Estimation approach used
inputs_used:
  - indicator: string     # What was observed
    value: string         # Observed value
    weight: number        # Contribution to estimate (0-1)
sensitivity:
  - factor: string
    impact: low | medium | high
confidence: number        # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.entity` | string | The entity whose attribute was estimated |
| `estimate.attribute` | string | The specific attribute that was estimated |
| `estimate.value_type` | enum | Whether value is direct measurement, inference, or proxy |
| `inputs_used` | array | Indicators and their contribution weights |
| `confidence` | number | Certainty based on evidence quality and inference strength |

## Examples

### Example 1: Estimating Code Complexity

**Input:**
```yaml
entity: "checkout-service"
attribute: "maintainability"
precision: "moderate"
scale: "ordinal (1-10)"
```

**Output:**
```yaml
estimate:
  target_type: attribute
  entity: "checkout-service"
  attribute: "maintainability"
  value: 5.8
  unit: "maintainability score (1-10 scale)"
  range:
    low: 4.5
    high: 7.0
  value_type: proxy-based
methodology: "Composite score from weighted proxy metrics: cyclomatic complexity (30%), test coverage (25%), documentation coverage (20%), dependency count (15%), code age (10%). Calibrated against team's historical maintainability assessments."
inputs_used:
  - indicator: "average cyclomatic complexity"
    value: "12.3 (moderate-high)"
    weight: 0.30
  - indicator: "test coverage"
    value: "67% (below target)"
    weight: 0.25
  - indicator: "documentation coverage"
    value: "45% of public APIs"
    weight: 0.20
  - indicator: "external dependency count"
    value: "34 dependencies"
    weight: 0.15
  - indicator: "median file age"
    value: "8 months since modification"
    weight: 0.10
sensitivity:
  - factor: "cyclomatic complexity calculation method"
    impact: medium
  - factor: "test quality vs. coverage quantity"
    impact: high
  - factor: "subjective calibration baseline"
    impact: medium
confidence: 0.62
evidence_anchors:
  - "tools/sonar:complexity_report"
  - "ci/coverage_report.xml:summary"
  - "docs/api/:file_count"
  - "package.json:dependencies"
assumptions:
  - "Proxy metrics correlate with actual maintainability"
  - "Historical calibration remains valid"
  - "All code is equally weighted regardless of criticality"
```

**Evidence pattern:** Composite metric from multiple proxy indicators.

---

### Example 2: Estimating Document Readability

**Input:**
```yaml
entity: "user_guide_v3.md"
attribute: "readability level"
evidence:
  - "Flesch-Kincaid grade level: 8.2"
  - "average sentence length: 16.4 words"
  - "technical term density: 12%"
scale: "ordinal (beginner, intermediate, advanced)"
```

**Output:**
```yaml
estimate:
  target_type: attribute
  entity: "user_guide_v3.md"
  attribute: "readability level"
  value: "intermediate"
  unit: "ordinal category"
  range:
    low: "beginner-intermediate"
    high: "intermediate-advanced"
  value_type: proxy-based
methodology: "Classification based on readability metrics. Flesch-Kincaid 8.2 maps to 8th-grade reading level. Technical term density of 12% suggests domain-specific vocabulary. Combined assessment places document at intermediate level."
inputs_used:
  - indicator: "Flesch-Kincaid grade level"
    value: "8.2"
    weight: 0.50
  - indicator: "average sentence length"
    value: "16.4 words (moderate)"
    weight: 0.25
  - indicator: "technical term density"
    value: "12% (moderate jargon)"
    weight: 0.25
sensitivity:
  - factor: "target audience assumptions"
    impact: high
  - factor: "domain-specific vocabulary assessment"
    impact: medium
  - factor: "visual complexity not captured"
    impact: low
confidence: 0.75
evidence_anchors:
  - "docs/user_guide_v3.md"
  - "tools/readability-analyzer:output"
assumptions:
  - "Readability metrics apply to technical documentation"
  - "Target audience has general literacy"
  - "Document structure doesn't affect comprehension"
```

**Evidence pattern:** Classification from standardized readability metrics.

---

### Example 3: Estimating Team Velocity

**Input:**
```yaml
entity: "backend-team"
attribute: "sprint velocity"
precision: "moderate"
evidence:
  - "Last 4 sprints: 32, 28, 35, 30 story points"
  - "Current team size: 5 developers"
  - "1 developer on vacation this sprint"
```

**Output:**
```yaml
estimate:
  target_type: attribute
  entity: "backend-team"
  attribute: "sprint velocity"
  value: 25.0
  unit: "story points per sprint"
  range:
    low: 22
    high: 28
  value_type: inferred
methodology: "Historical average (31.25 points) adjusted for 20% capacity reduction due to team member absence. Variance in historical data used for range bounds."
inputs_used:
  - indicator: "historical velocity average"
    value: "31.25 story points (std dev 2.9)"
    weight: 0.70
  - indicator: "capacity adjustment"
    value: "-20% (1 of 5 developers absent)"
    weight: 0.30
sensitivity:
  - factor: "story point estimation consistency"
    impact: high
  - factor: "sprint scope changes"
    impact: medium
  - factor: "team composition effects"
    impact: medium
confidence: 0.72
evidence_anchors:
  - "jira/velocity_report:last_4_sprints"
  - "hr/pto_calendar:current_sprint"
assumptions:
  - "Story point estimates are consistent across sprints"
  - "Team velocity scales linearly with capacity"
  - "No other factors affecting this sprint"
```

**Evidence pattern:** Historical baseline with capacity adjustment.

## Verification

- [ ] Entity and attribute are clearly specified
- [ ] Value type (measured, inferred, proxy-based) is declared
- [ ] Indicators used are listed with their contributions
- [ ] Estimate is within plausible bounds for the attribute
- [ ] Evidence anchors support the inputs_used claims

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Clearly distinguish estimated from measured values
- If proxy correlation is weak, lower confidence accordingly
- Do not estimate attributes that require domain expertise without stating limitations

## Composition Patterns

**Commonly follows:**
- `inspect` - To understand entity structure before estimating attributes
- `retrieve` - To gather indicator data
- `search` - To find comparable reference points

**Commonly precedes:**
- `compare` - To compare attributes across entities
- `forecast-attribute` - To project attribute evolution
- `discover-relationship` - To find attribute correlations

**Anti-patterns:**
- Never use for future attribute predictions (use forecast-attribute instead)
- Avoid when direct measurement is readily available

**Workflow references:**
- See `workflow_catalog.json#quality_assessment` for attribute estimation in QA context
