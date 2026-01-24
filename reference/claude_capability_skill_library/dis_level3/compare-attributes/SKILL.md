---
name: compare-attributes
description: Compare attributes, features, or metrics across multiple options to identify optimal choices. Use when evaluating product features, comparing metrics, or assessing configuration options.
argument-hint: "[option_a] [option_b] [attributes] [thresholds]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically compare specific attributes (features, metrics, specifications) across multiple options to support data-driven decision making with explicit thresholds and trade-off analysis.

**Success criteria:**
- Each attribute is measured consistently across all options
- Thresholds distinguish acceptable from unacceptable values
- Trade-offs between attributes are explicitly documented
- Recommendation accounts for attribute interdependencies

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `options` | Yes | array[string\|object] | Options to compare |
| `attributes` | Yes | array[string] | Attributes to evaluate (features, metrics, specs) |
| `thresholds` | No | object | Min/max acceptable values per attribute |
| `weights` | No | object | Relative importance of each attribute |
| `measurement_method` | No | string | How to measure (benchmark, spec sheet, analysis) |

## Procedure

1) **Catalog attributes**: Define each attribute precisely
   - Specify unit of measurement
   - Define how to obtain the value (spec, benchmark, calculation)
   - Identify which attributes are independent vs derived

2) **Apply thresholds**: If provided, mark hard constraints
   - Attributes below minimum threshold = disqualifying
   - Attributes above maximum threshold = potential overhead/waste
   - Document which options pass/fail thresholds

3) **Gather measurements**: For each option-attribute pair
   - Use consistent measurement methodology
   - Record raw values with evidence anchors
   - Note measurement uncertainty or variability

4) **Normalize scores**: Convert raw values to comparable scale
   - Linear normalization for continuous metrics
   - Ordinal mapping for categorical attributes
   - Higher = better (invert if necessary)

5) **Identify correlations**: Check for attribute interdependencies
   - Attributes that trade off (e.g., speed vs memory)
   - Attributes that cluster (e.g., price and quality tier)

6) **Synthesize recommendation**: Weight and aggregate
   - Apply weights to normalized scores
   - Flag options that fail hard thresholds
   - Recommend based on use-case priorities

## Output Contract

Return a structured object:

```yaml
options:
  - id: string
    summary: string
    passes_thresholds: boolean
attributes:
  - name: string
    unit: string | null
    direction: higher_better | lower_better
    weight: number
    threshold:
      min: number | null
      max: number | null
comparison_matrix:
  - option_id: string
    scores:
      - attribute: string
        raw_value: number | string
        normalized_score: number  # 0.0-1.0
        meets_threshold: boolean
        rationale: string
        evidence_anchor: string
correlations:
  - attributes: array[string]
    relationship: tradeoff | cluster | independent
    note: string
recommendation:
  choice: string
  rationale: string
  weighted_score: number
  runner_up: string | null
tradeoffs:
  - option: string
    pros: array[string]  # Attributes where this option excels
    cons: array[string]  # Attributes where this option lags
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `options` | array | Options with threshold pass/fail status |
| `attributes` | array | Attributes with units, direction, weights, thresholds |
| `comparison_matrix` | array | Raw and normalized values per option-attribute |
| `correlations` | array | Attribute interdependencies |
| `recommendation` | object | Winning option with weighted score |
| `tradeoffs` | array | Where each option excels and lags |
| `confidence` | number | 0.0-1.0 based on measurement quality |
| `evidence_anchors` | array[string] | Spec sheets, benchmarks, or measurements |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Comparing Cloud VM Instance Types

**Input:**
```yaml
options:
  - id: "aws-m5.large"
    provider: "AWS"
  - id: "gcp-n2-standard-2"
    provider: "GCP"
  - id: "azure-d2s-v3"
    provider: "Azure"
attributes:
  - "vcpu_count"
  - "memory_gb"
  - "network_bandwidth_gbps"
  - "price_per_hour"
thresholds:
  vcpu_count:
    min: 2
  memory_gb:
    min: 8
  price_per_hour:
    max: 0.15
weights:
  vcpu_count: 0.2
  memory_gb: 0.3
  network_bandwidth_gbps: 0.2
  price_per_hour: 0.3
```

**Output:**
```yaml
options:
  - id: "aws-m5.large"
    summary: "General purpose instance, Intel Xeon, EBS-optimized"
    passes_thresholds: true
  - id: "gcp-n2-standard-2"
    summary: "General purpose instance, Intel Cascade Lake"
    passes_thresholds: true
  - id: "azure-d2s-v3"
    summary: "General purpose instance, Intel Xeon, Premium Storage"
    passes_thresholds: false
attributes:
  - name: "vcpu_count"
    unit: "vCPUs"
    direction: higher_better
    weight: 0.2
    threshold:
      min: 2
      max: null
  - name: "memory_gb"
    unit: "GB"
    direction: higher_better
    weight: 0.3
    threshold:
      min: 8
      max: null
  - name: "network_bandwidth_gbps"
    unit: "Gbps"
    direction: higher_better
    weight: 0.2
    threshold:
      min: null
      max: null
  - name: "price_per_hour"
    unit: "USD"
    direction: lower_better
    weight: 0.3
    threshold:
      min: null
      max: 0.15
comparison_matrix:
  - option_id: "aws-m5.large"
    scores:
      - attribute: "vcpu_count"
        raw_value: 2
        normalized_score: 0.5
        meets_threshold: true
        rationale: "Matches minimum requirement exactly"
        evidence_anchor: "https://aws.amazon.com/ec2/instance-types/m5/"
      - attribute: "memory_gb"
        raw_value: 8
        normalized_score: 0.5
        meets_threshold: true
        rationale: "Matches minimum requirement exactly"
        evidence_anchor: "https://aws.amazon.com/ec2/instance-types/m5/"
      - attribute: "network_bandwidth_gbps"
        raw_value: 10
        normalized_score: 0.8
        meets_threshold: true
        rationale: "High baseline bandwidth"
        evidence_anchor: "https://aws.amazon.com/ec2/instance-types/m5/"
      - attribute: "price_per_hour"
        raw_value: 0.096
        normalized_score: 0.85
        meets_threshold: true
        rationale: "Well under threshold, good value"
        evidence_anchor: "https://aws.amazon.com/ec2/pricing/"
  - option_id: "gcp-n2-standard-2"
    scores:
      - attribute: "vcpu_count"
        raw_value: 2
        normalized_score: 0.5
        meets_threshold: true
        rationale: "Matches minimum requirement"
        evidence_anchor: "https://cloud.google.com/compute/docs/machine-types"
      - attribute: "memory_gb"
        raw_value: 8
        normalized_score: 0.5
        meets_threshold: true
        rationale: "Matches minimum requirement"
        evidence_anchor: "https://cloud.google.com/compute/docs/machine-types"
      - attribute: "network_bandwidth_gbps"
        raw_value: 10
        normalized_score: 0.8
        meets_threshold: true
        rationale: "Comparable to AWS"
        evidence_anchor: "https://cloud.google.com/compute/docs/network-bandwidth"
      - attribute: "price_per_hour"
        raw_value: 0.097
        normalized_score: 0.84
        meets_threshold: true
        rationale: "Slightly higher than AWS but within threshold"
        evidence_anchor: "https://cloud.google.com/compute/pricing"
  - option_id: "azure-d2s-v3"
    scores:
      - attribute: "vcpu_count"
        raw_value: 2
        normalized_score: 0.5
        meets_threshold: true
        rationale: "Matches minimum requirement"
        evidence_anchor: "https://docs.microsoft.com/azure/virtual-machines/dv3-dsv3-series"
      - attribute: "memory_gb"
        raw_value: 8
        normalized_score: 0.5
        meets_threshold: true
        rationale: "Matches minimum requirement"
        evidence_anchor: "https://docs.microsoft.com/azure/virtual-machines/dv3-dsv3-series"
      - attribute: "network_bandwidth_gbps"
        raw_value: 3
        normalized_score: 0.3
        meets_threshold: true
        rationale: "Lower than competitors"
        evidence_anchor: "https://docs.microsoft.com/azure/virtual-machines/dv3-dsv3-series"
      - attribute: "price_per_hour"
        raw_value: 0.192
        normalized_score: 0.2
        meets_threshold: false
        rationale: "Exceeds price threshold by 28%"
        evidence_anchor: "https://azure.microsoft.com/pricing/details/virtual-machines/"
correlations:
  - attributes: ["vcpu_count", "memory_gb"]
    relationship: cluster
    note: "Instance types bundle CPU and memory in fixed ratios"
  - attributes: ["network_bandwidth_gbps", "price_per_hour"]
    relationship: tradeoff
    note: "Higher bandwidth tiers generally cost more"
recommendation:
  choice: "aws-m5.large"
  rationale: "Best price-performance, highest weighted score among threshold-passing options"
  weighted_score: 0.73
  runner_up: "gcp-n2-standard-2"
tradeoffs:
  - option: "aws-m5.large"
    pros:
      - "Best price ($0.096/hr)"
      - "High network bandwidth (10 Gbps)"
      - "EBS optimization included"
    cons:
      - "Memory/CPU at minimum threshold"
      - "Committed use discounts less flexible than GCP"
  - option: "gcp-n2-standard-2"
    pros:
      - "Comparable specs to AWS"
      - "Sustained use discounts automatic"
      - "Live migration support"
    cons:
      - "Slightly higher price"
      - "Smaller ecosystem of integrated services"
  - option: "azure-d2s-v3"
    pros:
      - "Premium storage capable"
      - "Good for Microsoft ecosystem"
    cons:
      - "FAILS price threshold"
      - "Lower network bandwidth (3 Gbps)"
confidence: 0.85
evidence_anchors:
  - "https://aws.amazon.com/ec2/instance-types/m5/"
  - "https://aws.amazon.com/ec2/pricing/"
  - "https://cloud.google.com/compute/docs/machine-types"
  - "https://cloud.google.com/compute/pricing"
  - "https://docs.microsoft.com/azure/virtual-machines/dv3-dsv3-series"
  - "https://azure.microsoft.com/pricing/details/virtual-machines/"
assumptions:
  - "US region pricing (us-east-1, us-central1, East US)"
  - "On-demand pricing without reservations"
  - "Prices as of evaluation date"
  - "Network bandwidth is baseline, not burst"
```

**Evidence pattern:** Cloud provider documentation + pricing pages

## Verification

- [ ] All attributes measured with consistent methodology
- [ ] Threshold violations correctly identified
- [ ] Normalized scores in valid range (0.0-1.0)
- [ ] Weighted calculation is mathematically correct
- [ ] Disqualified options not recommended

**Verification tools:** Read (for spec sheets), Grep (for searching documentation)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Use consistent measurement methodology across all options
- Document when measurements have different precision or recency
- Flag when attributes may have changed since measurement
- Stop and clarify if thresholds create contradictory requirements

## Composition Patterns

**Commonly follows:**
- `search` - to find options to compare
- `retrieve` - to gather specifications
- `identify-attribute` - to clarify which attributes matter

**Commonly precedes:**
- `compare-entities` - for broader entity comparison using these attributes
- `generate-plan` - to plan based on selected option
- `summarize` - to create attribute comparison summary

**Anti-patterns:**
- Never compare attributes without units (ambiguous interpretation)
- Avoid mixing measurement methodologies within same attribute

**Workflow references:**
- See `workflow_catalog.json#procurement_decision` for purchasing workflows
