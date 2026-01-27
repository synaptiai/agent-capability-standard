# Edge Types in the Capability Ontology

**Version:** 1.0.0
**Status:** Standard
**Date:** 2026-01-27

---

## Overview

The capability ontology uses **directed edges** to express relationships between capabilities. Each edge has a type that determines its semantics and how it should be enforced by validators.

This document defines the 7 edge types supported by the ontology.

---

## Edge Type Definitions

### 1. `requires` (Hard Dependency)

**Purpose:** Express hard prerequisites that MUST be satisfied.

**Semantics:**
- The `from` capability MUST be executed before the `to` capability
- Validators MUST reject workflows that violate this ordering
- This is the strongest form of dependency

**Example:**
```json
{"from": "checkpoint", "to": "mutate", "type": "requires"}
```

This means: a `checkpoint` MUST exist before any `mutate` operation.

**Transitivity:** No. If A requires B and B requires C, A does not automatically require C.

---

### 2. `soft_requires` (Soft Dependency)

**Purpose:** Express recommended prerequisites that SHOULD be satisfied when available.

**Semantics:**
- The `from` capability SHOULD be executed before the `to` capability
- Validators SHOULD warn if not satisfied, but the workflow remains valid
- Allows flexibility while encouraging best practices

**Example:**
```json
{"from": "observe", "to": "ground", "type": "soft_requires"}
```

This means: observations SHOULD be grounded in evidence when possible.

**Transitivity:** No.

---

### 3. `enables` (Capability Flow)

**Purpose:** Express that one capability unlocks or makes another possible.

**Semantics:**
- The `from` capability's output can serve as input to the `to` capability
- Represents natural workflow composition patterns
- Does not enforce ordering; just documents capability relationships

**Example:**
```json
{"from": "plan", "to": "execute", "type": "enables"}
```

This means: planning enables execution (plans can be executed).

**Transitivity:** No.

---

### 4. `precedes` (Temporal Ordering)

**Purpose:** Express temporal ordering constraints independent of data dependencies.

**Semantics:**
- The `from` capability MUST complete before the `to` capability begins
- Enforces execution order even when no direct data dependency exists
- Validators MUST reject workflows that violate this ordering

**Example:**
```json
{"from": "checkpoint", "to": "mutate", "type": "precedes", "rationale": "State must be saved before any mutation"}
```

This means: checkpointing must temporally precede mutation in any workflow.

**Transitivity:** Yes. If A precedes B and B precedes C, then A precedes C.

**Use Cases:**
- Safety-critical sequencing (checkpoint before mutate)
- Logical workflow ordering (observe before detect)
- Resource management (acquire before release)

---

### 5. `conflicts_with` (Mutual Exclusivity)

**Purpose:** Express that two capabilities cannot coexist in the same workflow.

**Semantics:**
- The `from` and `to` capabilities MUST NOT both appear in a workflow
- Validators MUST reject workflows containing both capabilities
- Represents logical contradictions or resource conflicts

**Example:**
```json
{"from": "rollback", "to": "persist", "type": "conflicts_with", "rationale": "Cannot persist while rolling back state"}
```

This means: a workflow cannot both persist new state and rollback to previous state.

**Transitivity:** No.

**Symmetry:** Yes. If A conflicts_with B, then B conflicts_with A.

---

### 6. `alternative_to` (Substitutability)

**Purpose:** Express that capabilities can substitute for each other.

**Semantics:**
- The `from` capability can replace the `to` capability with compatible semantics
- Used for capability selection when multiple valid options exist
- Does not imply identical behavior, only compatible contracts

**Example:**
```json
{"from": "search", "to": "retrieve", "type": "alternative_to", "rationale": "Both acquire data, search by criteria vs retrieve by reference"}
```

This means: either search or retrieve can be used to acquire data.

**Transitivity:** No.

**Symmetry:** Yes. If A is alternative_to B, then B is alternative_to A.

**Use Cases:**
- Workflow optimization (choosing more efficient alternatives)
- Graceful degradation (falling back to alternative capabilities)
- Capability negotiation (selecting available options)

---

### 7. `specializes` (Inheritance)

**Purpose:** Express parent-child relationships between capabilities.

**Semantics:**
- The `from` capability is a more specific variant of the `to` capability
- The specialized capability inherits contracts from the general capability
- Enables capability hierarchies and taxonomies

**Example:**
```json
{"from": "classify", "to": "detect", "type": "specializes", "rationale": "Classification is specialized detection with categories"}
```

This means: `classify` is a specialized form of `detect` that assigns categories.

**Transitivity:** Yes. If A specializes B and B specializes C, then A specializes C.

**Use Cases:**
- Capability taxonomies (organizing by generality)
- Contract inheritance (specialized capabilities inherit base contracts)
- Domain specialization (generic capabilities refined for domains)

---

## Edge Type Summary

| Edge Type | Enforcement | Transitive | Symmetric | Primary Use |
|-----------|-------------|------------|-----------|-------------|
| `requires` | MUST | No | No | Hard prerequisites |
| `soft_requires` | SHOULD | No | No | Best practice recommendations |
| `enables` | Informational | No | No | Workflow composition patterns |
| `precedes` | MUST | Yes | No | Temporal ordering |
| `conflicts_with` | MUST | No | Yes | Mutual exclusivity |
| `alternative_to` | Informational | No | Yes | Substitutability |
| `specializes` | Informational | Yes | No | Inheritance hierarchy |

---

## Validation Rules

### L1 Validation (Basic)

Validators at L1 conformance MUST:
- Check `requires` edges are satisfied in workflow order
- Check `conflicts_with` edges are not both present in a workflow

### L2 Validation (Schema)

Validators at L2 conformance MUST additionally:
- Warn when `soft_requires` edges are not satisfied
- Check `precedes` edges respect temporal ordering

### L3 Validation (Contracts)

Validators at L3 conformance MUST additionally:
- Verify `specializes` relationships maintain contract compatibility
- Check `alternative_to` capabilities have compatible I/O schemas

---

## Edge Properties

All edges support these properties:

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `from` | string | Yes | Source capability ID |
| `to` | string | Yes | Target capability ID |
| `type` | enum | Yes | One of the 7 edge types |
| `rationale` | string | No | Human-readable explanation |
| `metadata` | object | No | Additional machine-readable data |

---

## Usage Guidelines

### When to Use Each Type

**Use `requires` when:**
- Safety depends on the ordering
- The workflow is invalid without the prerequisite
- No workaround exists

**Use `soft_requires` when:**
- Best practices recommend the ordering
- The workflow works but may be suboptimal without it
- Flexibility is needed for edge cases

**Use `enables` when:**
- Documenting natural capability composition
- Output of one flows to input of another
- No enforcement is needed

**Use `precedes` when:**
- Temporal ordering matters independent of data flow
- Multiple steps must happen in sequence
- Order affects correctness or safety

**Use `conflicts_with` when:**
- Capabilities are mutually exclusive
- Both cannot logically coexist
- Attempting both would cause errors or undefined behavior

**Use `alternative_to` when:**
- Multiple capabilities can achieve similar goals
- Workflows should choose one or the other
- Substitution is semantically valid

**Use `specializes` when:**
- Building capability hierarchies
- A capability is a refined version of another
- Contract inheritance is meaningful

---

## Examples in the Ontology

### Safety-Critical Precedes Chain

```
checkpoint --precedes--> mutate --precedes--> verify --precedes--> audit
```

This chain ensures:
1. State is saved before mutation
2. Mutation completes before verification
3. Verification results are audited

### Specialization Hierarchy

```
observe
  |
  +--specializes-- detect
                     |
                     +--specializes-- classify
```

This hierarchy shows:
- `detect` is specialized observation for patterns
- `classify` is specialized detection with categories

### Conflict Resolution

```
rollback --conflicts_with-- persist
mutate --conflicts_with-- rollback
```

These conflicts prevent:
- Persisting while rolling back
- Mutating during rollback

---

## Versioning

Edge types follow semantic versioning:
- Adding new edge types: MINOR version bump
- Changing edge type semantics: MAJOR version bump
- Adding edges of existing types: PATCH version bump

---

**End of Document**
