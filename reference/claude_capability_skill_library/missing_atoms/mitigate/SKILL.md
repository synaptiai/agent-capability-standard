---
name: mitigate
description: Detect/mitigate prompt injection, unsafe tool use, data leakage.
argument-hint: "[context] [data] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read
context: fork
agent: explore
---

## Intent
Execute **mitigate** as a reusable, evidence-first capability.

Success means you return the output contract **with grounded evidence** and **explicit assumptions**.

## Inputs
- Required: the data/context needed to run `mitigate`
- Optional: constraints (format, time horizon, thresholds), and “what good looks like”

## Procedure
1) **Minimize context load**: read the smallest set of files/snippets needed.
2) **State assumptions**: list unknowns and how you will handle them.
3) **Perform the capability**:
   - prefer small, verifiable steps
   - attach claims to evidence anchors
4) **Return output in the contract format**.

## Output contract
Return:
- Policy decisions: <allow/deny + rationale>
- Risks detected: <list>
- Mitigations: <actions taken>
- Safe next steps: <what can proceed>


## Verification
- Describe how to verify correctness (tests, alternate evidence, invariants).
- If verification requires tools not in `allowed-tools`, ask.

## Safety constraints
- Do not access secrets or sensitive paths.
- Do not execute destructive actions unless explicitly required and safe.
- If unclear or risky: stop and request clarification.
