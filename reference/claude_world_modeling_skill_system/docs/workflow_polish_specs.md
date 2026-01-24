# Workflow composition polish specs

This file documents missing-but-useful edge-case constructs.

## Cross-workflow invocation

Add a capability atom:
- `invoke-workflow`

Step example:
```yaml
- capability: invoke-workflow
  workflow_id: world_model_build
  input_bindings:
    domain: "${receive_out.source.name}"
  store_as: world_model_out
  condition: "${world_state_out} == null"
  skip_if_false: true
```

## World-state diffing

Add a capability atom:
- `diff-world-state`

Output should include:
- added_entities / removed_entities / modified_entities
- state_variable_deltas
- new_observations
- triggered_transitions

## Conflict resolution strategies (integrate)

Recommended enum:
- prefer_authoritative_sources
- prefer_recent
- prefer_high_confidence
- merge_with_uncertainty
- escalate_to_human

## Schema conformance assertions

Steps may declare:
- `output_conforms_to: <schema-ref>`

Example:
```yaml
- capability: world-state
  store_as: world_state_out
  output_conforms_to: "world_state_schema.yaml#/world_state"
```

## Parallel groups

Two valid patterns:
1) per-step markers:
```yaml
- capability: inspect
  parallel_group: context_gathering
- capability: search
  parallel_group: context_gathering
- join: all_complete
```

2) explicit group container (optional):
```yaml
- parallel_group: context_gathering
  join: all_complete
  steps:
    - {capability: inspect, store_as: inspect_out}
    - {capability: search, store_as: search_out}
```

## Recovery loops

Failure modes may include:
```yaml
recovery:
  goto_step: critique
  inject_context:
    failure_evidence: "${verify_out.failures}"
  max_loops: 3
```
