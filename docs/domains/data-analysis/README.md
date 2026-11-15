# Data Analysis Domain

This document describes how to use the Grounded Agency framework for data science and analytics environments.

## Overview

The data analysis domain profile is calibrated for environments where:
- **Data quality is critical** — Garbage in, garbage out
- **Reproducibility matters** — Analysis must be traceable
- **Statistics require rigor** — Uncertainty must be explicit
- **Models need governance** — Drift detection and retraining

The profile takes effect where a host, a safety layer or the validator applies it (Standard 1.2.0 [§5.21](../../../spec/STANDARD-v1.2.0.md#521-domain-profiles)): applied, its rules raise the flags of the steps and calls they name, and only tighten. A workflow's `profile` field applies nothing. See [Status of Domain Profiles](../README.md#status-of-domain-profiles).

## Domain Profile

**Profile location:** `schemas/profiles/data_analysis.yaml`

### Trust Weights

Data analysis trusts certified and validated sources:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| Certified Dataset | 0.95 | Validated, governed data |
| Data Warehouse | 0.92 | Curated enterprise data |
| Schema Registry | 0.92 | Authoritative schemas |
| Production DB | 0.90 | Source of truth |
| Feature Store | 0.90 | Engineered, validated |
| Data Quality System | 0.90 | Monitoring validation |
| ETL Pipeline | 0.88 | Processed data |
| Model Registry | 0.88 | Governed models |
| Data Steward | 0.85 | Human governance |
| Domain Expert | 0.82 | Subject matter knowledge |
| Analyst Annotation | 0.78 | Analyst notes |
| API Feed | 0.70 | External data |
| Public Dataset | 0.65 | Public, varying quality |
| Web Scrape | 0.55 | Unstructured, unreliable |

### Risk Thresholds

```yaml
auto_approve: low       # Low-risk analysis auto-approved
require_review: medium  # Medium requires data team review
require_human: high     # High-risk requires approval
block_autonomous:
  - mutate              # Never modify production data autonomously
  - send                # Never publish results without review
```

### Checkpoint Policy

Data analysis requires checkpoints before:
- Writing to production data stores
- Deploying models
- Publishing reports
- Modifying pipeline configurations

The profile states it as checkpoint rules on capabilities ([§5.21.3](../../../spec/STANDARD-v1.2.0.md#5213-effect-on-steps-and-calls); a `checkpoint` step is exempt):

```yaml
checkpoint_policy:
  # Standard v1.2 §5.21: capability ids or "*". From 1.0.0's labels:
  # before_data_mutation -> mutate; before_model_deployment -> execute;
  # before_report_publish -> send; before_pipeline_change (high_risk) and
  # during_batch_job (medium_risk) -> "*": medium_risk.
  mutate: always
  execute: always
  send: always
  "*": medium_risk
```

## Available Workflows

### 1. Data Pipeline Validation

**Goal:** Validate pipeline outputs for quality, schema, and statistical consistency.

**Capabilities used:**
- `retrieve` — Get pipeline output and schema
- `constrain` — Validate against schema
- `measure` — Calculate statistics
- `compare` — Compare to baseline
- `detect` — Find anomalies
- `verify` — Run data quality checks
- `ground` — Verify lineage
- `classify` — Classify validation result
- `generate` — Create validation report
- `audit` — Record validation

**Trigger:** Pipeline completion

**Output:** Validation report with pass/fail verdict

### 2. Anomaly Investigation

**Goal:** Investigate detected anomalies to find root cause.

**Capabilities used:**
- `retrieve` — Get anomaly data
- `observe` — Examine in context
- `discover` — Find patterns
- `attribute` — Identify causes
- `search` — Find related events
- `compare` — Compare to baseline
- `measure` — Quantify impact
- `simulate` — Project continuation
- `plan` — Generate remediation
- `explain` — Create summary
- `audit` — Record investigation

**Trigger:** Anomaly detection alert

**Output:** Investigation summary with recommendations

### 3. Report Generation

**Goal:** Generate data-driven reports with insights.

**Capabilities used:**
- `retrieve` — Get template
- `search` — Query data sources
- `measure` — Compute metrics
- `compare` — Benchmark comparisons
- `detect` — Find trends
- `attribute` — Identify drivers
- `predict` — Forecast next period
- `ground` — Anchor to evidence
- `generate` — Create report
- `transform` — Format for audience
- `audit` — Record generation

**Trigger:** Scheduled or on-demand

**Output:** Formatted report with grounded insights

### 4. Model Monitoring

**Goal:** Monitor ML model performance and detect drift.

**Capabilities used:**
- `receive` — Ingest predictions
- `retrieve` — Get baselines
- `measure` — Calculate performance
- `compare` — Compare to baseline
- `observe` — Current distributions
- `detect` — Data drift
- `detect` — Concept drift
- `attribute` — Drift contributors
- `predict` — Performance trajectory
- `plan` — Recommend intervention
- `generate` — Monitoring report
- `audit` — Record cycle

**Trigger:** Scheduled monitoring window

**Output:** Monitoring report with intervention recommendations

## Customization Guide

### Adjusting Data Quality Thresholds

```yaml
# Stricter thresholds for financial data
pipeline:
  anomaly_threshold: 2.0    # Stricter than default 2.5
  null_tolerance: 0.01      # Max 1% nulls
  schema_strict: true       # No extra columns allowed
```

### Model-Specific Drift Thresholds

```yaml
# Model with known seasonal patterns
model:
  drift_threshold: 0.15     # Higher tolerance for seasonality
  concept_drift_threshold: 0.08
  monitoring_window: "7d"   # Weekly assessment
```

### Custom Evidence Requirements

```yaml
evidence_policy:
  required_anchor_types:     # Anchor kinds (Standard 1.2.0 §6.5)
    - record                 # Data lineage
    - x-methodology          # A vendor kind: require methodology
  require_grounding: [measure, predict]
  minimum_confidence: 0.85  # Higher for regulated industry
```

## Integration Examples

### With Data Warehouses

```yaml
# Snowflake integration
search:
  query: ${template.queries}
  scope: snowflake://database/schema
  limit: 1000000
```

### With ML Platforms

```yaml
# MLflow integration
retrieve:
  target: mlflow://models/${model.id}/versions/latest
  format: model_metadata
```

### With Orchestrators

```yaml
# Airflow integration
receive:
  channel: airflow_events
  filter:
    dag_id: ${pipeline.dag_id}
    task_id: data_quality_check
```

## Statistical Rigor

### Confidence Requirements

All measurements must include uncertainty:

```yaml
measure:
  output:
    value: 0.85
    uncertainty:
      lower: 0.82
      upper: 0.88
    unit: accuracy
    confidence: 0.95
```

### Grounding Statistical Claims

```yaml
ground:
  claim: "Conversion rate increased 15%"
  sources:
    - query: "SELECT conversion_rate FROM metrics WHERE date BETWEEN ..."
    - sample_size: 50000
    - statistical_test: chi_squared
    - p_value: 0.001
  required_strength: strong
```

## Governance Considerations

1. **Always ground** metrics to source queries
2. **Include lineage** in all data transformations
3. **Version control** model artifacts
4. **Audit trail** for all report publications
5. **Drift detection** for all production models

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Data Analysis Workflows](../../../schemas/workflows/data_analysis_workflows.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
