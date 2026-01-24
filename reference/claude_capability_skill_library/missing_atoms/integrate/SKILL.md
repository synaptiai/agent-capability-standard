---
name: integrate
description: Combine heterogeneous sources into a unified model with conflict resolution + provenance.
argument-hint: "[inputs] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent
Execute **integrate** (layer: MODELING).

Success means you produce the output contract, grounded in evidence, and respect safety gates.

## Procedure
1) Minimize context load; read only what you need.
2) State assumptions and unknowns.
3) Execute `integrate` deterministically where possible.
4) Return structured output.

## Output contract
Return:
- Transformed: <output artifact>
- Target schema: <schema name or inline>
- Loss / distortion: <what changed or was dropped>
- Evidence: <anchors>
- Confidence: low/med/high + why


## Safety constraints
- mutation=False
- requires_checkpoint=False
- requires_approval=False
