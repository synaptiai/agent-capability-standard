# Press Kit

## Boilerplate (Use Verbatim)

**Agent Capability Standard** is an open specification for composable AI agent capabilities. It defines 36 atomic capabilities across 9 cognitive layers, a type-safe workflow DSL, and grounded world modeling with trust-aware conflict resolution. Built on the Grounded Agency philosophy, it makes agent reliability structural—not optional.

## One-Liner

A publishable open standard for **composable agent capabilities** with a **type-safe workflow DSL** and a **world modeling schema**.

## Key Statistics

| Metric | Value |
|--------|-------|
| Atomic capabilities | 36 |
| Cognitive layers | 9 |
| Reference workflows | 12 |
| Domain profiles | 8 (healthcare, manufacturing, data analysis, personal assistant, vision, audio, multimodal, general) |
| Compliance frameworks | 3 (EU AI Act, NIST AI RMF, ISO 42001) |
| Conformance levels | 4 (L1–L4) |
| License | Apache 2.0 |

## What Problem It Solves

Most agent systems fail in production because:
- Composition is implicit (no contracts)
- State is ungrounded (no provenance)
- Conflict resolution is undefined (no trust model)
- Safety is retrofitted (no checkpoints/rollback)

This standard fixes that by making reliability *structural*.

## Key Innovations

- **Atomic capability ontology** with explicit dependencies and I/O schemas
- **Workflow DSL** with gates, recovery loops, parallelism, typed bindings
- **Canonical world-state model** with uncertainty, provenance, lineage, retention
- **Authority trust model** with time decay and field-specific authority
- **Compiler-grade validator** that can propose deterministic transform patches
- **Domain parameterization** (36 atoms replace 99 domain-specific variants)

## Audience-Specific Pitches

### For Engineering Leaders

"Stop debugging agent failures at 2 AM. Agent Capability Standard provides typed contracts between capabilities, checkpoints before mutations, and audit trails for every decision. Your agents become structurally reliable—failures are visible and recoverable."

### For Researchers

"A formal ontology for agent capabilities derived from first principles (BDI, SOAR, ReAct). 36 irreducible cognitive operations across 9 layers, with typed composition semantics and grounded world modeling. Extensible via governance process."

### For Compliance Officers

"Every agent action has provenance and lineage. Checkpoint enforcement prevents unrecoverable state. Pre-built conformity assessments for EU AI Act, NIST AI RMF 1.0, and ISO 42001. Audit retention policies configurable per domain."

## How It Compares

| Aspect | LangChain / AutoGPT | MCP | Agent Capability Standard |
|--------|---------------------|-----|---------------------------|
| **Type** | Framework (implementation) | Protocol (connection) | Specification (semantics) |
| **Focus** | Building agents | Connecting tools to LLMs | Defining what agents can do safely |
| **Contracts** | Implicit | Tool schemas | Typed I/O with evidence anchors |
| **Safety** | Optional middleware | Not in scope | By construction (checkpoint, rollback) |
| **Validation** | Runtime only | Schema validation | Static + runtime (L1–L4 conformance) |
| **Provenance** | Rare | Not in scope | Required (grounded claims) |
| **Relationship** | Can implement this standard | Complementary (transport layer) | Defines capability semantics |

## Social Media Templates

### Twitter/X

```
Releasing Agent Capability Standard — an open spec for AI agents that don't break in production.

36 atomic capabilities · Type-safe workflow composition · Grounded world models · Trust-aware conflict resolution

Apache 2.0 · Reference validator included

github.com/synaptiai/agent-capability-standard
```

### LinkedIn

```
We're open-sourcing Agent Capability Standard, a formal specification for building reliable AI agent systems.

The problem: Most agent systems fail silently in production. Composition is implicit, state is ungrounded, and safety is retrofitted.

Our approach: 36 atomic capabilities across 9 cognitive layers, composed through a type-safe workflow DSL with structural safety (checkpoints, rollback, audit trails).

What's included:
• Capability ontology with typed I/O contracts
• 12 reference workflows with gates and recovery loops
• Domain profiles for healthcare, manufacturing, data analysis
• Compiler-grade validator with patch suggestions
• EU AI Act and NIST AI RMF conformity assessments

Apache 2.0 licensed. Spec + reference implementation + Claude Code plugin.

github.com/synaptiai/agent-capability-standard
```

### Hacker News

```
Title: Agent Capability Standard – A formal spec for composable, safe AI agents (36 capabilities, 9 layers)

Show HN: We derived 36 atomic agent capabilities from first principles
(BDI, SOAR, ReAct). They compose into workflows through a type-safe DSL
with checkpoints, rollback, and trust-aware conflict resolution.

Think of it as the periodic table for agent capabilities—atoms compose
into molecules (workflows), and the validator catches errors statically.

github.com/synaptiai/agent-capability-standard
```

## Short Announcement Template

We're releasing an open standard for building agent systems that don't break in production: atomic capabilities + type-safe workflow composition + grounded world models + trust-aware conflict resolution. Reference implementation included.

## Media Contact

For press inquiries: [Open a GitHub issue](https://github.com/synaptiai/agent-capability-standard/issues) with the `press` label.
