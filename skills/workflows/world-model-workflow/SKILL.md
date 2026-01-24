---
name: world-model-workflow
description: Build a rigorous world model (state+dynamics+uncertainty+provenance).
argument-hint: "[goal] [scope] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent
Run the composed workflow **world-model-workflow** using atomic capability skills.

Success means:
- every step output is grounded (evidence anchors)
- safety gates are respected (checkpoint before mutation)
- final result includes an audit trail

## Procedure
0) Create checkpoint marker if mutation might occur:
   - create `.claude/checkpoint.ok` after confirming rollback strategy.

1) Invoke `/retrieve` and store output as `retrieve_out`.
2) Invoke `/inspect` and store output as `inspect_out`.
3) Invoke `/identity-resolution` and store output as `identity-resolution_out`.
4) Invoke `/world-state` and store output as `world-state_out`.
5) Invoke `/state-transition` and store output as `state-transition_out`.
6) Invoke `/causal-model` and store output as `causal-model_out`.
7) Invoke `/uncertainty-model` and store output as `uncertainty-model_out`.
8) Invoke `/provenance` and store output as `provenance_out`.
9) Invoke `/grounding` and store output as `grounding_out`.
10) Invoke `/simulation` and store output as `simulation_out`.
11) Invoke `/summarize` and store output as `summarize_out`.

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
