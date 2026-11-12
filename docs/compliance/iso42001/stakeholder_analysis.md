# Stakeholder Analysis — ISO/IEC 42001 Clause 4 (Context of the Organization)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Clause:** 4 — Context of the Organization
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — Adapt stakeholder entries to organizational context

---

## 1. Purpose

This document fulfills ISO/IEC 42001 Clause 4.2 (Understanding the needs and expectations of interested parties) by identifying stakeholders relevant to AI systems built on the Grounded Agency framework, their requirements, and how the framework addresses them.

## 2. Internal and External Context (Clause 4.1)

### 2.1 Internal Factors

| Factor | Description | Framework Relevance |
|--------|-------------|-------------------|
| Organizational mission | Deploy AI agents for [domain-specific purpose] | Domain profiles define operational scope |
| Technical capabilities | Software engineering, ML/AI competencies | Competency framework (see Clause 7 document) |
| Risk appetite | Tolerance for autonomous AI decision-making | `risk_thresholds` in domain profiles |
| Existing infrastructure | CI/CD, monitoring, deployment pipelines | Integration with hooks, audit logs, evidence stores |
| Culture | Safety-first, evidence-based decision making | Aligns with Grounded Agency core principles |

### 2.2 External Factors

| Factor | Description | Framework Relevance |
|--------|-------------|-------------------|
| AI regulatory landscape | EU AI Act, NIST AI RMF, ISO 42001 | Compliance features mapped in `analysis/10-regulatory-compliance.md` |
| Industry standards | Domain-specific regulations (HIPAA, ISO 9001, GDPR) | Domain profiles encode industry requirements |
| Technology evolution | LLM capabilities, tool ecosystems, MCP protocol | Capability ontology extensible via governance process |
| Competitive environment | Industry adoption of responsible AI practices | Framework provides differentiation through structural safety |
| Public expectations | Transparency, fairness, accountability in AI | Evidence grounding, auditability, human oversight |

## 3. Stakeholder Register (Clause 4.2)

### 3.1 Internal Stakeholders

| Stakeholder | Role | Needs & Expectations | Relevant Framework Feature |
|-------------|------|---------------------|---------------------------|
| **Top Management** | Strategic oversight | AI systems align with business objectives; regulatory compliance assured; risks managed | AI policy (Clause 5), management review (Clause 9), risk treatment plan (Clause 6) |
| **AI System Owners** | Accountable for AI system lifecycle | Clear risk classification; operational controls; audit trails | Three-tier risk model, domain profiles, audit hooks |
| **AI System Operators** | Day-to-day AI system management | Usable configuration; clear escalation paths; monitoring tools | Domain profile YAML, `inquire` capability, EvidenceStore |
| **AI Safety Officers** | Safety and compliance oversight | Verifiable safety properties; incident procedures; audit capability | Structural enforcement, nonconformity procedure (Clause 10), audit checklist |
| **Software Engineers** | Build and maintain AI systems | Clear APIs; typed contracts; composable capabilities | Capability ontology I/O schemas, workflow DSL, SDK integration |
| **Domain Experts** | Validate domain-specific configuration | Meaningful trust weights; appropriate confidence thresholds; relevant evidence types | Domain profiles, trust weight calibration, evidence policy |
| **Internal Auditors** | Verify AIMS effectiveness | Audit trails; evidence of controls; compliance documentation | Audit hooks, EvidenceStore, this compliance document suite |

### 3.2 External Stakeholders

| Stakeholder | Role | Needs & Expectations | Relevant Framework Feature |
|-------------|------|---------------------|---------------------------|
| **Regulators** | Enforce AI regulations | Compliance evidence; technical documentation; risk management | Regulatory compliance analysis, risk treatment plan, audit trails |
| **Certification Bodies** | Assess conformity to ISO 42001 | Documented AIMS; evidence of implementation; management commitment | This compliance document suite, AI policy, management review records |
| **End Users** | Interact with AI-powered systems | Reliable outputs; explainable decisions; ability to escalate | `explain` capability, `inquire` capability, confidence scores |
| **Data Subjects** | Persons whose data is processed | Privacy; consent; right to explanation; data minimization | Provenance records, evidence store FIFO eviction, `explain` capability |
| **Customers / Clients** | Organizations deploying the framework | Compliance assurance; safety guarantees; domain customization | Domain profiles, structural enforcement, compliance documentation |
| **Industry Partners** | Organizations in the ecosystem | Interoperability; standard compliance; security | OASF mapping, typed contracts, security model |
| **Open Source Community** | Contributors and adopters | Clear governance; extensibility; documentation quality | Extension governance process, CLAUDE.md, tutorials |
| **Insurance Providers** | Underwrite AI-related risks | Quantified risk profiles; control evidence; incident history | Risk classification, audit logs, corrective action records |

## 4. Stakeholder Influence and Interest Matrix

```
                    High Interest
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    │   KEEP SATISFIED   │  MANAGE CLOSELY    │
    │                    │                    │
    │  Insurance         │  Top Management    │
    │  Providers         │  Regulators        │
    │  Industry Partners │  AI System Owners  │
    │                    │  Certification     │
    │                    │  Bodies            │
    │                    │  AI Safety Officers│
Low ├────────────────────┼────────────────────┤ High
Influence               │                    Influence
    │                    │                    │
    │   MONITOR          │  KEEP INFORMED     │
    │                    │                    │
    │  Open Source       │  Software Engineers│
    │  Community         │  AI Operators      │
    │                    │  Domain Experts    │
    │  Data Subjects     │  End Users         │
    │                    │  Customers         │
    │                    │                    │
    └────────────────────┼────────────────────┘
                         │
                    Low Interest
```

## 5. Stakeholder Communication Plan

| Stakeholder Group | Communication Method | Frequency | Owner | Content |
|-------------------|---------------------|-----------|-------|---------|
| Top Management | Management review meeting | Per cadence (see Clause 9) | AI Safety Officer | AIMS performance, risks, improvement actions |
| Regulators | Compliance reports | On request / per regulation | AI Safety Officer | Audit evidence, conformity documentation |
| Certification Bodies | Audit evidence packages | Per audit cycle | AI Safety Officer | Full AIMS documentation suite |
| AI System Operators | Operational dashboards, training | Ongoing / quarterly | AI System Owner | Configuration guidance, incident procedures |
| End Users | AI transparency disclosures | At interaction | AI System Owner | System capabilities, limitations, escalation paths |
| Data Subjects | Privacy notices | At data collection | Data Protection Officer | Processing purposes, rights, contact information |
| Open Source Community | Release notes, documentation | Per release | Project maintainers | Changes, migration guides, contribution guidelines |

## 6. Determining AIMS Scope (Clause 4.3)

The scope of the AI Management System shall consider:

| Scope Element | Determination |
|---------------|--------------|
| **AI system boundaries** | All systems using the Grounded Agency capability ontology and workflow engine |
| **Applicable regulatory requirements** | Per deployment domain — see `schemas/profiles/*.yaml` for domain-specific compliance fields |
| **Organizational boundaries** | [Define: teams, departments, business units operating AI systems] |
| **Technology boundaries** | Claude Code plugin environment, MCP tool ecosystem, SDK integrations |
| **Data boundaries** | Data processed by capability executions, stored in evidence stores, logged by audit hooks |
| **Exclusions and justifications** | [Document any exclusions with rationale per Clause 4.3 note] |

## 7. AI Management System (Clause 4.4)

The organization shall establish, implement, maintain, and continually improve an AIMS that includes:

| AIMS Component | Implementation | Document Reference |
|---------------|---------------|-------------------|
| Processes needed | Capability workflows, approval flows, review cycles | `schemas/workflow_catalog.yaml` |
| Process interactions | Capability edges (requires, enables, precedes) | `schemas/capability_ontology.yaml` edges section |
| Criteria and methods for control | Risk thresholds, checkpoint policies, evidence requirements | Domain profiles, hooks |
| Resources needed | Personnel competencies, tooling, infrastructure | Competency framework (Clause 7) |
| Responsibilities and authorities | Role definitions per AI policy | AI policy template (Clause 5) |
| Risks and opportunities | Risk treatment plan | Risk treatment plan (Clause 6) |
| Evaluation methods | Management review, internal audit | Management review (Clause 9), audit checklist |
| Improvement opportunities | Corrective actions, continual improvement | Nonconformity procedure (Clause 10) |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-CTX-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |

---

*This template fulfills ISO/IEC 42001:2023 Clause 4 requirements. All bracketed fields and example entries should be adapted to the specific organizational context before adoption.*
