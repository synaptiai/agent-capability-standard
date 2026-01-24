---
name: debug-workflow
description: Execute the Debug Code Change workflow end-to-end with safety gates.
argument-hint: "[goal] [scope] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent
Run the composed workflow **debug-workflow** using atomic capability skills.

Success means:
- every step output is grounded (evidence anchors)
- safety gates are respected (checkpoint before mutation)
- final result includes an audit trail

## Procedure
0) Create checkpoint marker if mutation might occur:
   - create `.claude/checkpoint.ok` after confirming rollback strategy.

1) Invoke `/inspect` and store output as `inspect_out`.
2) Invoke `/search` and store output as `search_out`.
3) Invoke `/map-relationships` and store output as `map-relationships_out`.
4) Invoke `/model-schema` and store output as `model-schema_out`.
5) Invoke `/critique` and store output as `critique_out`.
6) Invoke `/plan` and store output as `plan_out`.
7) Invoke `/act-plan` and store output as `act-plan_out`.
8) Invoke `/verify` and store output as `verify_out`.
9) Invoke `/audit` and store output as `audit_out`.
10) Invoke `/rollback` and store output as `rollback_out`.

## Output contract
Return:
- Step outputs: a compact summary per step (key results + evidence anchors)
- Final outcome: what changed/what was produced
- Verification: PASS/FAIL and evidence
- Audit log pointer: `.claude/audit.log` (if hooks enabled)
- Rollback note: what to do if anything fails

## Safety constraints
- If any step produces low confidence, stop and ask for clarification.
- Never proceed to `act-plan` without an explicit plan and verification criteria.
