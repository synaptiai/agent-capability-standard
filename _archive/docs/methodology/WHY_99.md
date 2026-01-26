# Why 99 Capabilities?

**Document Status**: Informative
**Last Updated**: 2026-01-26
**Version**: 1.0.0

---

## Executive Summary

The Grounded Agency ontology defines **99 atomic capabilities**. This document answers the obvious question: *Why 99?*

The short answer: **99 is derived, not arbitrary.**

The long answer follows.

---

## 1. The Core Claim

We claim that 99 capabilities are **sufficient to compose any grounded agent behavior**.

This is analogous to chemistry: just as ~118 elements combine into millions of molecules, 99 capabilities compose into unlimited workflows.

### What This Claim Means

- **Sufficient**: Any agent task can be expressed as a composition of these 99
- **Atomic**: Each capability is irreducible (cannot be decomposed without losing semantics)
- **Composable**: Capabilities have typed I/O contracts that enable reliable composition

### What This Claim Does NOT Mean

- **Not Final**: Capability #100 may be added if justified (see [Extension Governance](EXTENSION_GOVERNANCE.md))
- **Not Unique**: Other valid decompositions exist; this is *a* principled set, not *the* only set
- **Not Physical Law**: Unlike chemical elements, this is engineering design, not natural discovery

---

## 2. Historical Development

### Phase 1: DIS '23 Foundation

We began with the DIS '23 AI Capabilities framework [Yildirim et al. 2023], which identified 8 core verbs:

```
Detect → Identify → Estimate → Forecast
Compare → Discover → Generate → Act
```

These verbs classify AI features in products. They provided our taxonomic foundation.

### Phase 2: Domain Specialization

Each verb operates on different domains. We systematically enumerated the domains:

```
detect + {entity, activity, anomaly, drift, conflict, change, pattern}
  → 7 specialized capabilities

identify + {entity, activity, attribute, relationship, constraint, risk, opportunity, context}
  → 8 specialized capabilities

... and so on for each verb
```

This expansion added ~42 capabilities.

### Phase 3: Operational Requirements

Production agents need capabilities beyond classification:

**World State Management**
```
world-state, state-transition, causal-model, uncertainty-model,
identity-resolution, diff-world-state, merge-world-state, integrate
```

**Planning and Execution**
```
plan, schedule, prioritize, decide, decompose, synthesize
act-plan, transform, send, execute
```

**Evidence and Grounding**
```
provenance, grounding, evidence-aggregate
```

This added ~30 capabilities.

### Phase 4: Safety Layer

Reliable agents require safety primitives:

```
verify, audit, checkpoint, rollback, constrain, mitigate, improve
```

This added 7 capabilities.

### Phase 5: Infrastructure

Core infrastructure for complete agents:

```
PERCEPTION: retrieve, inspect, search, receive
MEMORY: persist, recall
COORDINATION: delegate, synchronize, negotiate
```

This added 12 capabilities.

### Total: 99

```
DIS '23 foundation:     8
Domain specialization: 42
Operational needs:     30
Safety layer:           7
Infrastructure:        12
────────────────────────
Total:                 99
```

---

## 3. Why Not Fewer?

### The Minimal Alternative: ~40 Capabilities

We considered a coarser ontology with broader capabilities like:
- `detect` (instead of detect-entity, detect-anomaly, etc.)
- `model` (instead of world-state, causal-model, etc.)
- `act` (instead of act-plan, generate-*, transform, etc.)

**Rejected because:**

1. **Runtime interpretation required**: Coarse capabilities need runtime logic to determine specific behavior
2. **Validation impossible**: Cannot statically check that "detect" produces the right output type
3. **Documentation gap**: Users can't see what specific operations are available

### The Tradeoff

| Granularity | Static Validation | Runtime Complexity | Documentation |
|-------------|-------------------|-------------------|---------------|
| Coarse (~40) | Limited | High | Vague |
| **Medium (99)** | **Strong** | **Low** | **Clear** |
| Fine (~200+) | Excessive | Low | Overwhelming |

99 is the sweet spot: fine enough for validation, coarse enough for comprehension.

---

## 4. Why Not More?

### The Maximal Alternative: 200+ Capabilities

We could add more capabilities by:
- Further domain specialization (detect-anomaly-temporal, detect-anomaly-spatial, ...)
- Tool-specific capabilities (query-postgres, call-api-rest, ...)
- Framework-specific capabilities (langchain-chain, autogen-conversation, ...)

**Rejected because:**

1. **Compositions, not atoms**: `detect-anomaly-temporal` = `detect-anomaly` + `temporal-model`
2. **Domain-specific**: `query-postgres` is an implementation of `retrieve`
3. **Framework coupling**: Capabilities should be framework-agnostic

### The Atomicity Test

A capability is atomic if it cannot be expressed as a composition of other capabilities.

When considering capability #100, we ask: "Is this truly atomic, or a composition?"

Most candidates fail this test.

---

## 5. The Periodic Table Analogy

### Why This Analogy Works

| Chemistry | Grounded Agency |
|-----------|-----------------|
| ~118 elements | 99 capabilities |
| Atoms are irreducible | Capabilities are atomic |
| Molecules are compositions | Workflows are compositions |
| Element groups (metals, gases) | Capability layers |
| Periodic table organizes by properties | Ontology organizes by function |

### Why This Analogy Has Limits

| Chemistry | Grounded Agency |
|-----------|-----------------|
| Elements discovered via physics | Capabilities designed via engineering |
| Fixed by natural law | Extensible by governance |
| Atomic numbers are unique identifiers | Capability IDs are assigned |

**The analogy communicates the design intent, not a claim about physical law.**

---

## 6. The Completeness Argument

### Informal Argument

Any agent task can be described as:

1. **Perceive** something about the world → PERCEPTION layer (4 capabilities)
2. **Model** what was perceived → MODELING layer (45 capabilities)
3. **Reason** about options → REASONING layer (20 capabilities)
4. **Act** to change the world → ACTION layer (12 capabilities)
5. **Ensure** safety invariants → SAFETY layer (7 capabilities)
6. **Reflect** on own operation → META layer (6 capabilities)
7. **Remember** across invocations → MEMORY layer (2 capabilities)
8. **Coordinate** with other agents → COORDINATION layer (3 capabilities)

Each layer has capabilities covering its domain. Therefore, any agent task can be composed.

### Formal Argument

See [LAYER_DERIVATION.md](LAYER_DERIVATION.md) for the MECE (Mutually Exclusive, Collectively Exhaustive) proof that the 8 layers cover all agent operations.

See [CAPABILITY_DERIVATION.md](CAPABILITY_DERIVATION.md) for the derivation of capabilities within each layer.

### Validation

- **Reference workflows**: 5 workflows demonstrate compositions across layers
- **Challenge workflows**: Attempts to construct non-composable tasks have failed
- **Gap analysis**: No fundamental capability gaps identified

---

## 7. What Could Change the Number?

### Reasons to Add Capability #100

1. **New primitive discovered**: A task that cannot be expressed as composition
2. **Layer expansion**: A new fundamental agent operation category
3. **Grounding requirements**: New evidence types requiring specialized handling

### Reasons to Remove Capabilities

1. **Composition identified**: A capability is actually a composition of others
2. **Redundancy**: Two capabilities are semantically equivalent
3. **Never used**: A capability has no use case (handled via deprecation)

### Process

See [EXTENSION_GOVERNANCE.md](EXTENSION_GOVERNANCE.md) for the RFC process.

---

## 8. Honest Acknowledgments

### What We Know

- 99 capabilities were derived systematically from established frameworks
- Each capability passes atomicity tests
- Reference workflows demonstrate compositional power

### What We Don't Know

- Whether 99 is the *minimum* sufficient set (there may be redundancy)
- Whether 99 is *complete* for all future agent tasks
- Whether alternative decompositions might be better for some purposes

### Our Commitment

We commit to:
- Documenting our methodology openly
- Accepting challenges to our completeness claim
- Evolving the ontology when evidence warrants

---

## 9. Conclusion

**Why 99?**

Because we started with 8 principled verbs, systematically expanded them along domain and operational axes, and stopped when additional candidates failed atomicity tests.

**Is 99 perfect?**

No. It's a well-justified engineering design, not a revealed truth.

**Is 99 sufficient?**

We believe so. Every workflow we've attempted can be composed from these 99. If you find a counterexample, please [open an issue](https://github.com/synaptiai/agent-capability-standard/issues).

---

## References

- Yildirim, N. et al. (2023). Creating Design Resources to Scaffold the Ideation of AI Concepts. DIS '23.
- [LAYER_DERIVATION.md](LAYER_DERIVATION.md) — Why 8 layers
- [CAPABILITY_DERIVATION.md](CAPABILITY_DERIVATION.md) — How capabilities were derived
- [EXTENSION_GOVERNANCE.md](EXTENSION_GOVERNANCE.md) — When to add #100
- [PERIODIC_TABLE.md](PERIODIC_TABLE.md) — The analogy explained
