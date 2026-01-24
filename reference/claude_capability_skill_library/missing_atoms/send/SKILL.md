---
name: send
description: Emit a message/event to an external system (requires explicit approval).
argument-hint: "[inputs] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read
context: fork
agent: explore
---

## Intent
Execute **send** (layer: ACTION).

Success means you produce the output contract, grounded in evidence, and respect safety gates.

## Procedure
1) Minimize context load; read only what you need.
2) State assumptions and unknowns.
3) Execute `send` deterministically where possible.
4) Return structured output.

## Output contract
Return:
- Delivery: success|failed|pending
- Destination: <where>
- Payload summary: <what was sent>
- Response: <if any>
- Evidence: <anchors/logs>
- Safety: <approval gate status>


## Safety constraints
- mutation=True
- requires_checkpoint=True
- requires_approval=True
