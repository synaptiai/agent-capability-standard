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

The framework provides five built-in telemetry sources that form the foundation of post-market monitoring:

| Telemetry Source | Data Collected | Collection Method | Storage |
|-----------------|---------------|-------------------|---------|
| **Audit log** (`.claude/audit.log`) | Every tool call that runs: timestamp, tool name, call id, status (`executed` or `failed`), skill name on a `Skill` call, digest of the tool input, and `recorded_by` (plugin version, digest of the hook configuration, the approval setting and the checkpoint maximum age). It names the tool, not the capability, and has no line for a call the hooks refused | PostToolUse and PostToolUseFailure hook (`posttooluse_log_tool.sh`) | Append-only log file, HMAC-chained, checked by `tools/verify_audit_log.py` |
| **Used checkpoint markers** (`.claude/checkpoints/used/`) | One file per gated call that used a checkpoint, named by the checkpoint id and the call id, holding the checkpoint's commit | PreToolUse hook (`pretooluse_require_checkpoint.sh`) | Files in the project |
| **SDK adapter's action records** (`GroundedAgentAdapter.export_action_records`) | Every call the adapter decided: tool, capability, call id, status (a refusal carries a `code`: `rejected` for a call refused before it ran, `failed` for one whose result was refused), checkpoint id, approval | Programmatic via SDK adapter | In memory, up to `call_record_limit`; the host exports them |
| **EvidenceStore** (`grounded_agency/state/evidence_store.py`) | Evidence anchors with their kind, reference, capability and call id, and the store's capture failures; it holds no confidence value | Programmatic via SDK adapter | In memory; `JsonlEvidenceStore` keeps a file |
| **CheckpointTracker** (`grounded_agency/state/checkpoint_tracker.py`) | Checkpoints taken, used, expired and pruned | Programmatic via SDK adapter | `tracker_state.json` and `pruned_checkpoints.jsonl` in its `checkpoint_dir` |

### 3.2 Data Collection Requirements (Art. 61(2))

| Art. 61(2) Requirement | Framework Data Source | Collection Mechanism |
|-----------------------|----------------------|---------------------|
| (a) Data on performance throughout lifetime | Audit log and adapter record frequency analysis; evidence anchor counts per capability from the EvidenceStore's `records()` | Automated aggregation from existing telemetry |
| (b) Feedback from users (deployers) | `inquire` capability invocations, escalation events | The adapter's action records (`capability` `inquire`); executor runs that end `escalated` |
| (c) Other available information | Validator results, profile configuration changes | Validator outputs (`tools/validate_*.py`), git history on profile files |

### 3.3 Additional Data Points for Monitoring

Beyond existing telemetry, the following data points should be collected at the deployment level:

| Data Point | Description | Collection Frequency | Source |
|-----------|-------------|---------------------|--------|
| Capability invocation distribution | Count of each capability invoked per period | Continuous | The adapter's action records (`capability`); the plugin's audit log counts tools, not capabilities |
| Confidence score distribution | Statistical summary (mean, P50, P95, min) per capability | Daily | None: no shipped component keeps the confidence values; capability outputs carry them, so a host that keeps the outputs computes this |
| Checkpoint enforcement rate | % of mutations preceded by valid checkpoint | Continuous | Plugin: audit log lines of gated calls joined by call id with the used checkpoint markers; SDK: the adapter's action records (`checkpoint_id` on each executed `mutate` or `send`) |
| Evidence coverage ratio | % of outputs with complete evidence anchors (vs. required anchor types) | Daily | Computed by the operator from the EvidenceStore's `records()` or `export()` against the anchor types the profile requires; there is no built-in check |
| Trust weight drift | Changes in effective trust weights over time | Weekly | Domain profile monitoring |
| Domain profile override frequency | Count of risk threshold overrides per period | Weekly | None: no shipped component records an override |
| Error and exception rate | Capability execution failures, timeout events | Continuous | `failed` lines of the audit log; `failed` and `rejected` records of the adapter |
| Human escalation rate | % of actions requiring human intervention vs. automated | Daily | The adapter's action records (`inquire` calls, and calls with an `approval`) |

The trust weight drift and profile override rows presuppose a host that applies a domain profile (Standard 1.2.0 §5.21): the reference executor, the validator, the Python adapter and the Standard Agents binding apply a profile they are given, and `grounded_agency/trust.py` applies its `trust_weights` (`merge_trust_weights`, `resolve`) when the host passes them. No shipped component records a profile override ([Status of Domain Profiles](../../domains/README.md#status-of-domain-profiles)).

## 4. Monitoring Cadence

### 4.1 Tiered Monitoring Schedule

| Cadence | Activities | Responsible Role | Output |
|---------|-----------|-----------------|--------|
| **Continuous** (real-time) | Checkpoint enforcement, high-risk capability gating; audit log integrity at each session's end | Automated (hooks + SDK) for enforcement; the AI System Operator runs the audit log check ([SECURITY.md §6.4](../../../spec/SECURITY.md#64-audit-review)) | Refusals shown in the session; the log hook's warnings |
| **Daily** | Evidence coverage check (computed from the EvidenceStore's records), error rate computation | AI System Operator | Daily monitoring dashboard |
| **Weekly** | Trend analysis (capability distribution shifts), trust weight drift review | AI System Operator | Weekly monitoring report |
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
| **Checkpoint enforcement rate** | % of high-risk capability invocations preceded by valid checkpoint | 100% | Plugin: gated calls in the audit log joined by call id with the used checkpoint markers (Bash calls are gated by their command, which the log does not hold, so they are not counted); SDK: executed `mutate` and `send` records of the adapter that carry a `checkpoint_id` | < 100% (any failure is critical) |
| **Evidence coverage** | % of capability outputs with all required evidence anchor types present | ≥ 99% | Computed by the operator from the EvidenceStore's `records()` or `export()`; there is no built-in check | < 95% |
| **Confidence floor adherence** | % of outputs meeting domain minimum confidence threshold | ≥ 99.5% | SDK: the adapter's F504 refusals with reason `below_minimum_confidence` (outputs below the applied profiles' minimum confidence), over its executed calls whose result carries a capability output | < 98% |
| **Human oversight response time** | Mean time from escalation request (`inquire`) to human response | < SLA (domain-specific) | Timestamps of the adapter's records of `inquire` calls; the plugin's log writes one line per call, after it ran, so it holds no start time | > 2x SLA |

### 5.2 Performance KPIs

| KPI | Definition | Target | Measurement Source | Alert Threshold |
|-----|-----------|--------|-------------------|-----------------|
| **Mutation frequency** | Count of `mutate`/`send` invocations per period | Stable trend (no unexplained increase) | The adapter's action records (`capability`); the plugin's log: lines of `Write`, `Edit` and the other tools it gates | > 2σ from rolling mean |
| **Confidence drift** | Change in mean confidence per capability over 30-day window | < 5% drift | None: no shipped component keeps the confidence values; a host that keeps the capability outputs computes this | > 10% drift |
| **Error rate** | Capability execution failure rate | < 1% | `failed` lines of the audit log; `failed` records of the adapter | > 5% |
| **Rollback frequency** | Count of `rollback` invocations per period | Decreasing trend | The adapter's action records (`capability` `rollback`); the plugin's log: `Skill` lines with `skill` `rollback` (a restore run through Bash is not identifiable there: the log holds no command) | Increasing over 3 consecutive periods |

### 5.3 Compliance KPIs

| KPI | Definition | Target | Measurement Source | Alert Threshold |
|-----|-----------|--------|-------------------|-----------------|
| **Validator pass rate** | % of validation runs passing all checks | 100% | `tools/validate_*.py` outputs | < 100% |
| **Profile configuration compliance** | % of deployed profiles matching approved configurations | 100% | Profile hash comparison | Any mismatch |
| **Audit log completeness** | % of tool calls that ran captured in audit log | 100% | Plugin: `tools/verify_audit_log.py` passes and the log hook reported no call it could not log or sign; SDK: the adapter's records exported before `call_record_limit` evicts any | < 100% |
| **Corrective action closure rate** | % of identified nonconformities resolved within SLA | ≥ 95% | AIMS-NCR-001 corrective action register | < 90% |

## 6. Escalation Levels

### 6.1 Four-Level Escalation Model

[SECURITY.md §6](../../../spec/SECURITY.md#6-incident-response) assigns each of the safety layer's alerts and audit review findings one of these levels.

| Level | Name | Criteria | Response Time | Responsible | Actions |
|-------|------|----------|--------------|-------------|---------|
| **L1** | Info | Single KPI approaching alert threshold; isolated anomaly | Next business day | AI System Operator | Log observation; monitor trend; no immediate action required |
| **L2** | Warning | KPI breaches alert threshold; pattern of anomalies | Within 8 hours | AI System Operator + AI Safety Officer | Root cause investigation; corrective action per AIMS-NCR-001; deployer notification if affected |
| **L3** | Critical | Safety KPI failure (checkpoint, evidence coverage); multiple concurrent warnings | Within 2 hours | AI Safety Officer + AI System Owner | Affected capability suspended or restricted; immediate corrective action; deployer notification; preliminary incident assessment |
| **L4** | Incident | Serious incident per Art. 62 definition; system poses risk to health/safety/rights | Immediate | AI System Owner + Legal/Regulatory | System withdrawal or recall initiated; Art. 62 notification within 15 days; market surveillance authority engagement |

### 6.2 Escalation Matrix by Profile

| Profile | L1 → L2 Threshold | L2 → L3 Threshold | L3 → L4 Threshold |
|---------|-------------------|-------------------|-------------------|
| Healthcare | Any confidence < 0.90 | Checkpoint failure; a clinical output with no `human_note` anchor (a clinician's verification) | Patient safety risk; regulatory non-compliance |
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

**Healthcare domain override:** `compliance.audit_retention_days: 2555` (7 years) is the minimum per healthcare profile; the 10-year EU AI Act requirement supersedes this where applicable. **Action required:** Deployers in high-risk contexts should override `audit_retention_days` to at least 3650 (10 years) in their deployed profile configuration to meet Art. 12(3) requirements. The value is a declaration: no shipped component reads `audit_retention_days` or keeps or deletes logs by it, so the deployer's log storage has to apply the period.

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
