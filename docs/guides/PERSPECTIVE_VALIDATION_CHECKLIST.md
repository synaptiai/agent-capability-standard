# Perspective Validation Checklist (PVC)

**Canonical location:** `docs/guides/PERSPECTIVE_VALIDATION_CHECKLIST.md`

This checklist complements **type/contract validation** with **socio-technical, security, governance, and operational validation**.

Treat it like a “meta-validator”: it doesn’t replace `tools/validate_workflows.py`; it catches the failure classes that are *not* primarily type errors (e.g., operator confusion, bad incentives, policy drift, irreversibility, data governance).

---

## How to use (rigorous, repeatable)

### Step 0 — Choose the target
Apply PVC to one of:
- a **capability** (node in `schemas/capability_ontology.yaml`)
- a **workflow** (entry in `schemas/workflow_catalog.yaml`)
- a **schema/policy** (`schemas/*.yaml`)
- a **runtime enforcement** component (`hooks/`, SDK adapter)
- a **document** (e.g., `docs/PROJECT_ARTICLE.md`)

### Step 0.5 — Copy the PVC report template

```yaml
target: docs/PROJECT_ARTICLE.md
context:
  domain: general | manufacturing | healthcare | personal_assistant | data_analysis | other
  deployment: local-dev | internal | customer-facing | safety-critical
  risk_tier: low | medium | high
stakeholders:
  - operator/on-call
  - end user
  - security
  - compliance/legal
  - product/engineering owners
assumptions:
  - "What you assume about tools, permissions, data, reversibility"
evidence:
  - "file:...#L"
  - "test:... (how to run)"
  - "benchmark:... (how to run)"
scorecard:
  HF-101: PASS|PARTIAL|FAIL|N/A
  HF-102: PASS|PARTIAL|FAIL|N/A
  HF-103: PASS|PARTIAL|FAIL|N/A
  ORG-201: PASS|PARTIAL|FAIL|N/A
  GOV-202: PASS|PARTIAL|FAIL|N/A
  ECON-301: PASS|PARTIAL|FAIL|N/A
  ECON-302: PASS|PARTIAL|FAIL|N/A
  SEC-401: PASS|PARTIAL|FAIL|N/A
  SEC-402: PASS|PARTIAL|FAIL|N/A
  CTRL-501: PASS|PARTIAL|FAIL|N/A
  ASSUR-601: PASS|PARTIAL|FAIL|N/A
  ASSUR-602: PASS|PARTIAL|FAIL|N/A
  DG-701: PASS|PARTIAL|FAIL|N/A
  ETH-801: PASS|PARTIAL|FAIL|N/A
  ECO-901: PASS|PARTIAL|FAIL|N/A
actions:
  - id: "DOC-001"
    priority: P0|P1|P2
    fix: "What to add/change"
    artifact: "doc|workflow|policy|hook|test|benchmark"
    owner: "role/team"
```

### Step 1 — Create a PVC report
Create a short report with:
- Target: `<name/path>`
- Context: domain + deployment assumptions
- Stakeholders: who is affected
- Scoring table (PASS / PARTIAL / FAIL / N/A) for tests below
- Evidence links: files, config, tests, benchmark outputs, example logs

### Step 2 — Score each test (no hand-waving)
**PASS** requires explicit, checkable evidence (e.g., documented invariant + where it’s enforced; a test/fixture; a policy file; a log format).

**PARTIAL** means the topic is acknowledged but lacks operational detail, measurable criteria, or enforcement points.

**FAIL** means the topic is absent or implied only by aspiration.

### Step 3 — Close the loop
For each FAIL/PARTIAL:
- pick a remediation pattern (listed per test)
- add an artifact: policy config, constraint, gate, hook, fixture, benchmark scenario, or doc section
- re-run the PVC report

---

## Core output: “Perspective Conformance”

You can optionally track maturity by coverage:
- **PVC-L1 (Narrative)**: risks and stakeholders are named (mostly doc-level)
- **PVC-L2 (Procedural)**: decision + escalation paths are defined (workflow/policy-level)
- **PVC-L3 (Enforced)**: invariants are mechanically enforced (validator/gates/hooks)
- **PVC-L4 (Measured)**: benchmarks/tabletops/red-teams prove properties in practice

---

## Tests (questions + acceptance criteria)

Each test is written to be “auditable”: it asks for explicit artifacts and measurable outcomes.

### A) Human Factors & Operator Cognition (HF)

#### HF-101 — Operator Comprehension Under Stress
**Intent**: An on-call engineer can understand “what happened” and “what to do next” quickly.

**Questions**
- What are the top 5 failure modes that will page someone?
- What information will they see first (logs, audit trail, UI)?
- Can they answer: *What changed? Why? With what confidence? How to undo?*

**Acceptance criteria (PASS requires all)**
- A single canonical “incident view” exists (doc or tool output format) containing:
  - last checkpoint id + scope
  - mutations performed (targets + diffs or references)
  - evidence anchors supporting decisions
  - current workflow step + next action (retry/rollback/escalate)
- A “tabletop exercise” recipe exists for at least one high-risk workflow (even if manual).

**Remediation patterns**
- Add an **audit summary schema** (fields above) and ensure hooks/adapter emit it.
- Add a **runbook** section to the workflow doc or domain profile.

#### HF-102 — Contestability & Safe Override
**Intent**: Humans can challenge/override decisions without bypassing safety.

**Questions**
- If a human disagrees with conflict resolution, what is the override mechanism?
- Is override auditable and reversible (where possible)?
- What is the fallback when uncertainty is high?

**Acceptance criteria**
- Override mechanism is explicitly defined (policy + logging + permissions).
- Overrides require evidence anchors and produce an audit record.
- Overrides cannot silently disable checkpoint/rollback requirements.

**Remediation patterns**
- Add `constrain` policy for override authorization + record format.
- Add workflow gate: “if manual override, require audit + checkpoint.”

#### HF-103 — Explanation Fidelity (Anti-Confabulation)
**Intent**: Explanations correspond to actual evidence and decisions.

**Questions**
- How do you prevent “nice story” explanations that don’t match execution?
- Can an explanation be regenerated from evidence anchors?

**Acceptance criteria**
- Explanation pathways reference concrete anchors (tool outputs, file paths, logs).
- There is a benchmark or fixture where explanation faithfulness is evaluated.

**Remediation patterns**
- Add a benchmark scenario (like `benchmarks/scenarios/decision_audit.py`) for your domain.
- Require `audit` step outputs to be referenced by `explain`.

---

### B) Socio-Technical & Governance (ORG/GOV)

#### ORG-201 — Ownership (RACI) for Policies and Weights
**Intent**: Trust weights, constraints, and approvals have explicit owners and change control.

**Questions**
- Who can change trust weights? Who reviews? How are changes rolled out?
- What is the rollback plan for a bad policy update?

**Acceptance criteria**
- Policy owners are specified (team/role), with change process and rollback procedure.
- Versioning strategy exists (semver or explicit policy version fields).

**Remediation patterns**
- Add governance doc section: “Policy ownership + review cadence + incident protocol.”
- Add policy version field and “policy diff” audit entries.

#### GOV-202 — Audit Interpretation & Review Process
**Intent**: Audit logs are not just generated; they are interpretable and reviewed.

**Questions**
- What constitutes an audit anomaly?
- How often are audits reviewed, and by whom?

**Acceptance criteria**
- Audit schema includes: actor, capability, intent/purpose, evidence anchors, outcome.
- Review process exists (even minimal): cadence + trigger conditions + retention.

**Remediation patterns**
- Add “audit anomaly detection” rules (simple heuristics) and an escalation path.

---

### C) Economics & Performance (ECON)

#### ECON-301 — Latency and Cost Budgets
**Intent**: Reliability work has explicit budgets and tradeoffs.

**Questions**
- What is the acceptable latency for validation, checkpoints, evidence collection?
- What is the storage cost of anchors/audits, and retention policy?

**Acceptance criteria**
- A stated latency target for critical workflows (p50/p95) or a “budget table”.
- A stated retention + sampling policy for audits/evidence (by risk level).

**Remediation patterns**
- Add tiered retention: low/medium/high risk workflows keep different evidence detail.
- Add “async evidence capture” option with integrity guarantees.

#### ECON-302 — ROI by Failure Class
**Intent**: Adoption is guided by “which failures pay back first.”

**Questions**
- Which failure classes dominate incidents (type mismatches, state corruption, conflicts)?
- Which PVC items reduce them measurably?

**Acceptance criteria**
- Map top incident categories to capabilities/workflow patterns.
- Include at least one before/after metric claim with a measurement plan.

**Remediation patterns**
- Add a domain-specific benchmark suite that mirrors real incident distribution.

---

### D) Adversarial & Security Engineering (SEC)

#### SEC-401 — Tool Abuse / Privilege Boundaries
**Intent**: Capabilities are treated as permissions with blast-radius control.

**Questions**
- What is the smallest set of tools/capabilities allowed per workflow?
- How do you prevent high-risk capabilities from being invoked indirectly?

**Acceptance criteria**
- Allowed-tools/capabilities are enumerated per workflow (or per deployment profile).
- There is a deny-by-default rule for high-risk mutations in strict mode.
- Sensitive paths/resources are explicitly constrained.

**Remediation patterns**
- Add `constrain` policies for file paths/domains, tool allowlists, and rate limits.

#### SEC-402 — Prompt Injection & Data Poisoning Handling
**Intent**: Structural mitigations are explicit even if content filtering isn’t solved here.

**Questions**
- How do you prevent retrieved content from becoming “instructions”?
- How are sources verified and trust-weighted?

**Acceptance criteria**
- Clear separation of “data” and “instructions” is specified in workflow patterns.
- Trust model + provenance anchors are required for high-impact decisions.

**Remediation patterns**
- Add a “tainted input” gate: require verification before acting on untrusted content.

---

### E) Control Theory & Feedback Loops (CTRL)

#### CTRL-501 — Loop Stability (Monitor/Replan/Retry)
**Intent**: Avoid oscillation, flapping, and infinite recovery loops.

**Questions**
- What prevents “replan every tick” or “retry forever”?
- How do thresholds/hysteresis work?

**Acceptance criteria**
- Explicit bounds exist: max retries, max recovery loops, cooldown windows.
- Thresholds include hysteresis or confidence gating (not single brittle cutoffs).

**Remediation patterns**
- Add `constrain` limits + recovery loop counters to workflow DSL patterns.

---

### F) Formal Assurance & Runtime Verification (ASSUR)

#### ASSUR-601 — Safety Case (Claims → Arguments → Evidence)
**Intent**: “Safe enough” is argued with evidence, not implied.

**Questions**
- What are the top safety claims (e.g., “no mutation without checkpoint”)?
- Where are they enforced (validator + hook + SDK adapter)?

**Acceptance criteria**
- For each safety claim: (a) enforcement point(s), (b) test/fixture, (c) audit evidence.

**Remediation patterns**
- Add a “safety case” section per workflow or per risk tier with links to tests.

#### ASSUR-602 — Runtime Monitors for Invariants
**Intent**: Detect invariant violations in the wild and respond.

**Questions**
- What is the detection mechanism when invariants are violated at runtime?
- What is the default response (halt, rollback, escalate)?

**Acceptance criteria**
- A monitor rule exists for at least one critical invariant.
- Alert + escalation path exists.

**Remediation patterns**
- Add a minimal invariant monitor (log-based or metrics-based) and a runbook.

---

### G) Legal, Privacy, and Data Governance (DG)

#### DG-701 — Evidence Retention, Redaction, and Access Control
**Intent**: Evidence anchors and audit trails don’t become an ungoverned data lake.

**Questions**
- Do evidence anchors capture secrets/PII? How is redaction handled?
- Who can access audit trails? For how long?

**Acceptance criteria**
- Retention policy exists by risk tier and data sensitivity.
- Access controls are documented (roles/scopes) and enforced in implementation.

**Remediation patterns**
- Add an “evidence minimization” policy and a redaction pipeline for anchors.

---

### H) Ethics, Power, and Legitimacy (ETH)

#### ETH-801 — Who Gets to Define “Authority”?
**Intent**: Make normative choices explicit: “trust weights encode power.”

**Questions**
- Who sets trust weights and field authority mappings?
- Who is harmed if a source is systematically deprioritized?

**Acceptance criteria**
- Document the decision process and the appeal/override path.
- Document at least one “harm scenario” and mitigation.

**Remediation patterns**
- Add a “trust model rationale” appendix with stakeholder review notes.

---

### I) Ecosystem & Adoption (ECO)

#### ECO-901 — Migration / Incremental Adoption Path
**Intent**: Teams can adopt the standard without rewriting everything.

**Questions**
- What’s the smallest valuable adoption unit (validator only? hooks only?)?
- How do you interop with existing frameworks/tools?

**Acceptance criteria**
- A staged adoption plan is documented, with clearly scoped milestones.
- Compatibility notes exist for at least one external ecosystem (SDK integration counts).

**Remediation patterns**
- Provide “minimum viable conformance” templates per domain.
