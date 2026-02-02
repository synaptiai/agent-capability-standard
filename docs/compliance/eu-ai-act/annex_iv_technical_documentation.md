# Annex IV Technical Documentation — EU AI Act Article 11

**Regulation:** EU AI Act (Regulation 2024/1689)
**Article:** 11 — Technical Documentation; Annex IV — Technical Documentation for High-Risk AI Systems
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Reference implementation — Demonstrates framework coverage of all 7 Annex IV required elements

---

## 1. Purpose

This document fulfills the technical documentation requirements of EU AI Act Art. 11 and Annex IV for high-risk AI systems built on the Grounded Agency framework. It addresses all 7 elements specified in Annex IV, providing either direct content or cross-references to framework artifacts that contain the required information.

The technical documentation shall be drawn up before the high-risk AI system is placed on the market or put into service (Art. 11(1)) and kept up to date (Art. 11(2)). This document provides the framework-level foundation; deployers must supplement it with deployment-specific information.

## 2. Annex IV Element 1 — General Description of the AI System

### 2.1 System Overview

| Property | Value |
|----------|-------|
| **System Name** | Grounded Agency — Agent Capability Standard |
| **Version** | 2.0.0 |
| **Type** | AI agent capability ontology and safety framework |
| **Intended Purpose** | Provide a formal specification for building safe, auditable, and composable AI agent systems |
| **Developer** | [Provider name and contact] |

### 2.2 Intended Purpose (Annex IV, 1(a))

The Grounded Agency framework is general-purpose AI agent infrastructure. It is not an AI system itself but provides:

1. **Capability ontology** — 36 atomic capabilities with typed I/O contracts, risk metadata, and compositional edges
2. **Domain parameterisation** — 7 domain profiles configuring safety thresholds per deployment context
3. **Workflow composition** — 12 reference workflow patterns composing capabilities into auditable sequences
4. **Safety enforcement** — Runtime hooks, checkpoint gates, and audit logging
5. **SDK integration** — Python adapter for the Claude Agent SDK

AI systems built on this framework inherit its structural safety properties and are classified by their deployment context (see EUAIA-CLS-001).

**Reference documents:**
- `docs/GROUNDED_AGENCY.md` — Full system description and academic paper
- `spec/WHITEPAPER.md` — Formal specification
- `README.md` — Project overview

### 2.3 Interaction with Other Systems (Annex IV, 1(b))

| Integration Point | Description | Interface Type |
|-------------------|-------------|---------------|
| Claude Agent SDK | Python SDK for building AI agents | Programmatic (Python API) |
| Claude Code | CLI tool for AI-assisted development | Plugin system (hooks, skills) |
| MCP (Model Context Protocol) | Tool and resource integration | MCP server protocol |
| Domain-specific APIs | EHR, SCADA, email, calendar, etc. (per profile) | Domain profile configuration |
| External validators | Schema validation, linting, testing | CLI tools (`tools/validate_*.py`) |

### 2.4 Versions of Software and Hardware (Annex IV, 1(c))

| Component | Version | Purpose |
|-----------|---------|---------|
| Capability ontology | 2.0.0 | Core specification |
| Python SDK integration | 0.1.0 | `grounded_agency/` package |
| Python runtime | 3.9+ | Execution environment |
| PyYAML | Latest stable | YAML processing for ontology/profiles |
| Claude Agent SDK | Per deployment | Agent execution runtime |

**Hardware requirements:** The framework is software-only. Hardware requirements are determined by the Claude Agent SDK and deployment environment.

### 2.5 Product Forms (Annex IV, 1(d))

The framework is distributed as:
- Open-source repository (capability ontology, profiles, workflows, tools, documentation)
- Claude Code plugin (hooks, skills)
- Python package (`grounded_agency/` — installable via `pip install -e ".[sdk]"`)

### 2.6 Instructions for Use (Annex IV, 1(e))

| Document | Content |
|----------|---------|
| `README.md` | Installation, quick start, project overview |
| `CLAUDE.md` | Developer instructions, commands, architecture reference |
| `docs/TUTORIAL.md` | Step-by-step tutorial for using the framework |
| `docs/FAQ.md` | Frequently asked questions |
| `docs/GLOSSARY.md` | Term definitions |
| `docs/WORKFLOW_PATTERNS.md` | Workflow composition patterns |

## 3. Annex IV Element 2 — Design Specifications

### 3.1 Architecture (Annex IV, 2(a))

#### 9-Layer Cognitive Architecture

| Layer | Purpose | Capabilities | Count |
|-------|---------|-------------|-------|
| **PERCEIVE** | Information acquisition | retrieve, search, observe, receive | 4 |
| **UNDERSTAND** | Making sense of information | detect, classify, measure, predict, compare, discover | 6 |
| **REASON** | Planning and analysis | plan, decompose, critique, explain | 4 |
| **MODEL** | World representation | state, transition, attribute, ground, simulate | 5 |
| **SYNTHESIZE** | Content creation | generate, transform, integrate | 3 |
| **EXECUTE** | Changing the world | execute, mutate, send | 3 |
| **VERIFY** | Correctness assurance | verify, checkpoint, rollback, constrain, audit | 5 |
| **REMEMBER** | State persistence | persist, recall | 2 |
| **COORDINATE** | Multi-agent interaction | delegate, synchronize, invoke, inquire | 4 |

**Reference:** `schemas/capability_ontology.yaml` — `layers` section

#### Typed Contract System

Every capability defines:
- **Input schema** — Required and optional parameters with types
- **Output schema** — Mandatory fields: `evidence_anchors` (array), `confidence` (number, 0-1)
- **Risk metadata** — `risk` (low/medium/high), `mutation` (boolean), `requires_checkpoint` (boolean), `requires_approval` (boolean)
- **Edges** — Relationships to other capabilities (7 edge types)

**Reference:** `schemas/capability_ontology.yaml` — `nodes` section, `spec/EDGE_TYPES.md`

#### Domain Profile System

Each profile configures:
- `trust_weights` — Source-specific trust levels (0.0-1.0)
- `risk_thresholds` — Autonomy levels (auto_approve, require_review, require_human, block_autonomous)
- `checkpoint_policy` — When to create checkpoints per action type
- `evidence_policy` — Required anchor types, minimum confidence, grounding requirements
- `domain_sources` — Trusted data sources with default trust levels

**Reference:** `schemas/profiles/*.yaml`, `schemas/profiles/profile_schema.yaml`

### 3.2 State Management (Annex IV, 2(a))

| Component | Purpose | Implementation |
|-----------|---------|---------------|
| **CheckpointTracker** | Manages checkpoint lifecycle (create, validate, expire) | `grounded_agency/state/checkpoint_tracker.py` |
| **EvidenceStore** | Collects and stores evidence anchors with provenance | `grounded_agency/state/evidence_store.py` |
| **Audit log** | Append-only record of all skill invocations | `.claude/audit.log` via PostToolUse hook |

### 3.3 Data Flow (Annex IV, 2(b))

```
Input Data → PERCEIVE (retrieve, search, observe, receive)
    │
    ├── Trust weighting (domain profile trust_weights)
    │
    v
Evidence Collection → UNDERSTAND (detect, classify, measure, predict, compare, discover)
    │
    ├── Evidence anchors attached to all outputs
    │
    v
Analysis → REASON (plan, decompose, critique, explain)
    │                           │
    v                           v
World Model → MODEL          Synthesis → SYNTHESIZE
(state, ground, simulate)    (generate, transform, integrate)
    │
    v
Execution → EXECUTE (execute, mutate, send)
    │
    ├── PreToolUse hook: checkpoint validation
    ├── Approval gate (if required)
    │
    v
Verification → VERIFY (verify, checkpoint, rollback, constrain, audit)
    │
    ├── PostToolUse hook: audit log entry
    │
    v
Persistence → REMEMBER (persist, recall)
    │
    v
Coordination → COORDINATE (delegate, synchronize, invoke, inquire)
```

### 3.4 Computational Resources (Annex IV, 2(c))

The framework itself has minimal computational requirements (YAML parsing, Python execution). Computational resource requirements are determined by:
- The underlying LLM (Claude model) used via the Agent SDK
- Domain-specific integrations (e.g., medical imaging processing, sensor data analysis)
- The scale of deployment (number of concurrent agent sessions)

## 4. Annex IV Element 3 — Development Process

### 4.1 Design Methodology (Annex IV, 3(a))

| Phase | Method | Documentation |
|-------|--------|---------------|
| **Capability derivation** | First-principles analysis from cognitive architectures (BDI, ReAct, Claude Skills, MCP) | `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md` |
| **Candidate evaluation** | Systematic evaluation of candidates against atomic, composable, typed, distinct, observable criteria | `docs/methodology/REJECTED_CANDIDATES.md` |
| **Layer assignment** | Cognitive mapping to BDI architecture layers | `schemas/capability_ontology.yaml` — `cognitive_mapping` per layer |
| **Edge derivation** | Analysis of capability dependencies, conflicts, specialisations | `spec/EDGE_TYPES.md` |
| **Profile calibration** | Domain expert consultation for trust weights, risk thresholds | `schemas/profiles/*.yaml` |
| **Workflow validation** | Design-time type inference and coercion checking | `tools/validate_workflows.py` |

### 4.2 Design Decisions (Annex IV, 3(a))

Key design decisions and their rationale:

| Decision | Rationale | Alternative Considered |
|----------|-----------|----------------------|
| 36 atomic capabilities (reduced from 99) | First-principles derivation eliminates redundancy; domain parameterisation replaces variants | 99-capability model with domain-specific variants |
| 9 cognitive layers | Maps to established BDI architecture; provides clear separation of concerns | Flat capability list; 3-layer (perception-reasoning-action) |
| Structural risk enforcement | Hooks physically prevent unsafe actions; not just logged warnings | Convention-based risk management |
| Domain profiles | One ontology serving multiple domains via configuration | Separate ontologies per domain |
| Evidence grounding | Every output carries evidence anchors and confidence | Trust-the-model approach |

**Reference:** `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md`, `docs/methodology/AGENT_ARCHITECTURE_RESEARCH.md`

### 4.3 Extension Governance (Annex IV, 3(b))

New capabilities must follow the 6-step process defined in `CLAUDE.md`:

1. **Update the ontology** — Add capability node with full I/O schemas, edges, layer assignment
2. **Create the skill** — Implement SKILL.md from enhanced template
3. **Update all capability count references** — Across documentation (15+ files)
4. **Validate** — Run ontology, workflow, and profile validators
5. **Update workflow catalog** — If adding workflow patterns
6. **Generate local schema** — `tools/sync_skill_schemas.py`

**Reference:** `CLAUDE.md` Section "Creating New Capabilities", `docs/methodology/EXTENSION_GOVERNANCE.md`

### 4.4 Training, Fine-tuning, and Testing (Annex IV, 3(c))

**Note:** The Grounded Agency framework does not perform training or fine-tuning of AI models. It is a *structural* framework that constrains and composes AI agent behaviour through typed contracts and safety gates. The underlying AI model (e.g., Claude) is trained separately by the model provider (Anthropic).

Training-related responsibilities:
- **Model provider** (Anthropic): Responsible for model training, fine-tuning, bias mitigation, and performance evaluation
- **Framework provider**: Responsible for structural safety (checkpoint enforcement, evidence grounding, audit logging)
- **Deployer**: Responsible for domain-specific configuration (profile selection, trust weight calibration)

## 5. Annex IV Element 4 — Monitoring, Functioning, and Control

### 5.1 Human Oversight Measures (Annex IV, 4(a))

| Measure | Implementation | Enforcement Level |
|---------|---------------|-------------------|
| **Block autonomous execution** | `block_autonomous` lists in domain profiles prevent specified capabilities from running without human authorization | Structural — profile configuration |
| **Require human approval** | `require_human` threshold in domain profiles gates actions at the specified risk level and above | Structural — profile configuration |
| **Require review** | `require_review` threshold triggers human review before action proceeds | Structural — profile configuration |
| **Inquire capability** | `inquire` capability enables agent to escalate to human for guidance | Capability — available in all workflows |
| **Checkpoint gating** | PreToolUse hook blocks mutations (Write, Edit, Bash) without valid checkpoint | Structural — runtime hook enforcement |

#### Human Oversight by Profile

| Profile | Auto-Approve | Require Review | Require Human | Blocked Capabilities |
|---------|-------------|---------------|--------------|---------------------|
| Healthcare | None | Low (all actions) | Low (all actions) | mutate, send, execute, delegate |
| Manufacturing | Low | Medium | High | mutate, send |
| Personal Assistant | Low | Medium | High | send, mutate |
| Data Analysis | Low | Medium | High | mutate, send |
| Vision | Low | Medium | High | mutate, send |
| Audio | Low | Medium | High | mutate, send |
| Multimodal | Low | Medium | High | mutate, send |

**Reference:** `schemas/profiles/*.yaml` — `risk_thresholds` sections

### 5.2 Logging and Monitoring (Annex IV, 4(b))

| Mechanism | What is Logged | How | Reference |
|-----------|---------------|-----|-----------|
| **PostToolUse audit hook** | Every skill invocation: timestamp, skill name, parameters | Automatic via `posttooluse_log_tool.sh` | `hooks/hooks.json` |
| **EvidenceStore** | Evidence anchors, confidence scores, provenance records | Programmatic via SDK adapter | `grounded_agency/state/evidence_store.py` |
| **CheckpointTracker** | Checkpoint creation, validation, expiry events | Programmatic via SDK adapter | `grounded_agency/state/checkpoint_tracker.py` |
| **Validator outputs** | Pass/fail status of all validation checks | CLI execution | `tools/validate_*.py` |

### 5.3 Safety Enforcement (Annex IV, 4(c))

| Enforcement | Mechanism | Bypass Prevention |
|-------------|-----------|-------------------|
| **PreToolUse checkpoint gate** | Shell hook intercepts Write, Edit, MultiEdit, NotebookEdit, Bash tool calls; blocks if no valid checkpoint marker | Hook runs before tool execution; tool cannot proceed without passing |
| **Conflict edges** | `conflicts_with` relationships prevent mutually exclusive capabilities from co-executing | Validated at design time by workflow validator |
| **Domain blocking** | `block_autonomous` capability lists prevent autonomous execution regardless of approval status | Enforced at profile evaluation level |
| **Trust decay** | Source trust halves every 14 days (τ₁/₂ = 14d, floor = 0.25) | Mathematical model; no override mechanism |

**Reference:** `hooks/hooks.json`, `schemas/capability_ontology.yaml` — edges

## 6. Annex IV Element 5 — Risk Management System

### 6.1 Risk Classification (Annex IV, 5(a))

The framework classifies all 36 capabilities into three risk tiers:

| Risk Tier | Count | Capabilities | Ontology Flags |
|-----------|-------|-------------|---------------|
| **Low** | 29 | retrieve, search, observe, receive, detect, classify, measure, predict, compare, discover, plan, decompose, critique, explain, state, transition, attribute, ground, simulate, generate, transform, integrate, verify, checkpoint, constrain, audit, persist, recall, inquire | `risk: low`, `mutation: false` (except checkpoint, audit, persist which have `mutation: true` but are safety-enabling) |
| **Medium** | 5 | execute, rollback, delegate, synchronize, invoke | `risk: medium`, `requires_approval: true` (execute) |
| **High** | 2 | mutate, send | `risk: high`, `mutation: true`, `requires_checkpoint: true`, `requires_approval: true` |

**Reference:** `schemas/capability_ontology.yaml` — risk fields per node, AIMS-RSK-001

### 6.2 Risk Mitigation Controls (Annex IV, 5(b))

| Risk Tier | Control Type | Controls |
|-----------|-------------|----------|
| **Low** | Detective | Evidence grounding (mandatory evidence_anchors + confidence), trust decay, critique loops |
| **Medium** | Preventive + Detective | Approval gates, domain blocking (`block_autonomous`), audit logging |
| **High** | Preventive + Detective + Corrective | Mandatory checkpoint, dual approval (checkpoint + explicit), PreToolUse hook gate, full provenance chain, rollback capability |

**Cross-reference:** EUAIA-CLS-001 (EU AI Act risk mapping), AIMS-RSK-001 (risk treatment plan)

### 6.3 Known Risks and Residual Risk (Annex IV, 5(c))

| Known Risk | Mitigation | Residual Risk | Monitoring |
|-----------|-----------|---------------|-----------|
| Hallucination (ungrounded output) | Evidence grounding requirement; `ground` capability | Reduced but not eliminated — depends on underlying LLM | Evidence coverage KPI (EUAIA-PMM-001) |
| Unauthorized mutation | Checkpoint gate, approval requirement, domain blocking | Very low — structural enforcement prevents bypass | Checkpoint enforcement rate KPI |
| Data exfiltration via `send` | Checkpoint gate, domain blocking, approval requirement | Very low — structural enforcement; domain profiles can fully block | Mutation frequency KPI |
| Stale data influence | Trust decay (τ₁/₂ = 14d), minimum trust floor (0.25) | Low — mathematical decay ensures bounded staleness | Confidence drift KPI |
| Over-reliance on AI output | Human oversight controls, `inquire` escalation, `critique` self-assessment | Medium — depends on deployer implementation of oversight | Human escalation rate KPI |
| Domain profile misconfiguration | Schema validation, profile validator | Low — structural validation catches schema violations | Profile configuration compliance KPI |
| Workflow composition error | Design-time type inference, edge constraint validation | Low — caught at design time before execution | Validator pass rate KPI |

**Reference:** AIMS-RSK-001 (residual risk assessment), EUAIA-PMM-001 (KPI monitoring)

### 6.4 Foreseeable Misuse (Annex IV, 5(d))

| Misuse Scenario | Impact | Framework Mitigation |
|----------------|--------|---------------------|
| Deployer disabling safety hooks | Removes checkpoint enforcement | Hooks are structural; disabling requires deliberate action; audit log detects absence |
| Deployer setting all risk thresholds to `auto_approve` | Removes human oversight | Profile schema enforces valid threshold levels; audit trail shows configuration |
| Using minimal-risk profile for high-risk deployment | Insufficient controls for deployment context | EUAIA-CLS-001 classification guides profile selection; compliance KPIs detect gaps |
| Treating framework outputs as ground truth | Over-reliance without human verification | Evidence anchors and confidence scores provide uncertainty signals; not presented as certainty |

## 7. Annex IV Element 6 — Post-Market Monitoring

### 7.1 Post-Market Monitoring System (Annex IV, 6)

A comprehensive post-market monitoring plan is defined in **EUAIA-PMM-001**, covering:

| Component | Summary | Reference |
|-----------|---------|-----------|
| Data collection plan | Three existing telemetry sources + 8 additional data points | EUAIA-PMM-001 Section 3 |
| Monitoring cadence | Six-tier schedule (continuous → daily → weekly → monthly → quarterly → annual) plus event-triggered | EUAIA-PMM-001 Section 4 |
| Key performance indicators | 12 KPIs across safety, performance, and compliance categories | EUAIA-PMM-001 Section 5 |
| Escalation model | Four levels (Info → Warning → Critical → Incident) with defined response times | EUAIA-PMM-001 Section 6 |
| Serious incident reporting | Art. 62 procedure with 15-day notification timeline | EUAIA-PMM-001 Section 7 |
| Data retention | Domain-specific retention (minimum 10 years for high-risk) | EUAIA-PMM-001 Section 9 |

### 7.2 Integration with AIMS Processes

| AIMS Process | Integration Point |
|-------------|-------------------|
| Corrective action (AIMS-NCR-001) | L2+ escalations trigger corrective action |
| Management review (AIMS-MGR-001) | Quarterly monitoring reports as standing agenda |
| Internal audit (AIMS-AUD-001) | Monitoring effectiveness as audit objective |
| Risk treatment (AIMS-RSK-001) | KPI trends inform risk reassessment |

## 8. Annex IV Element 7 — Testing and Validation

### 8.1 Validation Infrastructure (Annex IV, 7(a))

| Validator | Purpose | What It Checks |
|-----------|---------|---------------|
| `tools/validate_ontology.py` | Ontology graph integrity | Orphan nodes, cycles, edge symmetry, layer membership |
| `tools/validate_workflows.py` | Workflow composition validity | Type compatibility between steps, binding resolution, capability existence |
| `tools/validate_profiles.py` | Domain profile schema compliance | Profile structure against `profile_schema.yaml`, valid capability references |
| `tools/validate_skill_refs.py` | Skill file reference integrity | No phantom file paths in SKILL.md frontmatter |
| `tools/validate_yaml_util_sync.py` | YAML utility consistency | `safe_yaml.py` ↔ `yaml_util.py` synchronization |
| `tools/validate_transform_refs.py` | Transform mapping integrity | No broken `mapping_ref` paths in transform configurations |

### 8.2 Test Coverage (Annex IV, 7(b))

| Test Category | Implementation | Coverage |
|--------------|---------------|----------|
| **SDK integration tests** | `tests/test_sdk_integration.py` | GroundedAgentAdapter, CapabilityRegistry, ToolCapabilityMapper, CheckpointTracker, EvidenceStore |
| **Conformance tests** | `scripts/run_conformance.py` | End-to-end workflow execution against ontology contracts |
| **Unit tests** | `tests/test_*.py` | Individual component validation |
| **Schema validation** | Built into validators | YAML schema compliance for all artifacts |

### 8.3 Test Methodology (Annex IV, 7(c))

| Methodology | Description | Application |
|-------------|-------------|------------|
| **Structural validation** | Verify graph properties (no orphans, no cycles, edge symmetry) | `validate_ontology.py` |
| **Type inference** | Design-time type checking across workflow step bindings | `validate_workflows.py` |
| **Schema conformance** | Validate artifacts against JSON/YAML schemas | `validate_profiles.py`, profile_schema.yaml |
| **Reference integrity** | Verify all file path references resolve to existing files | `validate_skill_refs.py`, `validate_transform_refs.py` |
| **Seeded error detection** | Inject type errors and verify validator catches them | Documented in `docs/GROUNDED_AGENCY.md` evaluation (5 workflows, 51 steps) |
| **Domain coverage** | Verify all profiles exercise relevant capability subset | `validate_workflows.py` workflow-profile cross-validation |

### 8.4 Metrics and Performance (Annex IV, 7(d))

| Metric | Value | Source |
|--------|-------|--------|
| Schema coverage | 100% (all 36 capabilities have typed I/O contracts) | `schemas/capability_ontology.yaml` |
| Validator seeded error detection | 100% (all seeded type errors caught) | `docs/GROUNDED_AGENCY.md` evaluation |
| Workflow validation coverage | 12 reference workflows, all steps type-checked | `schemas/workflow_catalog.yaml` |
| Profile schema compliance | 7/7 profiles pass validation | `tools/validate_profiles.py` |
| Edge constraint coverage | All 7 edge types validated | `tools/validate_ontology.py` |

### 8.5 Known Limitations (Annex IV, 7(e))

| Limitation | Description | Mitigation |
|-----------|-------------|-----------|
| **Structural, not behavioural** | Validators check structure (types, references, schemas) but not runtime ML model behaviour | Deployers must implement behavioural testing for their specific AI model |
| **Trust weights are calibrated, not learned** | Domain profile trust weights are expert-calibrated, not data-driven | Periodic recalibration recommended per EUAIA-PMM-001 |
| **No automated bias detection** | Framework does not include automated fairness/bias testing | Deployers must implement bias testing per Art. 10(2)(f) for their specific use case |
| **Hook bypass possible** | Deployers with system access can disable safety hooks | Audit log detects hook absence; EUAIA-PMM-001 KPI monitoring |
| **LLM-dependent** | Framework safety properties assume a capable underlying LLM | Model capability assessment is the model provider's responsibility |
| **No hardware safety** | Framework is software-only; no hardware fault tolerance | Manufacturing and healthcare deployments must implement hardware safety layers independently |

### 8.6 Foreseeable Conditions (Annex IV, 7(f))

| Condition | Expected Behaviour | Framework Response |
|-----------|-------------------|-------------------|
| Normal operation | All capabilities execute within typed contracts; evidence grounding maintained | Standard audit logging, checkpoint management |
| Network disruption | External source access fails; confidence drops below threshold | Trust decay reduces reliance on stale data; `inquire` capability enables human escalation |
| High load | Multiple concurrent capability invocations | Checkpoint serialisation ensures state consistency; audit log ordering maintained |
| Adversarial input | Malicious data injected via external sources | Trust weights bound adversarial source influence; evidence grounding requirements expose low-confidence outputs |
| Profile misconfiguration | Incorrect risk thresholds or trust weights | Schema validation catches structural errors; monitoring KPIs detect operational anomalies |
| Model degradation | Underlying LLM quality decreases | Confidence score monitoring detects drift; escalation procedures activate |

## 9. Declaration of Conformity Preparation

### 9.1 Art. 47 Requirements

The EU declaration of conformity shall contain the following information:

| Element | Source |
|---------|--------|
| AI system name and type | Section 2.1 of this document |
| Provider name and address | [Provider information] |
| Statement that declaration is issued under sole responsibility of provider | [Provider statement] |
| Reference to harmonised standards or common specifications applied | EUAIA-NTB-001 Section 5 |
| Reference to notified body and certificate (if applicable) | Per EUAIA-NTB-001 assessment route |
| Place and date of issue | [Provider to complete] |
| Name and function of person signing | [Provider to complete] |

### 9.2 EU Database Registration (Art. 49)

Before placing a high-risk AI system on the market, the provider shall register in the EU database established under Art. 71, providing:

| Information | Source Document |
|-------------|----------------|
| Provider details | [Provider to complete] |
| AI system description | Section 2 of this document |
| Risk classification | EUAIA-CLS-001 |
| Conformity assessment route | EUAIA-NTB-001 |
| QMS documentation | EUAIA-QMS-001 |
| Intended purpose and intended deployment | EUAIA-CLS-001 Section 4 |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | EUAIA-TEC-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |
| Documentation Owner | [Name, Title] |

---

*This technical documentation addresses all 7 elements of EU AI Act Annex IV for AI systems built on the Grounded Agency framework. The framework provides structural compliance infrastructure; deployers must supplement with deployment-specific information (model performance metrics, domain-specific bias testing, hardware specifications). All bracketed fields should be adapted to organizational context. Cross-references: EUAIA-CLS-001 (risk classification), EUAIA-PMM-001 (post-market monitoring), EUAIA-NTB-001 (notified body assessment), EUAIA-QMS-001 (quality management system). AIMS documents: AIMS-RSK-001 (risk treatment), AIMS-NCR-001 (corrective actions), AIMS-MGR-001 (management review), AIMS-AUD-001 (internal audit), AIMS-CMP-001 (competency framework).*
