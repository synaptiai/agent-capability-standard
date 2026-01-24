---
name: estimate
description: Produce a numeric estimate with uncertainty range, methodology, and sensitivity analysis. Use when calculating values, probabilities, sizes, durations, or quantities.
argument-hint: "[quantity] [inputs] [methodology]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Derive a quantitative estimate for a specified quantity using available data, explicit methodology, and uncertainty quantification. Estimation produces a value with bounds, not just a point estimate.

**Success criteria:**
- Point estimate with confidence range (low/high bounds)
- Explicit methodology documented
- Sensitivity factors identified
- Assumptions that could change the estimate listed

**Compatible schemas:**
- `docs/schemas/estimation_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `quantity` | Yes | string | What to estimate (e.g., "execution time", "file count", "memory usage") |
| `inputs` | Yes | object\|string | Data sources or reference values for estimation |
| `methodology` | No | string | Preferred estimation approach (e.g., "analogy", "decomposition", "historical") |
| `constraints` | No | object | Bounds, precision requirements, or units |

## Procedure

1) **Clarify the quantity**: Define exactly what is being estimated
   - Units of measurement
   - Precision required
   - Temporal scope (point-in-time vs. over period)

2) **Gather input data**: Collect relevant data points for estimation
   - Historical data: past measurements of similar quantities
   - Reference data: benchmarks, documentation, specifications
   - Derived data: calculated from related measurements

3) **Select methodology**: Choose estimation approach based on data availability
   - **Analogy**: estimate by comparison to similar known cases
   - **Decomposition**: break into components, estimate each, aggregate
   - **Historical**: extrapolate from past measurements
   - **Expert judgment**: structured reasoning when data is sparse

4) **Calculate estimate with bounds**: Produce range, not just point estimate
   - Low bound: optimistic or minimum plausible value
   - High bound: pessimistic or maximum plausible value
   - Point estimate: most likely value

5) **Analyze sensitivity**: Identify which inputs most affect the estimate
   - High impact: small changes cause large estimate changes
   - Medium impact: proportional relationship
   - Low impact: minimal effect on final estimate

6) **Ground claims**: Attach evidence anchors to inputs and methodology
   - Reference data sources with `file:line` or URLs
   - Document calculation steps

7) **Assess confidence**: Rate based on data quality and methodology robustness

## Output Contract

Return a structured object:

```yaml
estimate:
  value: number | string | object  # Point estimate
  unit: string | null  # Unit of measurement
  range:
    low: number  # Optimistic/minimum bound
    high: number  # Pessimistic/maximum bound
  distribution: string | null  # normal, uniform, triangular, etc.
methodology: string  # How the estimate was derived
inputs_used: array[string]  # Data sources referenced
sensitivity:
  - factor: string  # Input that affects estimate
    impact: low | medium | high  # How much it affects result
confidence: number  # 0.0-1.0 based on data quality
evidence_anchors: array[string]  # File:line references
assumptions: array[string]  # Explicitly stated assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.value` | number\|string | The point estimate |
| `estimate.range` | object | Low and high bounds |
| `methodology` | string | Approach used for estimation |
| `inputs_used` | array | Data sources that informed estimate |
| `sensitivity` | array | Factors that most affect the result |
| `confidence` | number | 0.0-1.0 based on data completeness |
| `evidence_anchors` | array[string] | References to source data |
| `assumptions` | array[string] | Conditions that could change estimate |

## Examples

### Example 1: Estimate Test Suite Execution Time

**Input:**
```yaml
quantity: "test suite execution time"
inputs:
  test_count: 847
  avg_test_duration_ms: 45
  parallelism: 4
  setup_overhead_s: 12
methodology: "decomposition"
```

**Output:**
```yaml
estimate:
  value: 21.5
  unit: "seconds"
  range:
    low: 18
    high: 35
  distribution: "triangular"
methodology: "Decomposition: (test_count * avg_duration / parallelism) + setup"
inputs_used:
  - "test_count from pytest --collect-only"
  - "avg_test_duration from last 5 CI runs"
  - "parallelism from pytest.ini"
  - "setup_overhead measured from fixtures"
sensitivity:
  - factor: "parallelism"
    impact: high
  - factor: "avg_test_duration"
    impact: medium
  - factor: "setup_overhead"
    impact: low
confidence: 0.75
evidence_anchors:
  - "pytest.ini:3"
  - "ci_logs/run_2024_01_15.log:summary"
assumptions:
  - "No external service dependencies (mocked)"
  - "Test execution is CPU-bound, not I/O-bound"
  - "No test failures causing retries"
```

**Evidence pattern:** Read test configuration for counts and settings, analyze CI logs for historical durations.

---

### Example 2: Estimate Codebase Size for Migration

**Input:**
```yaml
quantity: "lines of code to migrate"
inputs:
  source_directory: "src/legacy/"
  file_patterns: ["*.java", "*.xml"]
methodology: "direct measurement with sampling"
```

**Output:**
```yaml
estimate:
  value: 45200
  unit: "lines"
  range:
    low: 42000
    high: 48000
  distribution: "uniform"
methodology: "Direct count via wc -l with pattern matching"
inputs_used:
  - "find src/legacy -name '*.java' | wc -l"
  - "Sampled 10 files for blank/comment ratio (22%)"
sensitivity:
  - factor: "blank/comment ratio"
    impact: medium
  - factor: "file pattern completeness"
    impact: high
confidence: 0.9
evidence_anchors:
  - "src/legacy/:directory-listing"
  - "tool:wc:line-count-output"
assumptions:
  - "All relevant files match provided patterns"
  - "XML config files included in migration scope"
```

## Verification

- [ ] Estimate includes both point value and range
- [ ] Range bounds are logically ordered (low < value < high)
- [ ] Methodology is documented and reproducible
- [ ] All inputs_used have corresponding evidence_anchors
- [ ] Sensitivity factors are ranked by impact
- [ ] Assumptions are falsifiable

**Verification tools:** Bash (for measurement commands), Read (for config verification)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always provide uncertainty range, never just point estimate
- Document methodology explicitly for reproducibility
- Flag low-confidence estimates (< 0.5) with explicit warning
- Do not estimate quantities with no available inputs - request data instead

## Composition Patterns

**Commonly follows:**
- `detect` - Estimate quantities for detected entities
- `identify` - Estimate properties of identified entities
- `inspect` - Estimate based on observed system state

**Commonly precedes:**
- `forecast` - Estimates feed into future projections
- `compare` - Estimates enable quantitative comparison
- `plan` - Estimates inform effort and resource planning

**Anti-patterns:**
- Never use estimate for existence checking (use `detect`)
- Avoid estimate for classification (use `identify`)
- Do not use estimate for future prediction (use `forecast`)

**Workflow references:**
- See `composition_patterns.md#risk-assessment` for estimate-risk usage
- See `composition_patterns.md#capability-gap-analysis` for effort estimation
