# Competency Framework — ISO/IEC 42001 Clause 7 (Support)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Clause:** 7 — Support
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — Adapt competency requirements to organizational roles

---

## 1. Purpose

This document fulfills ISO/IEC 42001 Clause 7.2 (Competence) and Clause 7.3 (Awareness) by defining the competency requirements for personnel operating AI systems built on the Grounded Agency framework. It specifies what people need to know, how to assess competence, and how to address gaps.

## 2. Competence Requirements (Clause 7.2)

### 2.1 Role-Based Competency Matrix

#### AI System Owner

| Competency Area | Required Knowledge | Proficiency Level | Assessment Method |
|----------------|-------------------|-------------------|-------------------|
| AI governance | ISO 42001 structure, AI policy, risk management | Expert | Interview + certification |
| Risk assessment | Three-tier risk model, domain risk profiles | Advanced | Scenario-based assessment |
| Regulatory landscape | EU AI Act, NIST AI RMF, domain regulations | Advanced | Knowledge assessment |
| Stakeholder management | Stakeholder analysis, communication planning | Advanced | Portfolio review |
| Incident management | Nonconformity procedure, corrective actions | Intermediate | Tabletop exercise |

#### AI System Operator

| Competency Area | Required Knowledge | Proficiency Level | Assessment Method |
|----------------|-------------------|-------------------|-------------------|
| Domain profile configuration | YAML syntax, profile schema fields, trust weights | Expert | Hands-on practical exam |
| Capability ontology | 9 layers, 36 capabilities, risk classifications | Advanced | Written assessment |
| Checkpoint management | CheckpointTracker, checkpoint lifecycle, rollback procedures | Expert | Hands-on practical exam |
| Audit log monitoring | Audit hook output, EvidenceStore queries, provenance records | Advanced | Log analysis exercise |
| Workflow management | Workflow catalog, step bindings, recovery loops | Advanced | Workflow configuration exercise |
| Incident response | Escalation paths, rollback execution, evidence preservation | Intermediate | Tabletop exercise |

#### AI Safety Officer

| Competency Area | Required Knowledge | Proficiency Level | Assessment Method |
|----------------|-------------------|-------------------|-------------------|
| Capability ontology maintenance | Full ontology structure, edge types, I/O schemas | Expert | Ontology modification exercise |
| Risk treatment | Risk treatment plan, control effectiveness assessment | Expert | Scenario-based assessment |
| Internal audit | Audit planning, execution, reporting, follow-up | Expert | Audit exercise or certification |
| ISO 42001 requirements | All clauses, Annex A controls, certification process | Expert | Certification (Lead Auditor) |
| Safety enforcement | Hooks, structural controls, conflict edges | Expert | Configuration verification exercise |
| Corrective action management | Root cause analysis, corrective action, effectiveness verification | Advanced | Case study analysis |

#### Domain Expert

| Competency Area | Required Knowledge | Proficiency Level | Assessment Method |
|----------------|-------------------|-------------------|-------------------|
| Domain-specific regulations | Industry regulations (HIPAA, ISO 9001, GDPR, etc.) | Expert | Certification or assessment |
| Trust weight calibration | Source authority weights, temporal decay, conflict resolution | Advanced | Calibration exercise |
| Evidence policy design | Required anchor types, confidence thresholds, grounding requirements | Advanced | Policy design exercise |
| Domain risk assessment | Domain-specific risk scenarios, mitigation strategies | Expert | Scenario-based assessment |

#### Software Engineer

| Competency Area | Required Knowledge | Proficiency Level | Assessment Method |
|----------------|-------------------|-------------------|-------------------|
| SDK integration | `GroundedAgentAdapter`, `CapabilityRegistry`, `ToolCapabilityMapper` | Expert | Code review + integration exercise |
| Capability I/O schemas | Input/output schema structure, type validation | Advanced | Schema design exercise |
| Workflow DSL | Step definitions, bindings, gates, parallel groups, recovery loops | Advanced | Workflow authoring exercise |
| Hook development | PreToolUse/PostToolUse hooks, shell script integration | Intermediate | Hook implementation exercise |
| Skill development | SKILL.md template, frontmatter, procedure steps | Intermediate | Skill authoring exercise |

#### Internal Auditor

| Competency Area | Required Knowledge | Proficiency Level | Assessment Method |
|----------------|-------------------|-------------------|-------------------|
| ISO 42001 requirements | All clauses, Annex A controls, audit criteria | Advanced | Certification or knowledge assessment |
| Audit methodology | Planning, execution, evidence collection, reporting | Expert | Lead Auditor certification or equivalent |
| Framework structure | Capability ontology, domain profiles, hooks, evidence stores | Advanced | Hands-on assessment |
| Risk assessment | Three-tier model, domain risk profiles, treatment plans | Advanced | Scenario-based assessment |
| Independence and objectivity | Audit ethics, conflict of interest avoidance | Expert | Certification or formal training |
| Reporting and follow-up | Finding classification, NCR drafting, corrective action tracking | Advanced | Audit report review |

### 2.2 Proficiency Levels

| Level | Definition | Evidence Required |
|-------|-----------|------------------|
| **Awareness** | Understands the concept and its importance | Completed awareness training |
| **Intermediate** | Can apply knowledge with guidance | Completed training + supervised practice |
| **Advanced** | Can apply knowledge independently in standard situations | Demonstrated competence in assessments + independent practice |
| **Expert** | Can apply knowledge in complex/novel situations and train others | Assessment + independent practice + mentoring record |

## 3. Awareness Requirements (Clause 7.3)

All persons working under the organization's control shall be aware of:

| Awareness Topic | Content | Delivery Method | Frequency |
|----------------|---------|-----------------|-----------|
| AI policy | Organization's AI principles, objectives, commitments | Onboarding + annual refresher | Annual |
| AIMS relevance | How their work contributes to the AIMS and its objectives | Role-specific briefing | Annual |
| Grounded Agency principles | Evidence grounding, safety-by-construction, reversibility | Training module | At onboarding |
| Risk classification | Three-tier model, what makes capabilities high/medium/low risk | Training module | At onboarding + on change |
| Nonconformity reporting | How to identify and report nonconformities | Training module | Annual |
| Their contribution | How their role's actions affect AIMS effectiveness | Performance review | Semi-annual |
| Consequences of non-conformance | Impact of not following AIMS procedures | Policy acknowledgment | Annual |

## 4. Competence Gap Management

### 4.1 Assessment Process

```
 ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
 │ 1. Identify  │───▶│ 2. Assess    │───▶│ 3. Plan      │───▶│ 4. Deliver   │
 │ Required     │    │ Current      │    │ Gap          │    │ Training     │
 │ Competencies │    │ Competencies │    │ Closure      │    │              │
 └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                     │
                                                                     ▼
                                              ┌──────────────┐    ┌──────────────┐
                                              │ 6. Record    │◀───│ 5. Evaluate  │
                                              │ Evidence     │    │ Effectiveness│
                                              └──────────────┘    └──────────────┘
```

### 4.2 Gap Closure Actions

| Action | Applicability | Evidence of Completion |
|--------|--------------|----------------------|
| Formal training course | New competency area | Certificate of completion |
| On-the-job training | Existing competency, new role | Supervisor sign-off + demonstration |
| Mentoring | Advancing proficiency level | Mentor log + assessment |
| Self-study | Supplementary knowledge | Assessment score |
| External certification | Regulatory or standards knowledge | Certification credential |
| Hands-on exercise | Technical skills | Exercise completion + review |
| Tabletop exercise | Incident response | Exercise participation record |

### 4.3 Competency Records

For each person, maintain:

| Record Element | Content | Retention |
|---------------|---------|-----------|
| Role assignment | Current role and responsibilities | Duration of assignment |
| Competency assessment | Assessment results per competency area | 3 years minimum |
| Training record | Courses completed, dates, providers | 5 years minimum |
| Certification status | Active certifications, expiry dates | Duration of certification + 1 year |
| Gap closure plan | Identified gaps and planned actions | Until gap closed + 1 year |
| Effectiveness evaluation | Post-training assessment results | 3 years minimum |

## 5. Communication (Clause 7.4)

| Communication | Audience | Method | Frequency | Responsible |
|--------------|----------|--------|-----------|-------------|
| AI policy updates | All staff | Email + intranet | On change | AI System Owner |
| AIMS performance | Top management | Management review report | Per review cycle | AI Safety Officer |
| Training schedule | Relevant staff | Calendar + notification | Quarterly | Training coordinator |
| Nonconformity alerts | AIMS stakeholders | Notification system | On occurrence | AI Safety Officer |
| Competency assessment results | Individual + manager | Confidential report | Post-assessment | Assessor |

## 6. Documented Information (Clause 7.5)

### 6.1 Required Documentation

| Document | Purpose | Location | Review Cycle |
|----------|---------|----------|-------------|
| AI policy | Clause 5 compliance | `docs/compliance/iso42001/ai_policy_template.md` | Annual |
| Stakeholder analysis | Clause 4 compliance | `docs/compliance/iso42001/stakeholder_analysis.md` | Annual |
| Risk treatment plan | Clause 6 compliance | `docs/compliance/iso42001/risk_treatment_plan.md` | Annual |
| This competency framework | Clause 7 compliance | `docs/compliance/iso42001/competency_framework.md` | Annual |
| Management review process | Clause 9 compliance | `docs/compliance/iso42001/management_review.md` | Annual |
| Nonconformity procedure | Clause 10 compliance | `docs/compliance/iso42001/nonconformity_procedure.md` | Annual |
| Internal audit checklist | Audit support | `docs/compliance/iso42001/internal_audit_checklist.md` | Per audit cycle |
| Capability ontology | Technical reference | `schemas/capability_ontology.yaml` | Per release |
| Domain profiles | Operational configuration | `schemas/profiles/*.yaml` | Per deployment |

### 6.2 Document Control

All AIMS documentation shall be:
- Identified (document ID, version, date)
- Reviewed and approved before use
- Available to relevant persons when needed
- Protected from unintended modification (version control via Git)
- Subject to change control (pull request review process)

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-CMP-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |

---

*This competency framework fulfills ISO/IEC 42001:2023 Clause 7 requirements. Role definitions and proficiency requirements should be adapted to organizational structure and operational needs.*
