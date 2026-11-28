# Third-Party AI Risk Procedure — Grounded Agency Framework

This procedure says how a deployer assesses a third-party component before an AI system built on the Grounded Agency framework uses it, and how the deployer monitors that component while the system runs. It closes gap G-03 of the NIST AI RMF profile (GV-6, policies and procedures for third-party AI) and gap G-10 (MG-3, third-party risk monitoring).

**Framework:** NIST AI Risk Management Framework (AI RMF 1.0), GV-6 and MG-3
**Subject Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — The deployer fills in the register (section 7) for each system
**Document ID:** NIST-TPR-001

---

## 1. Purpose and Scope

An agent built on the framework depends on parts that others make: the model, the tools it calls, the sources it reads, and the software it runs on. Each can change without notice, fail, or return content that is wrong or hostile. The framework gives each kind of component a control. This procedure makes the deployer choose the control, record the choice and check it on a schedule.

Roles are the ones in the AI policy template (AIMS-POL-001, section 5). The AI System Owner approves each component; the AI System Operator runs the monitoring; the AI Safety Officer reviews the register.

## 2. Components in Scope

| Kind | Examples | The framework's control |
|------|----------|------------------------|
| Model provider | The language model that plans and calls tools | Every call the model makes goes through the safety layer: checkpoint before `mutate` and `send`, approval, and the audit log |
| Tools | MCP servers, external APIs reached through `invoke` or `send`, Claude Code's own tools | A tool binding record (Standard 1.2.0 §5.18.1) names the tool's capability and its flags. A tool with no binding is unbound and treated as `mutate`, with a checkpoint and approval (§5.18.2). A domain profile's destination policy (`allowed_destinations`) limits where `send` may deliver (F504) |
| Data sources | A system of record, a sensor feed, an observability pipeline, another agent | The trust model gives each source type a weight (`schemas/authority_trust_model.yaml`: `system_of_record` 0.92 down to `human_note` 0.55), and each identity a trust class (`external` 0.35). A domain profile can override the weights. Evidence anchors record which source a claim rests on |
| Software | The plugin, the Python package and its dependencies, the `acs-core` package, the host runtime (Claude Code, a Standard Agents runtime) | Versions are pinned: `constraints.txt`, the npm lock files and the plugin version. Each audit line names the plugin version and the SHA-256 of its hook configuration (`recorded_by`) |
| Shared definitions | Domain profiles, workflow catalogs or skills written by another party | The validators refuse a profile or catalog with an error (`tools/validate_profiles.py`, `tools/validate_workflows.py`); a profile only tightens the ontology's flags |

A component that fits none of these kinds is assessed as a tool and treated as unbound until it has a binding.

## 3. Risk Tier of a Component

Give each component the tier of the highest-risk capability it is used through (Section 2.3 of the NIST AI RMF profile):

| Tier | The component is used through | Assessment depth | Monitoring cadence |
|------|-------------------------------|------------------|--------------------|
| High | `mutate` or `send`, or it is the model provider | Full questionnaire (section 4), approval by the AI System Owner, a tabletop exercise that uses it (NIST-TTX-001) | Weekly signal review, quarterly reassessment |
| Medium | `execute`, `invoke`, `delegate`, `synchronize` or `rollback` | Full questionnaire, approval by the AI System Owner | Monthly signal review, reassessment every six months |
| Low | Any other capability (the Low row of Section 2.3 of the profile), such as `retrieve`, `search` or `persist` | Short questionnaire (items 1, 2, 5 and 7) | Quarterly signal review, annual reassessment |

An unbound tool is High until a binding gives it another capability.

## 4. Assessment Before Use (GV-6)

Answer each item and keep the answers in the register.

1. **Identity.** Who supplies the component, under which contract or licence, and who the contact is for incidents.
2. **Function.** What the system uses it for, and through which capability.
3. **Binding.** Which tool binding record or safety layer covers it, and which flags it carries (checkpoint, approval). For a data source, which trust weight or trust class applies.
4. **Data.** What data the system sends to it, whether that includes personal or secret data, and where the data is processed and kept. The framework redacts known secret patterns from its records, but the deployer decides what may leave.
5. **Change.** How the supplier announces changes, and how the deployment pins a version.
6. **Failure.** What the system does when the component is unavailable or returns an error; whether a checkpoint can undo what it did; what a rollback cannot undo (a sent message, an external write).
7. **Evidence.** What the supplier offers as assurance (certifications, audit reports, a security contact, published incident history).
8. **Exit.** How the system stops using it, as in the decommissioning procedure (NIST-DCM-001, section 3).

The AI System Owner approves, approves with conditions (for example a destination policy or a lower trust weight), or rejects. Record the decision and its date.

## 5. Monitoring While in Use (MG-3)

The AI System Operator reviews these signals at the cadence of section 3:

| Signal | Where it comes from | Action when it appears |
|--------|--------------------|------------------------|
| Calls to the component that failed | Audit log lines for its tool with `status: failed` | Above the threshold the register sets: an L2 warning under the post-market monitoring plan (EUAIA-PMM-001, section 6.1) |
| Calls refused for its output | F504 for confidence below `minimum_confidence`, F505 for an ungrounded output, where a safety layer applies the profile | Review whether the trust weight or the component is still right |
| Sends it was not allowed to make | F504 under a destination policy | Investigate as a possible prompt injection or misuse; L3 if repeated |
| A version change | The plugin version and configuration digest in `recorded_by`; dependency updates; the supplier's notices | Reassess before the new version is used in production |
| A supplier incident or a change of terms | The supplier's notices, public advisories | Reassess at once; consider suspending the component |
| Trust in a source drifting | Conflicts resolved against the source, where the host records them; evidence it supplied that later proved wrong | Lower the weight in the domain profile, or remove the source |

The plugin's audit log records the calls that ran, not the calls its pre-tool-use hook refused (F501, F502, F504); the operator reads those refusals from the session's output.

## 6. Reassessment and Exit

Reassess a component when its cadence is due, when a signal of section 5 calls for it, or when it changes kind or tier. Repeat section 4, compare with the last answers, and record the outcome.

When a component is rejected on reassessment, remove its binding, its credentials and its entries in the domain profile, and follow the decommissioning procedure (NIST-DCM-001) for the parts of the system that depend on it. Record nonconformities under the nonconformity procedure (AIMS-NCR-001).

## 7. Third-Party Register

One row per component:

| Field | Value |
|-------|-------|
| Component and supplier | [Name, version] |
| Kind and capability | [Section 2; capability it is used through] |
| Tier | [High, Medium or Low] |
| Control | [Binding record and flags, trust weight or class, destination policy, pinned version] |
| Data sent | [Categories; personal or secret data: yes or no] |
| Assessment date and decision | [Date; approved, approved with conditions, rejected] |
| Conditions | [For example: `allowed_destinations` set to [...]] |
| Failure threshold | [Failed calls per week that raise an L2 warning] |
| Next review | [Date] |
| Owner | [AI System Operator] |

---

## Document Control

| Field | Value |
|-------|-------|
| **Document ID** | NIST-TPR-001 |
| **Title** | Third-Party AI Risk Procedure — Grounded Agency Framework |
| **Version** | 1.0 |
| **Date** | [YYYY-MM-DD] |
| **Author** | [Name, Title] |
| **Approved by** | [Name, Title] |
| **Classification** | Internal |
| **Review cycle** | Annual, or when the framework adds a kind of component or a control |
