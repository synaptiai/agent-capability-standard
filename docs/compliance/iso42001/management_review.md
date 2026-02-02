# Management Review Process — ISO/IEC 42001 Clause 9 (Performance Evaluation)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Clause:** 9 — Performance Evaluation
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — Adapt review cadence and participants to organizational structure

---

## 1. Purpose

This document establishes the management review process for AI systems built on the Grounded Agency framework, fulfilling ISO/IEC 42001 Clause 9.3 requirements. It defines the cadence, inputs, outputs, and record-keeping for management reviews of AIMS performance.

## 2. Monitoring and Measurement (Clause 9.1)

### 2.1 Monitoring Framework

The organization shall monitor and measure AIMS effectiveness using data from the framework's built-in observability mechanisms:

| Monitoring Area | Data Source | Metric | Collection Method |
|----------------|------------|--------|-------------------|
| **Safety compliance** | `PreToolUse` hook logs | Checkpoint enforcement rate (target: 100%) | Automated — hook intercepts all Write/Edit calls |
| **Audit completeness** | `.claude/audit.log` | Skill invocation logging rate (target: 100%) | Automated — PostToolUse hook |
| **Evidence grounding** | EvidenceStore | Outputs with evidence anchors (target: 100%) | Schema validation results |
| **Confidence thresholds** | EvidenceStore | Decisions meeting minimum confidence (target: per domain) | EvidenceStore queries |
| **Human oversight** | Approval records | Mean time to approve high-risk actions | Approval timestamp analysis |
| **Risk treatment effectiveness** | Corrective action records | Nonconformities per period (target: decreasing trend) | Manual collection |
| **Trust model health** | Trust weight configuration | Trust weights reviewed and calibrated (target: per profile) | `trust_model_reviewed_at` field |

### 2.2 Internal Audit (Clause 9.2)

Internal audits shall be conducted per the internal audit checklist (see `internal_audit_checklist.md`).

| Audit Element | Requirement |
|--------------|-------------|
| **Frequency** | Minimum annually; more frequently for high-risk domains |
| **Scope** | All AIMS processes covering Clauses 4–10 |
| **Auditor qualification** | Competent and independent of the area being audited |
| **Audit criteria** | ISO 42001 requirements, AI policy, documented procedures |
| **Audit method** | Document review, interviews, observation, tool verification |
| **Reporting** | Findings classified as nonconformity (major/minor) or observation |
| **Follow-up** | Corrective actions tracked per Clause 10 procedure |

## 3. Management Review Process (Clause 9.3)

### 3.1 Review Cadence

| Review Type | Frequency | Duration | Participants |
|------------|-----------|----------|-------------|
| **Full management review** | Quarterly | 2–3 hours | Top management, AI System Owner, AI Safety Officer, Domain Experts |
| **Interim review** | Monthly | 1 hour | AI System Owner, AI Safety Officer |
| **Ad-hoc review** | As triggered | Variable | Relevant stakeholders per trigger |

**Review Triggers (Ad-hoc):**
- Significant security incident or nonconformity
- Regulatory change affecting AIMS scope
- Major system change (new domain profile, capability addition)
- External audit or certification event
- Stakeholder complaint related to AI system behavior

### 3.2 Review Inputs (Clause 9.3 a–f)

Each management review shall consider the following inputs:

| # | Input | Source | Prepared By |
|---|-------|--------|-------------|
| 1 | **Status of actions from previous reviews** | Previous review minutes | AI Safety Officer |
| 2 | **Changes in external/internal issues** | Stakeholder analysis updates, regulatory changes | AI System Owner |
| 3 | **AIMS performance information** including: | | |
| 3a | – Nonconformities and corrective actions | Corrective action register | AI Safety Officer |
| 3b | – Monitoring and measurement results | Monitoring dashboard (Section 2.1 metrics) | AI System Operator |
| 3c | – Audit results | Internal audit reports | Internal Auditor |
| 3d | – AI system performance metrics | EvidenceStore analytics, confidence distributions | AI System Operator |
| 4 | **Feedback from interested parties** | Stakeholder communication records | AI System Owner |
| 5 | **Results of risk assessment** | Risk treatment plan status, residual risk changes | AI Safety Officer |
| 6 | **Opportunities for improvement** | Audit observations, operator feedback, industry developments | All participants |
| 7 | **AI-specific considerations** including: | | |
| 7a | – Changes in AI technology landscape | Industry analysis | AI Safety Officer |
| 7b | – New capability additions or ontology changes | Ontology change log | AI Safety Officer |
| 7c | – Domain profile changes and calibration status | Profile version history, `trust_model_reviewed_at` dates | Domain Experts |
| 7d | – Evidence store health (capacity, retention, quality) | EvidenceStore monitoring | AI System Operator |

### 3.3 Review Agenda Template

```
MANAGEMENT REVIEW MEETING — [Date]

1. Opening and attendance                              [5 min]
2. Previous review actions — status update             [10 min]
3. Context changes (internal/external)                 [10 min]
4. AIMS performance dashboard                          [20 min]
   a. Safety metrics (checkpoint compliance, audit completeness)
   b. Quality metrics (evidence grounding, confidence thresholds)
   c. Operational metrics (approval times, throughput)
5. Nonconformity and corrective action summary         [15 min]
6. Internal audit findings                             [15 min]
7. Risk treatment plan review                          [15 min]
   a. Residual risk status
   b. New risks identified
   c. Control effectiveness
8. AI-specific topics                                  [15 min]
   a. Technology changes
   b. Capability ontology updates
   c. Domain profile calibration status
9. Stakeholder feedback                                [10 min]
10. Improvement opportunities                          [15 min]
11. Decisions and actions                              [10 min]
12. Close — next review date                           [5 min]
```

### 3.4 Review Outputs (Clause 9.3)

Each management review shall produce documented decisions and actions related to:

| # | Output Category | Examples |
|---|----------------|----------|
| 1 | **Improvement opportunities** | Enhance monitoring for specific capabilities; add new evidence types; improve operator training |
| 2 | **Need for changes to the AIMS** | Update AI policy; modify risk thresholds; add/remove capabilities from `block_autonomous` |
| 3 | **Resource needs** | Additional training; tooling investment; staffing for audit/compliance |
| 4 | **Risk treatment updates** | New treatments for identified risks; changes to existing controls; residual risk acceptance decisions |
| 5 | **AI-specific decisions** | Approve new domain profiles; authorize capability additions; approve trust weight changes |
| 6 | **Action items** | Each with: description, owner, deadline, expected evidence of completion |

## 4. Performance Reporting

### 4.1 AIMS Performance Dashboard

The following metrics shall be reported at each management review:

```
┌─────────────────────────────────────────────────────────────┐
│                    AIMS PERFORMANCE DASHBOARD                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SAFETY METRICS                    QUALITY METRICS          │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │ Checkpoint Rate   │              │ Evidence Coverage │    │
│  │ [____%]   ▼ 100% │              │ [____%]   ▼ 100% │    │
│  └──────────────────┘              └──────────────────┘    │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │ Audit Coverage    │              │ Confidence Met   │    │
│  │ [____%]   ▼ 100% │              │ [____%]   ▼ Per  │    │
│  └──────────────────┘              │           domain │    │
│                                    └──────────────────┘    │
│  OPERATIONAL METRICS               IMPROVEMENT METRICS     │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │ Approval Time     │              │ NCRs This Period │    │
│  │ [__ min]  ▼ <SLA │              │ [____]   ▼ Trend │    │
│  └──────────────────┘              └──────────────────┘    │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │ Rollbacks Used    │              │ NCR Resolution   │    │
│  │ [____]            │              │ [____%]   ▼ >95% │    │
│  └──────────────────┘              └──────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Trend Analysis

Performance data shall be tracked over time to identify trends:

| Metric | Trend Direction | Action |
|--------|----------------|--------|
| Checkpoint compliance declining | Investigate root cause; potential hook misconfiguration | Corrective action |
| Nonconformities increasing | Review risk treatment effectiveness | Risk reassessment |
| Approval times increasing | Review staffing and escalation procedures | Resource allocation |
| Confidence scores declining | Investigate data quality and trust model calibration | Domain expert review |
| New domains deploying | Verify profile configuration and operator competency | Audit new deployment |

## 5. Record-Keeping

### 5.1 Review Records

Each management review shall produce the following records:

| Record | Content | Retention Period | Storage |
|--------|---------|-----------------|---------|
| **Meeting minutes** | Attendance, agenda items discussed, decisions made | 5 years minimum | Document management system |
| **Action register** | All actions with owner, deadline, status | Active until all closed + 3 years | Document management system |
| **Performance report** | Dashboard metrics, trend analysis, narrative summary | 5 years minimum | Document management system |
| **Decision log** | All decisions with rationale and authority | 5 years minimum | Document management system |
| **Input evidence** | Source data for all review inputs | 3 years minimum | As per source system retention |

### 5.2 Action Tracking

| Action Field | Content |
|-------------|---------|
| Action ID | Unique identifier (e.g., MR-2026-Q1-001) |
| Description | Clear statement of required action |
| Owner | Named individual responsible |
| Deadline | Target completion date |
| Priority | Critical / High / Medium / Low |
| Status | Open / In Progress / Completed / Overdue |
| Evidence | Document or artifact demonstrating completion |
| Verified By | Person who verified action completion |
| Verification Date | Date of verification |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-MGR-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |

---

*This management review process fulfills ISO/IEC 42001:2023 Clause 9.3 requirements. The cadence (quarterly full review, monthly interim) is a recommendation — adapt to organizational size and risk exposure. All bracketed fields should be adapted to organizational context.*
