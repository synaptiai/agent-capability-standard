# Edge Types in the Capability Ontology

**Version:** 1.1.0
**Status:** Standard (accompanies [STANDARD-v1.1.0](STANDARD-v1.1.0.md) §4.3)
**Date:** 2026-10-27

---

## Overview

The capability ontology uses **directed edges** to express relationships between capabilities. Each edge has a type that determines its semantics and how it should be enforced by validators.

This document defines the 7 edge types supported by the ontology.

**Runs before.** Throughout, step A *runs before* step B when A comes earlier
in the workflow's step list **and is not in the same `parallel_group`** as B.
Steps of one parallel group run concurrently, so neither completes before the
other starts.

**Changes in 1.1.0.** `precedes`, `conflicts_with` and `soft_requires` were
under-specified in 1.0.0 and implementations disagreed. 1.1.0 states their
semantics precisely (below); as clarifications they apply to 1.0 and 1.1
workflows alike. Six edges that described follow-ups rather than
prerequisites were re-typed (see [Changes to the ontology's edges](#changes-to-the-ontologys-edges-in-110)).

---

## Edge Type Definitions

### 1. `requires` (Hard Dependency)

**Purpose:** Express hard prerequisites that MUST be satisfied.

**Semantics:**
- Every `to` step MUST have a `from` step that runs before it
- Validators MUST reject workflows that violate this (V102, per `to` step)
- This is the strongest form of dependency

**Example:**
```json
{"from": "checkpoint", "to": "mutate", "type": "requires"}
```

This means: a `checkpoint` MUST exist before any `mutate` operation.

**Transitivity:** No. If A requires B and B requires C, A does not automatically require C.

**Coexistence with `precedes`:** Some capability pairs have both a `requires` and a `precedes` edge. For example, `checkpoint → mutate` has both: `requires` enforces the safety invariant (mutations need a prior checkpoint), while `precedes` enforces temporal ordering. These serve complementary roles: `requires` demands the checkpoint's presence before every mutation, while `precedes` only orders the two when both appear. A workflow that mutates with a checkpoint running concurrently in the same parallel group violates both.

---

### 2. `soft_requires` (Soft Dependency)

**Purpose:** Express recommended prerequisites that SHOULD be satisfied when available.

**Semantics:**
- A `to` capability's incoming `soft_requires` edges form one group: at least
  **one** of their `from` capabilities SHOULD run before each `to` step
  (any-of per target)
- Validators MUST warn when none does (W601), and the workflow remains valid
- Allows flexibility while encouraging best practices

**Example:**
```json
{"from": "observe", "to": "ground", "type": "soft_requires"}
{"from": "detect", "to": "ground", "type": "soft_requires"}
```

This means: grounding SHOULD follow something that produced evidence to
ground — an observation, a detection, a prediction, an attribution or an
explanation; any one of them satisfies it.

Because the group is any-of, only capabilities that are genuine alternatives
as prerequisites belong in one target's group. `constrain` is the soft
prerequisite of `execute`, `mutate` and `send` (check policy before acting);
`plan` is not, since any-of would let a plan stand in for the policy check
(`plan precedes execute/mutate` already orders a plan when present).

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
- If a workflow contains both capabilities, every `to` step MUST have a
  `from` step that runs before it
- It constrains order only: it never requires the `from` capability to be
  present (that is `requires`)
- Validators MUST reject workflows that violate this (V102, once per edge,
  at the first offending `to` step)

**Example:**
```json
{"from": "checkpoint", "to": "mutate", "type": "precedes", "rationale": "State must be saved before any mutation"}
```

This means: in a workflow that checkpoints and mutates, the checkpoint comes first.

**Pre-flight checks.** `mutate`, `execute` and `send` each precede `verify`:
`verify` checks results after the fact. A check *before* acting is
`constrain`; a `verify` placed before the mutation it would check is V102.

**Transitivity:** Validators check each edge directly. When all three of A,
B and C are present, A precedes B and B precedes C order A before C; if B is
absent, nothing orders A and C.

**Use Cases:**
- Safety-critical sequencing (checkpoint before mutate)
- Logical workflow ordering (observe before detect)
- Resource management (acquire before release)

---

### 5. `conflicts_with` (Mutual Exclusivity)

**Purpose:** Express that two capabilities cannot run at the same time.

**Semantics:**
- The `from` and `to` capabilities MUST NOT share a `parallel_group`
- In sequence they are allowed: a `rollback` after a `mutate` is the normal
  recovery pattern
- Validators MUST reject concurrent pairs (F504, once per group and pair)
- Represents state that two operations would race on

**Example:**
```json
{"from": "rollback", "to": "persist", "type": "conflicts_with", "rationale": "Cannot persist while rolling back state"}
```

This means: a workflow cannot persist new state while it rolls back to a previous state.

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
| `soft_requires` | SHOULD (any-of per target) | No | No | Best practice recommendations |
| `enables` | Informational | No | No | Workflow composition patterns |
| `precedes` | MUST, when both present | Via present steps | No | Temporal ordering |
| `conflicts_with` | MUST, within a parallel group | No | Yes | No concurrency |
| `alternative_to` | Informational | No | Yes | Substitutability |
| `specializes` | Informational | Yes | No | Inheritance hierarchy |

---

## Validation Rules

### L1 Validation (Basic)

Validators at L1 conformance MUST, in time linear in the number of steps:
- Check `requires` edges (V102)
- Check `precedes` edges (V102)
- Check `conflicts_with` edges within parallel groups (F504)
- Warn when a `soft_requires` group is unmet (W601)

### L2 Validation (Schema)

No additional edge checks.

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
- Running both at once would race on the same state
- Running them one after the other is fine

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
constrain --precedes--> mutate
checkpoint --precedes--> mutate --precedes--> verify --precedes--> audit
```

When these capabilities appear, this chain ensures:
1. Policy is checked and state is saved before mutation
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

These conflicts prevent, within one parallel group:
- Persisting while rolling back
- Mutating during rollback

Rolling back after a failed mutation, in sequence, is allowed.

---

## Changes to the ontology's edges in 1.1.0

| Edge | 1.0.0 | 1.1.0 | Why |
|------|-------|-------|-----|
| plan → critique | soft_requires | enables | Critique follows a plan; it is not a prerequisite of it |
| mutate → persist | soft_requires | enables | Persisting mutated state is a follow-up |
| constrain → audit | soft_requires | enables | Auditing a constraint check is a follow-up |
| generate → verify | soft_requires | enables | Verification follows generation |
| inquire → receive | soft_requires | enables | Receiving the answer follows asking |
| execute → audit | soft_requires | removed | An `enables` edge already expressed it |
| constrain → execute, mutate, send | — | soft_requires | Check policy before acting |

## Versioning

Edge types follow semantic versioning:
- Adding new edge types: MINOR version bump
- Changing edge type semantics: MAJOR version bump, except clarifications
  of under-specified semantics, which a MINOR release states as errata (as
  1.1.0 does for `precedes`, `conflicts_with` and `soft_requires`)
- Adding edges of existing types: PATCH version bump

---

**End of Document**
