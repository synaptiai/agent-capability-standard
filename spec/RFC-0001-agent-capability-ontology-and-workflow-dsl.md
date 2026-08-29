# RFC-0001: Agent capability ontology + type-safe workflow DSL
**Status:** Draft  
**Target:** Standard v1.0.0  
**Date:** 2026-01-24

## Summary
This RFC proposes a standards-grade foundation for production agent systems:
atomic capability ontology + workflow DSL + world modeling schemas + trust/identity policies + compiler-grade validator.

## Motivation
Agents fail in production primarily due to:
- implicit composition (no contracts)
- unreliable state (no provenance)
- identity conflation (no policy)
- undefined conflict resolution (no trust model)
- unsafe mutations (no checkpointing/rollback)

## Goals
- Make reliability structural, not emergent.
- Enable composable capability libraries.
- Make workflows statically checkable and patchable.

## Non-goals
- Mandating any specific LLM vendor/tooling.
- Full formal verification (out of scope for v1).

## Key decisions
1) **Atomic capabilities** vs monolithic skills
2) **Typed binding DSL** with ambiguity gating
3) **World state derived from observations**
4) **Trust and identity as first-class policies**
5) **Validator emits patches** rather than only errors

## Backward compatibility
Not applicable: this RFC defines the initial publication of the standard, so
there is no prior version to remain compatible with. Every guarantee it
establishes — forward compatibility through ignored unknown fields, backward
compatibility for existing workflows and capability semantics, and the schema
evolution table — is stated in §11 and applies from v1.0.0 onward.

## Conformance test updates
Conformance levels L1–L4 are defined by this RFC rather than modified by it.
The initial fixture set covers each level: positive fixtures that MUST pass,
negative fixtures that MUST fail with a specific error code, and patch fixtures
carrying expected coercion suggestions, run by `scripts/run_conformance.py`.

## Alternatives considered
- Pure agent frameworks without schemas (fails in production)
- Hard-coded pipelines (non-composable)
- Full theorem-proving (too heavy for adoption)

## Open questions
- Standardizing multi-agent coordination protocol
- Canonical adapters for common toolchains

