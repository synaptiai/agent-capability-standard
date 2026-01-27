# Manufacturing Domain

This document describes how to use the Grounded Agency framework for manufacturing and industrial automation environments.

## Overview

The manufacturing domain profile is calibrated for environments where:
- **Safety is paramount** — Equipment can cause physical harm
- **Sensor data is primary** — PLC/SCADA systems provide authoritative signals
- **Regulations apply** — ISO, OSHA, FDA compliance may be required
- **Human oversight is mandatory** — All actuator commands need approval

## Domain Profile

**Profile location:** `schemas/profiles/manufacturing.yaml`

### Trust Weights

Manufacturing environments trust hardware and verified systems over human notes:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| PLC System | 0.95 | Direct machine control, high reliability |
| SCADA System | 0.93 | Supervisory data, validated |
| Hardware Sensor | 0.92 | Physical measurements, calibrated |
| MES API | 0.90 | Manufacturing execution, verified |
| Quality System | 0.88 | QMS data, audited |
| Operator Note | 0.75 | Human input, valuable but subjective |
| Supplier Data | 0.70 | External, requires verification |

### Risk Thresholds

```yaml
auto_approve: low       # Only low-risk actions auto-approved
require_review: medium  # Medium+ requires human review
require_human: high     # High-risk requires human execution
block_autonomous:
  - mutate              # Never autonomous state changes
  - send                # Never autonomous external communications
```

### Checkpoint Policy

Manufacturing requires checkpoints before any action that affects:
- Actuators and machine control
- Production process parameters
- Quality decisions (accept/reject)
- Maintenance actions

## Available Workflows

### 1. Production Line Monitoring

**Goal:** Continuously monitor production line health and detect anomalies.

**Capabilities used:**
- `receive` — Ingest sensor data from PLC/SCADA
- `transform` — Normalize to standard schema
- `state` — Build line state model
- `detect` — Identify anomalies
- `measure` — Quantify risk
- `predict` — Forecast progression
- `plan` — Generate intervention recommendations
- `generate` — Create alerts
- `audit` — Record monitoring cycle

**Trigger:** Continuous (polling) or event-driven

**Output:** Alert with severity, context, and recommendations

### 2. Quality Control Loop

**Goal:** Inspect products and recommend disposition (accept/reject/rework).

**Capabilities used:**
- `retrieve` — Get product specifications
- `observe` — Collect inspection measurements
- `measure` — Quantify quality attributes
- `compare` — Compare to specifications
- `classify` — Recommend disposition
- `ground` — Anchor to evidence
- `explain` — Generate quality report
- `checkpoint` — Checkpoint before decision
- `audit` — Record inspection

**Trigger:** Batch completion or sampling schedule

**Output:** Disposition recommendation with evidence

### 3. Predictive Maintenance

**Goal:** Predict equipment failures and recommend maintenance actions.

**Capabilities used:**
- `retrieve` — Get equipment history
- `receive` — Ingest sensor telemetry
- `detect` — Identify degradation patterns
- `attribute` — Find likely causes
- `predict` — Forecast failure probability
- `measure` — Quantify business impact
- `compare` — Evaluate maintenance strategies
- `plan` — Generate work order recommendation
- `generate` — Create work order draft
- `audit` — Record analysis

**Trigger:** Scheduled or threshold-based

**Output:** Work order draft with strategy recommendation

### 4. Supply Chain Sync

**Goal:** Monitor inventory and prepare replenishment recommendations.

**Capabilities used:**
- `search` — Query inventory levels
- `retrieve` — Get material parameters
- `integrate` — Merge from multiple sources
- `state` — Build inventory model
- `compare` — Check against reorder points
- `detect` — Identify reorder needs
- `predict` — Forecast demand
- `plan` — Calculate order quantities
- `generate` — Create PO drafts
- `checkpoint` — Checkpoint before supplier action
- `audit` — Record sync cycle

**Trigger:** Scheduled or inventory event

**Output:** Purchase order drafts for approval

## Customization Guide

### Adjusting Trust Weights

Your environment may have different trust levels. To customize:

1. Copy the profile:
   ```bash
   cp schemas/profiles/manufacturing.yaml schemas/profiles/my_plant.yaml
   ```

2. Adjust weights based on your data source reliability:
   ```yaml
   trust_weights:
     # Your plant may have older PLCs with lower reliability
     plc_system: 0.88
     # Your operators may have excellent training
     operator_note: 0.82
   ```

3. Reference your custom profile in workflow invocations.

### Adding Domain Sources

Add your specific data sources:

```yaml
domain_sources:
  - name: Legacy SCADA
    type: sensor
    default_trust: 0.85
  - name: Manual Data Entry
    type: human
    default_trust: 0.70
```

### Checkpoint Granularity

Adjust checkpoint frequency based on criticality:

```yaml
checkpoint_policy:
  # Pharmaceutical manufacturing: checkpoint everything
  before_any_change: always

  # High-volume discrete: checkpoint only high-risk
  before_actuator_command: high_risk
```

## Integration Examples

### With Existing MES

```yaml
# Input binding example
receive:
  channel: mes_event_stream
  filter:
    plant_id: ${config.plant_id}
    event_types: [production_count, quality_event, downtime]
```

### With Historian

```yaml
# Retrieve historical sensor data
retrieve:
  target: historian://tags/${equipment.id}/temperature
  format: time_series
  range: 7d
```

## Safety Considerations

1. **Never disable checkpoints** for actuator commands
2. **Always ground** predictions and detections to sensor evidence
3. **Maintain audit trails** for regulatory compliance
4. **Test workflows** in simulation before production deployment

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Manufacturing Workflows](../../../schemas/workflows/manufacturing_workflows.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
