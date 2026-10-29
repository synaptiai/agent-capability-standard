# Roadmap

> For detailed product strategy and competitive analysis, see [analysis/12-product-roadmap.md](../analysis/12-product-roadmap.md).

## v1.0.0 — Initial Release (Released 2026-01-24) ✅

- 36 atomic capabilities across 9 cognitive layers
- Reference validator with type inference and patch suggestions
- 12 reference workflows in the workflow catalog
- Domain profiles for healthcare, manufacturing, data analysis, personal assistant
- Safety hooks (checkpoint enforcement, audit logging)
- Conformance test suite

## v1.0.4 — Domain Expansion (Released 2026-01-27) ✅

- Domain-specific workflow templates and automated profile validation
- Claude Agent SDK integration with safety patterns
- Benchmark suite for Grounded Agency validation
- Migration from 99 to 36 atomic capabilities with domain parameterization
- YAML-based capability ontology (migrated from JSON)
- Complete edge graph for orphan capabilities

## v1.0.5 — Interoperability (Released 2026-01-29) ✅

- OASF-to-Grounded-Agency capability mapping and compatibility adapter
- Modality handling for vision, audio, and multimodal domains
- Perspective validation checklist (PVC) system
- Self-contained skill dependencies

## v1.1.0 — In Progress 🔧

- [Standard v1.1.0](STANDARD-v1.1.0.md) (Candidate Standard), accepted by [RFC-0003](RFC-0003-orchestration-extensions.md) and [RFC-0004](RFC-0004-agent-identity.md); v1.0.0 remains supported
  - Condition expression language for conditions, gates and failure-mode triggers
  - Specified edge and safety-flag semantics
  - Diagnostic model with severities and warnings (W6xx)
  - Orchestration extensions (handlers, recovery and escalation, waits, approval, delegation, quorum, sender identity) specified and implemented in the reference validator and executor
- Reference validator moved to a Rust core (`core/`, compiled into `grounded_agency._core`), shared by `tools/validate_workflows.py` and the Python `WorkflowEngine`
- Multi-agent coordination runtime (delegate, synchronize, invoke)
- Workflow execution engine
- OASF GA extension mechanism for unmapped capabilities
- EU AI Act conformity assessment and NIST AI RMF profile
- ISO 42001 gap analysis and certification readiness
- Comprehensive analysis documentation package

## v1.1.0 — Planned

- Conformance test pack with CI automation
- Extended coercion mappings and schema-ref fixtures
- Official capability-to-skill scaffolder
- Plugin marketplace distribution

## v1.2.0 — Planned

- Multi-agent coordination protocol spec (formal)
- Streaming event ingestion patterns
- Formal trust calibration workflows
- Runtime telemetry and observability hooks

## v2.0.0 — Future Vision

- Cross-framework runtime adapter (LangChain, AutoGPT, CrewAI)
- Visual workflow builder
- Cloud-hosted validation API
- Certification program for conformance levels
