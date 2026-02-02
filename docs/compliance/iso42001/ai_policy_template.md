# AI Policy Template — ISO/IEC 42001 Clause 5 (Leadership)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Clause:** 5 — Leadership
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — Adapt to organizational context before use

---

## 1. Purpose

This AI policy establishes the organization's commitment to the responsible development, deployment, and management of AI systems built on the Grounded Agency framework. It fulfills ISO/IEC 42001 Clause 5.2 requirements for an AI policy that is appropriate to the organization's purpose and provides a framework for setting AI objectives.

## 2. Scope

This policy applies to all AI systems that:

- Use the Grounded Agency capability ontology (36 atomic capabilities across 9 cognitive layers)
- Execute workflows composed from the capability catalog
- Interact with external systems, data sources, or end users
- Operate under domain-specific profiles (healthcare, manufacturing, data analysis, etc.)

## 3. AI Principles

The organization commits to the following principles, which are structurally enforced by the Grounded Agency framework:

### 3.1 Grounded Decision-Making

All AI agent actions shall be backed by evidence anchors. No capability output may omit `evidence_anchors` or `confidence` fields. This is enforced at the schema level — ungrounded claims cannot pass output validation.

**Framework enforcement:** Output schemas in `schemas/capability_ontology.yaml` require `evidence_anchors` (array) and `confidence` (0.0–1.0) on every capability output.

### 3.2 Auditability and Transparency

All AI operations shall maintain complete audit trails. Every skill invocation is logged with timestamps. Every claim carries a `ProvenanceRecord` linking it to the agent, capability, and evidence that produced it.

**Framework enforcement:**
- `PostToolUse` hook logs all skill invocations to `.claude/audit.log`
- `EvidenceStore` captures tool executions as `EvidenceAnchor` objects
- `ProvenanceRecord` schema links claims to agents, capabilities, and evidence

### 3.3 Safety Through Structure

High-risk operations shall require checkpoints and approval before execution. This is not a policy recommendation but a structural gate — mutations physically cannot proceed without a preceding checkpoint.

**Framework enforcement:**
- `PreToolUse` hook blocks `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, and `Bash` without checkpoint marker
- High-risk capabilities (`mutate`, `send`) have `requires_checkpoint: true` and `requires_approval: true`
- `execute` capability has `requires_approval: true`
- Remaining medium-risk capabilities (`delegate`, `invoke`, `synchronize`, `rollback`) are controlled through domain profile `block_autonomous` lists

### 3.4 Reversibility

All state-changing operations shall be reversible. The checkpoint/rollback system ensures that any mutation can be undone within the checkpoint validity window.

**Framework enforcement:**
- `CheckpointTracker` manages checkpoint lifecycle with cryptographic IDs
- `rollback` capability in VERIFY layer enables state restoration
- `conflicts_with` edges prevent concurrent mutation and rollback

### 3.5 Human Oversight

AI systems shall operate under appropriate human oversight, calibrated by domain. Operators can configure the level of human involvement from fully autonomous (low-risk operations) to mandatory human execution (high-risk domains like healthcare).

**Framework enforcement:**
- `require_review` threshold in domain profiles
- `require_human` threshold in domain profiles
- `block_autonomous` lists per domain
- `inquire` capability for human escalation

## 4. Leadership Responsibilities (Clause 5.1)

Top management shall:

| Responsibility | Evidence | Cadence |
|---------------|----------|---------|
| Ensure the AI policy is established and maintained | This document, reviewed and signed | Annual review |
| Ensure integration of AIMS into business processes | Domain profiles configured for operational context | Per deployment |
| Ensure resources are available for the AIMS | Competency framework adherence (see Clause 7 document) | Quarterly |
| Communicate the importance of the AIMS | Training records, awareness sessions | Semi-annual |
| Ensure the AIMS achieves its intended outcomes | Management review outputs (see Clause 9 document) | Per review cycle |
| Direct and support persons to contribute to AIMS effectiveness | Role assignments, delegation authority | Ongoing |
| Promote continual improvement | Corrective action records (see Clause 10 document) | Ongoing |

## 5. Roles, Responsibilities, and Authorities (Clause 5.3)

### 5.1 AI System Owner

- Accountable for the AI system's compliance with this policy
- Approves domain profile configurations
- Reviews and approves risk treatment plans
- Authority to halt AI system operations

### 5.2 AI System Operator

- Configures domain profiles (`schemas/profiles/*.yaml`)
- Monitors audit logs and evidence stores
- Responds to checkpoint and approval requests
- Escalates nonconformities per Clause 10 procedure

### 5.3 AI Safety Officer

- Maintains the capability ontology and risk classifications
- Reviews and updates the risk treatment plan (Clause 6)
- Conducts or oversees internal audits
- Reports AIMS performance to top management

### 5.4 Domain Expert

- Validates domain-specific trust weights and confidence thresholds
- Reviews evidence requirements for domain profiles
- Approves workflow configurations for their domain

## 6. AI Objectives

The organization shall establish measurable AI objectives that are:

| Objective Category | Example Metric | Target | Measurement Source |
|-------------------|---------------|--------|-------------------|
| Safety | Checkpoint compliance rate | 100% | Audit log analysis |
| Accuracy | Minimum confidence threshold met | Per domain profile | EvidenceStore confidence scores |
| Transparency | Provenance coverage (claims with full provenance) | 100% | ProvenanceRecord completeness |
| Human oversight | Approval response time for high-risk actions | < 15 minutes | Approval request timestamps |
| Auditability | Audit log completeness | 100% of skill invocations | Audit hook verification |
| Improvement | Nonconformity resolution rate | > 95% within SLA | Corrective action records |

## 7. Communication

This policy shall be:

- Available as a documented artifact within the AIMS
- Communicated to all persons working under the organization's control
- Available to relevant interested parties (stakeholders) as appropriate
- Reviewed at planned intervals (minimum annually) for continuing suitability

## 8. Policy Review

| Review Trigger | Action Required |
|---------------|----------------|
| Annual scheduled review | Full policy review and update |
| Significant change in AI regulations | Assess impact, update policy if required |
| Change in organizational context | Review scope and applicability |
| Nonconformity or incident | Assess root cause, update policy if required |
| New domain profile deployment | Verify policy coverage for new domain |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-POL-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |
| Classification | [Internal / Confidential] |

---

*This template is aligned with ISO/IEC 42001:2023 Clause 5 requirements and grounded in the structural enforcement mechanisms of the Grounded Agency framework. Adapt all bracketed fields to your organizational context before adoption.*
