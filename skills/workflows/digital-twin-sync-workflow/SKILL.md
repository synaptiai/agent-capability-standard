---
name: digital-twin-sync-workflow
description: Run the digital twin sync loop: ingest signals → update twin → detect drift → decide/act safely → verify → audit → rollback if needed.
argument-hint: "[sources] [world_id] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Web, Bash, Edit, Git
context: fork
agent: general-purpose
---

## Intent
Synchronize a **digital twin** with real-time signals and keep it **grounded, safe, and auditable**.

This workflow is designed to **model both real and digital systems** using the canonical world-state schema:
- `world_state_schema.yaml`
- `world_state_example.yaml`

## Preconditions (hard gates)
1) **Policy constraints must exist** (`/constrain`)
2) **Checkpoint before mutation** (`/checkpoint`)
3) Any external side effects require explicit approval (do not `send` without approval)

## Procedure
0) Ensure you have a twin snapshot (existing or empty baseline).
   - If none exists, start with `/world-model-workflow`.

Then execute the sync loop:

1) Invoke `/receive` → store `receive_out`
2) Invoke `/transform` to normalize to canonical events → `transform_out`
3) Invoke `/integrate` to merge events with prior twin snapshot → `integrate_out`
4) Invoke `/identity-resolution` → `identity_resolution_out`
5) Invoke `/world-state` producing canonical snapshot → `world_state_out`
6) Invoke `/state-transition` apply rules → `state_transition_out`
7) Invoke `/detect-anomaly` drift detection → `detect_anomaly_out`
8) Invoke `/estimate-risk` risk estimate → `estimate_risk_out`
9) Invoke `/forecast-risk` risk forecast → `forecast_risk_out`
10) Invoke `/plan` remediation plan + verification criteria + rollback plan → `plan_out`
11) Invoke `/constrain` enforce policy constraints → `constrain_out`
12) Invoke `/checkpoint` create mutation gate marker → `checkpoint_out`
13) Invoke `/act-plan` execute if safe/approved → `act_plan_out`
14) Invoke `/verify` PASS/FAIL → `verify_out`
15) Invoke `/audit` provenance + tool log → `audit_out`
16) If FAIL or side effects → `/rollback` → `rollback_out`
17) Invoke `/summarize` decision-ready report → `summarize_out`

## Output contract
Return:
- Updated twin snapshot: `world_state_out`
- Drift report: key anomalies + triggers
- Risk: estimate + forecast
- Actions: executed or proposed + safety gates
- Verification: PASS/FAIL + evidence anchors
- Audit pointer: `.claude/audit.log` (if hooks enabled)
- Rollback status (if used)
- Next recommended sync interval

## Safety constraints
- Stop on low confidence.
- Never execute mutation without checkpoint.
- Never emit external side effects without explicit approval.
