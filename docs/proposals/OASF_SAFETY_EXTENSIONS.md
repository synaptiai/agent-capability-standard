# Proposed Safety Extensions for the Open Agentic Schema Framework (OASF)

**Authors:** Grounded Agency Contributors
**Date:** 2026-01-29
**OASF Target Version:** 0.8.x
**Status:** Draft Proposal

---

## 1. Executive Summary

This proposal recommends four safety extensions to the [Open Agentic Schema Framework (OASF)](https://schema.oasf.outshift.com) that would introduce structural safety guarantees into the framework. The extensions address a critical gap identified in our [comparative analysis](../research/analysis/OASF_comparison.md): OASF currently treats safety and security as a separate skill category (Category 8: Security & Privacy) rather than as cross-cutting concerns that apply to every agentic operation.

The four proposed extensions are:

1. **Evidence Anchoring** -- requiring all skill outputs to include traceable evidence references
2. **Checkpoint Primitive** -- preserving state before high-risk operations
3. **Rollback Primitive** -- enabling recovery when operations fail
4. **Pre-execution Constraints** -- enforcing policies before skill execution

These extensions are designed to be backward-compatible with the existing OASF skill taxonomy. They do not replace any current skills; rather, they add safety infrastructure that strengthens every existing OASF category.

---

## 2. Motivation

### 2.1 The Problem: Safety as an Optional Add-on

OASF v0.8.x organizes agent capabilities into 15 skill categories. Security and privacy considerations appear in Category 8 (Security & Privacy) and Category 13 (Governance & Compliance). This architecture treats safety as something an agent *can* do -- a skill to be invoked when appropriate -- rather than something an agent *must* do as part of every operation.

This design creates three classes of risk:

**Ungrounded claims.** An agent can generate output -- summaries, analyses, recommendations -- without any structural requirement to trace those outputs back to source data. When a RAG pipeline (Category 6) produces an answer, OASF provides no mechanism to verify that the answer is anchored to retrieved documents rather than fabricated from the model's parametric knowledge. The consequence is that hallucinated outputs are structurally indistinguishable from grounded ones.

**Irreversible mutations.** An agent can execute high-risk operations -- deploying infrastructure (Category 12), modifying data pipelines (Category 9), or invoking external APIs (Category 14) -- without any requirement to preserve state beforehand. If a deployment fails halfway through, or an API call triggers unintended consequences, there is no standardized recovery path. Each implementation must build its own recovery mechanism, leading to inconsistent and often absent safety nets.

**Unauditable decisions.** When an agent orchestrates multi-step workflows (Category 10) or makes governance decisions (Category 13), there is no structural requirement to record the evidence chain that led to each decision. Post-hoc auditing becomes impossible when the reasoning trail was never captured.

### 2.2 The Principle: Safety Must Be Structural

The fundamental insight motivating this proposal is that agent safety cannot be achieved through optional skills. Safety must be woven into the execution fabric itself. Consider an analogy: a programming language does not make memory safety "a library you can import." Languages like Rust encode memory safety into the type system. Similarly, agent frameworks should encode safety into their capability contracts.

The Grounded Agency Capability Ontology demonstrates this approach. Most of its 36 atomic capabilities include `evidence_anchors` and `confidence` in their output schemas. Capabilities in the EXECUTE, VERIFY, REMEMBER, and COORDINATE layers omit the `confidence` field since confidence scoring is not applicable to action and mutation capabilities -- these capabilities either succeed or fail, and their outputs are verified through other means (e.g., the `verify` capability). High-risk capabilities structurally require checkpoints before execution. Constraint checking precedes any mutation. These are not conventions to be followed by diligent implementers -- they are contracts enforced by the schema itself.

### 2.3 Real-World Failure Modes

Without structural safety guarantees, agentic systems are vulnerable to the following failure modes:

| Failure Mode | Example | Impact |
|-------------|---------|--------|
| Hallucinated justification | Agent cites a nonexistent policy to justify a compliance decision | Legal liability, regulatory violation |
| Cascading mutation failure | Agent deploys three microservices; second deployment fails; first cannot be rolled back | Production outage, data inconsistency |
| Undetected policy violation | Agent executes a data export without checking data residency constraints | Privacy breach, regulatory fine |
| Opaque orchestration | Multi-agent workflow produces incorrect result; no audit trail exists to diagnose which agent erred | Inability to debug or assign responsibility |

Each of these failure modes is preventable with the structural extensions proposed in this document.

---

## 3. Proposed Extensions

### 3.1 Evidence Anchoring

#### Problem

OASF skill outputs have no standard mechanism for tracing claims back to their source data. An information retrieval skill (Category 6) returns results, but downstream skills that consume those results have no structured way to reference which specific retrieved passages support their outputs.

#### Proposed Solution

Add an `evidence_anchors` array and a `confidence` score to the output schema of every OASF skill.

#### Schema Extension

```yaml
# Proposed addition to OASF skill output schema
evidence_output:
  type: object
  properties:
    evidence_anchors:
      type: array
      description: >
        References to source data that support this output.
        Each anchor identifies a specific piece of evidence.
      items:
        type: object
        required:
          - source
          - type
        properties:
          source:
            type: string
            description: URI, document ID, or reference to source data
          type:
            type: string
            enum:
              - document
              - observation
              - computation
              - external_api
              - human_input
            description: Category of evidence
          excerpt:
            type: string
            description: Relevant excerpt from the source
          location:
            type: object
            description: >
              Location within the source (page number,
              line range, timestamp, etc.)
            properties:
              page:
                type: integer
              line_start:
                type: integer
              line_end:
                type: integer
              timestamp:
                type: string
                format: date-time
    confidence:
      type: number
      minimum: 0
      maximum: 1
      description: >
        Confidence score for this output. Represents the degree
        to which the output is supported by the cited evidence.
        A score of 1.0 means fully supported; 0.0 means no
        supporting evidence found.
```

#### Example: Enhanced Information Retrieval Skill

```yaml
# Before: OASF Information Retrieval (Category 6) output
output:
  answer: "The quarterly revenue increased by 15%."

# After: With evidence anchoring
output:
  answer: "The quarterly revenue increased by 15%."
  evidence_anchors:
    - source: "s3://reports/Q3-2026-financial.pdf"
      type: document
      excerpt: "Revenue grew 15.2% quarter-over-quarter"
      location:
        page: 12
    - source: "db://metrics/revenue/Q3-2026"
      type: computation
      excerpt: "Q3: $4.2M, Q2: $3.65M, delta: +15.07%"
  confidence: 0.92
```

#### Adoption Guidance

- **Phase 1 (recommended):** Add `evidence_anchors` as an optional field to all skill output schemas. Skills that cannot provide evidence should return an empty array with a confidence of 0.0.
- **Phase 2 (target):** Make `evidence_anchors` required for skills in Categories 5 (Analytical), 6 (RAG), 8 (Security & Privacy), 13 (Governance & Compliance), and 15 (Advanced Reasoning & Planning).
- **Phase 3 (aspirational):** Make `evidence_anchors` required for all skill categories.

---

### 3.2 Checkpoint Primitive

#### Problem

OASF skills that modify state -- deploying infrastructure (Category 12), transforming data (Category 9), executing workflows (Category 14) -- have no standardized mechanism for preserving state before the operation begins. If the operation fails partway through, the system is left in an indeterminate state with no clear path to recovery.

#### Proposed Solution

Introduce a `checkpoint` skill that captures a snapshot of relevant state before high-risk operations. This skill would belong to a new Category 16: Safety & Recovery.

#### Schema Definition

```yaml
# Proposed OASF Skill: checkpoint (Category 16 - Safety & Recovery)
skill:
  id: 160101
  name: checkpoint
  category: 16
  subcategory: 1601
  description: >
    Capture a snapshot of the current system state to enable
    recovery if a subsequent operation fails. Creates an
    immutable reference point that can be used by the rollback
    skill to restore state.
  risk: low
  input:
    type: object
    required:
      - scope
    properties:
      scope:
        type: string
        description: >
          Identifies what state to capture. Can be a resource
          path, service identifier, or namespace.
      label:
        type: string
        description: Human-readable name for this checkpoint
      metadata:
        type: object
        description: >
          Additional context about why this checkpoint was
          created and what operation it precedes
        properties:
          reason:
            type: string
          preceding_skill:
            type: string
            description: >
              The skill ID of the operation this checkpoint
              protects
          created_by:
            type: string
            description: Agent or user that requested the checkpoint
      ttl:
        type: string
        description: >
          Time-to-live for this checkpoint. After expiry, the
          checkpoint may be garbage collected. Format: ISO 8601
          duration (e.g., PT1H for 1 hour).
  output:
    type: object
    required:
      - checkpoint_id
      - timestamp
      - evidence_anchors
    properties:
      checkpoint_id:
        type: string
        description: >
          Unique identifier for this checkpoint. Used by the
          rollback skill to reference the restore point.
      timestamp:
        type: string
        format: date-time
        description: When the checkpoint was created
      size_bytes:
        type: integer
        description: Size of the captured state snapshot
      scope:
        type: string
        description: Echoes back the scope that was checkpointed
      evidence_anchors:
        type: array
        description: References to the state data captured
      confidence:
        type: number
        minimum: 0
        maximum: 1
```

> **Note:** Elevating `timestamp` from optional to required is an intentional OASF strengthening -- audit trails require temporal ordering to be meaningful.

#### Integration with Existing Skills

The checkpoint skill should be invoked before any skill classified as high-risk. OASF does not currently assign risk levels to skills, so this proposal also recommends adding a `risk` attribute (see Section 4). Example integration:

```yaml
# Workflow: Safe Infrastructure Deployment
steps:
  - skill: 160101    # checkpoint
    input:
      scope: "kubernetes/namespace/production"
      label: "Pre-deployment checkpoint"
      metadata:
        reason: "Deploying new model version v2.3.1"
        preceding_skill: "120301"
  - skill: 120301    # infrastructure deployment
    input:
      target: "model-serving-v2.3.1"
      environment: "production"
  - skill: 110201    # performance monitoring
    input:
      target: "model-serving-v2.3.1"
      metrics: ["latency_p99", "error_rate"]
```

---

### 3.3 Rollback Primitive

#### Problem

When an OASF skill fails during execution, there is no standardized mechanism to restore the system to its previous state. Each implementation must build ad-hoc recovery logic, leading to inconsistent behavior and unreliable error handling.

#### Proposed Solution

Introduce a `rollback` skill that restores state to a previously created checkpoint. This skill is the complement of `checkpoint` and together they provide atomic operation semantics.

#### Schema Definition

```yaml
# Proposed OASF Skill: rollback (Category 16 - Safety & Recovery)
skill:
  id: 160102
  name: rollback
  category: 16
  subcategory: 1601
  description: >
    Restore system state to a previously created checkpoint.
    Used when a high-risk operation fails or produces
    unacceptable results. Requires a valid checkpoint_id from
    a prior checkpoint skill invocation.
  risk: medium
  input:
    type: object
    required:
      - checkpoint_id
    properties:
      checkpoint_id:
        type: string
        description: >
          The checkpoint to restore to. Must reference a valid,
          non-expired checkpoint created by the checkpoint skill.
      scope:
        type: string
        description: >
          Optional scope restriction. If provided, only the
          specified scope is rolled back. If omitted, the full
          checkpoint scope is restored.
      reason:
        type: string
        description: >
          Why the rollback is being performed. Recorded in the
          audit trail.
  output:
    type: object
    required:
      - restored
      - evidence_anchors
    properties:
      restored:
        type: boolean
        description: Whether the rollback succeeded
      previous_state:
        type: object
        description: Summary of the state before rollback
      restored_state:
        type: object
        description: Summary of the state after rollback
      changes_reverted:
        type: array
        items:
          type: string
        description: >
          List of changes that were undone by this rollback
      evidence_anchors:
        type: array
        description: >
          References to both the checkpoint data and the
          current state that was replaced
      confidence:
        type: number
        minimum: 0
        maximum: 1
```

#### Checkpoint-Rollback Interaction Pattern

The checkpoint and rollback skills form a paired safety mechanism:

```
checkpoint --> high-risk operation --> verify
                                       |
                              pass?--->| continue
                                       |
                              fail?--->| rollback --> audit
```

```yaml
# Workflow: Atomic Data Pipeline Update
steps:
  - skill: 160101    # checkpoint
    output_ref: cp
    input:
      scope: "pipeline/etl-main"
      label: "Pre-schema-migration"
  - skill: 090201    # data transformation (schema migration)
    output_ref: migration
    input:
      pipeline: "etl-main"
      operation: "migrate_schema_v4"
  - skill: 090301    # data quality assessment
    output_ref: quality
    input:
      target: "etl-main"
      metrics: ["completeness", "consistency"]
  # Gate: rollback if quality check fails
  - condition:
      check: "${quality.output.score} < 0.95"
      on_true:
        skill: 160102    # rollback
        input:
          checkpoint_id: "${cp.output.checkpoint_id}"
          reason: "Data quality score below threshold"
      on_false:
        skill: 130401    # audit
        input:
          event: "Schema migration completed successfully"
```

---

### 3.4 Pre-execution Constraints

#### Problem

OASF has governance and compliance skills (Category 13), but these are invoked as standalone skills at the discretion of the workflow designer. There is no mechanism to enforce that policy checks occur before specific operations. An agent can execute a data export without first checking data residency policies, or deploy infrastructure without verifying compliance requirements.

#### Proposed Solution

Introduce a `constrain` skill that checks a set of policy conditions before allowing a subsequent operation to proceed. If any constraint is violated, the operation is blocked and the violation is recorded.

#### Schema Definition

```yaml
# Proposed OASF Skill: constrain (Category 16 - Safety & Recovery)
skill:
  id: 160103
  name: constrain
  category: 16
  subcategory: 1602
  description: >
    Enforce policy constraints before a skill is executed.
    Evaluates a set of conditions against the current context
    and the planned operation. If any constraint is violated,
    the operation is blocked.
  risk: low
  input:
    type: object
    required:
      - target_skill
      - constraints
    properties:
      target_skill:
        type: string
        description: >
          The skill ID that will be executed after constraint
          checking. Used to load skill-specific policies.
      target_input:
        type: object
        description: >
          The planned input to the target skill. Constraints
          are evaluated against this input.
      constraints:
        type: array
        description: >
          Policies to evaluate. Each constraint defines a
          condition and the action to take on violation.
        items:
          type: object
          required:
            - id
            - condition
            - action_on_violation
          properties:
            id:
              type: string
              description: Unique constraint identifier
            description:
              type: string
              description: Human-readable constraint description
            condition:
              type: string
              description: >
                Evaluable condition expression. Returns true
                if the constraint is satisfied.
            action_on_violation:
              type: string
              enum:
                - block
                - warn
                - log
              description: >
                What to do if the constraint is violated.
                'block' prevents execution, 'warn' allows
                execution with a warning, 'log' records the
                violation silently.
            severity:
              type: string
              enum:
                - critical
                - high
                - medium
                - low
              description: Severity of a violation
  output:
    type: object
    required:
      - compliant
      - evidence_anchors
    properties:
      compliant:
        type: boolean
        description: >
          Whether all constraints with action 'block' are
          satisfied. If false, the target skill must not
          be executed.
      violations:
        type: array
        items:
          type: object
          properties:
            constraint_id:
              type: string
            description:
              type: string
            severity:
              type: string
            action_taken:
              type: string
        description: List of constraint violations found
      warnings:
        type: array
        items:
          type: string
        description: >
          Constraints that were violated with action 'warn'
      evidence_anchors:
        type: array
        description: >
          References to the policy documents, configuration,
          or rules that were evaluated
      confidence:
        type: number
        minimum: 0
        maximum: 1
```

> **Note:** The schema refinements for `constrain` are intentional -- OASF safety extensions deliberately strengthen constraint enforcement beyond the base ontology's minimal contract.

#### Example: Constrained Data Export

```yaml
# Workflow: Policy-checked data export
steps:
  - skill: 160103    # constrain
    output_ref: policy_check
    input:
      target_skill: "090201"
      target_input:
        operation: "export"
        destination: "eu-west-1"
        data_classification: "PII"
      constraints:
        - id: "data-residency-001"
          description: "PII data must not leave its origin region"
          condition: "${target_input.destination}.startsWith(${data.origin_region})"
          action_on_violation: block
          severity: critical
        - id: "export-approval-001"
          description: "Bulk exports require manager approval"
          condition: "${context.approvals}.includes('manager')"
          action_on_violation: block
          severity: high
        - id: "export-logging-001"
          description: "All exports should be logged"
          condition: "${context.audit_enabled} == true"
          action_on_violation: warn
          severity: medium
  # Only proceeds if policy_check.output.compliant == true
  - skill: 090201    # data transformation (export)
    condition: "${policy_check.output.compliant} == true"
    input:
      operation: "export"
      destination: "eu-west-1"
```

---

## 4. Implementation Guidance

### 4.1 Add Risk Classification to All OASF Skills

OASF skills do not currently carry a `risk` attribute. This proposal recommends adding a `risk` field to every skill definition:

```yaml
# Proposed addition to OASF skill schema
risk:
  type: string
  enum:
    - low
    - medium
    - high
  description: >
    Risk level of this skill. Determines what safety
    requirements apply:
    - low: No additional requirements
    - medium: Requires approval before execution
    - high: Requires checkpoint before execution and
            verification after execution
```

**Suggested risk classifications for existing OASF categories:**

| Category | Default Risk | Rationale |
|----------|-------------|-----------|
| 1. NLP | low | Read-only text processing |
| 2. Computer Vision | low | Read-only image analysis |
| 3. Audio | low | Read-only audio processing |
| 4. Tabular/Text | low | Read-only data analysis |
| 5. Analytical | low | Computation, no side effects |
| 6. RAG | low | Information retrieval |
| 7. Multi-modal | low | Format conversion |
| 8. Security & Privacy | medium | May affect security posture |
| 9. Data Engineering | medium | Modifies data pipelines |
| 10. Agent Orchestration | medium | Delegates to other agents |
| 11. Evaluation & Monitoring | low | Read-only monitoring |
| 12. DevOps/MLOps | high | Infrastructure changes |
| 13. Governance & Compliance | low | Policy evaluation |
| 14. Tool Interaction | medium | External API calls |
| 15. Advanced Reasoning | low | Computation, no side effects |
| 16. Safety & Recovery (new) | varies | Per-skill risk level |

Individual skills within a category may override the default risk level. For example, "content moderation" within NLP might be classified as `medium` because it affects content visibility.

### 4.2 Require Checkpoint for High-Risk Skills

Any skill with `risk: high` must be preceded by a `checkpoint` invocation in the workflow. Workflow validators should enforce this constraint:

```
RULE: For every skill S where S.risk == "high":
  There MUST exist a checkpoint skill invocation C
  such that C.precedes(S) in the workflow graph.
```

This is analogous to how database systems require `BEGIN TRANSACTION` before operations that modify data. The checkpoint is the agent equivalent of a transaction savepoint.

### 4.3 Add Evidence Anchors to Skill Output Schemas

All skill output schemas should be extended to include the `evidence_output` properties defined in Section 3.1. For backward compatibility:

- **Existing implementations** that do not produce evidence anchors should return an empty array: `evidence_anchors: []`
- **Confidence** should default to `null` when not computable, distinguishing "unknown confidence" from "zero confidence"
- **Schema validators** should accept outputs with or without evidence anchors during the transition period

### 4.4 Create Category 16: Safety & Recovery

The proposed skills form a new OASF category:

```yaml
category:
  id: 16
  name: "Safety & Recovery"
  description: >
    Cross-cutting safety primitives that ensure agent
    operations are recoverable, auditable, and policy-compliant.
    Unlike other categories that define domain-specific skills,
    these skills apply across all domains and should be
    integrated into any workflow that modifies state.
  subcategories:
    1601:
      name: "State Management"
      skills:
        - 160101: checkpoint
        - 160102: rollback
    1602:
      name: "Policy Enforcement"
      skills:
        - 160103: constrain
```

Evidence anchoring is not a separate skill but a schema extension that applies to all existing skills.

### 4.5 Backward Compatibility

These extensions are designed to be fully backward compatible:

| Change | Backward Compatible? | Migration Path |
|--------|---------------------|----------------|
| `evidence_anchors` in output | Yes | Optional field; existing outputs remain valid |
| `confidence` in output | Yes | Optional field; defaults to null |
| `risk` attribute on skills | Yes | New attribute; unset defaults to "low" |
| Category 16 skills | Yes | New skills; existing workflows unaffected |
| Checkpoint-before-high-risk rule | Opt-in | Enforced only when workflow validation is enabled |

Implementations can adopt these extensions incrementally. A framework that only adds evidence anchors -- without checkpoints or constraints -- still gains traceability benefits. Full adoption provides the complete safety guarantee.

---

## 5. Schema Examples

### 5.1 Before and After: RAG Skill with Safety Extensions

**Before** (current OASF RAG skill):

```yaml
skill:
  id: 060101
  name: "information_retrieval"
  category: 6
  subcategory: 601
  input:
    query:
      type: string
      description: "User query"
    sources:
      type: array
      description: "Knowledge base references"
  output:
    answer:
      type: string
      description: "Generated answer"
    sources_used:
      type: array
      description: "References used"
```

**After** (with safety extensions):

```yaml
skill:
  id: 060101
  name: "information_retrieval"
  category: 6
  subcategory: 601
  risk: low
  input:
    query:
      type: string
      description: "User query"
    sources:
      type: array
      description: "Knowledge base references"
  output:
    answer:
      type: string
      description: "Generated answer"
    sources_used:
      type: array
      description: "References used"
    evidence_anchors:
      type: array
      description: "Traceable references to source documents"
      items:
        type: object
        properties:
          source:
            type: string
          type:
            type: string
            enum: [document, observation, computation, external_api, human_input]
          excerpt:
            type: string
          location:
            type: object
    confidence:
      type: number
      minimum: 0
      maximum: 1
      description: "Degree to which the answer is supported by cited evidence"
```

### 5.2 Before and After: Infrastructure Deployment with Safety

**Before** (current OASF DevOps skill):

```yaml
# Workflow: Deploy model
steps:
  - skill: 120301    # infrastructure deployment
    input:
      target: "model-serving-v2.3.1"
      environment: "production"
```

**After** (with checkpoint, constraint, and rollback):

```yaml
# Workflow: Safe model deployment
steps:
  # Step 1: Check deployment policies
  - skill: 160103    # constrain
    output_ref: policy
    input:
      target_skill: "120301"
      constraints:
        - id: "deploy-window-001"
          description: "Deployments only during maintenance window"
          condition: "${time.hour} >= 2 AND ${time.hour} <= 6"
          action_on_violation: block
          severity: critical
        - id: "deploy-approval-001"
          description: "Production deployments require SRE approval"
          condition: "${context.approvals}.includes('sre')"
          action_on_violation: block
          severity: high

  # Step 2: Create checkpoint (only if policy passes)
  - skill: 160101    # checkpoint
    condition: "${policy.output.compliant} == true"
    output_ref: cp
    input:
      scope: "kubernetes/namespace/production"
      label: "Pre-deployment: model-serving-v2.3.1"

  # Step 3: Deploy
  - skill: 120301    # infrastructure deployment
    output_ref: deploy
    input:
      target: "model-serving-v2.3.1"
      environment: "production"

  # Step 4: Verify
  - skill: 110201    # performance monitoring
    output_ref: health
    input:
      target: "model-serving-v2.3.1"
      metrics: ["latency_p99", "error_rate", "success_rate"]
      threshold:
        error_rate: 0.01
        latency_p99: 200

  # Step 5: Rollback if unhealthy
  - condition:
      check: "${health.output.passed} == false"
      on_true:
        skill: 160102    # rollback
        input:
          checkpoint_id: "${cp.output.checkpoint_id}"
          reason: "Post-deployment health check failed"
```

### 5.3 Category 16 Skills Summary

```yaml
category_16:
  name: "Safety & Recovery"
  skills:
    160101:
      name: checkpoint
      risk: low
      purpose: "Save state for potential recovery"
      required_before: "Any skill with risk: high"
    160102:
      name: rollback
      risk: medium
      purpose: "Restore to a previous checkpoint"
      paired_with: checkpoint
    160103:
      name: constrain
      risk: low
      purpose: "Enforce policies before execution"
      applies_to: "Any skill, especially risk: medium and high"
```

---

## 6. Benefits

### 6.1 Structural Safety Guarantees

By embedding safety into the schema rather than leaving it as an optional skill, OASF would guarantee that:

- Every output can be traced to its source evidence
- High-risk operations always have a recovery path
- Policy violations are detected before they cause damage
- The safety mechanism is consistent across all implementations

### 6.2 Auditability and Compliance

Evidence anchors and constraint checking create a natural audit trail. When a regulator asks "why did the agent make this decision?", the evidence chain provides a concrete answer:

1. The `constrain` output shows which policies were checked
2. The `evidence_anchors` on each step show what data informed each decision
3. The `checkpoint` records show what state existed before each change
4. The `confidence` scores show how certain the agent was at each step

This is directly relevant to emerging AI governance requirements, including the EU AI Act's transparency obligations and the NIST AI Risk Management Framework's traceability recommendations.

### 6.3 Reduced Risk of Irreversible Failures

The checkpoint-rollback pair transforms high-risk operations from irreversible to recoverable. This is especially valuable for:

- **Infrastructure operations** (Category 12) where failed deployments currently require manual intervention
- **Data engineering** (Category 9) where pipeline failures can corrupt data
- **Multi-agent orchestration** (Category 10) where cascading failures can propagate across agents

### 6.4 Industry Alignment

These extensions align OASF with safety patterns already established in:

- **Database systems:** Transactions, savepoints, and rollback
- **Version control:** Commits, branches, and reverts
- **Cloud infrastructure:** Snapshots, blue-green deployments, and canary releases
- **Distributed systems:** Two-phase commit and saga patterns

Adopting these patterns at the agent framework level standardizes safety across the ecosystem rather than leaving it to individual implementations.

---

## 7. References

1. **Grounded Agency Capability Ontology v2.0.0** -- The capability ontology that defines the safety primitives proposed in this document.
   - Repository: [agent-capability-standard](https://github.com/synaptiai/agent-capability-standard)
   - Core ontology: `schemas/capability_ontology.yaml`

2. **Open Agentic Schema Framework (OASF)** -- The target framework for these proposed extensions.
   - Website: [https://schema.oasf.outshift.com](https://schema.oasf.outshift.com)
   - Organization: Cisco/Outshift

3. **OASF Comparison Analysis** -- The detailed gap analysis that identified the safety primitives missing from OASF.
   - Document: [`docs/research/analysis/OASF_comparison.md`](../research/analysis/OASF_comparison.md)

4. **Grounded Agency Design Philosophy** -- The principles underlying the safety model proposed here.
   - Document: [`docs/GROUNDED_AGENCY.md`](../GROUNDED_AGENCY.md)

5. **EU AI Act** -- European regulation requiring transparency and accountability in AI systems.
   - Reference: Regulation (EU) 2024/1689

6. **NIST AI Risk Management Framework** -- US framework for managing AI risks, emphasizing traceability and governance.
   - Reference: NIST AI 100-1

---

*This proposal was prepared by the Grounded Agency contributors as a constructive contribution to the OASF community. We welcome feedback and collaboration.*
