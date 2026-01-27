# Healthcare Domain

This document describes how to use the Grounded Agency framework for healthcare and clinical decision support environments.

## Overview

> **IMPORTANT:** This domain profile is designed for **Clinical Decision Support (CDS)** systems only. All clinical decisions must be made by licensed healthcare professionals. No autonomous clinical actions are permitted.

The healthcare domain profile is calibrated for environments where:
- **Patient safety is paramount** — Every recommendation must be grounded
- **Human oversight is mandatory** — All clinical actions require clinician decision
- **Regulatory compliance is required** — HIPAA, FDA, HL7 standards apply
- **Audit trails are critical** — 7-year retention for medical records

## Domain Profile

**Profile location:** `schemas/profiles/healthcare.yaml`

### Trust Weights

Healthcare trusts verified clinical systems and licensed professionals:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| ICD Codes | 0.98 | Standardized coding system |
| Physician Order | 0.96 | Licensed clinician decision |
| Drug Database | 0.95 | Verified interaction data |
| Laboratory System | 0.95 | Certified lab results |
| EHR System | 0.94 | Verified patient data |
| PACS/Imaging | 0.94 | Diagnostic imaging |
| Specialist Consult | 0.94 | Expert clinical opinion |
| Pharmacy System | 0.93 | Medication verification |
| Bedside Monitor | 0.92 | Real-time patient data |
| Clinical Guideline | 0.92 | Evidence-based standards |
| Pharmacist Review | 0.92 | Medication safety check |
| Nurse Assessment | 0.90 | Licensed clinical observation |
| Infusion Pump | 0.90 | Smart device data |
| Patient Reported | 0.75 | Patient self-report |
| Caregiver Input | 0.72 | Family/caregiver information |

### Risk Thresholds

```yaml
auto_approve: none      # NO autonomous clinical actions
require_review: low     # All actions require clinical review
require_human: low      # Almost everything needs human decision
block_autonomous:
  - mutate              # Never modify clinical records autonomously
  - send                # Never send clinical communications autonomously
  - execute             # Never execute clinical orders autonomously
  - delegate            # Never delegate clinical tasks autonomously
```

### Checkpoint Policy

Healthcare requires checkpoints before **every** recommendation:
- Before generating any clinical recommendation
- Before creating any clinical alert
- Before modifying any documentation
- Before suggesting any order
- Before any care handoff

## Available Workflows

### 1. Patient Monitoring

**Goal:** Monitor vital signs and generate clinician alerts.

**Capabilities used:**
- `receive` — Ingest vital signs from monitors
- `retrieve` — Get patient clinical context
- `transform` — Normalize to HL7 format
- `state` — Build physiological state
- `compare` — Compare to patient baseline
- `detect` — Identify clinical patterns
- `predict` — Forecast vital trajectory
- `classify` — Classify alert severity
- `ground` — Anchor to clinical evidence
- `generate` — Create clinician alert
- `checkpoint` — Checkpoint before delivery
- `audit` — Record with 7-year retention

**Trigger:** Continuous monitoring or threshold events

**Output:** Clinical alert for clinician review

### 2. Clinical Alert Triage

**Goal:** Triage incoming alerts and route to appropriate care team.

**Capabilities used:**
- `retrieve` — Get alert and patient context
- `search` — Find similar historical alerts
- `compare` — Compare to alert history
- `classify` — Classify acuity level
- `detect` — Identify alert fatigue risk
- `compare` — Rank potential responders
- `plan` — Recommend routing
- `generate` — Create routing recommendation
- `checkpoint` — Checkpoint decision
- `audit` — Record with full trail

**Trigger:** Incoming clinical alert

**Output:** Routing recommendation for clinical staff

### 3. Care Plan Review

**Goal:** Synthesize patient data and identify potential issues.

**Capabilities used:**
- `retrieve` — Get care plan, labs, medications
- `search` — Gather clinical notes
- `integrate` — Merge into unified view
- `detect` — Find drug interactions
- `compare` — Check lab trends vs targets
- `detect` — Identify care gaps
- `critique` — Assess plan for improvements
- `ground` — Anchor findings to evidence
- `explain` — Generate clinician summary
- `audit` — Record review

**Trigger:** Scheduled review or clinician request

**Output:** Care plan review summary for clinician

### 4. Handoff Preparation

**Goal:** Prepare comprehensive handoff documentation.

**Capabilities used:**
- `retrieve` — Get patient info, care plan, vitals
- `search` — Gather shift notes and events
- `integrate` — Merge for handoff
- `classify` — Classify patient acuity
- `detect` — Identify critical items
- `compare` — Prioritize pending tasks
- `generate` — Create SBAR handoff document
- `checkpoint` — Checkpoint preparation
- `audit` — Record handoff preparation

**Trigger:** Shift change

**Output:** Structured SBAR handoff document

## Customization Guide

### Adjusting for Specialty

Different specialties may have different priorities:

```yaml
# ICU setting - higher sensitivity
clinical_patterns:
  - mews_critical
  - sepsis_screen_aggressive
  - hemodynamic_instability
alert_threshold: 2  # Lower threshold, more sensitive
```

```yaml
# Outpatient setting - different patterns
clinical_patterns:
  - chronic_disease_decompensation
  - medication_adherence
  - preventive_care_gap
alert_threshold: 4  # Higher threshold, less noise
```

### Compliance Requirements

Adjust for your regulatory environment:

```yaml
compliance:
  hipaa: required
  fda_clinical_decision_support: advisory_only  # or device_regulated
  hl7_fhir: recommended
  audit_retention_days: 2555  # 7 years, adjust per jurisdiction
```

### Alert Fatigue Mitigation

Configure alert suppression:

```yaml
alert_policy:
  minimum_interval: 30m       # Don't re-alert within 30 minutes
  maximum_daily: 10           # Cap alerts per patient per day
  escalation_threshold: 3     # Escalate after 3 unacknowledged
  group_similar: true         # Bundle similar alerts
```

## Integration Examples

### With EHR Systems

```yaml
# Epic integration
retrieve:
  target: epic://patient/${patient.id}/encounter/current
  format: fhir_patient_summary
```

### With Laboratory Systems

```yaml
# HL7 lab results
receive:
  channel: hl7_v2
  filter:
    message_type: ORU^R01
    patient_id: ${patient.id}
```

### With Clinical Decision Support

```yaml
# CDS Hooks integration
invoke:
  workflow: cds_hooks_patient_view
  input:
    hook: patient-view
    context: ${patient_context}
```

## Safety Protocols

### Mandatory Requirements

1. **Always include disclaimers** in generated content:
   ```
   "For clinical decision support only. All decisions must be made by licensed clinicians."
   ```

2. **Never suppress critical alerts** regardless of fatigue settings

3. **Always ground** clinical recommendations to:
   - Patient-specific clinical data
   - Published clinical guidelines
   - Evidence-based medicine sources

4. **Maintain 7-year audit trails** for all clinical interactions

5. **Support clinician override** — never block a clinician's decision

### Prohibited Actions

The system **must never**:
- Autonomously modify patient records
- Send clinical communications without clinician approval
- Execute medication orders
- Make admission/discharge decisions
- Override clinician judgment
- Suppress critical safety alerts

## Regulatory Compliance

### HIPAA

- All patient data must be encrypted in transit and at rest
- Audit logs must track all PHI access
- Minimum necessary principle applies

### FDA Clinical Decision Support

This framework is designed for **Category 1 CDS** (advisory only):
- Information is presented to clinician for independent review
- Clinician can accept, modify, or reject recommendations
- No autonomous action capability

### HL7 FHIR

Recommended data formats:
- Patient: FHIR R4 Patient resource
- Observations: FHIR R4 Observation resource
- Alerts: FHIR R4 Communication resource

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Healthcare Workflows](../../../schemas/workflows/healthcare_workflows.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.json)
- [FDA Clinical Decision Support Guidance](https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software)
