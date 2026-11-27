# AI System Decommissioning Procedure — Grounded Agency Framework

This procedure says how to take an AI system built on the Grounded Agency framework out of service, and how the framework itself retires a capability, a workflow or a domain profile. It closes gap G-01 of the NIST AI RMF profile (GV-1.7, processes for decommissioning).

**Framework:** NIST AI Risk Management Framework (AI RMF 1.0), GV-1.7
**Subject Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — The deployer fills in the bracketed fields for each system
**Document ID:** NIST-DCM-001

---

## 1. Purpose and Scope

A system built on the framework leaves records behind: an audit log signed with a key, checkpoint commits that can still be restored, evidence and memory stores, and settings that grant the agent tools. Decommissioning ends the system's ability to act, keeps the records for as long as the deployment's retention rules require, and then disposes of them on purpose rather than by neglect.

The procedure has two parts:

| Part | Applies to | Owner |
|------|-----------|-------|
| Section 3 to 7: retiring a deployment | One AI system that runs on the framework: the Claude Code plugin, the Python adapter (`GroundedAgentAdapter`), the reference executor (`WorkflowRunner`) or the Standard Agents binding | The deployer's AI System Owner |
| Section 8: retiring part of the framework | A capability, workflow, domain profile or Standard version that this repository publishes | The repository's maintainers |

Roles are the ones in the AI policy template (AIMS-POL-001, section 5): AI System Owner, AI System Operator and AI Safety Officer.

## 2. Triggers

Start this procedure when any of these holds:

- The AI System Owner decides to retire the system or replace it.
- An L4 incident under the post-market monitoring plan (EUAIA-PMM-001, section 6.1) leads to withdrawal of the system.
- The system's domain profile, model provider or hosting contract ends and no replacement is approved.
- A review under the third-party risk procedure (NIST-TPR-001) finds a component the system depends on that can no longer be used and cannot be replaced.

Record the trigger, the date and the approver in the decommissioning record (section 9).

## 3. Stop the System From Acting

Do these steps in order, and record the time of each one.

1. **Announce the stop.** Tell the system's users and the parties that receive its output (the stakeholder register, AIMS-STK-001) when the system stops and what replaces it.
2. **Stop new runs.** Remove the system's triggers and schedules, and stop any host that starts runs (`WorkflowRunner`, a Standard Agents runtime). A run that is in progress either finishes or is cancelled; record which.
3. **Revoke the agent's tools.** Remove the MCP servers, API credentials and tokens the system was given. Rotate any credential that was shared with another system.
4. **Remove the plugin or the adapter.** For the Claude Code plugin, uninstall it, or remove its hooks from the settings that load them. For the Python adapter, remove `GroundedAgentAdapter` from the host. Removing the safety layer while the agent can still run would let calls run ungated, so step 3 comes first.
5. **Check that nothing still acts.** Confirm that no new line is written to the audit log after the stop time, and that no scheduled task names the system.

## 4. Preserve the Records

The records answer what the system did and how to undo it. Preserve them before anything is deleted.

| Record | Where it is | What to do |
|--------|------------|------------|
| Plugin audit log | `.claude/audit.log`, its head `.claude/audit.head`, and the head's anchor `<git dir>/acs/audit.head` | Verify it (step 1 below), then copy all three to the archive |
| Audit key | `~/.config/acs/audit.key`, or the `AUDIT_HMAC_KEY` the deployment set | Keep it, under the archive's access control, for as long as the log is kept; without it the log cannot be verified |
| Checkpoint markers | `.claude/checkpoints/used/` and `.claude/checkpoints/ended/` | Copy to the archive; each used marker's name `<checkpoint_id>.<call_id>.<suffix>` links a call to its restore point |
| Checkpoint commits | The commits named in `<git dir>/acs/checkpoints/commits/` | Keep them while a restore may still be needed (section 5) |
| SDK checkpoint state | The `CheckpointTracker` directory (`.checkpoints/` by default) | Copy to the archive |
| Evidence and memory stores | The paths the deployment gave the evidence store and the memory store | Copy to the archive, then apply the deployment's redaction rules |
| Run records and traces | Where the host keeps them | Copy to the archive |
| Configuration | The domain profiles applied, the workflow catalogs, the settings files and the plugin version | Copy to the archive, so that the system's behaviour can be reconstructed |

Steps:

1. **Verify the audit log** before archiving it: `python tools/verify_audit_log.py --log-file .claude/audit.log`. A failure is an incident: follow the nonconformity procedure (AIMS-NCR-001) before going on, and record the result.
2. **Keep a copy of the head where the agent could not write it**, such as another machine. Later, `tools/verify_audit_log.py --witness <copy>` shows whether the archived log was cut.
3. **Record checksums** (SHA-256) of every archived file in the decommissioning record.

## 5. Keep a Way Back

For a period the AI System Owner sets (default: [30] days), keep the means to restore the last state the system left:

- Do not run `git gc --prune=now` or delete the repository while a checkpoint commit may still be restored. An unreferenced commit stays restorable only until git prunes it.
- A checkpoint commit is restored as the rollback skill restores it: `git restore --source=<commit> --worktree -- <paths>`, and `git restore --source=<commit>^2 --staged -- <paths>` for the index.
- After the period, record that the way back is closed.

## 6. Retain and Dispose

1. **Retain.** Keep the archive for the retention period the deployment requires. A domain profile's `compliance` member can declare one (`audit_retention_days`), but the framework does not enforce it: the deployer's storage does.
2. **Dispose.** At the end of the period, delete the archive, the audit key and the checkpoint commits, and record the date, the method and who approved it.
3. **Personal data.** Where the records hold personal data, apply the deployer's data protection rules, which may require earlier deletion than the retention period.

## 7. Close Out

The AI System Owner signs the decommissioning record when:

- section 3 shows no action after the stop time;
- section 4 lists every record with its checksum and a passing verification;
- the way back of section 5 is open or recorded as closed;
- the risk treatment plan (AIMS-RSK-001) and the deployer's AI system inventory no longer list the system as active.

Report the decommissioning at the next management review (AIMS-MGR-001).

## 8. Retiring Part of the Framework

The repository retires a capability, a workflow, a domain profile or a feature of the Standard through its deprecation policy (Standard 1.2.0 §11.2):

1. The change is proposed by RFC, under the repository's governance.
2. The item is deprecated in a MINOR release. A use of it is reported with W603 (`DEPRECATED_FORM`), and the release notes give the migration path.
3. It stays accepted for at least six months, and until the next MAJOR release.
4. It is removed in the next MAJOR release, and the changelog says so.

A deployer that uses a deprecated item plans the migration during the deprecation period and records it in the risk treatment plan. A deployer that cannot migrate in time treats the removal as a decommissioning trigger (section 2) for the parts of the system that depend on it.

## 9. Decommissioning Record

| Field | Value |
|-------|-------|
| System | [Name and deployment] |
| Trigger and date | [Section 2] |
| Approved by | [AI System Owner] |
| Stop time | [Section 3, step 2] |
| Tools and credentials revoked | [List, with times] |
| Safety layer removed | [Time] |
| Audit log verification | [Command output, date] |
| Witness copy of the head | [Where it is kept] |
| Archive location and checksums | [Section 4, step 3] |
| Way back closed | [Date, or "open until" date] |
| Retention period and disposal date | [Section 6] |
| Signed off | [AI System Owner, date] |

---

## Document Control

| Field | Value |
|-------|-------|
| **Document ID** | NIST-DCM-001 |
| **Title** | AI System Decommissioning Procedure — Grounded Agency Framework |
| **Version** | 1.0 |
| **Date** | [YYYY-MM-DD] |
| **Author** | [Name, Title] |
| **Approved by** | [Name, Title] |
| **Classification** | Internal |
| **Review cycle** | Annual, or when the framework's records or their locations change |
