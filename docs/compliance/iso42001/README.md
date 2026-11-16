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
types). A domain profile takes effect where it is applied (Standard 1.2.0 §5.21): a host gives it to a run (the reference executor, `Run.start(profiles=…)` and `WorkflowRunner(profiles=…)`), a safety layer applies it to the calls it covers (the Python adapter, `GroundedAgentConfig(profiles=…)`, and the Standard Agents binding, `groundedTool({profiles})`), or the validator is given it (`tools/validate_workflows.py --profile`). Applied, `block_autonomous`, `require_human`, `require_review`, `auto_approve` and `checkpoint_policy` raise the flags of the steps and calls they name (a person approves each one that `require_human` or `block_autonomous` covers, and no standing mandate does); its grounding policy (`require_grounding`, with `required_anchor_types` as the anchor kinds that count, §5.20) fails a step or call whose output is not grounded (F505), and an output whose confidence is below `minimum_confidence` fails too (F504; the adapter checks the outputs it sees, those of the tools `create_grounded_mcp_server` serves); a profile only tightens, and one with an error is refused. A rule an implementation does not put in force refuses the profile instead of being dropped. Its destination policy (`allowed_destinations`, §4.4.2) is in force beside the host's own: the executor fails a `send` step it does not allow, and the adapter and the Standard Agents binding refuse such a `send` call (F504), before approval; no shipped profile sets one. The plugin hooks apply no profile, and a workflow's `profile` field applies nothing, so a deployment that relies on a profile setting applies the profile in its host or safety layer. Retention periods (`compliance`) remain declarations for the deployer's log storage. See [Status of Domain Profiles](../../domains/README.md#status-of-domain-profiles).
