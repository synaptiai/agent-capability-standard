---
name: checkpoint
description: Create a safety checkpoint marker before mutation/execution steps.
argument-hint: "[inputs] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit
context: fork
agent: general-purpose
---

## Intent
Execute **checkpoint** (layer: SAFETY).

Success means you produce the output contract, grounded in evidence, and respect safety gates.

## Procedure
1) Minimize context load; read only what you need.
2) State assumptions and unknowns.
3) Execute `checkpoint` deterministically where possible.
4) Return structured output.

## Output contract
Return:
- Checkpoint created: yes|no
- Marker: <path>
- Snapshot info: <what is protected>
- Next safe actions: <what may proceed>


## Safety constraints
- mutation=True
- requires_checkpoint=False
- requires_approval=False
