# Internal Audit Checklist — ISO/IEC 42001 (All 10 Clauses)

**Standard:** ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Ready for use — Adapt evidence sources to organizational context

---

## Audit Information

| Field | Value |
|-------|-------|
| Audit ID | [AUDIT-YYYY-NNN] |
| Audit Date(s) | [YYYY-MM-DD] |
| Auditor(s) | [Name(s)] |
| Audit Scope | [Full AIMS / Specific clauses / Specific domain] |
| Audit Criteria | ISO/IEC 42001:2023, AI Policy (AIMS-POL-001), domain profiles |

### Finding Classification

| Classification | Definition |
|---------------|-----------|
| **C** (Conforming) | Requirement fully met with evidence |
| **OFI** (Opportunity for Improvement) | Conforming but could be enhanced |
| **Minor NC** | Isolated deviation; limited impact on AIMS effectiveness |
| **Major NC** | Systematic failure or deviation that undermines AIMS effectiveness |
| **N/A** | Not applicable (with documented justification) |

---

## Clause 1–3: Scope, Normative References, Terms and Definitions

These clauses are informational and do not contain auditable requirements. However, verify foundational understanding:

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 1.1 | Is the scope of the AIMS clearly documented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder analysis (AIMS-CTX-001) Section 6 | |
| 1.2 | Does the scope consider internal/external issues (Clause 4.1)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | | |
| 1.3 | Does the scope consider stakeholder requirements (Clause 4.2)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | | |
| 1.4 | Are scope exclusions justified? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | | |

---

## Clause 4: Context of the Organization

### 4.1 Understanding the Organization and Its Context

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 4.1.1 | Are internal issues relevant to the AIMS identified? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder analysis Section 2.1 | |
| 4.1.2 | Are external issues relevant to the AIMS identified? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder analysis Section 2.2 | |
| 4.1.3 | Is the regulatory landscape documented (EU AI Act, NIST, ISO 42001)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | `analysis/10-regulatory-compliance.md` | |
| 4.1.4 | Are domain-specific regulatory requirements identified? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Domain profile `compliance` fields | |

### 4.2 Understanding the Needs and Expectations of Interested Parties

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 4.2.1 | Are interested parties (stakeholders) identified? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder register (AIMS-CTX-001 Section 3) | |
| 4.2.2 | Are stakeholder needs and expectations documented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder register columns | |
| 4.2.3 | Are stakeholder requirements tracked and reviewed? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Communication plan (AIMS-CTX-001 Section 5) | |

### 4.3 Determining the Scope of the AIMS

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 4.3.1 | Is the AIMS scope documented and available? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder analysis Section 6 | |
| 4.3.2 | Does the scope consider external/internal issues? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | | |
| 4.3.3 | Does the scope consider stakeholder requirements? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | | |
| 4.3.4 | Are scope boundaries clearly defined (technology, data, organizational)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | | |

### 4.4 AI Management System

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 4.4.1 | Is the AIMS established, implemented, maintained, and improved? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Compliance document suite | |
| 4.4.2 | Are AIMS processes and their interactions determined? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Capability ontology edges, workflow catalog | |
| 4.4.3 | Are criteria and methods for process control determined? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Domain profiles, hooks | |

---

## Clause 5: Leadership

### 5.1 Leadership and Commitment

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 5.1.1 | Does top management demonstrate commitment to the AIMS? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy approval, resource allocation, review participation | |
| 5.1.2 | Is the AI policy compatible with the organization's strategic direction? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AI policy (AIMS-POL-001) | |
| 5.1.3 | Are AIMS requirements integrated into business processes? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Domain profiles in operational use | |
| 5.1.4 | Are adequate resources available for the AIMS? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Budget, staffing, tooling records | |
| 5.1.5 | Is the importance of the AIMS communicated? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Communication records, awareness training | |

### 5.2 AI Policy

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 5.2.1 | Is an AI policy established and documented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AI policy template (AIMS-POL-001) | |
| 5.2.2 | Is the policy appropriate to the organization's purpose? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy Section 2 (Scope) | |
| 5.2.3 | Does the policy include commitment to satisfy requirements? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy Section 3 (Principles) | |
| 5.2.4 | Does the policy include commitment to continual improvement? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy Section 6 (Objectives) | |
| 5.2.5 | Is the policy communicated within the organization? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy Section 7 (Communication) | |
| 5.2.6 | Is the policy available to interested parties as appropriate? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Distribution records | |
| 5.2.7 | Is the policy reviewed at planned intervals? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy Section 8 (Review), review records | |

### 5.3 Organizational Roles, Responsibilities, and Authorities

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 5.3.1 | Are AIMS roles defined (Owner, Operator, Safety Officer, Domain Expert)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AI policy Section 5 | |
| 5.3.2 | Are responsibilities and authorities assigned and communicated? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Role descriptions, org chart | |
| 5.3.3 | Is there accountability for AIMS conformity? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Named AI System Owner | |
| 5.3.4 | Is there accountability for reporting AIMS performance to top management? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AI Safety Officer role | |

---

## Clause 6: Planning

### 6.1 Actions to Address Risks and Opportunities

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 6.1.1 | Are risks and opportunities related to AI identified? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan (AIMS-RSK-001) | |
| 6.1.2 | Is the risk assessment methodology documented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Section 2 | |
| 6.1.3 | Are risks classified using the three-tier model? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Ontology `risk` field on all 36 capabilities | |
| 6.1.4 | Are risk treatments defined for all three tiers (low/medium/high)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Sections 3.1–3.3 | |
| 6.1.5 | Are structural controls implemented for high-risk capabilities? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | PreToolUse hook, `requires_checkpoint`, `requires_approval` | Verify hook is active |
| 6.1.6 | Are domain-specific risk treatments documented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Section 5, domain profiles | |
| 6.1.7 | Is residual risk assessed and accepted? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Section 7 | |

### 6.2 AI Objectives and Planning to Achieve Them

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 6.2.1 | Are measurable AI objectives established? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Section 6 | |
| 6.2.2 | Are objectives consistent with the AI policy? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Cross-reference policy principles with objectives | |
| 6.2.3 | Are objectives monitored and measured? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Management review dashboard | |
| 6.2.4 | Is there a plan to achieve each objective (what, who, when, how)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Section 6.2 | |

---

## Clause 7: Support

### 7.1 Resources

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 7.1.1 | Are resources needed for the AIMS determined and provided? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Budget records, staffing | |
| 7.1.2 | Are infrastructure requirements met (tools, environments)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Claude Code plugin, MCP servers, SDK | |

### 7.2 Competence

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 7.2.1 | Are competency requirements defined for AIMS roles? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Competency framework (AIMS-CMP-001) | |
| 7.2.2 | Are persons competent based on education, training, or experience? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Competency records | |
| 7.2.3 | Are competency gaps identified and addressed? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Gap analysis records, training plans | |
| 7.2.4 | Is evidence of competence retained? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Training records, certifications | |

### 7.3 Awareness

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 7.3.1 | Are persons aware of the AI policy? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Awareness training records | |
| 7.3.2 | Are persons aware of their contribution to AIMS effectiveness? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Role briefings | |
| 7.3.3 | Are persons aware of implications of not conforming? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Policy acknowledgments | |

### 7.4 Communication

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 7.4.1 | Is internal/external communication planned (what, when, to whom, how)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder communication plan | |
| 7.4.2 | Are communication records maintained? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Meeting records, correspondence | |

### 7.5 Documented Information

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 7.5.1 | Does the AIMS include required documented information? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Compliance document suite (all AIMS-* documents) | |
| 7.5.2 | Is documented information properly identified (ID, version, date)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Document control tables | |
| 7.5.3 | Is documented information reviewed and approved? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Approval signatures | |
| 7.5.4 | Is documented information available when and where needed? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Repository access | |
| 7.5.5 | Is documented information protected from unintended alteration? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Git version control, branch protection | |

---

## Clause 8: Operation

### 8.1 Operational Planning and Control

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 8.1.1 | Are operational processes planned, implemented, and controlled? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Capability ontology, workflow catalog | Framework strength |
| 8.1.2 | Are criteria for processes established (I/O schemas, risk levels)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Ontology `input_schema`/`output_schema` per capability | |
| 8.1.3 | Are operational controls implemented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Hooks, checkpoints, approval gates | |
| 8.1.4 | Are planned changes controlled? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Checkpoint-before-mutation, PR review process | |
| 8.1.5 | Are outsourced processes controlled? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | `delegate` and `invoke` capabilities with approval | |

### 8.2 AI Risk Assessment (Operational)

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 8.2.1 | Is AI risk assessment performed at defined intervals? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan review cycle | |
| 8.2.2 | Is risk assessment documented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan (AIMS-RSK-001) | |
| 8.2.3 | Are risk assessment results used for treatment planning? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Risk treatment plan Sections 3–5 | |

### 8.3 AI Risk Treatment (Operational)

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 8.3.1 | Is the risk treatment plan implemented? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Hooks active, profiles configured, approvals flowing | |
| 8.3.2 | Are structural controls functioning? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Test: attempt Write without checkpoint (must be blocked) | Critical test |
| 8.3.3 | Are domain profile controls applied correctly? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | `block_autonomous` enforcement, confidence thresholds | |

### 8.4 AI System Lifecycle

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 8.4.1 | Is the AI system lifecycle defined? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Development, deployment, monitoring phases | |
| 8.4.2 | Are AI system changes managed through a controlled process? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Git version control, extension governance, PR reviews | |
| 8.4.3 | Are AI system inputs/outputs defined (capability I/O schemas)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | 36 capabilities each with `input_schema` and `output_schema` | |

---

## Clause 9: Performance Evaluation

### 9.1 Monitoring, Measurement, Analysis, and Evaluation

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 9.1.1 | Is monitoring and measurement planned (what, how, when)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Management review process Section 2 | |
| 9.1.2 | Are monitoring results analyzed and evaluated? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Performance dashboard, trend analysis | |
| 9.1.3 | Are safety metrics tracked (checkpoint compliance, audit coverage)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Audit logs, hook intercept records | |
| 9.1.4 | Are quality metrics tracked (evidence grounding, confidence)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | EvidenceStore analysis | |
| 9.1.5 | Are operational metrics tracked (approval times, rollbacks)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Operational records | |

### 9.2 Internal Audit

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 9.2.1 | Are internal audits conducted at planned intervals? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Audit schedule, this checklist | |
| 9.2.2 | Does the audit program consider importance and previous results? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Audit plan documentation | |
| 9.2.3 | Are audit criteria, scope, frequency, and methods defined? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Audit information table (above) | |
| 9.2.4 | Are auditors objective and impartial? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Auditor independence declaration | |
| 9.2.5 | Are audit results reported to relevant management? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Management review input #3c | |
| 9.2.6 | Are corrective actions taken for audit findings? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | NCR records per nonconformity procedure | |

### 9.3 Management Review

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 9.3.1 | Does management review the AIMS at planned intervals? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Review schedule, meeting records | |
| 9.3.2 | Does the review consider all required inputs? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Management review process Section 3.2 | |
| 9.3.3 | – Status of actions from previous reviews? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Action register | |
| 9.3.4 | – Changes in external/internal issues? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Updated stakeholder analysis | |
| 9.3.5 | – AIMS performance (NCRs, metrics, audits)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Performance dashboard | |
| 9.3.6 | – Feedback from interested parties? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Stakeholder communication records | |
| 9.3.7 | – Risk assessment results? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Updated risk treatment plan | |
| 9.3.8 | – Opportunities for improvement? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Improvement register | |
| 9.3.9 | Does the review produce required outputs? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Management review process Section 3.4 | |
| 9.3.10 | – Improvement opportunities? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Improvement register | |
| 9.3.11 | – Need for changes to the AIMS? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Change decisions documented | |
| 9.3.12 | – Resource needs? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Resource allocation decisions | |
| 9.3.13 | Are review records retained? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Meeting minutes, action register, decision log | |

---

## Clause 10: Improvement

### 10.1 Nonconformity and Corrective Action

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 10.1.1 | Is there a procedure for handling nonconformities? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Nonconformity procedure (AIMS-NCR-001) | |
| 10.1.2 | Does the procedure cover identification? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AIMS-NCR-001 Section 4 | |
| 10.1.3 | Does the procedure cover evaluation (severity classification)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AIMS-NCR-001 Section 4.2 | |
| 10.1.4 | Does the procedure cover corrective action (root cause + prevention)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AIMS-NCR-001 Sections 5.3–5.4 | |
| 10.1.5 | Does the procedure cover follow-up (effectiveness verification)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AIMS-NCR-001 Section 5.5 | |
| 10.1.6 | Are nonconformity records maintained? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | NCR register | |
| 10.1.7 | Are corrective actions effective (recurrence check)? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Verification records, recurrence analysis | |
| 10.1.8 | Is root cause analysis performed for major/critical NCRs? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | RCA records in NCRs | |

### 10.2 Continual Improvement

| # | Check | Finding | Evidence | Notes |
|---|-------|---------|----------|-------|
| 10.2.1 | Is the AIMS continually improved? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Improvement register, trend data | |
| 10.2.2 | Are improvement opportunities identified from multiple sources? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | AIMS-NCR-001 Section 6.1 | |
| 10.2.3 | Are improvements tracked and measured? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Improvement register | |
| 10.2.4 | Is there evidence of improvement over time? | [ ] C [ ] OFI [ ] Minor [ ] Major [ ] N/A | Trend analysis (declining NCRs, improving metrics) | |

---

## Framework-Specific Verification Tests

These are Grounded Agency-specific checks beyond standard ISO 42001 requirements:

| # | Test | Expected Result | Actual Result | Pass/Fail |
|---|------|----------------|---------------|-----------|
| F.1 | Attempt `Write` tool without checkpoint marker | Blocked by PreToolUse hook | | |
| F.2 | Invoke a skill and verify audit log entry | Entry in `.claude/audit.log` with timestamp | | |
| F.3 | Check `mutate` capability flags in ontology | `risk: high`, `mutation: true`, `requires_checkpoint: true`, `requires_approval: true` | | |
| F.4 | Check `send` capability flags in ontology | `risk: high`, `mutation: true`, `requires_checkpoint: true`, `requires_approval: true` | | |
| F.5 | Run workflow validator on all workflows | All pass type checking | | |
| F.6 | Verify healthcare profile `block_autonomous` | Contains `mutate`, `send`, `execute`, `delegate` | | |
| F.7 | Verify `conflicts_with` edges enforced | `mutate` ↔ `rollback`, `persist` ↔ `rollback` | | |
| F.8 | Run `python tools/validate_ontology.py` | No orphans, no cycles, symmetry intact | | |
| F.9 | Run `python tools/validate_profiles.py` | All profiles valid against schema | | |
| F.10 | Run `python tools/validate_workflows.py` | All workflows valid | | |
| F.11 | Verify `execute` capability has `requires_approval: true` | Flag present in ontology | | |
| F.12 | Verify medium-risk capabilities are controlled by domain profiles | `block_autonomous` lists include relevant capabilities per domain | | |

---

## Audit Summary

### Findings Summary

| Clause | Conforming | OFI | Minor NC | Major NC | N/A |
|--------|-----------|-----|----------|----------|-----|
| 4 (Context) | | | | | |
| 5 (Leadership) | | | | | |
| 6 (Planning) | | | | | |
| 7 (Support) | | | | | |
| 8 (Operation) | | | | | |
| 9 (Evaluation) | | | | | |
| 10 (Improvement) | | | | | |
| **Totals** | | | | | |

### Overall Assessment

| Assessment Area | Rating |
|----------------|--------|
| AIMS documentation completeness | [ ] Adequate [ ] Gaps identified |
| Structural safety controls | [ ] Functioning [ ] Deficiencies found |
| Risk treatment implementation | [ ] Effective [ ] Improvements needed |
| Management commitment evidence | [ ] Demonstrated [ ] Insufficient |
| Continual improvement evidence | [ ] Demonstrated [ ] Insufficient |

### Auditor Recommendation

[ ] AIMS conforms to ISO/IEC 42001:2023 requirements
[ ] AIMS substantially conforms with minor nonconformities to address
[ ] AIMS has significant gaps requiring major corrective action
[ ] AIMS is not yet ready for certification audit

### Next Steps

| Action | Owner | Deadline |
|--------|-------|----------|
| | | |
| | | |
| | | |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | AIMS-AUD-001 |
| Version | 1.0 |
| Template Effective Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |

---

*This internal audit checklist covers all 10 ISO/IEC 42001:2023 clauses plus framework-specific verification tests. Use this for internal audit planning and execution. Findings should be documented per the nonconformity procedure (AIMS-NCR-001) where applicable.*
