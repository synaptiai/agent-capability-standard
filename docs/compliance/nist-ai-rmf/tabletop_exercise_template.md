# Tabletop Exercise Template — Grounded Agency Framework

This template runs a tabletop exercise on one high-risk flow: an agent, working through the Claude Code plugin, makes an approved Write that destroys uncommitted work, and the operator must find the restore point and undo it. It gives the expected codes, what the operator looks at first and the recovery commands, and it closes gap G-09 of the NIST AI RMF profile (MG-2.2, response plans tested).

**Framework:** NIST AI Risk Management Framework (AI RMF 1.0), MG-2.2
**Subject Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Template — The deployer fills in the bracketed fields and the exercise record (section 8)
**Document ID:** NIST-TTX-001

---

## 1. Purpose

The exercise checks that an on-call operator can answer four questions about a change the agent made: what changed, under which call, with which approval, and how to undo it. It checks the records and the recovery commands as they work today, so it also finds gaps in the records.

The test `tests/test_tabletop_exercise.py` plays every step of section 5 and every inject of section 6 against the plugin's hooks and checks the expected results given here, so a change to the hooks that makes this template wrong fails the test suite.

## 2. Roles

| Role | In the exercise |
|------|----------------|
| Facilitator | Runs the scenario, gives the injects, keeps time |
| AI System Operator | Finds the records and restores the state (AIMS-POL-001, section 5.2) |
| AI Safety Officer | Judges whether the controls worked and records findings (section 5.3) |
| AI System Owner | Decides on escalation and signs the record (section 5.1) |

## 3. Preconditions

- A git repository with the plugin installed, and its hooks loaded.
- Claude Code's strict sandbox in the user settings (hooks README, "The strict sandbox"). Without it, every Bash call is a gated `mutate`, no checkpoint can be taken through Bash, and step 2 is refused with F501.
- The permission mode is `default`, `acceptEdits` or `plan`, so an approval request reaches a person.
- An audit key: `~/.config/acs/audit.key`, or `AUDIT_HMAC_KEY` set outside the project's settings.
- A tracked file `notes.txt` with changes that are not committed. These are the work the agent destroys.

## 4. Scenario

The agent is asked to tidy `notes.txt`. It overwrites the file with a Write. The person approves the Write without reading it. Ten minutes later the person notices that their uncommitted work is gone and calls the operator.

## 5. Steps and Expected Results

Each step gives what happens, the expected result, and where the operator looks first.

**Step 1. The agent calls Write with no checkpoint.**

- Expected: refused with `F501 CHECKPOINT_REQUIRED`, and the file is unchanged.
- Look at: the session's output. The audit log records calls that ran, so it has no line for this one.

**Step 2. The agent runs `git stash create "checkpoint: before rewrite"`.**

- Expected: allowed with no approval, because it is the `checkpoint` capability. The take hook writes `.claude/checkpoint.ok`, whose `commit` is the commit git printed.
- Look at: `.claude/checkpoint.ok`.

**Step 3. The agent calls Write again.**

- Expected: the pre-tool-use hook uses the checkpoint, moves the marker to `.claude/checkpoints/used/<checkpoint_id>.<call_id>.<suffix>` and asks the person with `F502 APPROVAL_REQUIRED: Write (capability 'mutate') requires approval`. The person approves and the file is overwritten.
- Look at: the approval prompt.

**Step 4. The operator is called.**

- Expected: the audit log `.claude/audit.log` has a line with `"tool": "Write"`, `"status": "executed"` and the call's `call_id`. The used marker whose name holds that call id, `used/<checkpoint_id>.<call_id>.<suffix>`, holds the restore point in its `commit`.
- Look at: first the audit log, then the used marker.

**Step 5. The operator restores.**

- Expected: the agent's restore, `git stash apply <commit>`, is a `rollback` and passes the hook, but git refuses it because `notes.txt` changed since the checkpoint. The operator restores from their own terminal, outside the hooks, with `git restore --source=<commit> --worktree -- notes.txt` and then `git restore --source=<commit>^2 --staged -- notes.txt`. The file holds the uncommitted work again.
- Look at: `notes.txt`.

**Step 6. The operator checks.**

- Expected: `git diff --quiet <commit> -- notes.txt` exits 0, and `python tools/verify_audit_log.py` reports a valid chain.
- Look at: the output of the two commands.

Commands for step 4:

```bash
jq -c 'select(.tool == "Write") | {timestamp, status, call_id}' .claude/audit.log
ls .claude/checkpoints/used/ | grep -F ".<call_id>."
jq -r .commit .claude/checkpoints/used/<checkpoint_id>.<call_id>.<suffix>
```

Notes for step 5:

- A checkpoint taken on a clean tree records `HEAD` as its commit. Restore it with `git restore --source=HEAD --staged --worktree -- <paths>`.
- `git stash create` saves tracked files only. A file the agent created after the checkpoint is not in it: remove it with `rm -f -- <path>`.
- If the agent runs the `git restore` line itself, it is a `mutate`: it needs a new checkpoint and an approval. The new checkpoint keeps the overwritten state too, which is useful evidence.

```mermaid
---
title: From the approved Write to the restored file
---
flowchart TB
  accDescr: The agent's Write is refused with F501 until a checkpoint is taken; with a checkpoint, the marker moves to the used directory under a name that holds the call id, and the person is asked with F502. The operator reads the call id from the audit log, finds the used marker with that call id, reads the restore commit from it and restores the file with git restore from their own terminal.
  w1["Write, no checkpoint"] -->|refused| f501["F501"]
  cp["git stash create"] --> marker[".claude/checkpoint.ok"]
  marker --> w2["Write"]
  w2 -->|"marker moved to used/ and person asked, F502"| run["Write runs"]
  run --> log["Audit line: tool, status, call_id"]
  log -->|call_id| used["used marker: commit"]
  used -->|commit| restore["git restore from the operator's terminal"]
```

## 6. Injects

The facilitator adds one or more of these after step 3:

| Inject | Expected result | What it tests |
|--------|-----------------|---------------|
| The session runs in `bypassPermissions` mode | The Write is refused: `F502 APPROVAL_REQUIRED`, because no person can be asked. The file is unchanged | That a mode with no person refuses rather than runs |
| The checkpoint is more than 30 minutes old | The Write is refused with F501 (an expired marker). An expired checkpoint can still be restored | That expiry limits authority, not recovery |
| A turn ends between steps 2 and 3 | The marker is filed under `.claude/checkpoints/ended/`, and the Write is refused with F501 | The execution boundary |
| The audit log's last line is deleted | `python tools/verify_audit_log.py` fails, and the log hook's next call reports that `audit.log` no longer holds the entry its head records | Tamper detection |

## 7. Escalation

Use the levels of the post-market monitoring plan (EUAIA-PMM-001, section 6.1):

| Finding in the exercise | Level |
|------------------------|-------|
| The state was restored and the log verifies | L1: record and close |
| The restore point could not be found, or the restore failed | L2: root cause and corrective action under AIMS-NCR-001 |
| A gated call ran with no checkpoint, or the log fails verification | L3: suspend the plugin's use until fixed |

## 8. Exercise Record

| Field | Value |
|-------|-------|
| Date and duration | [YYYY-MM-DD, minutes] |
| Facilitator and participants | [Names and roles] |
| Plugin version | [From `recorded_by.version` in the audit log] |
| Injects used | [Section 6] |
| Time from call to restore point found | [Minutes] |
| Time from call to state restored | [Minutes] |
| Steps whose result differed from section 5 | [Step and what happened] |
| Findings and corrective actions | [With AIMS-NCR-001 numbers] |
| Next exercise | [Date; at least once a year, and after each plugin upgrade] |
| Signed off | [AI System Owner, date] |

## 9. Debrief Questions

1. How long did the operator take to find the restore point, and what slowed it down?
2. Did anyone read the approval prompt in step 3, and would they have caught the problem?
3. Which record would the operator have wanted that did not exist?
4. Would the recovery have worked if the agent had created new files as well?

---

## Document Control

| Field | Value |
|-------|-------|
| **Document ID** | NIST-TTX-001 |
| **Title** | Tabletop Exercise Template — Grounded Agency Framework |
| **Version** | 1.0 |
| **Date** | [YYYY-MM-DD] |
| **Author** | [Name, Title] |
| **Approved by** | [Name, Title] |
| **Classification** | Internal |
| **Review cycle** | Annual, or when the hooks or the audit record change |
