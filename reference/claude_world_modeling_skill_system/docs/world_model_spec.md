# World modeling spec (rigorous)

This is the conceptual scaffold you’ll use to model both **real** and **digital** systems.

## 0) Definitions

A **world model** is a structured representation of:
- **Entities** (things that exist)
- **State variables** (attributes at time t)
- **Relationships** (edges + constraints)
- **Dynamics** (state transitions over time)
- **Causal mechanisms** (interventions and effects)
- **Observations** (evidence)
- **Uncertainty** (what is unknown/noisy)
- **Provenance** (where claims come from)

A **digital twin** is a world model that also includes:
- synchronization rules between real-world signals and digital state
- drift detection (when twin diverges from reality)
- control actions (closed-loop actuation)

---

## 1) Core data structures

### 1.1 Entity
- id: stable identifier
- type: class/category
- aliases: known alternate identifiers
- attributes: { key: value }
- relationships: edges to other entities
- confidence: [0,1]

### 1.2 State variable (time-indexed)
- name
- value
- units
- timestamp
- source (observation/projection)
- uncertainty: { interval | distribution, epistemic/aleatoric }

### 1.3 Relationship edge
- src_entity_id
- dst_entity_id
- relation_type
- constraints (cardinality, invariants)
- confidence

### 1.4 Transition rule (state machine)
- preconditions (guards)
- trigger event
- effects (state updates)
- allowed next states
- rollback rule (inverse operation)

### 1.5 Causal graph
- nodes = state variables
- edges = causal influence
- mechanisms = assumptions explaining why edge exists
- interventions = do(X=x) effects (counterfactuals)

### 1.6 Provenance record
- claim_id
- evidence anchors (file:line, tool output ids)
- transformations (summaries/derivations)
- author (agent/skill)
- timestamp

---

## 2) The “world modeling pipeline” (capability composition)

1) `retrieve` + `inspect`  
2) `identity-resolution`  
3) `world-state`  
4) `map-relationships`  
5) `state-transition`  
6) `causal-model`  
7) `uncertainty-model`  
8) `grounding` + `provenance`  
9) `simulation`  
10) `summarize`

---

## 3) Safety invariants

- Every claim must have **evidence anchors**.
- Uncertainty must be explicit.
- Any action must be:
  - planned (`plan`)
  - verified (`verify`)
  - auditable (`audit`)
  - reversible (`rollback`)

---

## 4) Minimum viable “world model output”

Return YAML/JSON containing:
- entities
- state variables
- relationships
- transitions
- causal edges (optional)
- uncertainty model
- provenance map


## Canonical schema
- `docs/schemas/world_state_schema.yaml`
- `docs/schemas/world_state_example.yaml`
