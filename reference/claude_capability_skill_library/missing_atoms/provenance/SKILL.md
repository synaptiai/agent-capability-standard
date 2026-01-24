---
name: provenance
description: Track the origin, transformations, and decision lineage for data and claims. Use when establishing trust, debugging data quality issues, or auditing how conclusions were reached.
argument-hint: "[target] [depth: shallow|deep] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Establish **provenance** - the complete history of where data came from, how it was transformed, and what decisions shaped its current form. This enables trust, reproducibility, and debugging.

**Success criteria:**
- Origin sources are identified with timestamps
- All transformations are documented with inputs/outputs
- Decision points have recorded rationale
- Chain of custody is complete (no gaps)
- Integrity can be verified where checksums exist

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | Entity, data, or claim to trace provenance for |
| `depth` | No | string | `shallow` (immediate sources) or `deep` (full history); default: deep |
| `include_decisions` | No | boolean | Include decision rationale in lineage; default: true |
| `constraints` | No | object | Time bounds, source filters |

## Procedure

1) **Identify target**: Determine what we're tracing provenance for
   - Data artifact (file, record, model output)
   - Claim or assertion (factual statement)
   - Entity (resolved identity from multiple sources)
   - Decision (action taken or recommendation made)

2) **Trace origin**: Find the primary source(s)
   - For data: Original creation point (API call, user input, sensor)
   - For claims: Source documents, observations, or calculations
   - For entities: First appearance in any system
   - Record: timestamp, actor (human/system), context

3) **Document transformations**: Track how data changed
   - Each transformation step: input -> process -> output
   - Tools/code used for transformation
   - Parameters and configuration
   - Data loss or enrichment at each step

4) **Capture decision points**: Record where choices were made
   - What alternatives existed
   - What criteria were used
   - Who/what made the decision
   - Confidence at decision time

5) **Verify chain integrity**: Check for gaps or inconsistencies
   - All steps connected (output of one is input to next)
   - Timestamps are monotonic (no time travel)
   - Hashes match where available
   - No unexplained changes

6) **Assess source authority**: Rate reliability of origins
   - Primary sources (direct observation) > Secondary (reported)
   - Official records > informal documentation
   - Automated systems > manual entry (for some data)
   - Recent > stale

7) **Identify gaps**: Document missing provenance
   - Steps where transformation is unknown
   - Sources that couldn't be traced
   - Decisions without recorded rationale

8) **Build lineage representation**: Structure the provenance chain
   - Graph structure (DAG of transformations)
   - Temporal sequence
   - Branching points where data diverged

## Output Contract

Return a structured object:

```yaml
lineage:
  entity_id: string  # What we traced
  entity_type: string  # data, claim, entity, decision
  origin:
    source: string  # Original source (file, API, system)
    timestamp: string  # ISO 8601
    actor: string | null  # Who/what created it
    context: string | null  # Circumstances of creation
    authority: low | medium | high
  transformations:
    - step: integer  # Order in chain
      operation: string  # What transformation occurred
      input: string  # Reference to input
      output: string  # Reference to output
      tool: string | null  # Tool or process used
      timestamp: string
      actor: string | null
      parameters: object | null
      data_quality:
        added: array[string]  # Fields/data added
        removed: array[string]  # Fields/data removed
        modified: array[string]  # Fields/data changed
  decisions:
    - step: integer  # Where in chain
      decision: string  # What was decided
      alternatives: array[string]  # Other options considered
      rationale: string  # Why this choice
      actor: string  # Who decided
      confidence: number
  current_location: string  # Where data/entity is now
integrity:
  hash: string | null  # Current hash if computable
  verified: boolean  # Could we verify the chain?
  chain_of_custody: array[string]  # All custodians
  gaps:
    - position: string  # Where in chain
      description: string  # What's missing
      impact: low | medium | high
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `origin` | object | Where the data/entity first came from |
| `transformations` | array | Sequence of changes to the data |
| `decisions` | array | Choices made that affected the data |
| `integrity` | object | Verification status of the chain |
| `gaps` | array | Missing provenance information |

## Examples

### Example 1: Model Output Provenance

**Input:**
```yaml
target: "prediction_user_churn_20250124"
depth: deep
```

**Output:**
```yaml
lineage:
  entity_id: "prediction_user_churn_20250124"
  entity_type: "data"
  origin:
    source: "stripe_api:customers"
    timestamp: "2025-01-20T00:00:00Z"
    actor: "data_pipeline_v2"
    context: "Nightly customer data sync"
    authority: high
  transformations:
    - step: 1
      operation: "extract"
      input: "stripe_api:customers"
      output: "raw/customers_20250120.parquet"
      tool: "airflow:stripe_extract_dag"
      timestamp: "2025-01-20T02:15:00Z"
      actor: "data_pipeline_v2"
      parameters: { date: "2025-01-20", full_refresh: false }
      data_quality:
        added: []
        removed: []
        modified: []
    - step: 2
      operation: "transform"
      input: "raw/customers_20250120.parquet"
      output: "processed/customer_features_20250120.parquet"
      tool: "dbt:customer_features"
      timestamp: "2025-01-20T03:00:00Z"
      actor: "data_pipeline_v2"
      parameters: { model_version: "2.3.1" }
      data_quality:
        added: ["days_since_last_purchase", "lifetime_value", "engagement_score"]
        removed: ["raw_event_log"]
        modified: ["purchase_count"]
    - step: 3
      operation: "predict"
      input: "processed/customer_features_20250120.parquet"
      output: "predictions/churn_scores_20250124.parquet"
      tool: "mlflow:churn_model_v4"
      timestamp: "2025-01-24T06:00:00Z"
      actor: "ml_inference_service"
      parameters: { model_id: "churn_v4_20250115", threshold: 0.7 }
      data_quality:
        added: ["churn_probability", "churn_risk_tier"]
        removed: []
        modified: []
  decisions:
    - step: 2
      decision: "Used engagement_score instead of raw_events"
      alternatives: ["raw_event_counts", "session_duration"]
      rationale: "engagement_score showed better correlation with churn in validation"
      actor: "data_science_team"
      confidence: 0.85
    - step: 3
      decision: "Set threshold at 0.7 for high-risk classification"
      alternatives: ["0.5 (balanced)", "0.8 (high precision)"]
      rationale: "Optimize for recall - prefer to catch more churners"
      actor: "product_manager"
      confidence: 0.9
  current_location: "predictions/churn_scores_20250124.parquet"
integrity:
  hash: "sha256:abc123def456..."
  verified: true
  chain_of_custody:
    - "stripe_api"
    - "data_pipeline_v2"
    - "ml_inference_service"
  gaps: []
confidence: 0.95
evidence_anchors:
  - "airflow:logs/stripe_extract_20250120"
  - "dbt:run_results/20250120"
  - "mlflow:runs/churn_inference_20250124"
assumptions:
  - "Stripe API data is authoritative for customer records"
  - "dbt transformations are deterministic"
```

**Evidence pattern:** Traced from ML output back through pipeline, collected logs from each system.

---

### Example 2: Claim Provenance

**Input:**
```yaml
target:
  claim: "The API latency increased 30% after the v2.5 deployment"
depth: deep
```

**Output:**
```yaml
lineage:
  entity_id: "claim_latency_increase_v25"
  entity_type: "claim"
  origin:
    source: "datadog:dashboard/api_latency"
    timestamp: "2025-01-24T11:30:00Z"
    actor: "sre_oncall"
    context: "Investigating alert for latency SLO breach"
    authority: medium
  transformations:
    - step: 1
      operation: "observation"
      input: "datadog:metrics/api.latency.p99"
      output: "raw_observation"
      tool: "datadog_ui"
      timestamp: "2025-01-24T11:30:00Z"
      actor: "sre_oncall"
      data_quality:
        added: []
        removed: []
        modified: []
    - step: 2
      operation: "calculation"
      input: "raw_observation"
      output: "percent_change"
      tool: "manual_calculation"
      timestamp: "2025-01-24T11:35:00Z"
      actor: "sre_oncall"
      parameters:
        before: "45ms (baseline 7-day avg)"
        after: "58.5ms (current p99)"
        formula: "(58.5 - 45) / 45 = 0.30"
      data_quality:
        added: ["percent_change"]
        removed: []
        modified: []
  decisions:
    - step: 1
      decision: "Used p99 latency instead of mean"
      alternatives: ["p50", "mean", "p95"]
      rationale: "p99 better captures tail latency issues affecting users"
      actor: "sre_oncall"
      confidence: 0.9
    - step: 2
      decision: "Used 7-day average as baseline"
      alternatives: ["24h average", "pre-deploy snapshot", "same day last week"]
      rationale: "7-day average smooths daily variations"
      actor: "sre_oncall"
      confidence: 0.8
  current_location: "incident_report:INC-2025-0124"
integrity:
  hash: null
  verified: true
  chain_of_custody:
    - "datadog"
    - "sre_oncall"
  gaps:
    - position: "step 2"
      description: "Manual calculation not in version control"
      impact: low
confidence: 0.85
evidence_anchors:
  - "datadog:dashboard/api_latency?from=2025-01-17&to=2025-01-24"
  - "deployment_log:v2.5_20250124"
assumptions:
  - "Datadog metrics are accurate and complete"
  - "No other changes occurred between baseline and current measurement"
```

## Verification

- [ ] Origin is identified with timestamp and source
- [ ] Transformation chain is continuous (no gaps in custody)
- [ ] Timestamps are monotonically increasing
- [ ] Hashes match where available
- [ ] All actors are identified

**Verification tools:** Hash verification, log correlation, timestamp validation

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not fabricate provenance - mark gaps explicitly
- When chain is broken, document impact on confidence
- Distinguish between verified and assumed provenance
- Protect sensitive provenance data (PII in actor names, etc.)

## Composition Patterns

**Commonly follows:**
- `retrieve` - Get data before tracing its history
- `identity-resolution` - Trace provenance of resolved entities
- `grounding` - Provenance supports grounding claims

**Commonly precedes:**
- `audit` - Provenance feeds into audit records
- `verify` - Provenance helps verify data quality
- `explain` - Provenance supports explanations

**Anti-patterns:**
- Never claim provenance is complete without verification
- Avoid circular provenance (A from B, B from A)

**Workflow references:**
- See `composition_patterns.md#world-model-build` for provenance in model construction
- See `composition_patterns.md#digital-twin-sync-loop` for ongoing provenance tracking
