# Roadmap

The Standard and the plugin have separate version numbers. The Standard is the
specification. The plugin is the reference implementation: the validator, the
executor, the skills, the hooks and the Python package. Plugin 2.0.0 implements
Standard 1.1.0.

For the full list of changes, see the [specification changelog](CHANGELOG.md)
and the [project changelog](../CHANGELOG.md).

## Standard

| Version | Date | Status |
|---------|------|--------|
| [1.1.0](STANDARD-v1.1.0.md) | 2026-10-28 | Candidate Standard, current |
| [1.0.0](STANDARD-v1.0.0.md) | 2026-01-24 | Supported |
| 1.2.0 | Not scheduled | Planned |

Standard 1.1.0 was accepted by [RFC-0003](RFC-0003-orchestration-extensions.md)
and [RFC-0004](RFC-0004-agent-identity.md). It adds:

- a condition expression language for conditions, gates and failure-mode
  triggers;
- defined semantics for ontology edges and step safety flags;
- a diagnostic model with severities and warning codes;
- orchestration extensions that a workflow opts into: triggers, handler steps,
  recovery and escalation, waits, approval, delegation, quorum and sender
  identity.

[Appendix C](STANDARD-v1.1.0.md#appendix-c-changes-from-100) of the 1.1.0 text
lists every change from 1.0.0.

Standard 1.2.0 has one proposal so far:
[RFC-0002](RFC-0002-agent-reliability-profile.md) (Draft), which adds
cross-session behavioural reliability for agents.

## Plugin and tools

| Version | Date | Main changes |
|---------|------|--------------|
| 2.0.0 | 2026-10-29 | Implements Standard 1.1.0. The validator and the executor are one Rust core, used by `tools/validate_workflows.py` and by the Python package. |
| 1.2.0 | 2026-02-04 | Workflow execution engine; multi-agent coordination runtime (delegate, synchronize, invoke); OASF mapping and extension mechanism; vision, audio and multimodal profiles; EU AI Act, NIST AI RMF and ISO 42001 documents. |
| 1.0.0 to 1.1.1 | 2026-01-24 to 2026-01-27 | Early releases, listed in the [project changelog](../CHANGELOG.md). |

## Next

Planned work is tracked in three
[GitHub milestones](https://github.com/synaptiai/agent-capability-standard/milestones).
The open items are listed below.

### Hardening and developer experience

- [Standalone description-to-contract CLI tool](https://github.com/synaptiai/agent-capability-standard/issues/103)

### Runtime and ecosystem

- [Streaming events for real-time evidence collection](https://github.com/synaptiai/agent-capability-standard/issues/77)
- [Trust calibration tooling](https://github.com/synaptiai/agent-capability-standard/issues/78)
- [Domain profile marketplace](https://github.com/synaptiai/agent-capability-standard/issues/79)
- [Automated compliance reporting](https://github.com/synaptiai/agent-capability-standard/issues/80)
- [Plugin SDK for third-party extensions](https://github.com/synaptiai/agent-capability-standard/issues/81)

### Standards and scale

- [Industry standard adoption (ISO/IEC candidate)](https://github.com/synaptiai/agent-capability-standard/issues/82)
- [Multi-language SDKs (TypeScript, Rust, Go, Java)](https://github.com/synaptiai/agent-capability-standard/issues/83)
- [Certification program for AI agents](https://github.com/synaptiai/agent-capability-standard/issues/84)
- [Federated trust networks](https://github.com/synaptiai/agent-capability-standard/issues/85)
- [Formal verification of workflow compositions](https://github.com/synaptiai/agent-capability-standard/issues/86)
- [Pluggable safety backends](https://github.com/synaptiai/agent-capability-standard/issues/88)

## Under consideration

These ideas are not scheduled and have no issue yet.

- Visual workflow builder
- Cloud-hosted validation API
- Runtime adapters for other agent frameworks, such as LangChain, CrewAI
  and AutoGPT
- A formal specification of the multi-agent coordination protocol
- Runtime telemetry and observability hooks
- More coercion mappings in the transform coercion registry
