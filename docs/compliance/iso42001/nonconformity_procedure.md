# Nonconformity and Corrective Action Procedure — ISO/IEC 42001 Clause 10 (Improvement)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Clause:** 10 — Improvement
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — Adapt severity classifications and timelines to organizational context

---

## 1. Purpose

This procedure defines how nonconformities in the AI Management System are identified, evaluated, corrected, and prevented from recurring. It fulfills ISO/IEC 42001 Clause 10.1 (Nonconformity and corrective action) and Clause 10.2 (Continual improvement).

## 2. Scope

This procedure applies to all nonconformities related to:

- AI system behavior that deviates from intended outcomes
- AIMS process failures (policy, risk treatment, monitoring, review)
- Capability execution failures (safety control bypass, evidence grounding failures)
- Domain profile misconfiguration or calibration errors
- Audit findings (internal or external)
- Stakeholder complaints related to AI system performance
- Regulatory non-compliance

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Nonconformity** | Non-fulfillment of a requirement (ISO 42001, AI policy, domain profile, or operational procedure) |
| **Correction** | Immediate action to eliminate a detected nonconformity |
| **Corrective action** | Action to eliminate the cause of a nonconformity and prevent recurrence |
| **Root cause** | Fundamental reason a nonconformity occurred |
| **Observation** | Situation that, if not addressed, could become a nonconformity |
| **NCR** | Nonconformity Report — documented record of a nonconformity |

## 4. Nonconformity Identification

### 4.1 Detection Sources

| Source | Detection Mechanism | Example |
|--------|-------------------|---------|
| **Structural enforcement** | PreToolUse hook blocks unauthorized mutations | Write/Edit without checkpoint marker |
| **Schema validation** | Output schema rejects outputs without evidence anchors | Missing `evidence_anchors` or `confidence` field |
| **Audit log analysis** | PostToolUse hook logging reveals anomalies | Unusual mutation frequency, bypassed approvals |
| **Internal audit** | Systematic assessment against ISO 42001 requirements | Finding during Clause 9.2 audit |
| **Management review** | Performance metric review reveals degradation | Declining confidence scores, increasing approval times |
| **Operator report** | Operator observes unexpected system behavior | Incorrect workflow output, failed rollback |
| **Stakeholder feedback** | External party reports issue | End user complaint, regulator inquiry |
| **Workflow validation** | Design-time type checker detects errors | Type mismatch in workflow step bindings |
| **Domain profile review** | Trust weight calibration review reveals drift | Trust weights no longer appropriate for data sources |

### 4.2 Severity Classification

| Severity | Definition | Response Timeline | Examples |
|----------|-----------|-------------------|---------|
| **Critical** | Safety control failure; potential for harm or data loss; structural enforcement bypassed | Immediate containment (< 1 hour); correction within 24 hours; corrective action within 7 days | Checkpoint enforcement failure; unauthorized mutation; evidence store data loss |
| **Major** | Significant deviation from requirements; systematic process failure; repeated minor nonconformity | Correction within 48 hours; corrective action within 30 days | Missing audit logs for extended period; domain profile misconfiguration affecting decisions; failed trust weight calibration |
| **Minor** | Isolated deviation; limited impact; does not affect safety controls | Correction within 7 days; corrective action within 60 days | Single missing evidence anchor; documentation gap; incomplete training record |
| **Observation** | Not yet a nonconformity; potential for becoming one if not addressed | Tracked for next review cycle | Approaching capacity limits in EvidenceStore; trust weights not reviewed in 90+ days |

## 5. Nonconformity Handling Procedure

### 5.1 Process Flow

```
┌─────────────┐
│ 1. IDENTIFY │  Detect nonconformity from any source (Section 4.1)
└──────┬──────┘
       ▼
┌─────────────┐
│ 2. CONTAIN  │  React: Stop the immediate impact
│             │  - Halt affected workflows
│             │  - Rollback to last checkpoint (if applicable)
│             │  - Isolate affected domain/capability
└──────┬──────┘
       ▼
┌──────────────┐
│ 3. EVALUATE  │  Classify severity (Section 4.2)
│              │  Record NCR (Section 5.2)
│              │  Assign owner
└──────┬───────┘
       ▼
┌─────────────┐
│ 4. CORRECT  │  Implement immediate correction
│             │  - Fix the immediate issue
│             │  - Restore compliant state
│             │  - Verify correction effective
└──────┬──────┘
       ▼
┌──────────────────┐
│ 5. ROOT CAUSE    │  Analyze why it happened (Section 5.3)
│    ANALYSIS      │  - Use appropriate technique (5 Whys, fishbone, etc.)
│                  │  - Identify systemic causes
│                  │  - Determine if similar NCRs can occur elsewhere
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 6. CORRECTIVE    │  Eliminate the cause (Section 5.4)
│    ACTION        │  - Define actions to prevent recurrence
│                  │  - Assign owner and timeline
│                  │  - Implement changes
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 7. VERIFY        │  Confirm effectiveness (Section 5.5)
│    EFFECTIVENESS │  - Verify corrective action implemented
│                  │  - Monitor for recurrence
│                  │  - Close NCR or escalate
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 8. RECORD &      │  Document everything (Section 5.6)
│    LEARN         │  - Update NCR with all details
│                  │  - Report to management review
│                  │  - Share lessons learned
└──────────────────┘
```

### 5.2 Nonconformity Report (NCR)

Each nonconformity shall be documented in an NCR containing:

| Field | Content |
|-------|---------|
| NCR ID | Unique identifier (e.g., NCR-2026-001) |
| Date Identified | Date the nonconformity was detected |
| Identified By | Person or system that detected it |
| Detection Source | Source from Section 4.1 (audit, hook, report, etc.) |
| Description | Clear description of what the nonconformity is |
| Requirement Reference | Which requirement was not fulfilled (ISO clause, policy, profile) |
| Severity | Critical / Major / Minor (per Section 4.2) |
| Affected Scope | Capabilities, workflows, domains, users affected |
| Evidence | Audit logs, screenshots, evidence store records |
| Containment Actions | Immediate actions taken to contain the issue |
| Correction | Actions taken to fix the immediate issue |
| Root Cause | Result of root cause analysis |
| Corrective Action | Actions to prevent recurrence |
| Owner | Person responsible for corrective action |
| Deadline | Target date for corrective action completion |
| Verification Method | How effectiveness will be verified |
| Verification Date | Date effectiveness was verified |
| Verified By | Person who verified effectiveness |
| Status | Open / Contained / Corrected / Closed / Escalated |

### 5.3 Root Cause Analysis

Root cause analysis shall be performed for all Major and Critical nonconformities. For Minor nonconformities, root cause analysis is recommended but may be simplified.

**Recommended Techniques:**

| Technique | When to Use | Output |
|-----------|------------|--------|
| **5 Whys** | Single-cause, straightforward issues | Linear cause chain |
| **Fishbone (Ishikawa)** | Multiple potential causes | Categorized cause diagram |
| **Fault Tree Analysis** | Complex, safety-critical issues | Boolean logic tree |
| **Timeline Analysis** | Sequence-dependent issues | Event timeline with cause identification |

**Framework-Specific Root Cause Categories:**

| Category | Description | Examples |
|----------|-------------|---------|
| **Structural** | Framework enforcement mechanism failure | Hook misconfiguration, schema validation gap |
| **Configuration** | Domain profile or ontology misconfiguration | Incorrect trust weights, wrong risk threshold |
| **Operational** | Operator error or process failure | Missed review, incorrect approval |
| **Design** | Workflow or capability design deficiency | Missing edge in ontology, insufficient evidence requirements |
| **External** | External system or data source issue | API failure, sensor malfunction, data quality |
| **Knowledge** | Competency gap or awareness failure | Operator unaware of procedure, insufficient training |

### 5.4 Corrective Action Planning

Corrective actions shall:

1. **Address the root cause** — not just the symptom
2. **Be proportionate** to the severity and risk of recurrence
3. **Have a defined owner** and deadline
4. **Be verifiable** — define what evidence demonstrates effectiveness
5. **Consider structural enforcement** — prefer structural controls (hooks, schema changes, ontology edges) over procedural controls (policies, training) where possible

**Corrective Action Hierarchy** (prefer higher tiers):

| Tier | Control Type | Effectiveness | Examples |
|------|-------------|---------------|---------|
| 1 | **Structural elimination** | Highest | Add ontology edge, modify schema, add hook |
| 2 | **Automated detection** | High | Add monitoring rule, enhance audit analysis |
| 3 | **Process change** | Medium | Update procedure, add review step |
| 4 | **Training/awareness** | Lower | Training module, awareness communication |
| 5 | **Documentation update** | Lowest | Update documentation, add warning |

### 5.5 Effectiveness Verification

| Verification Method | When to Use | Evidence |
|--------------------|------------|---------|
| **Structural test** | Corrective action is a structural control | Run validation tools; attempt to reproduce nonconformity (must fail) |
| **Audit log review** | Corrective action is operational | Review audit logs for period after implementation |
| **Re-audit** | Corrective action is process-related | Conduct focused audit of affected area |
| **Monitoring** | Corrective action needs time to evaluate | Monitor metrics for defined period (minimum 30 days) |
| **Simulation** | Safety-critical corrective action | Simulate the nonconformity scenario; verify detection/prevention |

### 5.6 Record Retention

| Record | Retention Period | Storage |
|--------|-----------------|---------|
| NCR (all fields) | 5 years from closure | Document management system |
| Root cause analysis | 5 years from NCR closure | Attached to NCR |
| Corrective action evidence | 5 years from verification | Attached to NCR |
| Audit evidence (logs, screenshots) | Per domain retention policy (e.g., healthcare: 7 years) | Archive storage |

## 6. Continual Improvement (Clause 10.2)

### 6.1 Improvement Sources

| Source | Mechanism | Frequency |
|--------|-----------|-----------|
| NCR trends | Analyze nonconformity patterns by category, severity, root cause | Quarterly |
| Management review outputs | Improvement actions from Clause 9.3 reviews | Per review cycle |
| Internal audit observations | Non-binding findings that suggest improvement | Per audit cycle |
| Technology advances | New framework capabilities, tool improvements | Ongoing |
| Stakeholder feedback | Suggestions and requests from interested parties | Ongoing |
| Industry best practices | Benchmarking against other AIMS implementations | Annual |

### 6.2 Improvement Tracking

All improvement actions shall be tracked with:

| Field | Content |
|-------|---------|
| Improvement ID | Unique identifier |
| Source | Where the improvement was identified |
| Description | What improvement is proposed |
| Expected Benefit | What outcome is expected |
| Priority | Based on risk reduction and resource requirements |
| Owner | Person responsible |
| Status | Proposed / Approved / In Progress / Completed / Deferred |
| Outcome | Actual results after implementation |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-NCR-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |

---

*This procedure fulfills ISO/IEC 42001:2023 Clause 10 requirements. It covers identification, evaluation, corrective action, and follow-up as required by acceptance criteria. Adapt severity timelines and retention periods to organizational context.*
