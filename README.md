# Agent Capability Ontology + Workflow DSL (v1.0.0)

This repository contains a publish-ready specification and reference implementation for:

- **Atomic capability ontology** (composable agent primitives)
- **Workflow DSL** (composition: bindings, gates, recovery loops, parallel groups)
- **World state + event schemas** (grounded observations, provenance, uncertainty)
- **Trust + identity policies** (authority ranking, alias scoring, merge/split)
- **Compiler-grade validator** (schema resolution, type inference, consumer input checking, patch suggestions)

**Status:** Candidate Standard v1.0.0  
**Release date:** 2026-01-24

## What you get
- A standards-grade spec: `docs/STANDARD-v1.0.0.md`
- An RFC-style motivation + design record: `docs/RFC-0001-*.md`
- A whitepaper suitable for Arxiv/Medium: `docs/WHITEPAPER.md`
- Conformance + test requirements: `docs/CONFORMANCE.md`
- Governance + versioning policy: `docs/GOVERNANCE.md`
- Security model + disclosure process: `docs/SECURITY.md`

## Reference implementation
The reference implementation lives in the `claude_world_modeling_skill_system` folder inside the v10 bundle.
It includes the validator and canonical schemas.

## How to contribute
Start with `docs/GOVERNANCE.md`.

