# Workflow DSL spec (rigorous)

Defines how workflows are composed from atomic capabilities without guessing.

See:
- `workflows/workflow_catalog.yaml`
- `ontology/capability_ontology.yaml`

Key features:
- per-step IO contracts (via capability schemas)
- failure modes + recovery actions
- timeouts + retries
- risk propagation and safety gates
