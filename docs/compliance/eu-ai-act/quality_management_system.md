# Quality Management System — EU AI Act Article 17

**Regulation:** EU AI Act (Regulation 2024/1689)
**Article:** 17 — Quality Management System
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Reference implementation — Maps Art. 17 requirements to framework controls and ISO 42001 AIMS documents

---

## 1. Purpose

This document demonstrates how the Grounded Agency framework satisfies the quality management system (QMS) requirements of EU AI Act Art. 17 for providers of high-risk AI systems. It maps each of the 11 Art. 17 requirements to framework implementations, evidence artifacts, and cross-references to the ISO 42001 AIMS document suite.

The QMS described here is proportionate to the size of the provider's organisation and designed to ensure compliance with Art. 8-15 in a systematic manner (Art. 17(1)).

## 2. Scope

This QMS applies to:
- All high-risk AI systems built on the Grounded Agency framework (per EUAIA-CLS-001)
- The full AI lifecycle: design, development, testing, deployment, post-market monitoring
- All 36 capabilities in the ontology, all 7 domain profiles, and all 12 workflow patterns

## 3. Art. 17 Compliance Matrix

### 3.1 Requirement (a) — Strategy for Regulatory Compliance

**Art. 17(1)(a):** "a strategy for regulatory compliance, including compliance with conformity assessment procedures and procedures for the management of modifications to the high-risk AI system"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Regulatory compliance strategy | Risk classification per EU AI Act risk taxonomy; conformity assessment routing | EUAIA-CLS-001 (risk classification), EUAIA-NTB-001 (assessment route) |
| Conformity assessment procedure | Internal control (Annex VI) or notified body (Annex VII) per profile | EUAIA-NTB-001 Section 3 (decision tree) |
| Management of modifications | CLAUDE.md capability creation checklist; extension governance process | `CLAUDE.md` Section "Creating New Capabilities", `docs/methodology/EXTENSION_GOVERNANCE.md` |
| Version control | Semantic versioning in ontology meta; git-based change tracking | `schemas/capability_ontology.yaml` — `meta.version` |

**ISO 42001 Cross-Reference:** Clause 6.1 (Actions to address risks), Clause 8.4 (AI system impact assessment)

### 3.2 Requirement (b) — Design and Development Control

**Art. 17(1)(b):** "techniques, procedures and systematic actions to be used for the design, design control and design verification of the high-risk AI system"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Design technique | First-principles derivation of 36 capabilities from cognitive architectures | `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md` |
| Design control | Typed I/O contracts (input_schema, output_schema) for every capability | `schemas/capability_ontology.yaml` — node schemas |
| Design verification | 6 validators checking structural integrity, references, schema consistency | `tools/validate_ontology.py`, `tools/validate_workflows.py`, `tools/validate_profiles.py`, `tools/validate_skill_refs.py`, `tools/validate_yaml_util_sync.py`, `tools/validate_transform_refs.py` |
| Edge constraints | 7 edge types (requires, soft_requires, enables, precedes, conflicts_with, alternative_to, specializes) | `schemas/capability_ontology.yaml` — edges, `spec/EDGE_TYPES.md` |
| Layer architecture | 9 cognitive layers organizing capabilities | `schemas/capability_ontology.yaml` — `layers` section |
| Domain parameterisation | Single capability with domain parameter vs. domain-specific variants | CLAUDE.md "Domain Parameterization" table |

**ISO 42001 Cross-Reference:** Clause 8.2 (AI system life cycle processes), Annex B (AI objectives)

### 3.3 Requirement (c) — Development and Quality Assurance Testing

**Art. 17(1)(c):** "techniques, procedures and systematic actions to be used for the development, quality control and quality assurance of the high-risk AI system, including testing and validation"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Development procedures | Capability creation checklist (6 steps) with mandatory validation | `CLAUDE.md` Section "Creating New Capabilities" |
| Quality control | Pre-merge validation pipeline: ontology, workflows, profiles, skill refs, YAML sync, transform refs | `tools/validate_*.py` (6 validators) |
| Quality assurance | Conformance test suite for end-to-end validation | `scripts/run_conformance.py`, `tests/` directory |
| Testing | SDK integration tests; unit tests for adapter, registry, mapper, tracker, store | `tests/test_sdk_integration.py`, `tests/test_*.py` |
| Validation | Schema validation for all YAML artifacts; profile schema enforcement | `schemas/profiles/profile_schema.yaml`, `tools/validate_profiles.py` |
| Skill schema sync | Automated local schema generation from ontology | `tools/sync_skill_schemas.py` |

**ISO 42001 Cross-Reference:** Clause 8.2 (AI system life cycle processes), Clause 9.1 (Monitoring, measurement, analysis and evaluation)

### 3.4 Requirement (d) — Data Management

**Art. 17(1)(d):** "techniques, procedures and systematic actions for data management, including data acquisition, data collection, data analysis, data labelling, data storage, data filtration, data mining, data aggregation and data retention and any other operation regarding the data"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Data acquisition | Trust-weighted source model with domain-specific weights | `schemas/profiles/*.yaml` — `trust_weights` sections |
| Data collection | EvidenceStore with typed evidence anchors | `grounded_agency/state/evidence_store.py` |
| Data analysis | Confidence scoring with domain-specific minimum thresholds | Evidence policies in domain profiles |
| Data labelling | Required anchor types per domain profile | `evidence_policy.required_anchor_types` per profile |
| Data storage | Append-only audit log; checkpoint metadata store; evidence store | `hooks/hooks.json`, `grounded_agency/state/checkpoint_tracker.py`, `grounded_agency/state/evidence_store.py` |
| Data filtration | Trust decay model (halves every 14 days, floor 0.25) | Trust model in `grounded_agency/` |
| Data retention | Domain-specific retention (healthcare: 2555 days); Art. 12 minimum 10 years | Domain profiles `compliance` section; EUAIA-PMM-001 Section 9 |
| Provenance tracking | ProvenanceRecord linking evidence to source, timestamp, and capability | EvidenceStore provenance API |

**ISO 42001 Cross-Reference:** Clause 8.3 (Data for AI systems), Annex C (AI-related data management)

### 3.5 Requirement (e) — Risk Management

**Art. 17(1)(e):** "a risk management system as referred to in Article 9"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Risk identification | Structural risk classification in ontology metadata | `schemas/capability_ontology.yaml` — `risk`, `mutation`, `requires_checkpoint`, `requires_approval` per capability |
| Risk analysis | Three-tier model: Low (29), Medium (5), High (2) | AIMS-RSK-001 (risk treatment plan), EUAIA-CLS-001 |
| Risk evaluation | Domain profiles configure risk thresholds per deployment context | `schemas/profiles/*.yaml` — `risk_thresholds` |
| Risk treatment | Structural controls (hooks, conflicts_with edges), operational controls (approvals, blocking), detective controls (audit, evidence) | AIMS-RSK-001 Sections 3.1-3.3 |
| Residual risk acceptance | Formal acceptance per risk tier with monitoring | AIMS-RSK-001 Section 7 |
| Risk monitoring | Post-market monitoring KPIs | EUAIA-PMM-001 Section 5 |

**ISO 42001 Cross-Reference:** Clause 6.1 (Actions to address risks), Annex A.2 (Policies related to AI), Annex A.7 (AI system risk management)

### 3.6 Requirement (f) — Post-Market Monitoring

**Art. 17(1)(f):** "a post-market monitoring system as referred to in Article 61"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Post-market monitoring plan | Formal monitoring plan with data collection, KPIs, escalation, incident reporting | EUAIA-PMM-001 |
| Data collection | Existing telemetry (audit log, EvidenceStore, CheckpointTracker) | EUAIA-PMM-001 Section 3 |
| Monitoring cadence | Five-tier schedule (continuous → annual) plus event-triggered | EUAIA-PMM-001 Section 4 |
| KPIs | Safety, performance, and compliance KPIs with alert thresholds | EUAIA-PMM-001 Section 5 |
| Serious incident reporting | Art. 62 notification procedure with 15-day timeline | EUAIA-PMM-001 Section 7 |

**ISO 42001 Cross-Reference:** Clause 9.1 (Monitoring), Clause 10.1 (Nonconformity and corrective action)

### 3.7 Requirement (g) — Incident and Malfunction Reporting

**Art. 17(1)(g):** "procedures related to the reporting of a serious incident in accordance with Article 62"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Incident detection | Four-level escalation model (Info → Warning → Critical → Incident) | EUAIA-PMM-001 Section 6 |
| Incident classification | Serious incident definition per Art. 3(49) | EUAIA-PMM-001 Section 7.1 |
| Reporting procedure | 6-step procedure from detection to follow-up | EUAIA-PMM-001 Section 7.2 |
| Notification content | Structured notification elements per Art. 62(1) | EUAIA-PMM-001 Section 7.3 |
| Authority interaction | Response procedures for market surveillance authority requests | EUAIA-PMM-001 Section 7.4 |
| Corrective action | Nonconformity and corrective action procedure | AIMS-NCR-001 |

**ISO 42001 Cross-Reference:** Clause 10.1 (Nonconformity and corrective action), Clause 10.2 (Continual improvement)

### 3.8 Requirement (h) — Communication with Authorities

**Art. 17(1)(h):** "procedures for communication with national competent authorities, other relevant authorities, including those providing or supporting access to data, notified bodies, other operators, customers or other interested parties"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Market surveillance authority communication | Serious incident reporting procedure; corrective action reporting | EUAIA-PMM-001 Section 7 |
| Notified body interaction | Conformity assessment routing; documentation provision | EUAIA-NTB-001 Section 6 |
| Deployer communication | Deployer notification at L2+ escalation levels | EUAIA-PMM-001 Section 6.1 |
| Stakeholder communication | Stakeholder analysis with communication requirements | AIMS-STK-001 (stakeholder analysis) |
| EU database registration | Technical documentation and declaration for Art. 49 registration | EUAIA-TEC-001, Art. 47 declaration |

**ISO 42001 Cross-Reference:** Clause 7.4 (Communication), Annex A.6 (Communication)

### 3.9 Requirement (i) — Systems and Procedures for Record Keeping

**Art. 17(1)(i):** "systems and procedures for record keeping of all relevant documentation and information, including documentation and information per Article 18"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Technical documentation | Annex IV documentation | EUAIA-TEC-001 |
| Audit logs | Append-only skill invocation log | `hooks/hooks.json` — PostToolUse hook, `.claude/audit.log` |
| Evidence records | Typed evidence anchors with provenance | `grounded_agency/state/evidence_store.py` |
| Checkpoint records | Checkpoint creation, validation, expiry metadata | `grounded_agency/state/checkpoint_tracker.py` |
| Configuration records | Domain profiles with version tracking | `schemas/profiles/*.yaml` with git history |
| Retention policy | Domain-specific retention periods; minimum 10 years for high-risk | EUAIA-PMM-001 Section 9 |
| Integrity | Append-only log; schema validation prevents corruption | Audit hook, validators |

**ISO 42001 Cross-Reference:** Clause 7.5 (Documented information), Annex A.3 (Internal organization)

### 3.10 Requirement (j) — Resource Management

**Art. 17(1)(j):** "resource management, including security-of-supply related measures"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Human resources | Competency framework defining AI roles and required competencies | AIMS-CMP-001 (competency framework) |
| Technical resources | 6 validators, SDK integration, conformance test suite | `tools/validate_*.py`, `grounded_agency/`, `scripts/run_conformance.py` |
| Infrastructure | Plugin architecture (hooks, skills, profiles); Claude Agent SDK dependency | `.claude-plugin/plugin.json`, `grounded_agency/` |
| Supply chain | SDK dependency management; profile configuration management | `pyproject.toml` or `setup.py` dependencies |
| Continuity | Checkpoint mechanism for state recovery; rollback capability | `grounded_agency/state/checkpoint_tracker.py` |

**ISO 42001 Cross-Reference:** Clause 7.1 (Resources), Clause 7.2 (Competence), Annex A.3 (Internal organization)

### 3.11 Requirement (k) — Accountability Framework

**Art. 17(1)(k):** "an accountability framework setting out the responsibilities of the management and other staff with regard to all the aspects listed in this paragraph"

| Requirement Element | Framework Implementation | Evidence |
|-------------------|--------------------------|----------|
| Role definitions | AI System Owner, AI System Operator, AI Safety Officer, Domain Expert | AIMS-CMP-001 Section 3 (roles) |
| Management responsibility | Management review process with standing agenda items | AIMS-MGR-001 (management review) |
| Monitoring responsibility | Monitoring roles per cadence level | EUAIA-PMM-001 Section 4.1 |
| Escalation responsibility | Escalation matrix with responsible roles per level | EUAIA-PMM-001 Section 6.1 |
| Incident reporting responsibility | Art. 62 reporting chain: Operator → Safety Officer → Owner → Legal | EUAIA-PMM-001 Section 7.2 |
| Audit responsibility | Internal audit programme and auditor competency | AIMS-AUD-001 (internal audit checklist) |

**ISO 42001 Cross-Reference:** Clause 5.1 (Leadership and commitment), Clause 5.3 (Roles, responsibilities and authorities)

## 4. Art. 17 to ISO 42001 Cross-Reference Table

| Art. 17 Requirement | ISO 42001 Clause | AIMS Document | EU AI Act Document |
|---------------------|-----------------|---------------|-------------------|
| (a) Regulatory compliance strategy | 6.1, 8.4 | AIMS-RSK-001 | EUAIA-CLS-001, EUAIA-NTB-001 |
| (b) Design and development | 8.2, Annex B | — | EUAIA-TEC-001 (Element 2) |
| (c) Development and QA testing | 8.2, 9.1 | — | EUAIA-TEC-001 (Element 7) |
| (d) Data management | 8.3, Annex C | — | EUAIA-TEC-001 (Element 2) |
| (e) Risk management | 6.1, Annex A.2, A.7 | AIMS-RSK-001 | EUAIA-CLS-001 |
| (f) Post-market monitoring | 9.1, 10.1 | — | EUAIA-PMM-001 |
| (g) Incident reporting | 10.1, 10.2 | AIMS-NCR-001 | EUAIA-PMM-001 (Section 7) |
| (h) Communication with authorities | 7.4, Annex A.6 | AIMS-STK-001 | EUAIA-NTB-001 |
| (i) Record keeping | 7.5, Annex A.3 | — | EUAIA-TEC-001, EUAIA-PMM-001 (Section 9) |
| (j) Resource management | 7.1, 7.2, Annex A.3 | AIMS-CMP-001 | — |
| (k) Accountability framework | 5.1, 5.3 | AIMS-CMP-001, AIMS-MGR-001 | EUAIA-PMM-001 (Section 6) |

## 5. QMS Documentation Hierarchy

```
EU AI Act Art. 17 QMS
├── Level 1: Policy
│   ├── AI Policy (AIMS-POL-001 / AI Policy Template)
│   └── Risk Classification (EUAIA-CLS-001)
│
├── Level 2: Procedures
│   ├── Risk Treatment (AIMS-RSK-001)
│   ├── Post-Market Monitoring (EUAIA-PMM-001)
│   ├── Nonconformity & Corrective Action (AIMS-NCR-001)
│   ├── Notified Body Assessment (EUAIA-NTB-001)
│   └── Internal Audit (AIMS-AUD-001)
│
├── Level 3: Technical Documentation
│   ├── Annex IV Technical Documentation (EUAIA-TEC-001)
│   ├── Capability Ontology (schemas/capability_ontology.yaml)
│   ├── Domain Profiles (schemas/profiles/*.yaml)
│   └── Workflow Catalog (schemas/workflow_catalog.yaml)
│
└── Level 4: Records
    ├── Audit Log (.claude/audit.log)
    ├── Evidence Store (grounded_agency/state/evidence_store.py)
    ├── Checkpoint Records (grounded_agency/state/checkpoint_tracker.py)
    ├── Validation Results (tools/validate_*.py outputs)
    └── Management Review Minutes (AIMS-MGR-001 records)
```

## 6. QMS Review and Maintenance

### 6.1 Review Triggers

| Trigger | QMS Review Scope | Responsible |
|---------|-----------------|-------------|
| Ontology version change | Requirements (b), (c), (e) — design, testing, risk | AI Safety Officer |
| New domain profile | Requirements (a), (d), (e) — compliance, data, risk | AI System Owner |
| Art. 62 incident | All requirements — full QMS review | AI System Owner + Management |
| Regulatory guidance update | Affected requirements | Legal/Regulatory + AI Safety Officer |
| Annual review | All requirements | AI System Owner |

### 6.2 QMS Maturity Assessment

| Maturity Level | Description | Current Assessment |
|---------------|-------------|-------------------|
| **Level 1 — Initial** | QMS exists but informal | — |
| **Level 2 — Managed** | QMS documented and followed | — |
| **Level 3 — Defined** | QMS standardised across deployments | **Current: Framework provides standardised QMS infrastructure** |
| **Level 4 — Measured** | QMS performance measured via KPIs | Partially (EUAIA-PMM-001 defines KPIs; implementation pending) |
| **Level 5 — Optimising** | QMS continuously improved based on data | Target state |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | EUAIA-QMS-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |
| QMS Owner | [Name, Title] |

---

*This quality management system document maps all 11 Art. 17 requirements to the Grounded Agency framework's implementations and cross-references the ISO 42001 AIMS document suite. The framework provides Level 3 (Defined) QMS maturity as infrastructure; deployers must operationalise the remaining elements for their specific context. All bracketed fields should be adapted to organizational context. For risk classification, see EUAIA-CLS-001. For post-market monitoring, see EUAIA-PMM-001. For technical documentation, see EUAIA-TEC-001.*
