# Capability ontology (rigorous)

This ontology is the **single source of truth** for the skill library.

It models:
- **Nodes** = atomic capabilities (DIS + agentic + world modeling)
- **Edges** = compositional dependencies (requires/enables/verifies/governed_by)

Use it to:
1) Validate coverage (do we have a skill for every node?)
2) Compose workflows (traverse edges to build a pipeline)
3) Enforce safety (risk=high nodes must include verify+rollback)

Files:
- `capability_ontology.json`
- `capability_ontology.yaml`
