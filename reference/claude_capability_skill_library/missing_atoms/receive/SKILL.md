---
name: receive
description: Ingest and parse incoming messages/events into structured form.
argument-hint: "[inputs] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent
Execute **receive** (layer: PERCEPTION).

Success means you produce the output contract, grounded in evidence, and respect safety gates.

## Procedure
1) Minimize context load; read only what you need.
2) State assumptions and unknowns.
3) Execute `receive` deterministically where possible.
4) Return structured output.

## Output contract
Return:
- Messages: <list>
- Parsed events: <structured>
- Conflicts/unknowns: <list>
- Evidence: <anchors/logs>


## Safety constraints
- mutation=False
- requires_checkpoint=False
- requires_approval=False
