# Risk Treatment Plan — ISO/IEC 42001 Clause 6 (Planning)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Clause:** 6 — Planning
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Reference implementation — Maps framework risk model to ISO 42001 risk treatment requirements

---

## 1. Purpose

This document fulfills ISO/IEC 42001 Clause 6.1 (Actions to address risks and opportunities) by providing a formal risk treatment plan that maps the framework's three-tier risk classification to specific mitigation controls. It also addresses Clause 6.2 (AI objectives and planning to achieve them).

## 2. Risk Assessment Methodology

### 2.1 Risk Identification

Risks are identified through the capability ontology's structural classification. Every capability in `schemas/capability_ontology.yaml` carries explicit risk metadata:

- `risk`: Classification level (`low`, `medium`, `high`)
- `mutation`: Whether the capability changes persistent state (`true`/`false`)
- `requires_checkpoint`: Whether state preservation is mandatory before execution
- `requires_approval`: Whether human or system approval is required

### 2.2 Risk Analysis

Risk is analyzed along three dimensions:

| Dimension | Assessment Criteria | Source |
|-----------|-------------------|--------|
| **Likelihood** | Frequency of capability invocation in workflows | Workflow catalog usage patterns |
| **Impact** | Mutation potential, external system interaction, reversibility | Ontology flags (`mutation`, `requires_checkpoint`) |
| **Detectability** | Monitoring and audit coverage | Audit hooks, EvidenceStore, evidence policy |

### 2.3 Risk Evaluation

The three-tier model provides a consistent risk evaluation:

| Risk Level | Criteria | Count | Capabilities |
|------------|----------|-------|-------------|
| **Low** | Read-only, analytical, or safety-enabling operations | 29 | retrieve, search, observe, receive, detect, classify, measure, predict, compare, discover, plan, decompose, critique, explain, state, transition, attribute, ground, simulate, generate, transform, integrate, verify, checkpoint, constrain, audit, persist, recall, inquire |
| **Medium** | Indirect state impact, delegation, or execution requiring oversight | 5 | execute, rollback, delegate, synchronize, invoke |
| **High** | Mutation of persistent state; external transmission; checkpoint mandatory | 2 | mutate, send |

**Note:** `checkpoint`, `audit`, and `persist` have `mutation: true` but are classified as low risk because they are safety-enabling operations (creating checkpoints, recording audits, storing data) rather than destructive state changes. They are included in the low-risk count above.

## 3. Risk Treatment Plan — By Risk Tier

### 3.1 Low-Risk Capabilities (29 capabilities)

**Risk Profile:** No mutation, read-only or analytical. Failure mode is primarily incorrect output (wrong classification, failed retrieval, inaccurate prediction).

| Risk | Treatment | Control | Implementation |
|------|-----------|---------|---------------|
| Incorrect output | Accept + Detect | Evidence grounding | Output schemas require `evidence_anchors` and `confidence` |
| Stale data | Mitigate | Temporal decay | Trust model halves trust every 14 days; min trust floor 0.25 |
| Hallucination | Mitigate | Grounding requirement | `ground` capability anchors claims to evidence; `require_grounding` in evidence policy |
| Bias in classification | Detect + Escalate | Critique loop | `critique` capability for self-assessment; `inquire` for human escalation |
| Resource exhaustion | Mitigate | Loop limits | `max_loops` on recovery loops prevents infinite retry |

**Domain Override:** Domain profiles can elevate low-risk capabilities to require review. Healthcare sets `require_review: low`, meaning even low-risk capabilities undergo human review.

**Controls Summary:**
- Structural: Output schema validation (mandatory evidence + confidence)
- Operational: Trust model temporal decay
- Detective: EvidenceStore monitoring
- Domain: Profile-level threshold overrides

### 3.2 Medium-Risk Capabilities (5 capabilities)

**Risk Profile:** These capabilities affect execution flow, delegate authority, or restore state. Failure modes include unauthorized execution, improper delegation, and failed rollback. The `execute` capability carries `requires_approval: true` in the ontology; the remaining medium-risk capabilities are controlled through domain profile `block_autonomous` lists and workflow-level access controls.

| Capability | Specific Risk | Treatment | Control | Implementation |
|-----------|--------------|-----------|---------|---------------|
| `execute` | Unintended code execution | Mitigate | Pre-execution approval | `requires_approval: true` (ontology-enforced); domain profiles can block via `block_autonomous` |
| `rollback` | Data loss from incorrect restoration | Mitigate | Checkpoint validation | Checkpoint scope verification before rollback; `conflicts_with: [persist, mutate]` |
| `delegate` | Authority escalation | Mitigate | Domain blocking + audit | Domain `block_autonomous` lists; delegation logged in audit trail |
| `synchronize` | Consistency violation | Mitigate | Domain blocking + verification | Domain `block_autonomous` lists; state agreement verification |
| `invoke` | Unauthorized workflow execution | Mitigate | Domain blocking + access control | Domain `block_autonomous` lists; workflow-level access control |

**Domain Override:** Manufacturing and healthcare profiles block several medium-risk capabilities from autonomous execution entirely.

**Controls Summary:**
- Structural: `requires_approval: true` on `execute`
- Operational: Domain-specific `block_autonomous` lists
- Detective: Audit hook logging of all skill invocations
- Corrective: `rollback` capability for state recovery (itself gated by approval)

### 3.3 High-Risk Capabilities (2 capabilities)

**Risk Profile:** Direct mutation of persistent state or external transmission. Failure modes include data corruption, unauthorized data exfiltration, irreversible changes, and compliance violations.

| Capability | Specific Risk | Treatment | Control | Implementation |
|-----------|--------------|-----------|---------|---------------|
| `mutate` | Data corruption | Mitigate | Checkpoint + approval | `requires_checkpoint: true`, `requires_approval: true`; `PreToolUse` hook blocks without checkpoint marker |
| `mutate` | Irreversible change | Mitigate | State preservation | Checkpoint created before mutation; `rollback` available within validity window |
| `mutate` | Unauthorized change | Mitigate | Approval gate | Human or system approval required before execution |
| `send` | Data exfiltration | Mitigate | Checkpoint + approval | `requires_checkpoint: true`, `requires_approval: true` |
| `send` | Incorrect transmission | Mitigate | State preservation | Checkpoint enables post-transmission investigation and recovery |
| `send` | Compliance violation | Mitigate | Domain constraints | Healthcare blocks `send` via `block_autonomous`; evidence policy mandates `clinician_verification` |

**Structural Enforcement (not bypassable):**

1. **PreToolUse Hook Gate:** `pretooluse_require_checkpoint.sh` intercepts `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, and `Bash` tool calls. If no valid checkpoint marker exists, the operation is blocked at the tool level — not logged as a warning, but physically prevented from executing.

2. **Conflict Prevention:** The ontology defines `conflicts_with` edges:
   - `mutate` conflicts with `rollback` — cannot mutate during rollback
   - `persist` conflicts with `rollback` — cannot persist during rollback
   These are enforced by the workflow validator at design time.

3. **Domain Profile Blocking:** Domain profiles can add `mutate` and `send` to `block_autonomous`, preventing any autonomous execution regardless of approval status.

**Controls Summary:**
- Structural: PreToolUse hook gate (runtime enforcement), conflict edges (design-time enforcement)
- Operational: Mandatory checkpoint before mutation, dual approval (checkpoint + explicit)
- Detective: Full provenance chain (EvidenceStore + ProvenanceRecord + audit log)
- Corrective: Rollback to pre-mutation checkpoint
- Domain: `block_autonomous` for high-risk domains

## 4. Risk Treatment Options Reference

Per ISO 31000 risk treatment framework:

| Option | Definition | Framework Application |
|--------|-----------|----------------------|
| **Avoid** | Eliminate the activity | `block_autonomous` removes capability from autonomous execution |
| **Mitigate** | Reduce likelihood or impact | Checkpoints, approvals, evidence grounding, confidence thresholds |
| **Transfer** | Share risk with another party | `delegate` to human operator; `inquire` for escalation |
| **Accept** | Acknowledge with monitoring | Low-risk capabilities with evidence grounding and audit |

## 5. Cross-Domain Risk Treatment Matrix

| Domain Profile | Low-Risk Treatment | Medium-Risk Treatment | High-Risk Treatment |
|---------------|-------------------|---------------------|-------------------|
| **Healthcare** | Require review (all capabilities) | Block autonomous (execute, delegate) | Block autonomous (mutate, send); clinician verification required |
| **Manufacturing** | Auto-approve low | Require review | Block autonomous (mutate, send); before_process_change checkpoint |
| **Data Analysis** | Auto-approve low | Require review | Require human approval; data lineage mandatory |
| **Personal Assistant** | Auto-approve low | Auto-approve with logging | Require human approval |

## 6. AI Objectives and Planning (Clause 6.2)

### 6.1 AI Risk Management Objectives

| Objective | Metric | Target | Measurement | Owner |
|-----------|--------|--------|-------------|-------|
| Zero uncontrolled mutations | % of mutations preceded by checkpoint | 100% | Audit log cross-reference | AI Safety Officer |
| Full audit coverage | % of skill invocations logged | 100% | Audit hook verification | AI System Operator |
| Evidence grounding compliance | % of outputs with evidence anchors | 100% | Schema validation results | AI System Owner |
| Confidence threshold adherence | % of decisions meeting domain minimum confidence | 100% | EvidenceStore analysis | Domain Expert |
| Timely human oversight | Mean time to approval for high-risk actions | < SLA | Approval timestamp analysis | AI System Operator |
| Risk treatment effectiveness | Nonconformities per quarter | Decreasing trend | Corrective action records | AI Safety Officer |

### 6.2 Planning to Achieve Objectives

| Action | Resources | Timeline | Responsible | Evidence of Completion |
|--------|-----------|----------|-------------|----------------------|
| Deploy checkpoint enforcement hooks | Engineering team | Per deployment | AI System Operator | Hook configuration verified in production |
| Configure domain profiles | Domain experts + operators | Per domain | AI System Owner | Profile validation passing |
| Establish audit log monitoring | Operations team | [Timeline] | AI System Operator | Monitoring dashboard operational |
| Train operators on AIMS | Training facilitator | [Timeline] | AI Safety Officer | Competency records (Clause 7) |
| Conduct initial risk assessment | AI Safety Officer + domain experts | [Timeline] | AI Safety Officer | This document, reviewed and approved |

## 7. Residual Risk Assessment

After applying all treatments:

| Risk Tier | Inherent Risk | Treatment Effectiveness | Residual Risk | Acceptable? |
|-----------|--------------|------------------------|---------------|-------------|
| Low | Low | High (structural evidence grounding) | Very Low | Yes |
| Medium | Medium | High (approval gates + audit) | Low | Yes |
| High | High | Very High (structural checkpoint + approval + domain blocking) | Low | Yes, with monitoring |

**Residual Risk Acceptance:** The AI System Owner shall formally accept residual risks by signing this risk treatment plan. Residual risks shall be reviewed at each management review cycle (see Clause 9 document).

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-RSK-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |
| Risk Owner | [Name, Title] |

---

*This risk treatment plan maps the Grounded Agency framework's three-tier risk model to ISO/IEC 42001:2023 Clause 6 requirements. All bracketed fields should be adapted to organizational context. The capability-to-risk mappings are derived from `schemas/capability_ontology.yaml` and are current as of framework v2.0.0.*
