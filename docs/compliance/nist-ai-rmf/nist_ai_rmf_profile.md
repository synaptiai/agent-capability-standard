# NIST AI RMF 1.0 Profile — Grounded Agency Framework

**Framework:** NIST AI Risk Management Framework (AI RMF 1.0), January 2023
**Profile Type:** Current/Target Profile for AI Agent Infrastructure
**Subject Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Reference analysis — Maps framework capabilities to all four NIST core functions
**Document ID:** NIST-RMF-001

---

## 1. Purpose and Scope

This document provides a NIST AI RMF 1.0 profile that maps the Grounded Agency framework's 36 atomic capabilities, 9 cognitive layers, 7 domain profiles, and safety model to all four core NIST functions: **Govern**, **Map**, **Measure**, and **Manage**.

**Key distinction:** The Grounded Agency framework is *infrastructure* — a capability ontology, safety model, and composition engine — not a deployed AI system. This profile assesses the framework's structural support for each NIST function. AI systems *built on* this framework inherit its safety properties but require deployer-specific profile customization for their operational context.

### 1.1 Scope

This profile covers:

- All 4 NIST AI RMF core functions and their 19 categories
- Tier assessment (Partial → Risk Informed → Repeatable → Adaptive) for each function
- Evidence mapping from NIST sub-categories to framework components
- Maturity roadmap from current profile to target profile
- Cross-references to ISO 42001 and EU AI Act compliance suites

### 1.2 Intended Audience

| Audience | Use |
|----------|-----|
| Framework deployers | Customize this profile for specific AI system deployments |
| Compliance officers | Verify NIST AI RMF alignment and identify gaps |
| Auditors and assessors | Cross-reference NIST requirements to framework evidence |
| Risk managers | Assess residual risk and plan remediation |

---

## 2. Framework Overview

### 2.1 NIST AI RMF Structure

The NIST AI RMF 1.0 organizes AI risk management into four core functions:

| Function | Purpose | Categories |
|----------|---------|------------|
| **GOVERN** | Establish and maintain organizational AI risk governance | GV-1 through GV-6 |
| **MAP** | Identify and characterize AI system context and risks | MP-1 through MP-5 |
| **MEASURE** | Analyze, assess, and track AI risks | ME-1 through ME-4 |
| **MANAGE** | Prioritize and act on AI risks | MG-1 through MG-4 |

### 2.2 Grounded Agency Framework

The Grounded Agency framework provides 36 atomic capabilities across 9 cognitive layers, composed through typed contracts with structural safety enforcement:

| Component | Count | Risk Relevance |
|-----------|-------|---------------|
| Atomic capabilities | 36 | Typed I/O contracts, risk metadata, dependency edges |
| Cognitive layers | 9 | PERCEIVE → UNDERSTAND → REASON → MODEL → SYNTHESIZE → EXECUTE → VERIFY → REMEMBER → COORDINATE |
| Domain profiles | 7 | Trust weights, risk thresholds, checkpoint policies, compliance configuration |
| Workflow patterns | 12 | Composable capability sequences with safety gates |
| Edge types | 7 | `requires`, `soft_requires`, `enables`, `precedes`, `conflicts_with`, `alternative_to`, `specializes` |

### 2.3 Risk Classification

| Risk Level | Count | Capabilities | Safety Properties |
|------------|-------|-------------|-------------------|
| **Low** | 29 | retrieve, search, observe, receive, detect, classify, measure, predict, compare, discover, plan, decompose, critique, explain, state, transition, attribute, ground, simulate, generate, transform, integrate, verify, checkpoint, constrain, audit, persist, recall, inquire | `mutation: false`, no special restrictions |
| **Medium** | 5 | execute, rollback, delegate, synchronize, invoke | `requires_approval: true` for some, human review recommended |
| **High** | 2 | mutate, send | `mutation: true`, `requires_checkpoint: true`, `requires_approval: true` |

---

## 3. Profile Methodology

### 3.1 Tier Assessment Criteria

NIST AI RMF defines four organizational tiers for AI risk management maturity:

| Tier | Name | Characteristics |
|------|------|----------------|
| **Tier 1** | Partial | Ad hoc, reactive, limited awareness of AI risks. Risk management is not formalized. |
| **Tier 2** | Risk Informed | Risk-aware practices exist but may not be organization-wide. Policies exist but implementation varies. |
| **Tier 3** | Repeatable | Organization-wide policies implemented consistently. Risk management is formalized and documented. |
| **Tier 4** | Adaptive | Continuous improvement based on lessons learned. Automated monitoring, predictive risk indicators, organizational agility. |

### 3.2 Assessment Approach

Each NIST category is assessed using:

1. **Framework implementation** — What structural features address this category
2. **Evidence files** — Specific file paths demonstrating implementation
3. **Coverage level** — Full, Partial, or Gap
4. **Infrastructure vs. deployer distinction** — Whether the framework provides structural support or requires deployer implementation

### 3.3 Coverage Definitions

| Coverage | Definition |
|----------|-----------|
| **Full** | Framework structurally enforces the requirement; no deployer action needed |
| **Partial** | Framework provides structural support; deployer must configure or extend |
| **Gap** | Framework does not address this requirement; deployer must implement independently |

---

## 4. GOVERN Function

**Purpose:** Cultivate and implement a culture of AI risk management within organizations that design, develop, deploy, evaluate, and use AI systems.

### 4.1 GV-1: Policies, Processes, Procedures, and Practices

**NIST Description:** Policies, processes, procedures, and practices across the organization related to the mapping, measuring, and managing of AI risks are in place, transparent, and implemented effectively.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **GV-1.1** — Legal and regulatory requirements identified | EU AI Act conformity suite, ISO 42001 compliance suite, regulatory compliance analysis | `docs/compliance/eu-ai-act/`, `docs/compliance/iso42001/`, `analysis/10-regulatory-compliance.md` | Full |
| **GV-1.2** — Trustworthy AI characteristics integrated | Grounded Agency principles: grounded, auditable, safe, composable | `spec/WHITEPAPER.md` (principles section), `docs/GROUNDED_AGENCY.md` | Full |
| **GV-1.3** — Risk tolerances determined | Domain profiles define `min_confidence`, `block_autonomous`, `require_human` thresholds per deployment context | `schemas/profiles/*.yaml`, `schemas/profiles/profile_schema.yaml` | Full |
| **GV-1.4** — Risk management process established | Three-tier risk model structurally embedded in ontology; risk treatment plan documents controls per tier | `schemas/capability_ontology.yaml` (risk fields), `docs/compliance/iso42001/risk_treatment_plan.md` | Full |
| **GV-1.5** — Processes for ongoing monitoring | EvidenceStore tracks tool executions; audit hooks log skill invocations; management review process defined | `grounded_agency/state/evidence_store.py`, `hooks/hooks.json`, `docs/compliance/iso42001/management_review.md` | Full |
| **GV-1.6** — Mechanisms for inventory and documentation | Capability ontology serves as formal inventory; technical documentation covers all Annex IV elements | `schemas/capability_ontology.yaml`, `docs/compliance/eu-ai-act/annex_iv_technical_documentation.md` | Full |
| **GV-1.7** — Processes for decommissioning | Gap — No formal AI system decommissioning procedure documented | — | Gap |

### 4.2 GV-2: Accountability Structures

**NIST Description:** Accountability structures are in place so that the appropriate teams and individuals are empowered, responsible, and trained for mapping, measuring, and managing AI risks.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **GV-2.1** — Roles and responsibilities defined | Competency framework defines 6 roles with proficiency levels; RACI-style accountability documented | `docs/compliance/iso42001/competency_framework.md` | Full |
| **GV-2.2** — Training and awareness programs | Training tracks defined per role; awareness, intermediate, advanced, expert proficiency levels | `docs/compliance/iso42001/competency_framework.md` (§4–5) | Full |
| **GV-2.3** — Senior leadership oversight | Management review process with quarterly cadence; top management participation required | `docs/compliance/iso42001/management_review.md` | Full |

### 4.3 GV-3: Workforce Diversity, Equity, Inclusion, and Accessibility

**NIST Description:** Workforce diversity, equity, inclusion, and accessibility processes are prioritized in the mapping, measuring, and managing of AI risks.

| Category | Framework Implementation | Coverage |
|----------|--------------------------|----------|
| **GV-3** | Stakeholder analysis identifies affected parties; domain profiles parameterize per deployment context. Framework does not prescribe organizational workforce policies. | Partial — Deployer must implement organizational DEIA policies |

### 4.4 GV-4: Organizational Culture

**NIST Description:** Organizational teams are committed to a culture that considers and communicates AI risk.

| Category | Framework Implementation | Coverage |
|----------|--------------------------|----------|
| **GV-4** | AI policy template establishes organizational commitment; competency framework ensures knowledge distribution; nonconformity procedure encourages reporting. Evidence: `docs/compliance/iso42001/ai_policy_template.md`, `docs/compliance/iso42001/nonconformity_procedure.md` | Partial — Framework provides templates; deployer must foster organizational culture |

### 4.5 GV-5: Stakeholder Engagement

**NIST Description:** Ongoing stakeholder engagement is planned, and mechanisms for stakeholders to provide feedback are established.

| Category | Framework Implementation | Coverage |
|----------|--------------------------|----------|
| **GV-5** | Stakeholder analysis identifies 6 stakeholder categories with communication channels and frequency. `inquire` capability enables human escalation at runtime. Evidence: `docs/compliance/iso42001/stakeholder_analysis.md`, `skills/inquire/SKILL.md` | Partial — Framework provides structure; deployer must implement engagement processes |

### 4.6 GV-6: Policies and Procedures for Third-Party AI

**NIST Description:** Policies and procedures are in place to address AI risks and benefits arising from third-party software and data.

| Category | Framework Implementation | Coverage |
|----------|--------------------------|----------|
| **GV-6** | Trust model defines source weights for external data (`hardware_sensor: 0.95`, `system_of_record: 0.92`, down to `unverified: 0.20`). `invoke` capability handles external API calls with typed contracts. No formal third-party AI vendor assessment procedure. Evidence: `schemas/authority_trust_model.yaml` | Partial — Trust weights for data sources exist; third-party vendor assessment is a gap |

> **GOVERN Function — Tier Assessment**
>
> | Criterion | Assessment |
> |-----------|-----------|
> | **Current Tier** | **Tier 2 — Risk Informed** |
> | **Target Tier** | Tier 3 — Repeatable |
> | **Justification** | Domain profiles, risk treatment plan, competency framework, and compliance documentation provide risk-informed governance. GV-1.7 (decommissioning), GV-3 (DEIA), and GV-6 (third-party vendor assessment) are gaps that prevent Tier 3 classification. Organizational adoption depends on deployer commitment. |
> | **Key gaps** | Decommissioning procedure (GV-1.7), DEIA policies (GV-3), third-party vendor assessment (GV-6) |

---

## 5. MAP Function

**Purpose:** Establish context to frame AI risks, identify AI system risks, and characterize the potential benefits and costs of AI systems.

### 5.1 MP-1: Context Establishment

**NIST Description:** Context is established and understood.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **MP-1.1** — Intended purpose documented | Every capability has formal input/output contracts with typed schemas; workflow catalog documents composition patterns | `schemas/capability_ontology.yaml` (all 36 capability definitions), `schemas/workflow_catalog.yaml` | Full |
| **MP-1.2** — Interdependencies mapped | 7 edge types (requires, soft_requires, enables, precedes, conflicts_with, alternative_to, specializes) explicitly map capability dependencies | `schemas/capability_ontology.yaml` (edges section), `spec/EDGE_TYPES.md` | Full |
| **MP-1.3** — Deployment context characterized | 7 domain profiles define operational context: trust weights, risk thresholds, compliance requirements, evidence policies | `schemas/profiles/healthcare.yaml`, `schemas/profiles/manufacturing.yaml`, `schemas/profiles/data_analysis.yaml`, `schemas/profiles/personal_assistant.yaml`, `schemas/profiles/vision.yaml`, `schemas/profiles/audio.yaml`, `schemas/profiles/multimodal.yaml` | Full |
| **MP-1.4** — Assumptions documented | First-principles derivation methodology documents design assumptions; whitepaper states core principles | `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md`, `spec/WHITEPAPER.md` | Full |
| **MP-1.5** — User interactions characterized | `inquire` capability for human escalation; `require_human` flag in profiles; `block_autonomous` lists | `schemas/profiles/profile_schema.yaml`, `skills/inquire/SKILL.md` | Full |

### 5.2 MP-2: AI System Categorization

**NIST Description:** Categorization of the AI system is performed.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **MP-2.1** — AI system categorized by risk | Three-tier risk model (low/medium/high) embedded in ontology; EU AI Act risk classification maps profiles to 4 regulatory tiers | `schemas/capability_ontology.yaml` (risk field), `docs/compliance/eu-ai-act/risk_classification.md` | Full |
| **MP-2.2** — Risk levels communicated | Risk metadata exposed in capability definitions; domain profiles set explicit thresholds; risk classification document provides transparent categorization | `schemas/capability_ontology.yaml`, `schemas/profiles/*.yaml` | Full |
| **MP-2.3** — System characteristics documented | Typed I/O contracts for all 36 capabilities; output schemas include `confidence`, `evidence_anchors`, `provenance` fields | `schemas/capability_ontology.yaml` (input_schema, output_schema for each capability) | Full |

### 5.3 MP-3: AI Capabilities, Targeted Usage, Goals, and Expected Benefits

**NIST Description:** AI capabilities, targeted usage, goals, and expected benefits and costs compared with appropriate benchmarks are understood.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **MP-3** | 36 capabilities with formal descriptions, I/O contracts, and risk metadata. Domain parameterization (`domain: anomaly`, `domain: entity`) enables targeted usage. Workflow catalog defines 12 reusable composition patterns. | `schemas/capability_ontology.yaml`, `schemas/workflow_catalog.yaml`, `docs/FAQ.md` | Full |

### 5.4 MP-4: Risks and Impacts

**NIST Description:** Risks and impacts related to AI systems are assessed.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **MP-4** | Risk treatment plan covers risk identification, analysis, evaluation per ISO 42001. STRIDE threat model in security scan. `conflicts_with` edges identify incompatible operations. | `docs/compliance/iso42001/risk_treatment_plan.md`, `analysis/04-security-scan-findings.md` (§7), `schemas/capability_ontology.yaml` (conflicts_with edges) | Full |

### 5.5 MP-5: Impact Assessment

**NIST Description:** Impacts to individuals, groups, communities, and organizations are characterized.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **MP-5** | Stakeholder analysis identifies 6 categories of affected parties. Risk classification distinguishes high-risk from low-risk deployments. No formal impact assessment methodology for specific populations. | `docs/compliance/iso42001/stakeholder_analysis.md`, `docs/compliance/eu-ai-act/risk_classification.md` | Partial — Impact assessment methodology for specific populations is a gap |

> **MAP Function — Tier Assessment**
>
> | Criterion | Assessment |
> |-----------|-----------|
> | **Current Tier** | **Tier 3 — Repeatable** |
> | **Target Tier** | Tier 4 — Adaptive |
> | **Justification** | Strong structural foundation: typed capability contracts, 7 domain profiles with trust weights, 3-tier risk classification, 7 edge types for dependency mapping, comprehensive risk treatment plan. Context establishment (MP-1) and categorization (MP-2) are formalized and repeatable. MP-5 (impact assessment) gap prevents Tier 4. |
> | **Key gaps** | Formal impact assessment methodology for specific populations (MP-5); adaptive context updates from operational data |

---

## 6. MEASURE Function

**Purpose:** Employ quantitative and qualitative methods to analyze, assess, and track AI risks.

### 6.1 ME-1: Methods and Metrics

**NIST Description:** Appropriate methods and metrics are identified and applied.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **ME-1.1** — Measurement approaches identified | Confidence scores required on all capability outputs; evidence anchors link claims to sources; 6 structural validators | `schemas/capability_ontology.yaml` (output schemas with `confidence` field), `tools/validate_*.py` | Full |
| **ME-1.2** — Metrics selected for trustworthiness | Per-domain `min_confidence` thresholds (healthcare: 0.90, manufacturing: 0.85, data analysis: 0.80); trust weights per source type | `schemas/profiles/*.yaml`, `schemas/authority_trust_model.yaml` | Full |
| **ME-1.3** — Metrics documented and communicated | Output schemas formally define metric structure; evidence policies specify grounding requirements per domain | `schemas/capability_ontology.yaml` (output_schema), `schemas/profiles/profile_schema.yaml` (evidence_policy) | Full |

### 6.2 ME-2: AI Systems Evaluation

**NIST Description:** AI systems are evaluated for trustworthy characteristics.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **ME-2.1** — Evaluation conducted | Conformance test suite validates structural properties; 6 validators check ontology, workflows, profiles, skill refs, transform refs, YAML sync | `scripts/run_conformance.py`, `tools/validate_ontology.py`, `tools/validate_workflows.py`, `tools/validate_profiles.py`, `tools/validate_skill_refs.py`, `tools/validate_transform_refs.py`, `tools/validate_yaml_util_sync.py` | Full |
| **ME-2.2** — Evaluation results documented | EvidenceStore captures tool executions as evidence anchors; checkpoint tracker records state transitions; audit log records all skill invocations | `grounded_agency/state/evidence_store.py`, `grounded_agency/state/checkpoint_tracker.py`, `.claude/audit.log` | Partial — Evidence is captured structurally but aggregated reporting/dashboards are a gap |
| **ME-2.3** — Continuous monitoring implemented | EvidenceStore tracks executions; temporal decay model degrades trust over time (`half_life: P14D`); audit hooks capture all skill invocations in real time | `grounded_agency/state/evidence_store.py`, `schemas/authority_trust_model.yaml` (decay_model), `hooks/hooks.json` | Partial — Real-time alerting and dashboard visualization are gaps |

### 6.3 ME-3: Trustworthy AI Actor Competency

**NIST Description:** Mechanisms for tracking identified AI risks over time are in place.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **ME-3** | Competency framework defines roles and proficiency levels (Awareness → Intermediate → Advanced → Expert). Training tracks per role with assessment methods. | `docs/compliance/iso42001/competency_framework.md` | Full |

### 6.4 ME-4: External Inputs and Feedback

**NIST Description:** Feedback about efficacy of measurement is collected and assessed.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **ME-4** | `inquire` capability enables runtime escalation to humans. Stakeholder analysis defines communication channels. Management review process collects measurement feedback quarterly. No automated external feedback collection mechanism. | `skills/inquire/SKILL.md`, `docs/compliance/iso42001/stakeholder_analysis.md`, `docs/compliance/iso42001/management_review.md` | Partial — Structural support exists; automated feedback collection is a gap |

> **MEASURE Function — Tier Assessment**
>
> | Criterion | Assessment |
> |-----------|-----------|
> | **Current Tier** | **Tier 2 — Risk Informed** |
> | **Target Tier** | Tier 3 — Repeatable |
> | **Justification** | Confidence scores and evidence anchors are structurally enforced on all outputs. Six validators provide repeatable structural evaluation. Temporal decay model tracks information freshness. However, real-time monitoring dashboards, aggregated reporting, alerting infrastructure, and automated external feedback collection are gaps. These prevent consistent, organization-wide measurement. |
> | **Key gaps** | Real-time monitoring dashboard (ME-2.3), aggregated evaluation reporting (ME-2.2), automated feedback collection (ME-4) |

---

## 7. MANAGE Function

**Purpose:** Allocate resources, and plan, implement, communicate, and monitor risk response strategies.

### 7.1 MG-1: Risk Prioritization and Response

**NIST Description:** AI risks based on assessments and other analytical output from the MAP and MEASURE functions are prioritized, responded to, and managed.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **MG-1.1** — Risk response plans developed | Checkpoint-before-mutation enforcement for all high-risk capabilities; rollback capability for state recovery; `block_autonomous` prevents unsupervised execution of dangerous operations | `hooks/hooks.json` (PreToolUse checkpoint gate), `skills/rollback/SKILL.md`, `schemas/profiles/*.yaml` (block_autonomous) | Full |
| **MG-1.2** — Residual risk documented | Risk treatment plan documents residual risk per tier; nonconformity procedure tracks unresolved findings | `docs/compliance/iso42001/risk_treatment_plan.md`, `docs/compliance/iso42001/nonconformity_procedure.md` | Full |
| **MG-1.3** — Risk response prioritized | Three-tier risk model assigns priority structurally — high-risk capabilities (mutate, send) get mandatory checkpoints and approval; medium-risk get approval; low-risk are unrestricted | `schemas/capability_ontology.yaml` (risk, requires_checkpoint, requires_approval fields) | Full |
| **MG-1.4** — Risk response monitored | Audit hooks log all skill invocations; EvidenceStore tracks execution state; management review evaluates nonconformities quarterly. No automated incident detection. | `hooks/hooks.json`, `grounded_agency/state/evidence_store.py`, `docs/compliance/iso42001/management_review.md` | Partial — Automated incident detection is a gap |

### 7.2 MG-2: Strategies for Minimizing Negative Impacts

**NIST Description:** Strategies to maximize AI benefits and minimize negative impacts are planned, prepared, implemented, documented, and informed by input from relevant AI actors.

| Sub-Category | Framework Implementation | Evidence | Coverage |
|-------------|--------------------------|----------|----------|
| **MG-2.1** — Response plans documented | Post-market monitoring plan defines escalation procedures and incident response; nonconformity procedure defines detection → containment → correction → verification workflow | `docs/compliance/eu-ai-act/post_market_monitoring.md`, `docs/compliance/iso42001/nonconformity_procedure.md` | Full |
| **MG-2.2** — Response plans tested | Recovery loop limits (`max_loops`) prevent infinite retry; rollback restores prior checkpoints; `constrain` capability enforces operational bounds. Conformance test suite validates structural properties. | `schemas/capability_ontology.yaml` (max_loops), `skills/rollback/SKILL.md`, `skills/constrain/SKILL.md`, `scripts/run_conformance.py` | Partial — Tabletop exercises and scenario testing are not documented |
| **MG-2.3** — Incident documentation maintained | Audit log records all skill invocations with timestamps; ProvenanceRecord chains track claim lineage; world state versioning preserves history with parent links | `.claude/audit.log`, `schemas/world_state_schema.yaml` (provenance), `grounded_agency/state/evidence_store.py` | Full |

### 7.3 MG-3: Third-Party Risk Management

**NIST Description:** AI risks and benefits from third-party resources are regularly monitored, and risk treatment is applied and documented.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **MG-3** | Trust model assigns weights to external sources; `invoke` capability uses typed contracts for external API calls; temporal decay degrades trust in stale third-party data. No formal third-party risk monitoring procedure. | `schemas/authority_trust_model.yaml`, `skills/invoke/SKILL.md`, `schemas/capability_ontology.yaml` (invoke capability) | Partial — Trust weights exist; formal third-party monitoring procedure is a gap |

### 7.4 MG-4: Risk Treatment Documentation and Monitoring

**NIST Description:** Risk treatments, including response and recovery, and communication plans for identified and measured AI risks are documented and monitored regularly.

| Category | Framework Implementation | Evidence | Coverage |
|----------|--------------------------|----------|----------|
| **MG-4** | Risk treatment plan is comprehensive (per ISO 42001 Clause 6). Management review process monitors quarterly. Post-market monitoring plan defines KPIs and escalation. Internal audit checklist validates controls. | `docs/compliance/iso42001/risk_treatment_plan.md`, `docs/compliance/iso42001/management_review.md`, `docs/compliance/eu-ai-act/post_market_monitoring.md`, `docs/compliance/iso42001/internal_audit_checklist.md` | Full |

> **MANAGE Function — Tier Assessment**
>
> | Criterion | Assessment |
> |-----------|-----------|
> | **Current Tier** | **Tier 3 — Repeatable** |
> | **Target Tier** | Tier 4 — Adaptive |
> | **Justification** | Strong structural enforcement: checkpoint-before-mutation is mandatory, rollback is available for state recovery, three-tier risk model assigns response priority, audit hooks provide comprehensive logging, and nonconformity procedure defines corrective action workflow. Risk treatment and documentation (MG-1.2, MG-2.1, MG-2.3, MG-4) are formalized and repeatable. Automated incident detection (MG-1.4) and tabletop scenario testing (MG-2.2) gaps prevent Tier 4. |
> | **Key gaps** | Automated incident detection (MG-1.4), tabletop exercises (MG-2.2), formal third-party risk monitoring (MG-3) |

---

## 8. Tier Assessment Summary

### 8.1 Consolidated Assessment

| Function | Current Tier | Target Tier | Gap Count | Key Strengths |
|----------|-------------|-------------|-----------|---------------|
| **GOVERN** | Tier 2 — Risk Informed | Tier 3 — Repeatable | 3 | Domain profiles, risk treatment plan, competency framework, compliance suites |
| **MAP** | Tier 3 — Repeatable | Tier 4 — Adaptive | 1 | Typed contracts, 7 domain profiles, 3-tier risk model, 7 edge types |
| **MEASURE** | Tier 2 — Risk Informed | Tier 3 — Repeatable | 3 | Confidence scores, evidence anchors, temporal decay, 6 validators |
| **MANAGE** | Tier 3 — Repeatable | Tier 4 — Adaptive | 3 | Checkpoint enforcement, rollback, audit hooks, nonconformity procedure |

### 8.2 Overall Maturity

**Weighted assessment:** Tier 2.5 (between Risk Informed and Repeatable)

The framework is strongest in MAP and MANAGE functions, where typed contracts and structural safety enforcement provide repeatable, formalized risk management. GOVERN and MEASURE functions require additional organizational and monitoring infrastructure to reach Tier 3.

### 8.3 Gap Inventory

| ID | Gap | Function | Category | Priority | Effort |
|----|-----|----------|----------|----------|--------|
| G-01 | AI system decommissioning procedure | GOVERN | GV-1.7 | Medium | Low |
| G-02 | DEIA policies for AI risk management | GOVERN | GV-3 | Medium | Medium |
| G-03 | Third-party AI vendor assessment | GOVERN | GV-6 | High | Medium |
| G-04 | Population-specific impact assessment | MAP | MP-5 | Medium | High |
| G-05 | Aggregated evaluation reporting | MEASURE | ME-2.2 | High | Medium |
| G-06 | Real-time monitoring dashboard | MEASURE | ME-2.3 | High | High |
| G-07 | Automated external feedback collection | MEASURE | ME-4 | Low | Medium |
| G-08 | Automated incident detection | MANAGE | MG-1.4 | High | High |
| G-09 | Tabletop exercises and scenario testing | MANAGE | MG-2.2 | Medium | Low |
| G-10 | Third-party risk monitoring procedure | MANAGE | MG-3 | Medium | Medium |

---

## 9. Maturity Roadmap

### 9.1 Current Profile Summary

The Grounded Agency framework currently provides:

- **Structural safety enforcement** — Checkpoint-before-mutation, typed contracts, risk metadata
- **Domain-parameterized risk management** — 7 profiles with trust weights and compliance configuration
- **Comprehensive documentation** — EU AI Act and ISO 42001 compliance suites
- **Auditability infrastructure** — Evidence anchors, audit hooks, provenance tracking

### 9.2 Target Profile

The target profile achieves:

- **GOVERN Tier 3** — Organization-wide policies with formal third-party and decommissioning procedures
- **MAP Tier 4** — Adaptive context that updates from operational data with formal impact assessment
- **MEASURE Tier 3** — Real-time monitoring with aggregated reporting and automated feedback
- **MANAGE Tier 4** — Automated incident detection with predictive risk indicators

### 9.3 Gap Remediation Roadmap

#### Phase 1: Foundation (0–3 months)

**Objective:** Close low-effort gaps and establish monitoring baseline.

| Action | Closes Gap | Target Tier Impact | Deliverable |
|--------|-----------|-------------------|-------------|
| Document AI system decommissioning procedure | G-01 (GV-1.7) | GOVERN → closer to Tier 3 | `docs/compliance/nist-ai-rmf/decommissioning_procedure.md` |
| Add NIST AI RMF sub-category references to domain profiles | — (traceability) | Cross-cutting | Updated `schemas/profiles/*.yaml` with `nist_mapping` field |
| Document tabletop exercise template and schedule | G-09 (MG-2.2) | MANAGE → closer to Tier 4 | `docs/compliance/nist-ai-rmf/tabletop_exercise_template.md` |
| Extend management review inputs to include NIST function metrics | — (integration) | GOVERN + MEASURE | Updated `docs/compliance/iso42001/management_review.md` |

#### Phase 2: Core Improvements (3–6 months)

**Objective:** Build monitoring infrastructure and formalize assessment processes.

| Action | Closes Gap | Target Tier Impact | Deliverable |
|--------|-----------|-------------------|-------------|
| Build monitoring dashboard from EvidenceStore + audit logs | G-05 (ME-2.2), G-06 (ME-2.3) | MEASURE → Tier 3 | Dashboard application with aggregated metrics |
| Develop formal impact assessment methodology | G-04 (MP-5) | MAP → closer to Tier 4 | `docs/compliance/nist-ai-rmf/impact_assessment_methodology.md` |
| Create third-party AI risk procedures | G-03 (GV-6), G-10 (MG-3) | GOVERN → Tier 3, MANAGE → closer to Tier 4 | `docs/compliance/nist-ai-rmf/third_party_risk_procedure.md` |
| Document DEIA considerations for AI risk management | G-02 (GV-3) | GOVERN → Tier 3 | Policy addendum in AI policy template |

#### Phase 3: Adaptive Maturity (6–12 months)

**Objective:** Achieve adaptive maturity through automation and predictive capabilities.

| Action | Closes Gap | Target Tier Impact | Deliverable |
|--------|-----------|-------------------|-------------|
| Implement automated incident detection from audit patterns | G-08 (MG-1.4) | MANAGE → Tier 4 | Anomaly detection on audit log patterns |
| Build automated external feedback collection | G-07 (ME-4) | MEASURE → Tier 3+ | Feedback collection pipeline integrated with stakeholder channels |
| Develop predictive risk indicators from confidence trends | — (advanced) | MEASURE → Tier 3+ | Trend analysis on EvidenceStore confidence data |
| Enable continuous profile adaptation from operational data | — (advanced) | MAP → Tier 4 | Automated domain profile tuning based on operational metrics |

### 9.4 Roadmap Visualization

```
Current State                    Target State
─────────────                    ────────────
GOVERN:  Tier 2 ──Phase 1+2──→  Tier 3
MAP:     Tier 3 ──Phase 2+3──→  Tier 4
MEASURE: Tier 2 ──Phase 2+3──→  Tier 3
MANAGE:  Tier 3 ──Phase 1+3──→  Tier 4
```

---

## 10. Cross-Reference Matrix

### 10.1 NIST AI RMF → Framework Components

| NIST Function | Primary Framework Components | Key Files |
|--------------|------------------------------|-----------|
| GOVERN | Domain profiles, competency framework, AI policy, management review | `schemas/profiles/*.yaml`, `docs/compliance/iso42001/` |
| MAP | Capability ontology, edge types, risk classification, domain profiles | `schemas/capability_ontology.yaml`, `spec/EDGE_TYPES.md`, `docs/compliance/eu-ai-act/risk_classification.md` |
| MEASURE | EvidenceStore, confidence scores, validators, trust model | `grounded_agency/state/evidence_store.py`, `tools/validate_*.py`, `schemas/authority_trust_model.yaml` |
| MANAGE | CheckpointTracker, rollback, audit hooks, nonconformity procedure | `grounded_agency/state/checkpoint_tracker.py`, `hooks/hooks.json`, `docs/compliance/iso42001/nonconformity_procedure.md` |

### 10.2 NIST AI RMF → ISO 42001 Suite

| NIST Category | ISO 42001 Document | Doc ID |
|--------------|-------------------|--------|
| GV-1 (Policies) | AI Policy Template | AIMS-POL-001 |
| GV-1 (Risk management) | Risk Treatment Plan | AIMS-RSK-001 |
| GV-2 (Accountability) | Competency Framework | AIMS-CMP-001 |
| GV-2 (Oversight) | Management Review | AIMS-MGR-001 |
| GV-5 (Stakeholders) | Stakeholder Analysis | AIMS-STK-001 |
| MP-2 (Categorization), MP-4 (Risks) | Risk Treatment Plan | AIMS-RSK-001 |
| ME-2 (Evaluation) | Internal Audit Checklist | AIMS-AUD-001 |
| MG-1 (Risk response) | Nonconformity Procedure | AIMS-NCR-001 |
| MG-4 (Monitoring) | Management Review | AIMS-MGR-001 |

### 10.3 NIST AI RMF → EU AI Act Suite

| NIST Category | EU AI Act Document | Doc ID |
|--------------|-------------------|--------|
| GV-1.1 (Legal requirements) | All EU AI Act documents | EUAIA-*-001 |
| MP-2 (Categorization) | Risk Classification | EUAIA-CLS-001 |
| ME-2 (Evaluation) | Quality Management System | EUAIA-QMS-001 |
| MG-1 (Risk response) | Post-Market Monitoring | EUAIA-PMM-001 |
| MG-2 (Minimize impact) | Post-Market Monitoring | EUAIA-PMM-001 |
| MG-4 (Documentation) | Annex IV Technical Documentation | EUAIA-TEC-001 |
| — (Conformity assessment) | Notified Body Assessment | EUAIA-NTB-001 |

### 10.4 NIST AI RMF → Regulatory Compliance Analysis

This profile expands on the NIST AI RMF mapping in `analysis/10-regulatory-compliance.md`:

| Analysis Section | Profile Section | Relationship |
|-----------------|----------------|-------------|
| §1.2 (NIST AI RMF overview) | §2.1 (Framework overview) | Profile provides detailed sub-category mapping |
| §4 (Trust model) | §5.1 MP-1, §6.1 ME-1 | Trust weights map to MAP context and MEASURE metrics |
| §7.4 (NIST profile development) | This document | Profile fulfills §7.4 recommended actions |
| Appendix A (NIST rows) | §4–7 (all functions) | Profile provides sub-category evidence for each function |

---

## Appendix A: Evidence Inventory

This appendix provides a consolidated inventory of all framework files cited as evidence throughout this profile.

### A.1 Schemas and Ontology

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `schemas/capability_ontology.yaml` | 36 capability definitions, risk metadata, typed I/O contracts, edge types | MP-1, MP-2, MP-3, MP-4, ME-1, MG-1 |
| `schemas/workflow_catalog.yaml` | 12 workflow composition patterns | MP-1, MP-3 |
| `schemas/profiles/healthcare.yaml` | Healthcare domain profile (min_confidence: 0.90) | GV-1, MP-1, ME-1 |
| `schemas/profiles/manufacturing.yaml` | Manufacturing domain profile (min_confidence: 0.85) | GV-1, MP-1, ME-1 |
| `schemas/profiles/data_analysis.yaml` | Data analysis domain profile (min_confidence: 0.80) | GV-1, MP-1, ME-1 |
| `schemas/profiles/personal_assistant.yaml` | Personal assistant domain profile | GV-1, MP-1 |
| `schemas/profiles/vision.yaml` | Vision modality profile | MP-1 |
| `schemas/profiles/audio.yaml` | Audio modality profile | MP-1 |
| `schemas/profiles/multimodal.yaml` | Multimodal profile | MP-1 |
| `schemas/profiles/profile_schema.yaml` | Profile schema definition (block_autonomous, require_human, evidence_policy) | GV-1, MP-1, MG-1 |
| `schemas/authority_trust_model.yaml` | Trust weights, temporal decay model | MP-1, ME-1, ME-2, MG-3 |
| `schemas/world_state_schema.yaml` | World state versioning, provenance records | MG-2 |

### A.2 SDK Components

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `grounded_agency/state/evidence_store.py` | Evidence anchor capture, tool execution tracking | ME-1, ME-2, MG-1 |
| `grounded_agency/state/checkpoint_tracker.py` | Checkpoint lifecycle, state preservation | MG-1, MG-2 |

### A.3 Safety Enforcement

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `hooks/hooks.json` | PreToolUse checkpoint gate, PostToolUse audit logging | GV-1, ME-2, MG-1 |
| `.claude/audit.log` | Persistent audit trail of skill invocations | ME-2, MG-2 |

### A.4 Validation Tools

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `tools/validate_ontology.py` | Ontology graph validation (orphans, cycles, symmetry) | ME-2 |
| `tools/validate_workflows.py` | Workflow validation against ontology | ME-2 |
| `tools/validate_profiles.py` | Domain profile schema validation | ME-2 |
| `tools/validate_skill_refs.py` | Skill file reference validation | ME-2 |
| `tools/validate_transform_refs.py` | Transform mapping reference validation | ME-2 |
| `tools/validate_yaml_util_sync.py` | YAML utility sync validation | ME-2 |
| `scripts/run_conformance.py` | Conformance test suite | ME-2 |

### A.5 Compliance Documentation

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `docs/compliance/eu-ai-act/risk_classification.md` | EU AI Act risk classification (EUAIA-CLS-001) | GV-1, MP-2 |
| `docs/compliance/eu-ai-act/quality_management_system.md` | QMS mapping to Art. 17 (EUAIA-QMS-001) | GV-1, ME-2 |
| `docs/compliance/eu-ai-act/post_market_monitoring.md` | Post-market monitoring plan (EUAIA-PMM-001) | MG-2, MG-4 |
| `docs/compliance/eu-ai-act/annex_iv_technical_documentation.md` | Technical documentation (EUAIA-TEC-001) | GV-1, MG-4 |
| `docs/compliance/eu-ai-act/notified_body_assessment.md` | Conformity assessment route (EUAIA-NTB-001) | GV-1 |
| `docs/compliance/iso42001/risk_treatment_plan.md` | Risk treatment controls (AIMS-RSK-001) | GV-1, MP-4, MG-1 |
| `docs/compliance/iso42001/competency_framework.md` | Roles and proficiency levels (AIMS-CMP-001) | GV-2, ME-3 |
| `docs/compliance/iso42001/management_review.md` | Management review process (AIMS-MGR-001) | GV-2, MG-4 |
| `docs/compliance/iso42001/nonconformity_procedure.md` | NCR workflow (AIMS-NCR-001) | MG-1, MG-2 |
| `docs/compliance/iso42001/ai_policy_template.md` | AI policy template (AIMS-POL-001) | GV-1, GV-4 |
| `docs/compliance/iso42001/stakeholder_analysis.md` | Stakeholder identification (AIMS-STK-001) | GV-5, MP-5, ME-4 |
| `docs/compliance/iso42001/internal_audit_checklist.md` | Internal audit programme (AIMS-AUD-001) | ME-2, MG-4 |

### A.6 Specification and Methodology

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `spec/WHITEPAPER.md` | Core principles, derivation methodology | GV-1, MP-1 |
| `spec/EDGE_TYPES.md` | Edge type definitions for capability relationships | MP-1, MP-4 |
| `spec/SECURITY.md` | Security specification | MP-4 |
| `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md` | First-principles derivation methodology | MP-1 |
| `docs/GROUNDED_AGENCY.md` | Grounded Agency philosophy and principles | GV-1 |
| `analysis/10-regulatory-compliance.md` | Regulatory compliance analysis | GV-1, cross-cutting |
| `analysis/04-security-scan-findings.md` | STRIDE threat model, security assessment | MP-4 |

### A.7 Skills

| File | Evidence For | NIST Categories |
|------|-------------|----------------|
| `skills/inquire/SKILL.md` | Human escalation capability | GV-5, ME-4, MG-1 |
| `skills/rollback/SKILL.md` | State recovery capability | MG-1, MG-2 |
| `skills/constrain/SKILL.md` | Operational bounds enforcement | MG-2 |
| `skills/invoke/SKILL.md` | External API integration with typed contracts | GV-6, MG-3 |
| `skills/explain/SKILL.md` | Transparency and explainability | GV-1 |
| `skills/critique/SKILL.md` | Self-assessment capability | GV-1, ME-1 |

---

## Document Control

| Field | Value |
|-------|-------|
| **Document ID** | NIST-RMF-001 |
| **Title** | NIST AI RMF 1.0 Profile — Grounded Agency Framework |
| **Version** | 1.0 |
| **Date** | [YYYY-MM-DD] |
| **Author** | [Name, Title] |
| **Reviewer** | [Name, Title] |
| **Approved by** | [Name, Title] |
| **Classification** | Internal |
| **Review cycle** | Annual, or upon significant framework changes |

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | [YYYY-MM-DD] | Initial release — All 4 NIST AI RMF functions, 19 categories, tier assessments, maturity roadmap |

### Review Triggers

This document should be reviewed when:

- The capability ontology changes (new capabilities, modified risk classifications)
- Domain profiles are added or modified
- New compliance documentation is produced
- NIST AI RMF is updated or supplemented (e.g., NIST AI 600-1 Generative AI Profile)
- Organizational context changes significantly

---

*This profile was produced as part of the Agent Capability Standard documentation suite. It reflects the framework state as of version 2.0.0 (January 2026). The NIST AI RMF is a living framework; this profile should be reviewed and updated as the framework evolves.*
