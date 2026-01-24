---
name: estimate-relationship
description: Approximate the strength, type, or nature of a relationship between entities. Use when quantifying connections, measuring correlation, or assessing dependencies.
argument-hint: "[entity_a] [entity_b] [--type <relationship-type>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce a quantitative or qualitative estimate of the relationship between two or more entities. This skill answers "how strongly are A and B related?" or "what is the nature of the connection between A and B?" It assesses current or historical relationships, not predicted future relationships.

**Success criteria:**
- Relationship strength is quantified with appropriate metric
- Relationship type/direction is classified
- Evidence supporting the relationship is cited
- Uncertainty in the relationship estimate is expressed

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entity_a` | Yes | string | First entity in the relationship |
| `entity_b` | Yes | string | Second entity in the relationship |
| `relationship_type` | No | string | Type to assess: causal, correlational, dependency, hierarchical, temporal |
| `scope` | No | object | Context boundaries for the relationship |
| `metric` | No | string | How to measure: coefficient, score, categorical |

## Procedure

1) **Identify the entities and relationship context**: Clarify what entities are being compared and in what domain.
   - What are the entities? (variables, systems, people, concepts)
   - What type of relationship is being assessed?
   - What scope or context bounds the relationship?

2) **Determine appropriate relationship metric**: Select how to quantify the relationship.
   - **Correlational**: Pearson, Spearman, or mutual information
   - **Dependency**: Coupling score, dependency count, call frequency
   - **Causal**: Effect size, intervention response
   - **Hierarchical**: Distance, containment level
   - **Categorical**: Type classification (strong/weak, direct/indirect)

3) **Gather evidence of relationship**: Collect data showing the connection.
   - Look for co-occurrence patterns
   - Find direct references between entities
   - Identify shared attributes or behaviors
   - Search for documented dependencies

4) **Compute relationship strength**: Apply the chosen metric to the evidence.
   - Calculate quantitative measure if data supports it
   - Classify qualitatively if quantitative data is insufficient
   - Determine direction if relationship is asymmetric

5) **Assess relationship quality**: Evaluate confidence in the relationship finding.
   - How much data supports this relationship?
   - Are there confounders that could explain the connection?
   - Is the relationship stable or contextual?

6) **Format output with grounding**: Structure per contract with evidence anchors.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: relationship
  value: number | string  # Relationship strength (0-1, coefficient, or category)
  unit: string | null     # Metric type (correlation, coupling, etc.)
  range:
    low: number           # Lower bound of relationship strength
    high: number          # Upper bound of relationship strength
relationship:
  type: string            # causal, correlational, dependency, hierarchical, temporal
  direction: string       # a->b, b->a, bidirectional, undirected
  symmetry: symmetric | asymmetric
methodology: string       # How relationship was measured
inputs_used:
  - string                # Evidence and data sources
sensitivity:
  - factor: string        # What could change the relationship
    impact: low | medium | high
confidence: number        # 0.0-1.0
evidence_anchors:
  - string                # file:line, url, or tool reference
assumptions:
  - string                # Explicit assumptions about the relationship
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.value` | number/string | Strength of relationship (e.g., 0.85 correlation, "strong") |
| `relationship.type` | string | Nature of the relationship |
| `relationship.direction` | string | Which entity influences which |
| `methodology` | string | How the relationship was identified and measured |
| `confidence` | number | Certainty in both existence and strength of relationship |

## Examples

### Example 1: Estimating Code Module Coupling

**Input:**
```yaml
entity_a: "auth-service module"
entity_b: "user-service module"
relationship_type: "dependency"
scope:
  codebase: "main-backend"
metric: "coupling score"
```

**Output:**
```yaml
estimate:
  target_type: relationship
  value: 0.73
  unit: "coupling coefficient (0-1 scale)"
  range:
    low: 0.68
    high: 0.78
relationship:
  type: dependency
  direction: "user-service -> auth-service"
  symmetry: asymmetric
methodology: "Counted import statements and function calls between modules, normalized by total external dependencies of each module. Coupling = (cross-module calls) / (total external calls)."
inputs_used:
  - "user-service imports: 12 from auth-service"
  - "auth-service imports: 2 from user-service"
  - "user-service total external imports: 34"
  - "function call analysis: 28 cross-boundary calls"
sensitivity:
  - factor: "indirect dependencies through shared libraries"
    impact: medium
  - factor: "runtime vs compile-time dependencies"
    impact: low
  - factor: "interface vs implementation coupling"
    impact: high
confidence: 0.82
evidence_anchors:
  - "src/user-service/auth_client.py:1-15"
  - "src/auth-service/exports.py:public_api"
  - "tools/dependency-analyzer:coupling_report"
assumptions:
  - "Import count is proxy for coupling strength"
  - "All imports are actively used"
  - "Compile-time dependencies represent runtime behavior"
```

**Evidence pattern:** Static analysis of code dependencies with normalization.

---

### Example 2: Estimating Variable Correlation in Dataset

**Input:**
```yaml
entity_a: "page_load_time"
entity_b: "bounce_rate"
relationship_type: "correlational"
scope:
  dataset: "web_analytics_q4"
  sample_size: 50000
metric: "correlation coefficient"
```

**Output:**
```yaml
estimate:
  target_type: relationship
  value: 0.64
  unit: "Pearson correlation coefficient"
  range:
    low: 0.61
    high: 0.67
relationship:
  type: correlational
  direction: "bidirectional (correlation)"
  symmetry: symmetric
methodology: "Pearson correlation computed over 50,000 page view sessions. 95% confidence interval via Fisher z-transformation. Outliers beyond 3 std dev removed (0.2% of data)."
inputs_used:
  - "page_load_time: mean 2.3s, std 1.1s"
  - "bounce_rate: mean 42%, std 18%"
  - "n = 50,000 sessions after outlier removal"
  - "correlation test: r=0.64, p<0.001"
sensitivity:
  - factor: "device type (mobile vs desktop)"
    impact: high
  - factor: "page content type"
    impact: medium
  - factor: "user intent (browsing vs purchasing)"
    impact: medium
confidence: 0.88
evidence_anchors:
  - "data/web_analytics_q4.parquet:schema"
  - "analysis/correlation_matrix.py:output"
  - "reports/performance_analysis.md:section_3"
assumptions:
  - "Linear relationship is appropriate model"
  - "No lurking variables fully explain the correlation"
  - "Sample is representative of typical traffic"
```

**Evidence pattern:** Statistical correlation analysis with confidence intervals.

## Verification

- [ ] Both entities are clearly identified
- [ ] Relationship type is specified and appropriate
- [ ] Strength metric matches the relationship type
- [ ] Direction is stated (or explicitly marked as undirected)
- [ ] Evidence anchors show the connection between entities

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not confuse correlation with causation without causal evidence
- State when relationship may be spurious or confounded
- If relationship is contextual, note the context boundaries

## Composition Patterns

**Commonly follows:**
- `detect-entity` - To identify entities before assessing relationships
- `search` - To find evidence of connections
- `inspect` - To understand entity structure

**Commonly precedes:**
- `discover-relationship` - When estimate reveals unexpected pattern
- `compare` - To compare relationship strengths
- `explain` - To articulate why relationship exists

**Anti-patterns:**
- Never claim causal relationship from correlation alone
- Avoid estimating relationships without sufficient co-occurrence data

**Workflow references:**
- See `workflow_catalog.json#dependency_analysis` for architecture review context
