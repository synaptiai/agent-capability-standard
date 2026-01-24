---
name: gap-analysis-workflow
description: Identify capability gaps and propose new skills with prioritization.
argument-hint: "[goal] [scope] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent
Run the composed workflow **gap-analysis-workflow** using atomic capability skills.

Success means:
- every step output is grounded (evidence anchors)
- safety gates are respected (checkpoint before mutation)
- final result includes an audit trail

## Procedure
0) Create checkpoint marker if mutation might occur:
   - create `.claude/checkpoint.ok` after confirming rollback strategy.

1) Invoke `/inspect` and store output as `inspect_out`.
2) Invoke `/map-relationships` and store output as `map-relationships_out`.
3) Invoke `/discover-relationship` and store output as `discover-relationship_out`.
4) Invoke `/compare-plans` and store output as `compare-plans_out`.
5) Invoke `/prioritize` and store output as `prioritize_out`.
6) Invoke `/generate-plan` and store output as `generate-plan_out`.
7) Invoke `/audit` and store output as `audit_out`.

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
