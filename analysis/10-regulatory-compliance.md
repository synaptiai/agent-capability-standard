# Regulatory Compliance Analysis

**Project:** Agent Capability Standard (Grounded Agency)
**Version:** 2.0.0
**Date:** January 2026
**Scope:** Mapping of framework capabilities to AI regulatory requirements, gap analysis, and certification pathway

---

## Table of Contents

1. [AI Regulatory Landscape](#1-ai-regulatory-landscape)
2. [Built-In Compliance Features](#2-built-in-compliance-features)
3. [Domain-Specific Compliance](#3-domain-specific-compliance)
4. [Trust Model Compliance Mapping](#4-trust-model-compliance-mapping)
5. [Safety-by-Construction: Regulatory Alignment](#5-safety-by-construction-regulatory-alignment)
6. [Gap Analysis](#6-gap-analysis)
7. [Certification Pathway](#7-certification-pathway)

---

## 1. AI Regulatory Landscape

The regulatory environment for AI systems has matured substantially. Four primary frameworks define the compliance landscape relevant to agent systems that perform autonomous actions.

### 1.1 EU AI Act (2024)

The EU AI Act establishes a risk-based classification system with tiered obligations:

- **Unacceptable Risk:** Prohibited systems (social scoring, real-time biometric identification in public spaces).
- **High Risk:** Systems in critical domains (healthcare, transportation, employment) requiring conformity assessments, technical documentation, human oversight, and post-market monitoring.
- **Limited Risk:** Transparency obligations (chatbots, emotion recognition) requiring disclosure that users are interacting with AI.
- **Minimal Risk:** No specific obligations, voluntary codes of conduct encouraged.

Key articles relevant to agent systems:
- **Article 9:** Risk management system with continuous iterative process.
- **Article 12:** Record-keeping with automatic logging of events for traceability.
- **Article 13:** Transparency requirements including interpretable outputs and human-understandable explanations.
- **Article 14:** Human oversight mechanisms enabling human intervention, override, and shutdown.
- **Article 15:** Accuracy, robustness, and cybersecurity requirements.

### 1.2 NIST AI Risk Management Framework (AI RMF 1.0)

The NIST AI RMF provides a voluntary, process-oriented framework structured around four core functions:

- **Govern:** Establish policies, roles, and accountability structures for AI risk management. Define organizational risk tolerance and decision-making processes.
- **Map:** Contextualize risks by identifying system use cases, stakeholders, known limitations, and potential impacts. Catalog AI system components and their risk characteristics.
- **Measure:** Quantify risks through metrics, testing, and evaluation. Monitor AI systems for performance degradation, bias, and emergent behavior.
- **Manage:** Allocate resources to respond to identified risks. Implement mitigations, define escalation procedures, and maintain documentation.

The framework emphasizes that AI risk management is not a one-time assessment but a continuous lifecycle activity.

### 1.3 ISO/IEC 42001: AI Management System

ISO/IEC 42001 specifies requirements for establishing, implementing, maintaining, and continually improving an AI Management System (AIMS). Key clauses:

- **Clause 4:** Context of the organization -- understanding internal and external factors affecting AI deployment.
- **Clause 5:** Leadership commitment and AI policy definition.
- **Clause 6:** Planning -- risk assessment, opportunity identification, and AI system objectives.
- **Clause 7:** Support -- resources, competence, awareness, communication, and documented information.
- **Clause 8:** Operational planning and control for AI system lifecycle.
- **Clause 9:** Performance evaluation -- monitoring, measurement, internal audit, and management review.
- **Clause 10:** Continual improvement -- nonconformity handling and corrective actions.

### 1.4 OWASP AI Security and Privacy Guide

The OWASP AI Security and Privacy Guide addresses security best practices specific to AI systems:

- **Data poisoning** and training data integrity controls.
- **Model theft** and intellectual property protection.
- **Prompt injection** and input validation for LLM-based systems.
- **Output validation** to prevent hallucinated or harmful content.
- **Privacy leakage** through model inversion or membership inference attacks.
- **Supply chain security** for ML models and dependencies.

---

## 2. Built-In Compliance Features

The Grounded Agency framework provides structural mechanisms -- not merely documentation -- that map directly to regulatory requirements. This section traces each built-in feature to the regulation it satisfies.

### 2.1 Audit Trails and Provenance

**Framework Implementation:**

The framework implements a multi-layered audit and provenance system:

1. **EvidenceStore** (`grounded_agency/state/evidence_store.py`): Captures every tool execution as an `EvidenceAnchor` with structured metadata including reference strings, evidence kind (`tool_output`, `file`, `command`, `mutation`), ISO-8601 timestamps, and sanitized metadata with injection protection.

2. **Audit Log Hook** (`hooks/hooks.json`): A `PostToolUse` hook on all `Skill` invocations routes through `posttooluse_log_tool.sh`, creating a persistent audit trail in `.claude/audit.log` with timestamps for every skill invocation.

3. **ProvenanceRecord** (defined in `schemas/world_state_schema.yaml`): A first-class schema type that links every claim to:
   - `claim_id`: Unique identifier for the assertion
   - `created_at`: Timestamp of the claim
   - `agent`: The subagent or skill that produced the claim
   - `capability`: The capability ID from the ontology that was exercised
   - `anchors`: Array of evidence anchors supporting the claim
   - `transformations`: Operations applied to derive the claim
   - `assumptions`: Explicit assumptions made during derivation

4. **World State Guarantees**: The world state schema declares that "All entities have stable ids and provenance" and "All relationships carry optional uncertainty and provenance" as structural invariants.

**Regulatory Mapping:**

| Feature | EU AI Act | NIST AI RMF | ISO 42001 |
|---------|-----------|-------------|-----------|
| EvidenceStore with timestamped anchors | Art. 12 (record-keeping) | Measure (quantify through evidence) | Clause 9 (performance evaluation) |
| Audit log of skill invocations | Art. 12 (automatic logging) | Govern (accountability structures) | Clause 9.2 (internal audit) |
| ProvenanceRecord linking claims to agents | Art. 13 (transparency) | Map (identify system components) | Clause 7.5 (documented information) |
| Immutable observations (append-only) | Art. 15 (robustness) | Manage (maintain integrity) | Clause 8 (operational control) |

### 2.2 Risk Classification

**Framework Implementation:**

The capability ontology classifies all 36 atomic capabilities into a three-tier risk model:

| Risk Level | Count | Capabilities | Safety Properties |
|------------|-------|-------------|-------------------|
| **Low** | 26 | retrieve, search, observe, receive, detect, classify, measure, predict, compare, discover, plan, decompose, critique, explain, state, transition, attribute, ground, simulate, generate, transform, integrate, verify, constrain, persist, recall, inquire | `mutation: false`, no special restrictions |
| **Medium** | 7 | execute, rollback, delegate, synchronize, invoke | `requires_approval: true` for some, human review recommended |
| **High** | 3 | mutate, send (+ checkpoint, audit as mutation-flagged but low-risk) | `mutation: true`, `requires_checkpoint: true`, `requires_approval: true` |

Domain profiles further restrict autonomous behavior through `block_autonomous` lists. For example, the healthcare profile blocks autonomous execution of `mutate`, `send`, `execute`, and `delegate`.

**Regulatory Mapping:**

| Framework Feature | EU AI Act Classification |
|-------------------|--------------------------|
| Low-risk capabilities (no mutation) | Minimal risk (no specific obligations) |
| Medium-risk capabilities (requires_approval) | Limited risk (transparency obligations) |
| High-risk capabilities (requires_checkpoint + approval) | High risk (conformity assessment required) |
| `block_autonomous` capability lists | Mechanism to enforce unacceptable-risk prohibitions per domain |

The three-tier model provides a natural mapping to the EU AI Act's risk pyramid, with the additional structural enforcement that high-risk capabilities cannot physically execute without a preceding checkpoint and explicit approval.

### 2.3 Human Oversight (HITL)

**Framework Implementation:**

Multiple mechanisms enforce human-in-the-loop controls:

1. **`require_review` threshold** (profile schema): Configurable minimum risk level at which human review is mandatory. The healthcare profile sets this to `low`, requiring review of virtually all actions.

2. **`require_human` threshold** (profile schema): Configurable minimum risk level at which a human must perform the action. Manufacturing sets this to `high`; healthcare sets it to `low`.

3. **`requires_approval` flag** (ontology): Medium-risk capabilities (`execute`, `delegate`, `synchronize`, `invoke`) carry this flag, structurally requiring approval before invocation.

4. **`inquire` capability** (COORDINATE layer): A dedicated capability for seeking explicit human input, enabling agents to escalate decisions rather than acting autonomously under uncertainty.

5. **`block_autonomous` lists** (domain profiles): Per-domain lists of capabilities that must never run without human intervention. Healthcare blocks `mutate`, `send`, `execute`, and `delegate`.

**Regulatory Mapping:**

| Feature | EU AI Act Art. 14 Requirement | Status |
|---------|-------------------------------|--------|
| Human ability to understand AI system | `explain` + `critique` capabilities | Supported |
| Human ability to interpret outputs | Evidence anchors with confidence scores | Supported |
| Human ability to decide not to use | `require_human` threshold in profiles | Supported |
| Human ability to override or reverse | `rollback` capability + checkpoint system | Supported |
| Human ability to intervene or stop | `constrain` capability + `block_autonomous` | Supported |

### 2.4 Safety Controls

**Framework Implementation:**

The safety control stack operates at multiple levels:

1. **Checkpoint-Before-Mutation Enforcement**: The `PreToolUse` hook (`pretooluse_require_checkpoint.sh`) intercepts all `Write` and `Edit` tool uses and blocks them unless a valid checkpoint marker exists. This is not a policy recommendation -- it is a structural gate enforced at runtime.

2. **Rollback Capability**: The `rollback` capability in the VERIFY layer enables state restoration to any previous checkpoint. The `CheckpointTracker` (`grounded_agency/state/checkpoint_tracker.py`) manages checkpoint lifecycle with cryptographic IDs (128-bit entropy from SHA-256), scope-based validation, automatic expiry (default 30 minutes), and consumption tracking.

3. **Constrain Capability**: The `constrain` capability enforces policy and access control, acting as a runtime policy engine that can block capability execution based on domain rules.

4. **Conflict Prevention**: The ontology defines `conflicts_with` edges that enforce mutual exclusivity at the structural level:
   - `persist` conflicts with `rollback` (cannot persist while rolling back state)
   - `mutate` conflicts with `rollback` (cannot mutate during rollback operation)

5. **Recovery Loop Limits**: Workflow recovery loops are bounded by `max_loops` to prevent infinite retry scenarios (mitigating DoS through recovery exhaustion).

**Regulatory Mapping:**

| Feature | NIST AI RMF Manage Function |
|---------|----------------------------|
| Checkpoint enforcement | Resource allocation for risk response (state preservation) |
| Rollback capability | Incident response and recovery procedures |
| Constrain capability | Policy implementation and enforcement |
| Recovery loop limits | Continuous monitoring for failure modes |
| Conflict prevention edges | Structural controls preventing unsafe combinations |

### 2.5 Transparency

**Framework Implementation:**

1. **`explain` capability** (REASON layer): Generates human-understandable rationale for decisions, satisfying the right to explanation for automated decision-making.

2. **`critique` capability** (REASON layer): Provides self-assessment of decisions, identifying weaknesses, biases, and limitations in the agent's own reasoning.

3. **Evidence anchors with confidence scores**: Every capability output includes `evidence_anchors` (array of references to source data) and `confidence` (numeric score between 0.0 and 1.0), making the basis for decisions inspectable.

4. **Typed uncertainty**: The world state schema distinguishes between epistemic uncertainty (lack of knowledge), aleatoric uncertainty (inherent randomness), and mixed uncertainty, preventing the conflation of "we don't know" with "it's inherently unpredictable."

**Regulatory Mapping:**

| Feature | EU AI Act Art. 13 Requirement | Status |
|---------|-------------------------------|--------|
| Interpretable operations | `explain` capability with structured output | Supported |
| Appropriate level of accuracy/robustness | Confidence scores + typed uncertainty | Supported |
| Known limitations and foreseeable risks | `critique` capability for self-assessment | Supported |
| Human-understandable output format | Evidence anchors linking to source data | Supported |

---

## 3. Domain-Specific Compliance

### 3.1 Healthcare (HIPAA)

The healthcare domain profile (`schemas/profiles/healthcare.yaml`) is explicitly calibrated for clinical decision support with regulatory compliance as a primary design constraint.

**Profile Configuration:**

```yaml
compliance:
  hipaa: required
  fda_clinical_decision_support: advisory_only
  hl7_fhir: recommended
  audit_retention_days: 2555  # 7 years for medical records
```

**HIPAA Alignment:**

| HIPAA Requirement | Framework Feature | Implementation |
|-------------------|-------------------|----------------|
| Access controls | `block_autonomous` blocks `mutate`, `send`, `execute`, `delegate` | All clinical actions require human authorization |
| Audit controls | `audit_retention_days: 2555` (7 years) | Retention policy declared for medical record audit trails |
| Integrity controls | `minimum_confidence: 0.90` for all clinical evidence | Very high confidence threshold prevents uncertain clinical outputs |
| Person/entity authentication | Trust weights distinguish physician orders (0.96) from patient self-reports (0.75) | Source authority calibrated to clinical roles |
| Transmission security | `send` capability requires checkpoint + approval | Clinical communications cannot be sent autonomously |

**Evidence Requirements:**

The healthcare profile mandates five anchor types for all clinical claims:
- `clinical_data_point`: Grounding in actual patient data
- `guideline_reference`: Linkage to published clinical guidelines
- `audit_trail`: Record of the decision-making process
- `clinician_verification`: Human clinician sign-off
- `timestamp`: Temporal anchoring for all events

**Limitations:**

The profile declares `fda_clinical_decision_support: advisory_only`, explicitly positioning the system as a clinical decision support tool rather than an autonomous medical device. This distinction is important for FDA regulatory classification.

### 3.2 Manufacturing (ISO Compliance)

The manufacturing domain profile (`schemas/profiles/manufacturing.yaml`) targets industrial automation, production monitoring, and quality control with ISO compliance considerations.

**Safety-Critical Operations:**

| Manufacturing Requirement | Framework Feature | Implementation |
|--------------------------|-------------------|----------------|
| Equipment safety (OSHA) | `block_autonomous` blocks `mutate` and `send` | No autonomous state changes to equipment |
| Quality management (ISO 9001) | `checkpoint_policy` requires checkpoints before quality decisions | All accept/reject decisions are reversible |
| Sensor calibration (ISO/IEC 17025) | Trust weights: PLC (0.95), SCADA (0.93), hardware sensors (0.92) | Calibrated trust based on sensor type and reliability |
| Process documentation | Evidence policy requires `sensor_reading`, `system_log`, `operator_confirmation`, `timestamp` | Four-anchor evidence chain for all claims |
| Change management | `before_process_change: always` checkpoint policy | All production changes are checkpointed |

**Equipment Lifecycle Tracking:**

The manufacturing profile's trust weight hierarchy (PLC > SCADA > hardware sensors > MES API > ERP) reflects the industrial automation reliability stack, with direct hardware readings receiving the highest trust. The `before_actuator_command: always` checkpoint policy ensures that all machine control commands can be reversed.

**Quality Control Workflows:**

Referenced workflows (`production_line_monitoring`, `quality_control_loop`, `predictive_maintenance`, `supply_chain_sync`) compose capabilities from the ontology with manufacturing-specific evidence requirements and checkpoint policies.

### 3.3 Data Processing (GDPR)

The data analysis profile (`schemas/profiles/data_analysis.yaml`) and the framework's provenance infrastructure provide GDPR-relevant data processing controls.

**GDPR Alignment:**

| GDPR Requirement | Framework Feature | Implementation |
|------------------|-------------------|----------------|
| Lawfulness of processing (Art. 6) | Domain profiles declare processing purpose and scope | Profile `description` and `workflows` fields |
| Purpose limitation (Art. 5(1)(b)) | Capability-specific evidence grounding | `require_grounding` list limits what capabilities can claim |
| Data minimization (Art. 5(1)(c)) | Bounded evidence stores with FIFO eviction | `EvidenceStore(max_anchors=10000)` prevents unbounded data retention |
| Accuracy (Art. 5(1)(d)) | Confidence thresholds (`minimum_confidence: 0.80`) | Data analysis requires high confidence for all decisions |
| Storage limitation (Art. 5(1)(e)) | Checkpoint expiry (default 30 minutes) | Temporary state is automatically cleaned |
| Integrity and confidentiality (Art. 5(1)(f)) | Metadata sanitization in `EvidenceStore` | Injection prevention, size limits, depth limits |
| Right to explanation (Art. 22) | `explain` capability | Automated decision-making is explainable |
| Data lineage tracking | `data_lineage` required anchor type | Evidence policy mandates lineage for all data claims |

**Provenance for Data Lineage:**

The `ProvenanceRecord` type provides a structural mechanism for tracking data lineage:
- `claim_id` uniquely identifies each data assertion
- `agent` and `capability` trace which component produced the data
- `anchors` link back to source data
- `transformations` record what operations were applied
- `assumptions` make implicit dependencies explicit

This provenance chain supports GDPR's data lineage requirements and the right to know how personal data was processed.

---

## 4. Trust Model Compliance Mapping

The authority trust model (`schemas/authority_trust_model.yaml`) provides a formal framework for source evaluation that maps to regulatory requirements for data quality and risk contextualization.

### 4.1 Source Authority Weights

**Default Source Ranking:**

| Source Type | Weight | Regulatory Significance |
|-------------|--------|------------------------|
| `hardware_sensor` | 0.95 | Physical measurement (highest reliability) |
| `system_of_record` | 0.92 | Authoritative database |
| `primary_api` | 0.88 | Live system integration |
| `observability_pipeline` | 0.80 | Derived monitoring data |
| `derived_inference` | 0.65 | AI/ML model outputs |
| `human_note` | 0.55 | Unstructured human input |

This ranking explicitly encodes that AI-derived inferences (`0.65`) are less trusted than direct measurements (`0.95`), addressing a core regulatory concern about AI reliability.

### 4.2 Temporal Decay

The trust model implements temporal decay with configurable parameters:

```yaml
decay_model:
  half_life: P14D        # Trust halves every 14 days
  min_trust: 0.25        # Floor prevents zero-trust collapse
  refresh_events:
    - heartbeat
    - healthcheck
    - authoritative_update
```

**Regulatory Mapping (NIST AI RMF Map Function):**

- **Risk Contextualization:** Temporal decay ensures that stale information is automatically down-weighted, addressing the NIST requirement to contextualize risks based on information freshness.
- **Continuous Monitoring:** Refresh events (`heartbeat`, `healthcheck`) create a continuous monitoring loop that satisfies the NIST requirement for ongoing risk assessment.
- **Information Quality:** The decay model prevents decisions based on outdated evidence, supporting the NIST principle that risk measurement must account for data quality.

### 4.3 Conflict Resolution

The trust model defines a formal conflict resolution function:

```
score = trust_weight(source) * confidence * recency_factor
recency_factor = exp(-age / half_life)
```

With explicit tie-breakers:
1. Prefer authoritative source
2. Prefer high confidence
3. Escalate to human

The third tie-breaker -- escalation to human -- directly implements the EU AI Act's human oversight requirement as a fallback when automated resolution is ambiguous.

### 4.4 Override Controls

```yaml
overrides:
  allow_manual_override: true
  requires_anchors: true
  audit_required: true
```

Manual overrides are permitted but constrained: they require evidence anchors (preventing ungrounded overrides) and audit logging (ensuring accountability). This aligns with the EU AI Act's requirement that human oversight includes the ability to override but with appropriate controls.

---

## 5. Safety-by-Construction: Regulatory Alignment

A distinguishing characteristic of the Grounded Agency framework is that compliance properties are enforced structurally through the architecture rather than through policy documents alone. This section examines how architectural choices produce regulatory alignment.

### 5.1 Structural Enforcement vs. Documentation-Only Compliance

| Compliance Approach | Example | Failure Mode |
|--------------------|---------|--------------|
| **Documentation-only** | Policy stating "create checkpoints before mutations" | Policy can be ignored; no runtime enforcement |
| **Structural enforcement** | `PreToolUse` hook blocks `Write`/`Edit` without checkpoint marker | Mutation physically cannot proceed without checkpoint |

The Grounded Agency framework uses structural enforcement for its most critical safety properties:

- **Checkpoint-before-mutation**: Enforced by `pretooluse_require_checkpoint.sh` hook intercepting `Write` and `Edit` tool calls.
- **Evidence grounding**: Enforced by capability output schemas that require `evidence_anchors` and `confidence` fields.
- **Typed contracts**: Enforced by input/output schema validation at the ontology level.
- **Mutual exclusivity**: Enforced by `conflicts_with` edges in the capability graph.

### 5.2 Type-Safe Workflow Composition

The workflow DSL with design-time type checking prevents unsafe capability combinations:

- **Input/Output Contract Validation**: The workflow validator infers types from capability schemas and checks that producer outputs match consumer inputs. This prevents data type mismatches that could lead to incorrect decisions.
- **Binding Path Verification**: All binding references are statically validated to prevent runtime reference errors.
- **Consumer Contract Checking**: Type mismatches between workflow steps are detected before execution.

This maps to the EU AI Act Article 15 requirement for accuracy and robustness -- type-safe composition prevents a class of errors that could undermine system reliability.

### 5.3 Conflicts_with Edge Enforcement

The ontology defines four `conflicts_with` edges that enforce mutual exclusivity:

| Conflict Pair | Rationale | Safety Impact |
|--------------|-----------|---------------|
| `persist` <-> `rollback` | Cannot persist while rolling back state | Prevents state corruption during recovery |
| `mutate` <-> `rollback` | Cannot mutate during rollback operation | Prevents compounding failures during recovery |

These conflicts are not recommendations; they are structural constraints that the workflow validator enforces at design time. A workflow that attempts to execute `mutate` and `rollback` simultaneously will fail validation.

### 5.4 Evidence Grounding Prevents Ungrounded Claims

The ontology requires that every capability output includes `evidence_anchors` and `confidence`. This structural requirement means:

- Claims without evidence cannot pass output schema validation.
- Confidence scores cannot be omitted, forcing explicit quantification of certainty.
- Downstream capabilities that consume outputs inherit the evidence chain, creating end-to-end provenance.

This directly addresses the EU AI Act's transparency requirements and NIST AI RMF's measurement function -- every decision is traceable to its evidentiary basis.

---

## 6. Gap Analysis

Despite the framework's strong compliance foundations, several gaps remain between current capabilities and full regulatory compliance.

### 6.1 Data Retention Automation

**Current State:** The healthcare profile declares `audit_retention_days: 2555` and the data analysis profile relies on `EvidenceStore` FIFO eviction, but there is no automated retention enforcement. The `retention_policy` mechanism is declarative -- it defines intent but does not implement automated data lifecycle management.

**Gap:** No automated mechanism to:
- Enforce retention periods (auto-delete after N days)
- Archive data to cold storage after retention period
- Generate retention compliance reports
- Handle legal hold exceptions

**Regulatory Impact:** GDPR Article 5(1)(e) (storage limitation), HIPAA retention requirements, EU AI Act Article 12 (record-keeping duration).

### 6.2 Automated Consent Tracking

**Current State:** The provenance system tracks data lineage through `ProvenanceRecord` but does not include a consent management layer. There is no mechanism to record, verify, or withdraw consent for data processing.

**Gap:** No automated mechanism to:
- Record consent grants with purpose and scope
- Track consent withdrawal and propagate to downstream processing
- Maintain consent audit trail
- Enforce processing restrictions based on consent status

**Regulatory Impact:** GDPR Articles 6-7 (lawfulness of processing, conditions for consent).

### 6.3 Real-Time Monitoring and Alerting

**Current State:** The framework logs events through audit hooks and maintains evidence stores, but does not include a real-time monitoring or alerting system. Detection of anomalies relies on post-hoc analysis of audit logs.

**Gap:** No automated mechanism to:
- Monitor capability invocations in real-time
- Alert on suspicious patterns (e.g., unusual mutation frequency)
- Detect drift in model outputs or confidence scores
- Trigger automated incident response

**Regulatory Impact:** EU AI Act Article 9 (post-market monitoring), NIST AI RMF Measure function (continuous monitoring), ISO 42001 Clause 9.1 (monitoring and measurement).

### 6.4 Formal Certification Documentation

**Current State:** The framework provides structural safety properties and domain profiles but does not generate the documentation artifacts required for formal certification.

**Gap:** No automated generation of:
- Technical documentation packages (EU AI Act Annex IV)
- Conformity assessment reports
- Risk assessment documentation in regulatory formats
- Compliance matrices linking requirements to implementations

**Regulatory Impact:** EU AI Act Article 11 (technical documentation), ISO 42001 Clause 7.5 (documented information requirements).

### 6.5 Privacy Impact Assessment Tooling

**Current State:** The framework's evidence grounding and provenance features provide raw data for privacy assessments, but there is no integrated privacy impact assessment (PIA) workflow.

**Gap:** No integrated tooling for:
- Data Protection Impact Assessments (DPIA) per GDPR Article 35
- Privacy risk quantification
- Data flow mapping for privacy analysis
- Automated identification of personal data in evidence stores

**Regulatory Impact:** GDPR Article 35 (data protection impact assessment), NIST Privacy Framework.

### 6.6 Incident Response Automation

**Current State:** The security model (`spec/SECURITY.md`) defines an incident response process (Contain, Assess, Rollback, Investigate, Remediate) but this is a manual procedure. The rollback capability provides state recovery, but orchestration is manual.

**Gap:** No automated mechanism to:
- Detect security incidents from audit log patterns
- Automatically contain affected workflows
- Orchestrate rollback across multiple checkpoints
- Generate incident reports from audit trails
- Track remediation status

**Regulatory Impact:** NIST Cybersecurity Framework (Respond/Recover functions), EU AI Act Article 62 (reporting obligations for serious incidents).

### 6.7 Summary Gap Matrix

| Gap | GDPR | EU AI Act | NIST AI RMF | ISO 42001 | Priority |
|-----|------|-----------|-------------|-----------|----------|
| Data retention automation | Art. 5(1)(e) | Art. 12 | Manage | Clause 8 | High |
| Consent tracking | Art. 6-7 | -- | Govern | Clause 8 | High |
| Real-time monitoring | -- | Art. 9 | Measure | Clause 9.1 | Medium |
| Certification documentation | -- | Art. 11, Annex IV | -- | Clause 7.5 | Medium |
| Privacy impact assessment | Art. 35 | Art. 9 | Map | Clause 6 | Medium |
| Incident response automation | -- | Art. 62 | Manage | Clause 10 | Low |

---

## 7. Certification Pathway

This section outlines practical steps toward formal regulatory certification, leveraging the framework's existing compliance strengths.

### 7.1 SOC 2 Type II Readiness Assessment

**Objective:** Demonstrate that the framework's controls operate effectively over time (typically 6-12 month observation period).

**Trust Services Criteria Mapping:**

| SOC 2 Criteria | Framework Feature | Readiness |
|----------------|-------------------|-----------|
| **Security** (CC6): Logical and physical access | `constrain` capability, `block_autonomous` lists, `requires_approval` flags | Partial -- access control is capability-level, not user-level |
| **Availability** (CC7): System operations | `checkpoint`/`rollback` capabilities, recovery loop limits | Supported -- state recovery is structural |
| **Processing Integrity** (CC8): Complete and accurate processing | Evidence grounding, typed contracts, schema validation | Strong -- structural enforcement of data integrity |
| **Confidentiality** (CC9): Information protection | Metadata sanitization, evidence store size limits | Partial -- no encryption at rest |
| **Privacy** (P1-P8): Personal information lifecycle | ProvenanceRecord, evidence anchors | Partial -- lineage tracking without consent management |

**Recommended Actions:**
1. Implement user-level access controls (identity and authentication layer).
2. Add encryption for audit logs and evidence stores at rest.
3. Build automated evidence collection for SOC 2 audit periods.
4. Engage a SOC 2 auditor for preliminary gap assessment.

### 7.2 ISO 42001 Gap Analysis

**Objective:** Assess readiness for ISO/IEC 42001 AI Management System certification.

**Clause-by-Clause Assessment:**

| Clause | Requirement | Framework Coverage | Gap |
|--------|-------------|-------------------|-----|
| 4 (Context) | Understand organizational context | Domain profiles define context | Needs stakeholder analysis documentation |
| 5 (Leadership) | AI policy and commitment | Framework principles documented | Needs organizational policy template |
| 6 (Planning) | Risk assessment and objectives | Three-tier risk model, trust weights | Needs formal risk treatment plan |
| 7 (Support) | Resources, competence, documentation | CLAUDE.md, tutorials, API docs | Needs competency framework for operators |
| 8 (Operation) | Operational planning and control | Capability ontology, workflow DSL | Strong -- structural operational controls |
| 9 (Evaluation) | Monitoring and audit | EvidenceStore, audit hooks | Needs management review process |
| 10 (Improvement) | Corrective action | Rollback, checkpoint | Needs nonconformity handling procedure |

**Recommended Actions:**
1. Create an AI policy template aligned with ISO 42001 Clause 5.
2. Document a formal risk treatment plan mapping capability risks to mitigations.
3. Establish a management review process for AI system performance.
4. Develop a nonconformity and corrective action procedure.
5. Conduct an internal audit against ISO 42001 requirements.

### 7.3 EU AI Act Conformity Assessment Preparation

**Objective:** Prepare for conformity assessment if the system is deployed in high-risk use cases (healthcare, critical infrastructure).

**Annex IV Technical Documentation Requirements:**

| Documentation Element | Framework Source | Action Needed |
|----------------------|-----------------|---------------|
| General description of the AI system | `docs/GROUNDED_AGENCY.md`, `spec/WHITEPAPER.md` | Reformat for regulatory submission |
| Design specifications and system architecture | Capability ontology, layer architecture | Generate Annex IV-compliant architecture document |
| Development process description | `docs/methodology/` directory | Document development lifecycle formally |
| Monitoring, functioning, and control | Audit hooks, evidence store, checkpoint tracker | Document operational monitoring procedures |
| Risk management system | Three-tier risk model, domain profiles | Create EU AI Act-specific risk management document |
| Post-market monitoring plan | (Gap) | Develop post-market monitoring plan |
| Validation and testing documentation | `tools/validate_*.py`, `tests/` | Document testing methodology and results |

**Recommended Actions:**
1. Classify the system under the EU AI Act risk categories for each deployment domain.
2. Prepare Annex IV technical documentation package.
3. Engage a notified body for conformity assessment (if high-risk classification).
4. Develop a post-market monitoring plan.
5. Establish a quality management system aligned with Article 17.

### 7.4 NIST AI RMF Profile Development

**Objective:** Develop a NIST AI RMF profile that maps the framework's capabilities to the four core functions.

**Profile Structure:**

```
GOVERN
  GV-1: Policies and procedures
    -> Domain profiles (healthcare, manufacturing, data-analysis)
    -> Risk thresholds (auto_approve, require_review, require_human)
    -> Block_autonomous capability lists

  GV-2: Accountability structures
    -> ProvenanceRecord (agent + capability tracking)
    -> Audit hooks (skill invocation logging)

MAP
  MP-1: Context establishment
    -> Domain profiles define operational context
    -> Trust weights calibrate source reliability

  MP-2: Risk identification
    -> Three-tier risk classification (low/medium/high)
    -> Capability mutation flags
    -> Conflicts_with edges identify incompatible operations

MEASURE
  ME-1: Risk measurement
    -> Confidence scores on all capability outputs
    -> Evidence anchor requirements per domain
    -> Minimum confidence thresholds

  ME-2: Continuous monitoring
    -> EvidenceStore tracking tool executions
    -> Checkpoint lifecycle tracking
    -> Temporal decay model for information freshness

MANAGE
  MG-1: Risk response
    -> Checkpoint-before-mutation enforcement
    -> Rollback capability for state recovery
    -> Recovery loop limits (max_loops)

  MG-2: Risk documentation
    -> Audit log of all skill invocations
    -> ProvenanceRecord chain for all claims
    -> World state versioning with parent links
```

**Recommended Actions:**
1. Formalize the NIST AI RMF profile as a standalone document.
2. Map each sub-category to specific framework capabilities with evidence.
3. Identify tier levels (Partial, Risk Informed, Repeatable, Adaptive) for each function.
4. Develop a maturity roadmap from current state to target profile.

---

## Appendix A: Compliance Feature Cross-Reference

| Regulation / Article | Framework Feature | File / Component |
|---------------------|-------------------|------------------|
| EU AI Act Art. 9 (Risk Management) | Three-tier risk model | `schemas/capability_ontology.yaml` (risk field) |
| EU AI Act Art. 12 (Record-Keeping) | EvidenceStore + audit hooks | `grounded_agency/state/evidence_store.py`, `hooks/hooks.json` |
| EU AI Act Art. 13 (Transparency) | `explain` + `critique` capabilities | `skills/explain/SKILL.md`, `skills/critique/SKILL.md` |
| EU AI Act Art. 14 (Human Oversight) | `require_human`, `inquire`, `block_autonomous` | `schemas/profiles/profile_schema.yaml` |
| EU AI Act Art. 15 (Accuracy) | Typed contracts, schema validation | `schemas/capability_ontology.yaml` (input/output schemas) |
| NIST AI RMF Govern | Domain profiles, accountability | `schemas/profiles/*.yaml` |
| NIST AI RMF Map | Trust model, risk context | `schemas/authority_trust_model.yaml` |
| NIST AI RMF Measure | Evidence anchors, confidence scores | `grounded_agency/state/evidence_store.py` |
| NIST AI RMF Manage | Checkpoints, rollback, constrain | `grounded_agency/state/checkpoint_tracker.py` |
| ISO 42001 Clause 8 | Capability ontology, workflow DSL | `schemas/capability_ontology.yaml`, `schemas/workflow_catalog.yaml` |
| ISO 42001 Clause 9 | Audit hooks, evidence store | `hooks/hooks.json`, `grounded_agency/state/evidence_store.py` |
| HIPAA (Access Controls) | `block_autonomous`, `require_human` | `schemas/profiles/healthcare.yaml` |
| HIPAA (Audit Controls) | `audit_retention_days: 2555` | `schemas/profiles/healthcare.yaml` |
| GDPR Art. 5 (Principles) | ProvenanceRecord, evidence policy | `schemas/world_state_schema.yaml` |
| GDPR Art. 22 (Automated Decisions) | `explain` capability | `skills/explain/SKILL.md` |
| GDPR Art. 35 (DPIA) | (Gap -- no PIA tooling) | -- |
| OWASP (Prompt Injection) | Typed contracts, gates, metadata sanitization | `spec/SECURITY.md`, `grounded_agency/state/evidence_store.py` |
| OWASP (Output Validation) | Output schema validation | `schemas/capability_ontology.yaml` (output_schema) |

## Appendix B: Domain Profile Compliance Summary

| Profile | Primary Regulations | min_confidence | block_autonomous | audit_retention |
|---------|--------------------|----------------|------------------|-----------------|
| Healthcare | HIPAA, FDA, HL7 | 0.90 | mutate, send, execute, delegate | 2555 days (7 years) |
| Manufacturing | ISO 9001, OSHA, FDA | 0.85 | mutate, send | Not specified |
| Data Analysis | GDPR, SOX (if financial) | 0.80 | mutate, send | Not specified |
| Personal Assistant | Consumer protection | (default) | (default) | Not specified |

---

*This analysis was produced as part of the Agent Capability Standard documentation suite. It reflects the framework state as of version 2.0.0 (January 2026). Regulatory landscapes evolve; this document should be reviewed and updated as new regulations take effect or existing ones are amended.*
