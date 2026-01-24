---
name: inspect
description: Inspect a target (file/dir/URL/entity) and return a structured observation: identity, structure, properties, relationships, condition, and evidence anchors.
argument-hint: "[target] [lens] [depth]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent
Turn an unknown target into a **structured observation** compatible with:
- `event_schema.yaml`
- `world_state_schema.yaml`

This is a *read-only* capability.

## Inputs
- `target` (required): path | uri | entity_ref
- `depth`: shallow | deep (default: deep)
- `lens`: optional list of aspects to prioritize (e.g. ["schema","errors","dependencies"])

## Procedure
1) Identify the target type (file, folder, repo area, endpoint descriptor).
2) Extract *identity* (what is this?) and *structure* (how is it organized?).
3) Extract *properties* (key attributes) and *relationships* (depends_on, owns, located_in, etc.).
4) Extract *condition* (health/status/risks) based on observed signals.
5) Ground every non-trivial claim with evidence anchors.

## Output contract
Return a single object:

```yaml
identity: {id?, type?, name?, namespace?}
structure: {kind, shape, key_parts}
properties: {high_signal: {}, other: {}}
relationships: [{src, relation, dst, attributes?}]
condition: {status: healthy|degraded|unknown, signals: [], risks: []}
confidence: 0..1
evidence_anchors: ["file:line", "url", "tool:..."]
assumptions: []
```

## Safety constraints
- mutation=false
- do not fabricate evidence anchors
- if confidence < 0.5: explicitly request missing artifacts
