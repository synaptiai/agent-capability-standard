# Post-Market Monitoring Plan — EU AI Act Article 61

**Regulation:** EU AI Act (Regulation 2024/1689)
**Article:** 61 — Post-Market Monitoring by Providers of High-Risk AI Systems
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Reference implementation — Defines monitoring plan leveraging existing framework telemetry

---

## 1. Purpose

This document establishes a post-market monitoring system for AI systems built on the Grounded Agency framework, as required by Art. 61 for high-risk AI systems. It defines how existing framework telemetry (audit logs, EvidenceStore, CheckpointTracker) is aggregated, analyzed, and reported to fulfill post-market monitoring obligations.

This plan is proportionate to the nature and risk class of the AI system (Art. 61(1)) and forms part of the quality management system described in EUAIA-QMS-001.

## 2. Scope

This monitoring plan applies to:
- AI systems classified as **high-risk** under EUAIA-CLS-001 (healthcare, manufacturing, and context-dependent profiles when deployed in Annex III areas)
- Limited-risk AI systems where the provider elects to implement monitoring (recommended for personal_assistant deployments)
- All capabilities in the ontology, with particular focus on high-risk (`mutate`, `send`) and medium-risk (`execute`, `rollback`, `delegate`, `synchronize`, `invoke`) capabilities

## 3. Data Collection Plan

### 3.1 Existing Telemetry Sources

The framework provides three built-in telemetry sources that form the foundation of post-market monitoring:

| Telemetry Source | Data Collected | Collection Method | Storage |
|-----------------|---------------|-------------------|---------|
| **Audit log** (`.claude/audit.log`) | All skill invocations with timestamps | PostToolUse hook (`posttooluse_log_tool.sh`) | Append-only log file |
| **EvidenceStore** (`grounded_agency/state/evidence_store.py`) | Evidence anchors, confidence scores, provenance records | Programmatic via SDK adapter | In-memory with persistence API |
| **CheckpointTracker** (`grounded_agency/state/checkpoint_tracker.py`) | Checkpoint creation, validation, expiry, rollback events | Programmatic via SDK adapter | Checkpoint metadata store |

### 3.2 Data Collection Requirements (Art. 61(2))

| Art. 61(2) Requirement | Framework Data Source | Collection Mechanism |
|-----------------------|----------------------|---------------------|
| (a) Data on performance throughout lifetime | EvidenceStore confidence trends, audit log frequency analysis | Automated aggregation from existing telemetry |
| (b) Feedback from users (deployers) | `inquire` capability invocations, escalation events | Extracted from audit log (inquire events) |
| (c) Other available information | Validator results, profile configuration changes | Validator outputs (`tools/validate_*.py`), git history on profile files |

### 3.3 Additional Data Points for Monitoring

Beyond existing telemetry, the following data points should be collected at the deployment level:

| Data Point | Description | Collection Frequency | Source |
|-----------|-------------|---------------------|--------|
| Capability invocation distribution | Count of each capability invoked per period | Continuous | Audit log aggregation |
| Confidence score distribution | Statistical summary (mean, P50, P95, min) per capability | Daily | EvidenceStore query |
| Checkpoint enforcement rate | % of mutations preceded by valid checkpoint | Continuous | CheckpointTracker validation log |
| Evidence coverage ratio | % of outputs with complete evidence anchors (vs. required anchor types) | Daily | EvidenceStore completeness check |
| Trust weight drift | Changes in effective trust weights over time | Weekly | Domain profile monitoring |
| Domain profile override frequency | Count of risk threshold overrides per period | Weekly | Audit log + profile config |
| Error and exception rate | Capability execution failures, timeout events | Continuous | SDK error handling |
| Human escalation rate | % of actions requiring human intervention vs. automated | Daily | Audit log (inquire events) |

## 4. Monitoring Cadence

### 4.1 Tiered Monitoring Schedule

| Cadence | Activities | Responsible Role | Output |
|---------|-----------|-----------------|--------|
| **Continuous** (real-time) | Checkpoint enforcement validation, audit log integrity, high-risk capability gating | Automated (hooks + SDK) | Real-time alerts on enforcement failures |
| **Daily** | Confidence score aggregation, evidence coverage check, error rate computation | AI System Operator | Daily monitoring dashboard |
| **Weekly** | Trend analysis (confidence drift, capability distribution shifts), trust weight drift review | AI System Operator | Weekly monitoring report |
| **Monthly** | KPI review against targets, domain profile calibration assessment, corrective action status | AI Safety Officer | Monthly performance report |
| **Quarterly** | Comprehensive performance review, risk model reassessment, regulatory compliance check | AI Safety Officer + AI System Owner | Quarterly review report (input to AIMS-MGR-001 management review) |
| **Annual** | Full system audit, risk classification review (EUAIA-CLS-001 reassessment), regulatory update incorporation | AI System Owner + external audit (if applicable) | Annual conformity assessment update |

### 4.2 Event-Triggered Monitoring

In addition to scheduled monitoring, the following events trigger immediate monitoring activities:

| Trigger Event | Response | Timeline |
|--------------|----------|----------|
| Checkpoint enforcement failure | Immediate investigation; system pause if repeated | Within 1 hour |
| Confidence score below domain minimum (e.g., < 0.90 for healthcare) | Capability output quarantined; human review required | Within 4 hours |
| Capability execution failure (high-risk capability) | Incident log entry; root cause analysis initiated | Within 4 hours |
| Domain profile modification | Validation pipeline run; impact assessment | Before deployment |
| Ontology or workflow catalog change | Full validator suite; regression testing | Before deployment |
| User/deployer complaint or feedback | Logged; triaged per severity (Section 6) | Within 24 hours |
| External vulnerability disclosure affecting framework | Security assessment; patch evaluation | Within 24 hours |

## 5. Key Performance Indicators (KPIs)

### 5.1 Safety KPIs

| KPI | Definition | Target | Measurement Source | Alert Threshold |
|-----|-----------|--------|-------------------|-----------------|
| **Checkpoint enforcement rate** | % of high-risk capability invocations preceded by valid checkpoint | 100% | CheckpointTracker + audit log cross-reference | < 100% (any failure is critical) |
| **Evidence coverage** | % of capability outputs with all required evidence anchor types present | ≥ 99% | EvidenceStore completeness validation | < 95% |
| **Confidence floor adherence** | % of outputs meeting domain minimum confidence threshold | ≥ 99.5% | EvidenceStore confidence analysis | < 98% |
| **Human oversight response time** | Mean time from escalation request (`inquire`) to human response | < SLA (domain-specific) | Audit log timestamp analysis | > 2x SLA |

### 5.2 Performance KPIs

| KPI | Definition | Target | Measurement Source | Alert Threshold |
|-----|-----------|--------|-------------------|-----------------|
| **Mutation frequency** | Count of `mutate`/`send` invocations per period | Stable trend (no unexplained increase) | Audit log aggregation | > 2σ from rolling mean |
| **Confidence drift** | Change in mean confidence per capability over 30-day window | < 5% drift | EvidenceStore trend analysis | > 10% drift |
| **Error rate** | Capability execution failure rate | < 1% | SDK error handling | > 5% |
| **Rollback frequency** | Count of `rollback` invocations per period | Decreasing trend | Audit log aggregation | Increasing over 3 consecutive periods |

### 5.3 Compliance KPIs

| KPI | Definition | Target | Measurement Source | Alert Threshold |
|-----|-----------|--------|-------------------|-----------------|
| **Validator pass rate** | % of validation runs passing all checks | 100% | `tools/validate_*.py` outputs | < 100% |
| **Profile configuration compliance** | % of deployed profiles matching approved configurations | 100% | Profile hash comparison | Any mismatch |
| **Audit log completeness** | % of skill invocations captured in audit log | 100% | Audit log count vs. SDK invocation count | < 100% |
| **Corrective action closure rate** | % of identified nonconformities resolved within SLA | ≥ 95% | AIMS-NCR-001 corrective action register | < 90% |

## 6. Escalation Levels

### 6.1 Four-Level Escalation Model

| Level | Name | Criteria | Response Time | Responsible | Actions |
|-------|------|----------|--------------|-------------|---------|
| **L1** | Info | Single KPI approaching alert threshold; isolated anomaly | Next business day | AI System Operator | Log observation; monitor trend; no immediate action required |
| **L2** | Warning | KPI breaches alert threshold; pattern of anomalies | Within 8 hours | AI System Operator + AI Safety Officer | Root cause investigation; corrective action per AIMS-NCR-001; deployer notification if affected |
| **L3** | Critical | Safety KPI failure (checkpoint, evidence coverage); multiple concurrent warnings | Within 2 hours | AI Safety Officer + AI System Owner | Affected capability suspended or restricted; immediate corrective action; deployer notification; preliminary incident assessment |
| **L4** | Incident | Serious incident per Art. 62 definition; system poses risk to health/safety/rights | Immediate | AI System Owner + Legal/Regulatory | System withdrawal or recall initiated; Art. 62 notification within 15 days; market surveillance authority engagement |

### 6.2 Escalation Matrix by Profile

| Profile | L1 → L2 Threshold | L2 → L3 Threshold | L3 → L4 Threshold |
|---------|-------------------|-------------------|-------------------|
| Healthcare | Any confidence < 0.90 | Checkpoint failure; missing clinician_verification | Patient safety risk; regulatory non-compliance |
| Manufacturing | Confidence drift > 5% | Actuator command without checkpoint | Equipment safety risk; process control failure |
| Vision/Audio/Multimodal | Confidence drift > 10% | Evidence anchor missing for classification output | Biometric misidentification; rights violation |
| Data Analysis | Error rate > 2% | Data lineage gap; unauthorized mutation | Decision impact on rights (credit, employment) |
| Personal Assistant | Error rate > 5% | Unauthorized send attempt | Privacy breach; communication sent without consent |

## 7. Serious Incident Reporting (Art. 62)

### 7.1 Definition of Serious Incident

Per Art. 3(49), a serious incident is an incident or malfunctioning that directly or indirectly leads to:
- Death or serious damage to health
- Serious and irreversible disruption of critical infrastructure management
- Breach of obligations under Union law intended to protect fundamental rights
- Serious damage to property or the environment

### 7.2 Reporting Procedure

| Step | Action | Timeline | Responsible | Evidence Required |
|------|--------|----------|-------------|-------------------|
| 1 | Incident detection and initial assessment | Immediate | AI System Operator | Audit log snapshot, EvidenceStore state, checkpoint status |
| 2 | Escalation to L4 and system containment | Within 1 hour | AI Safety Officer | Containment actions documented |
| 3 | Preliminary incident report preparation | Within 24 hours | AI System Owner | Incident description, affected users, initial root cause |
| 4 | Notification to market surveillance authority | Within 15 days of awareness | AI System Owner + Legal | Art. 62(1) notification via EU database (Art. 71) |
| 5 | Detailed investigation report | Within 30 days | AI Safety Officer | Full root cause analysis, corrective actions, preventive measures |
| 6 | Follow-up notifications (if causal link unclear) | As determined | AI System Owner | Updated findings, revised timeline |

### 7.3 Notification Content (Art. 62(1))

The notification to the market surveillance authority shall include:

| Element | Source |
|---------|--------|
| Identification of the AI system | System registry entry, EUAIA-TEC-001 reference |
| Description of the serious incident | L4 escalation report |
| Corrective actions taken or envisaged | AIMS-NCR-001 corrective action record |
| Causal link assessment (AI system → incident) | Root cause analysis from investigation report |
| Known or estimated number of affected persons | Deployment telemetry, deployer reports |
| Date and location of the serious incident | Audit log timestamps, deployment records |

### 7.4 Market Surveillance Authority Interaction

| Situation | Action | Reference |
|-----------|--------|-----------|
| Authority requests additional information | Provide within timeline specified by authority | Art. 62(3) |
| Authority determines additional testing needed | Cooperate and provide technical documentation | Art. 62, EUAIA-TEC-001 |
| Similar incidents reported by deployers | Aggregate analysis; update monitoring thresholds | Art. 26 (deployer obligations) |
| Authority mandates corrective measures | Implement within specified timeline; report completion | Art. 16(1) |

## 8. Integration with AIMS Processes

### 8.1 Cross-References

| AIMS Process | Document | Integration Point |
|-------------|----------|-------------------|
| Corrective Action | AIMS-NCR-001 (nonconformity procedure) | L2+ escalations trigger corrective action per Section 4 of nonconformity procedure |
| Management Review | AIMS-MGR-001 (management review) | Quarterly monitoring reports are standing agenda items |
| Internal Audit | AIMS-AUD-001 (internal audit checklist) | Monitoring plan effectiveness is an audit objective |
| Risk Treatment | AIMS-RSK-001 (risk treatment plan) | KPI trends inform risk reassessment; residual risk acceptance review |

### 8.2 Continuous Improvement Cycle

```
Monitoring Data → KPI Analysis → Threshold Check
                                      │
                    ┌─────────────────┴──────────────────┐
                    │                                     │
              Within threshold                    Threshold breached
                    │                                     │
              Continue monitoring              Escalation (L1→L4)
                                                         │
                                              Corrective Action
                                              (AIMS-NCR-001)
                                                         │
                                              Root Cause Analysis
                                                         │
                                              Preventive Measures
                                                         │
                                              Update Monitoring
                                              (thresholds, KPIs)
                                                         │
                                              Management Review
                                              (AIMS-MGR-001)
```

## 9. Data Retention

| Data Type | Retention Period | Basis | Storage |
|-----------|-----------------|-------|---------|
| Audit logs | Minimum 10 years (or longer per domain) | Art. 12(3) — logging for high-risk systems | Append-only log with integrity verification |
| Evidence records | Minimum 10 years | Art. 11 — technical documentation retention | EvidenceStore with backup |
| Checkpoint metadata | Minimum 10 years | Art. 12(3) | CheckpointTracker with backup |
| Monitoring reports (daily/weekly) | 3 years | Operational retention | Monitoring dashboard archive |
| Monitoring reports (monthly/quarterly) | 10 years | Management review records | Document management system |
| Incident reports | 10 years (or longer per regulatory requirement) | Art. 62 records | Incident management system |
| KPI trend data | 10 years | Performance baseline for drift detection | Time-series database |

**Healthcare domain override:** `compliance.audit_retention_days: 2555` (7 years) is the minimum per healthcare profile; the 10-year EU AI Act requirement supersedes this where applicable.

## 10. Plan Review and Update

This post-market monitoring plan shall be reviewed and updated:

| Trigger | Action |
|---------|--------|
| At each quarterly management review | Assess plan effectiveness based on KPI trends |
| Upon any L3 or L4 escalation | Review and update affected monitoring thresholds |
| Upon ontology or profile changes | Reassess data collection plan and KPI coverage |
| Upon regulatory guidance updates | Incorporate new requirements from implementing acts or standards |
| Annually | Full plan review as part of annual conformity reassessment |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | EUAIA-PMM-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |
| Monitoring Owner | [Name, Title] |

---

*This post-market monitoring plan leverages the Grounded Agency framework's existing telemetry infrastructure (audit logs, EvidenceStore, CheckpointTracker) to fulfill EU AI Act Art. 61 requirements. No new collection infrastructure is required — the plan defines aggregation, analysis, and reporting over existing data sources. All bracketed fields should be adapted to organizational context. For risk classification basis, see EUAIA-CLS-001. For quality management system integration, see EUAIA-QMS-001. For serious incident response procedures, cross-reference AIMS-NCR-001 (corrective actions) and AIMS-MGR-001 (management review).*
