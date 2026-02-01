# Executive Summary

**Project:** Agent Capability Standard (Grounded Agency)
**Version:** Plugin v1.1.0 / SDK v0.1.0
**Repository:** `synaptiai/agent-capability-standard`
**Date:** 2026-01-30 (Updated: 2026-02-01)
**Document:** 13 of 13 -- Analysis & Due Diligence Package

---

## Table of Contents

1. [One-Page Executive Summary](#1-one-page-executive-summary)
2. [Market Opportunity](#2-market-opportunity)
3. [Technology Differentiators](#3-technology-differentiators)
4. [Business Model](#4-business-model)
5. [Key Metrics](#5-key-metrics)
6. [Investment Highlights](#6-investment-highlights)

---

## 1. One-Page Executive Summary

### Problem

AI agents today lack three critical properties that prevent enterprise adoption at scale:

1. **No formal safety guarantees.** Existing agent frameworks (LangChain, AutoGen, CrewAI) focus on orchestration -- chaining LLM calls, managing tool access, and routing between models. None provides structural enforcement that mutations require checkpoints, that decisions must be backed by evidence, or that failures result in safe rollback. Safety is left to convention and prompt engineering.

2. **No auditable decision-making.** When an AI agent takes an action -- modifying a file, sending a network request, invoking an external API -- there is no standardized provenance trail linking the action to the evidence that justified it. Post-incident analysis relies on log scraping rather than structured audit records.

3. **No composable capability framework.** Agent capabilities are defined ad-hoc: each framework invents its own tool abstraction, its own permission model, and its own composition mechanism. There is no formal type system for capability inputs and outputs, no design-time validation that a workflow's steps are compatible, and no domain-parameterized abstraction that avoids the combinatorial explosion of domain-specific tool variants.

### Solution

The **Agent Capability Standard** (Grounded Agency) addresses all three gaps through a formal capability ontology:

- **36 atomic capabilities** across **9 cognitive layers** (PERCEIVE, UNDERSTAND, REASON, MODEL, SYNTHESIZE, EXECUTE, VERIFY, REMEMBER, COORDINATE), derived from first principles rather than empirical tool catalogs.
- **Safety-by-construction**: Mutation operations (`mutate`, `send`) structurally require checkpoints. The system is fail-closed by default -- unknown operations are classified as high-risk. Dual-layer enforcement (shell hooks + Python SDK permission callbacks) provides defense-in-depth.
- **Typed workflow composition**: 12 reference workflows with formal step bindings, gate conditions, recovery loops, and parallel groups. A type inference engine validates workflows at design time, with coercion transforms resolving type mismatches automatically.
- **Evidence grounding**: Every capability returns `evidence_anchors` (source references with confidence scores) and `provenance` (lineage tracking). The trust model applies source authority rankings with temporal decay.
- **Domain parameterization**: Instead of 99+ domain-specific capability variants (`detect-anomaly`, `detect-entity`, `detect-drift`), the ontology uses 36 parameterized capabilities (`detect(domain: anomaly)`), achieving the same expressiveness with 64% fewer nodes.

### Traction

| Channel | Status |
|---------|--------|
| Open source | GitHub: `synaptiai/agent-capability-standard` (Apache-2.0) |
| Claude Code plugin | Published on Synapti marketplace |
| Python SDK | `grounded-agency` on PyPI (v0.1.0) |
| Reference workflows | 12 production-ready patterns with typed bindings |
| Domain profiles | 7 profiles (healthcare, manufacturing, audio, vision, multimodal, data analysis, personal assistant) |
| OASF interoperability | 15 OASF categories mapped with bidirectional translation |
| Formal standard | v1.0.0 published with RFC 2119 normative language |
| Governance | SemVer, RFC process, compatibility rules, security policy |

---

## 2. Market Opportunity

### 2.1 Market Context

The AI agent ecosystem is undergoing a structural shift from simple chatbot interfaces to autonomous agents that take real-world actions. This shift creates three market-level demands:

1. **Safety infrastructure.** As agents gain tool access (file systems, APIs, databases, cloud infrastructure), the blast radius of incorrect actions grows. Enterprises require structural guarantees -- not just prompts that say "be careful" -- before deploying agents in production.

2. **Regulatory compliance.** The EU AI Act (2024), NIST AI Risk Management Framework, and ISO/IEC 42001 impose specific requirements on AI systems that perform autonomous actions: risk classification, human oversight, audit logging, transparency, and post-market monitoring. No existing agent framework provides native compliance infrastructure.

3. **Interoperability.** The fragmented agent landscape (LangChain, AutoGen, CrewAI, Semantic Kernel, custom implementations) creates vendor lock-in and integration friction. A capability-level standard enables agents built on different frameworks to interoperate through shared contracts.

### 2.2 Competitive Landscape

| Framework | Focus | Safety Model | Type System | Domain Profiles |
|-----------|-------|-------------|-------------|-----------------|
| LangChain | Tool orchestration | None (developer responsibility) | None | None |
| AutoGen | Multi-agent conversation | Basic role-based | None | None |
| CrewAI | Agent teams | Role-based permissions | None | None |
| Semantic Kernel | Plugin architecture | Basic permission model | Plugin contracts | None |
| **Grounded Agency** | **Formal capability ontology** | **Structural (checkpoint/evidence/rollback)** | **Full type system with inference** | **7 domain profiles** |

### 2.3 The Gap

There is a structural gap between academic research on agent architectures (BDI models, cognitive architectures, formal verification) and production agent frameworks (tool orchestration, prompt chaining, API wrappers). The Agent Capability Standard bridges this gap by providing:

- Formal rigor (typed contracts, graph-validated compositions) in a production-ready package (Python SDK, CLI tools, marketplace plugin).
- Safety guarantees that are enforced structurally (not by convention) and auditable (not just logged).
- Domain specialization without combinatorial explosion (parameterized capabilities, profile-driven configuration).

---

## 3. Technology Differentiators

### 3.1 Safety-by-Construction

Mutations are not permitted by default. The system requires an explicit checkpoint before any capability tagged `mutation: true` can execute. If the checkpoint is missing, the operation is blocked -- not warned, blocked. This is enforced at two independent layers:

- **Shell hook layer**: `pretooluse_require_checkpoint.sh` intercepts Claude Code tool invocations and checks for a `.claude/checkpoint.ok` marker file before allowing mutations.
- **Python SDK layer**: `GroundedAgentAdapter.permission_callback` classifies tool inputs using compiled regex patterns and requires `CheckpointTracker` state before granting permission.

Both layers must pass. Neither can be bypassed without modifying the hook configuration or SDK initialization. The system is fail-closed: unknown operations default to `risk: high` and require checkpoint verification.

### 3.2 Cognitive Layer Architecture

The 9 cognitive layers are derived from first principles of agent cognition, not from empirical tool catalogs:

| Layer | Role | Analogy |
|-------|------|---------|
| PERCEIVE | Acquire information from the environment | Senses |
| UNDERSTAND | Make sense of acquired information | Cognition |
| REASON | Plan, analyze, and critique | Executive function |
| MODEL | Represent and simulate the world | Mental model |
| SYNTHESIZE | Create new content and artifacts | Creative output |
| EXECUTE | Change the external world | Motor action |
| VERIFY | Ensure correctness and safety | Quality control |
| REMEMBER | Persist and recall state | Memory |
| COORDINATE | Interact with other agents | Social cognition |

This layered architecture provides a principled decomposition that is both complete (covers the full agent lifecycle) and minimal (no redundant layers).

### 3.3 Domain Parameterization

Traditional approaches create separate capabilities for each domain variant, leading to combinatorial explosion:

```
detect-anomaly, detect-entity, detect-drift, detect-pattern, ...
estimate-risk, estimate-impact, estimate-cost, estimate-duration, ...
forecast-risk, forecast-time, forecast-demand, forecast-capacity, ...
```

The Agent Capability Standard uses domain parameters on 36 atomic capabilities:

```
detect(domain: anomaly)    -- Same capability, different parameter
detect(domain: entity)     -- Shares input/output contract structure
measure(domain: risk)      -- Domain-specific validation via profiles
predict(domain: time)      -- Profile-driven trust and evidence policies
```

This reduces the ontology from 99+ nodes to 36 while preserving full expressiveness through domain profile configuration.

### 3.4 Formal Type System

Workflows are validated at design time through a type inference engine that:

1. Resolves `$ref` bindings across workflow steps.
2. Infers output types from capability I/O contracts in the ontology.
3. Validates consumer input schemas against producer output schemas.
4. Applies coercion transforms (defined in `schemas/transforms/*.yaml`) to resolve compatible type mismatches.
5. Reports type errors with step-level granularity and suggests automated patches.

This catches composition errors before execution -- a capability that no other agent framework provides.

### 3.5 Evidence Grounding

Every capability in the ontology returns structured evidence:

- **`evidence_anchors`**: Array of source references with `ref` (URI or identifier), `kind` (file, URL, API response, observation), and `confidence` (0.0--1.0).
- **`provenance`**: Lineage information linking the output to the inputs and intermediate steps that produced it.
- **`confidence`**: Aggregate confidence score reflecting source authority, temporal freshness, and corroboration.

The trust model applies source authority rankings (primary source > peer-reviewed > institutional > domain expert > crowd-sourced > AI-generated) with temporal decay (half-life: 14 days) and conflict resolution policies.

### 3.6 Trust Model

Source authority is not flat. The framework defines a six-tier trust hierarchy:

| Rank | Source Type | Base Weight |
|------|------------|-------------|
| 1 | Primary source (direct observation, official documentation) | 1.0 |
| 2 | Peer-reviewed (academic papers, audited reports) | 0.9 |
| 3 | Institutional (government databases, standards bodies) | 0.8 |
| 4 | Domain expert (recognized practitioners, verified experts) | 0.7 |
| 5 | Crowd-sourced (community knowledge bases, forums) | 0.5 |
| 6 | AI-generated (model outputs without human verification) | 0.3 |

Temporal decay ensures that stale evidence is progressively devalued. Conflicting evidence is resolved through configurable policies defined in domain profiles.

### 3.7 OASF Interoperability

The framework maps to the Open Agentic Schema Framework (OASF v0.8.0) through bidirectional translation covering 15 OASF categories. Mapping types include:

- **Direct**: 1:1 correspondence between an OASF skill code and a Grounded Agency capability.
- **Domain**: An OASF skill maps to a parameterized capability with a specific domain value.
- **Composition**: An OASF skill maps to a sequence of multiple capabilities.
- **Workflow**: An OASF skill maps to a complete reference workflow.

The `OASFAdapter` Python class provides programmatic translation in both directions with round-trip fidelity validation.

---

## 4. Business Model

### 4.1 Open Standard (Current)

The core ontology, schemas, workflows, and domain profiles are released under Apache-2.0. This establishes the standard as a public good, enabling adoption without licensing friction and encouraging community contribution.

**Deliverables:**
- `schemas/capability_ontology.yaml` -- 36-capability formal ontology
- `schemas/workflow_catalog.yaml` -- 12 reference workflows
- `schemas/profiles/*.yaml` -- 7 domain profiles
- `tools/*.py` -- 5 validation tools
- `spec/` -- Formal standard, whitepaper, governance model

### 4.2 Python SDK (Current)

The `grounded-agency` Python package (PyPI) provides Claude Agent SDK integration. Open source under Apache-2.0 (license harmonization completed -- TD-008 resolved).

**Modules:** `GroundedAgentAdapter`, `CapabilityRegistry`, `ToolCapabilityMapper`, `CheckpointTracker`, `EvidenceStore`, `OASFAdapter`, plus hook callbacks.

### 4.3 Enterprise (Planned)

Enterprise offerings would build on the open standard:

- **Custom domain profiles**: Industry-specific trust weights, risk thresholds, checkpoint policies, and evidence requirements for regulated sectors (healthcare, finance, defense, critical infrastructure).
- **Compliance tooling**: Automated compliance report generation mapping agent behavior to regulatory requirements (EU AI Act, NIST AI RMF, ISO 42001).
- **Custom workflows**: Domain-specific workflow patterns with validated step bindings and tested recovery loops.
- **Managed validation**: Hosted validation-as-a-service for continuous conformance checking of deployed agent configurations.

### 4.4 Certification (Planned)

An agent certification program would provide third-party validation that agent implementations conform to the standard:

- **Conformance levels**: L1 (Validator), L2 (Type), L3 (Contract), L4 (Patch) -- progressively stricter conformance requirements.
- **Certified profiles**: Verified domain profiles with tested evidence policies and trust configurations.
- **Compliance badges**: Machine-readable certification markers for agent deployments.

### 4.5 Marketplace (Planned)

A marketplace for community and commercial contributions:

- **Domain profiles**: Industry-specific configurations contributed by domain experts.
- **Workflow patterns**: Validated workflow compositions for common agent tasks.
- **Capability extensions**: New atomic capabilities following the extension governance process.
- **Interop adapters**: Adapters for additional agent frameworks beyond Claude Agent SDK.

---

## 5. Key Metrics

### 5.1 Architecture Metrics

| Metric | Value |
|--------|-------|
| Atomic capabilities | 36 |
| Cognitive layers | 9 |
| Workflow patterns | 12 |
| Domain profiles | 7 |
| Edge types | 7 |
| Ontology edges | 80+ |
| Entity classes | 24 (11 digital + 13 physical) |
| Entity subtypes | 57 |
| OASF categories mapped | 15 |

### 5.2 SDK Metrics

| Metric | Value |
|--------|-------|
| Core Python modules | 6 |
| Hook callback modules | 2 |
| Adapter modules | 1 (OASF) |
| Total Python SDK LOC | 2,568+ |
| Runtime dependencies | 1 (PyYAML) |
| Optional dependencies | 1 (claude-agent-sdk) |
| Dataclass models | 7 |
| Public API methods | 35+ |

### 5.3 Validation & Testing Metrics

| Metric | Value |
|--------|-------|
| Validation tools | 7 |
| Conformance test fixtures | 22 |
| YAML schema files | 28 |
| Skill implementations | 41 |
| Transform mappings | 7 |
| Conformance levels | 4 (L1--L4) |
| CI pipeline | `.github/workflows/ci.yml` (Python 3.10–3.12 matrix) |

### 5.4 Quality Metrics

| Metric | Value |
|--------|-------|
| Security risks identified | 16 total — **all 12 resolved** (PRs #89–#93); 4 P3 long-term items tracked |
| Technical debt items | 14 identified — **12 resolved**, 2 remaining (TD-006 workflow engine, TD-010 OASF gaps) |
| YAML safe_load violations | 0 |
| Unsafe deserialization | None detected |
| Default-deny coverage | Full (unknown operations -> high risk) |

### 5.5 Regulatory Alignment

| Framework | Coverage |
|-----------|----------|
| EU AI Act | Risk classification, audit logging, human oversight, transparency |
| NIST AI RMF | Govern, Map, Measure, Manage functions addressed |
| ISO/IEC 42001 | AI Management System controls mapped |
| HIPAA (Healthcare) | Healthcare domain profile with PHI protections |

---

## 6. Investment Highlights

### 6.1 First-Mover Advantage

The Agent Capability Standard is the first formal safety ontology for AI agents. While other frameworks focus on orchestration (how to chain tools together), this project defines the semantic and safety contracts that govern what agents can do, under what conditions, and with what evidence. There is no comparable offering in the market.

### 6.2 Minimal Dependency Surface

The entire Python SDK has exactly **one runtime dependency** (PyYAML). The optional dependency (claude-agent-sdk) is imported conditionally. This minimal surface reduces supply chain risk, simplifies auditing, and ensures long-term maintainability.

### 6.3 Production-Ready SDK

The Python SDK provides type-safe dataclasses, compiled regex classifiers, structured evidence collection, checkpoint lifecycle management, and OASF interoperability. It integrates with the Claude Agent SDK through a clean adapter pattern that does not require forking or monkey-patching the upstream SDK.

### 6.4 Regulatory Compliance Alignment

The framework's built-in capabilities directly address requirements from three major regulatory frameworks:

- **EU AI Act**: Risk classification (`risk` field on every capability), audit trail (`audit` capability), human oversight (`checkpoint` + `constrain`), transparency (`explain` + `critique`).
- **NIST AI RMF**: Continuous risk management (domain profiles), metrics and measurement (`measure` capability), documentation (formal standard, whitepaper).
- **ISO/IEC 42001**: AI management system controls mapped to capability ontology operations.

This alignment positions the standard as compliance infrastructure -- not just a development tool.

### 6.5 Extensible Architecture

The architecture supports extension along multiple dimensions without breaking existing deployments:

- **New capabilities**: Extension governance process with SemVer compatibility rules.
- **New domains**: Domain profiles configure trust, risk, and evidence policies without modifying the ontology.
- **New frameworks**: OASF adapter pattern is replicable for other agent frameworks.
- **New workflows**: Workflow DSL v2 supports composition of any ontology-defined capabilities.

### 6.6 Quantitative Summary

| Dimension | Evidence |
|-----------|----------|
| **Completeness** | 36 capabilities covering 9 cognitive layers -- derived from first principles, validated against OASF (15 categories) |
| **Safety** | Dual-layer enforcement, fail-closed default, 3 risk levels, checkpoint/evidence/rollback pattern |
| **Quality** | 7 validation tools, 22 conformance fixtures, 28 YAML schemas, CI pipeline, 12/14 debt items resolved, all 12 security items resolved |
| **Scale** | 2,568+ LOC SDK, 1,912-line ontology, 1,909-line workflow catalog, 41 skill implementations |
| **Standards** | Formal standard (RFC 2119), whitepaper, governance model, security policy |
| **Ecosystem** | PyPI package, Claude Code plugin, Synapti marketplace, GitHub repository |

---

*Document 13 of 13 -- Agent Capability Standard Analysis & Due Diligence Package*
*Generated: 2026-01-30 | Updated: 2026-02-01 | Tool: Claude Code (Opus 4.5)*
*Repository: synaptiai/agent-capability-standard*
