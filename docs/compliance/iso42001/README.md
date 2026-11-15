# ISO/IEC 42001 Documents

ISO/IEC 42001:2023 sets the requirements for an AI management system (AIMS).
These seven documents map the Grounded Agency framework to its clauses 4 to
7, 9 and 10. Clause 8 (Operation) has no document of its own: its audit
questions are in the internal audit checklist. Most are templates: fill in the
bracketed fields for your organization before you use them.

| Clause | Document | Doc ID | Purpose |
|--------|----------|--------|---------|
| 4 | [Stakeholder Analysis](stakeholder_analysis.md) | AIMS-CTX-001 | Lists the interested parties and their requirements, and how the framework meets them. |
| 5 | [AI Policy Template](ai_policy_template.md) | AIMS-POL-001 | A policy for AI systems built on the framework, to adapt and adopt. |
| 6 | [Risk Treatment Plan](risk_treatment_plan.md) | AIMS-RSK-001 | Maps the framework's three risk levels to treatment controls. |
| 7 | [Competency Framework](competency_framework.md) | AIMS-CMP-001 | The competence and awareness that people operating the systems need. |
| 9.2 | [Internal Audit Checklist](internal_audit_checklist.md) | AIMS-AUD-001 | Audit questions for every clause, with the evidence to check. |
| 9.3 | [Management Review](management_review.md) | AIMS-MGR-001 | How often management reviews the AIMS, and its inputs and outputs. |
| 10 | [Nonconformity Procedure](nonconformity_procedure.md) | AIMS-NCR-001 | How nonconformities are found, corrected and prevented. |

The [EU AI Act documents](../eu-ai-act/README.md) cross-reference these, and the
[NIST AI RMF profile](../nist-ai-rmf/nist_ai_rmf_profile.md) maps the same
framework to NIST's functions.

These documents cite settings of the domain profiles (`block_autonomous`,
`require_human`, `require_review`, confidence thresholds, required anchor
types). A domain profile is informative data for hosts and workflow authors.
Standard 1.1.0 does not say how one is applied, and no shipped component
loads or selects one: the validator, the executor and the plugin hooks do not
use a profile, and the Python package applies only a profile's
`trust_weights`, when a caller passes them to `grounded_agency/trust.py`. A
profile setting is a control only where the organization's host implements it or
where it is written into a workflow. What is enforced today rests on the
ontology's safety flags, through the validator, the reference executor, the
Python adapter and the plugin hook. See
[Status of Domain Profiles](../../domains/README.md#status-of-domain-profiles).
