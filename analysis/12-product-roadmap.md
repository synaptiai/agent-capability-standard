# Product Roadmap

## Agent Capability Standard (Grounded Agency)

**Document Version:** 1.1.0
**Last Updated:** 2026-02-01
**Scope:** Full product roadmap covering current state, short-term plans, medium-term initiatives, long-term vision, competitive positioning, and strategic priorities.

---

## Table of Contents

1. [Current State (v1.0.0 -- v1.0.5)](#1-current-state-v100--v105)
2. [Short-Term Roadmap (v1.1.0)](#2-short-term-roadmap-v110)
3. [Medium-Term Roadmap (v1.2.0)](#3-medium-term-roadmap-v120)
4. [Long-Term Vision (v2.0+)](#4-long-term-vision-v20)
5. [Competitive Landscape](#5-competitive-landscape)
6. [Strategic Priorities](#6-strategic-priorities)

---

## 1. Current State (v1.0.0 -- v1.1.0)

The Agent Capability Standard reached its initial publication candidate (v1.0.0) on 2026-01-24. Subsequent patch releases through v1.0.5 hardened the foundation across six major deliverable areas. The v1.1.0 release (2026-02-01) delivered all planned hardening items: CI pipeline, expanded conformance testing (22 fixtures), CLI scaffolder, checkpoint persistence, JSON Schema validation, license harmonization, performance optimization, and shell hook hardening.

### 1.1 Capability Ontology

**36 atomic capabilities** organized across **9 cognitive layers**, defined in `schemas/capability_ontology.yaml` (1,911 lines of formal specification).

| Layer | Count | Capabilities | Purpose |
|-------|-------|--------------|---------|
| PERCEIVE | 4 | retrieve, search, observe, receive | Information acquisition |
| UNDERSTAND | 6 | detect, classify, measure, predict, compare, discover | Making sense of information |
| REASON | 4 | plan, decompose, critique, explain | Planning and analysis |
| MODEL | 5 | state, transition, attribute, ground, simulate | World representation |
| SYNTHESIZE | 3 | generate, transform, integrate | Content creation |
| EXECUTE | 3 | execute, mutate, send | Changing the world |
| VERIFY | 5 | verify, checkpoint, rollback, constrain, audit | Correctness assurance |
| REMEMBER | 2 | persist, recall | State persistence |
| COORDINATE | 4 | delegate, synchronize, invoke, inquire | Multi-agent interaction |

Each capability has a full input/output contract with typed schemas, risk classification, edge relationships (requires, enables, precedes, conflicts_with, alternative_to, specializes, soft_requires), and evidence anchor requirements. Domain specialization is achieved through parameters rather than separate capability variants -- `detect(domain: anomaly)` instead of `detect-anomaly`.

### 1.2 Reference Workflow Patterns

**12 composed workflow patterns** in `schemas/workflow_catalog.yaml` providing production-ready compositions with gates, recovery loops, parallel groups, and typed bindings:

| Workflow | Goal | Risk Level |
|----------|------|------------|
| `monitor_and_replan` | Detect world changes and trigger replanning | Medium |
| `clarify_intent` | Resolve ambiguous user requests | Low |
| `debug_code_change` | Safely diagnose and fix bugs/regressions | High |
| `world_model_build` | Construct structured world model with dynamics | Low |
| `capability_gap_analysis` | Assess systems for missing capabilities | Medium |
| `digital_twin_sync_loop` | Synchronize digital twin state with drift detection | High |
| `digital_twin_bootstrap` | Initialize digital twin and run first sync | High |
| `analyze` | Examine data thoroughly | Medium |
| `mitigate` | Reduce identified risks | High |
| `optimize` | Iteratively improve through discovery | Medium |
| `orchestrate` | Coordinate multiple agents | High |
| `security_audit` | Audit systems for vulnerabilities | Medium |

The Workflow DSL (v2) supports bindings, conditions, gates, recovery loops, and parallel groups with full type inference.

### 1.3 Python SDK (grounded-agency v0.1.0)

The `grounded_agency/` Python package provides Claude Agent SDK integration with **6 core modules**:

| Module | File | Purpose |
|--------|------|---------|
| `GroundedAgentAdapter` | `adapter.py` | Main entry point wrapping SDK options with safety layer |
| `CapabilityRegistry` | `capabilities/registry.py` | Loads and queries capability ontology |
| `ToolCapabilityMapper` | `capabilities/mapper.py` | Maps SDK tools to capability metadata |
| `CheckpointTracker` | `state/checkpoint_tracker.py` | Manages checkpoint lifecycle for mutation safety |
| `EvidenceStore` | `state/evidence_store.py` | Collects evidence anchors from tool executions |
| `OASFAdapter` | `adapters/oasf.py` | OASF compatibility layer |

Additional support modules include hook callbacks (`hooks/evidence_collector.py`, `hooks/skill_tracker.py`) for real-time evidence collection and skill invocation tracking.

### 1.4 Domain Profiles

**7 domain profiles** in `schemas/profiles/` providing domain-specific trust weights, risk thresholds, checkpoint policies, and evidence requirements:

| Profile | File | Focus |
|---------|------|-------|
| Audio | `audio.yaml` | Audio processing and speech analysis |
| Data Analysis | `data_analysis.yaml` | Data pipelines and analytical workflows |
| Healthcare | `healthcare.yaml` | Clinical and healthcare-specific safety |
| Manufacturing | `manufacturing.yaml` | Industrial and manufacturing automation |
| Multimodal | `multimodal.yaml` | Cross-modal (vision + audio + text) workflows |
| Personal Assistant | `personal_assistant.yaml` | Consumer-facing assistant interactions |
| Vision | `vision.yaml` | Image and video processing |

Each profile is validated against `profile_schema.yaml` to ensure structural conformance.

### 1.5 Validation Tools

**7 validation tools** in `tools/` providing compiler-grade checking:

| Tool | Purpose |
|------|---------|
| `validate_workflows.py` | Validates workflows against ontology (L1-L4 conformance) |
| `validate_profiles.py` | Validates domain profiles against schema |
| `validate_skill_refs.py` | Validates skill file references (no phantom paths) |
| `validate_ontology.py` | Validates ontology graph (orphans, cycles, symmetry) |
| `validate_transform_refs.py` | Validates transform `mapping_ref` paths (no broken refs) |
| `validate_yaml_util_sync.py` | Validates YAML utility sync (`safe_yaml.py` ↔ `yaml_util.py`) |
| `sync_skill_schemas.py` | Syncs skill-local schemas from ontology |

The workflow validator supports `$ref` resolution, type inference, consumer input schema checking, and automated patch suggestions with optional diff output.

### 1.6 OASF Interoperability

**15 OASF categories mapped** in `schemas/interop/oasf_mapping.yaml`, providing bidirectional translation between the Open Agentic Schema Framework (OASF v0.8.0) and the Grounded Agency capability ontology. Mapping types include direct (1:1 correspondence), domain (parameter specialization), composition (multiple capabilities), and workflow (composed pattern mapping).

### 1.7 Claude Code Plugin

The plugin delivers safety enforcement through Claude Code hooks:

| Hook | File | Enforcement |
|------|------|-------------|
| PreToolUse (Write/Edit) | `pretooluse_require_checkpoint.sh` | Requires checkpoint marker before mutations |
| PostToolUse (Skill) | `posttooluse_log_tool.sh` | Logs skill invocations to `.claude/audit.log` |

Configuration is managed through `hooks/hooks.json` with shell-based enforcement scripts.

### 1.8 Conformance Testing Framework

**22 test fixtures** providing positive and negative conformance tests (expanded from 5 in v1.0.5 to 22 in v1.1.0):

| Fixture | Type | Tests |
|---------|------|-------|
| `pass_reference.workflow_catalog.yaml` | Positive | Valid workflow passes all checks |
| `fail_unknown_capability.workflow_catalog.yaml` | Negative | Unknown capability reference |
| `fail_bad_binding_path.workflow_catalog.yaml` | Negative | Invalid binding path |
| `fail_consumer_contract_mismatch.workflow_catalog.yaml` | Negative | Type mismatch at consumer |
| `fail_ambiguous_untyped.workflow_catalog.yaml` | Negative | Ambiguous untyped node |

Expectations are codified in `tests/EXPECTATIONS.json` for automated conformance runs via `scripts/run_conformance.py`.

### 1.9 World State and Trust Model

- **World state schema** with entity taxonomy, observation events, provenance tracking, uncertainty modeling, and retention policies
- **Trust model** with authority weights, confidence scores, temporal decay, and field-specific authority ranking
- **Identity resolution policy** for entity deduplication and cross-source fusion

### 1.10 Additional Deliverables

- **Formal standard** (`spec/STANDARD-v1.0.0.md`) with normative language (RFC 2119)
- **Whitepaper** (`spec/WHITEPAPER.md`) with motivation, design rationale, and evaluation approach
- **Governance model** (`spec/GOVERNANCE.md`) with SemVer, RFC process, and compatibility rules
- **Security policy** (`spec/SECURITY.md`) for vulnerability reporting
- **40 skill implementations** in `skills/` (36 atomic + 4 workflow compositions)
- **Perspective Validation Checklist (PVC)** system for multi-perspective reviews

---

## 2. Short-Term Roadmap (v1.1.0) -- **COMPLETED 2026-02-01**

**Target:** Q2 2026 → **Delivered: 2026-02-01** (ahead of schedule)
**Theme:** Hardening, automation, and developer experience

### 2.1 Conformance Test Expansion (20+ Fixtures) -- **COMPLETED**

**Priority:** Critical
**Effort:** Medium
**Status:** **Delivered** -- 22 fixtures covering all 4 conformance levels.

Expand the conformance test suite from 5 to 20+ fixtures to cover:
- All 4 conformance levels (L1 Validator, L2 Type, L3 Contract, L4 Patch)
- Edge cases in binding resolution (nested refs, circular bindings, optional fields)
- Recovery loop validation (correct rollback trigger semantics)
- Parallel group validation (dependency ordering, fan-out/fan-in correctness)
- Gate condition evaluation (boolean expressions, threshold comparisons)
- Cross-workflow invocation (`invoke-workflow` reference integrity)
- Patch suggestion accuracy (deterministic transform validation)

### 2.2 CI/CD Pipeline (GitHub Actions) -- **COMPLETED**

**Priority:** Critical
**Effort:** Medium
**Status:** **Delivered** -- `.github/workflows/ci.yml` runs all 7 validators, conformance tests, pytest, mypy, and ruff.

Establish automated quality gates:
- Run all 5 validators on every PR (`validate_workflows`, `validate_profiles`, `validate_skill_refs`, `validate_ontology`, `sync_skill_schemas`)
- Execute conformance test suite with pass/fail reporting
- YAML lint and schema validation for all schema files
- SDK unit tests (`pytest tests/`) with coverage reporting
- Automated release tagging aligned with SemVer governance

### 2.3 CLI Scaffolder -- **COMPLETED**

**Priority:** High
**Effort:** Medium
**Status:** **Delivered** -- `tools/scaffold.py` generates capabilities, workflows, and profiles from templates.

Build a CLI tool to generate new capabilities, workflows, and profiles from templates:

```bash
# Generate a new capability with skill, schema, and ontology entry
acs scaffold capability --name "negotiate" --layer COORDINATE

# Generate a new workflow from a pattern
acs scaffold workflow --name "incident_response" --pattern mitigate

# Generate a new domain profile
acs scaffold profile --domain "fintech"
```

This directly addresses the multi-file update burden documented in CLAUDE.md (ontology, skill, counts across 10+ files, schema sync).

### 2.4 Checkpoint Persistence -- **COMPLETED**

**Priority:** High
**Effort:** Medium
**Status:** **Delivered** -- File-based backend in `.checkpoints/`; `CheckpointTracker` bridges shell and SDK layers.

The current `CheckpointTracker` is in-memory only. Add durable persistence backends:
- **File-based backend** (JSON/YAML checkpoint files in `.checkpoints/`)
- **SQLite backend** for structured queries and checkpoint history
- **Pluggable interface** (`CheckpointBackend` ABC) for custom storage implementations
- Checkpoint retention policies (time-based, count-based cleanup)

### 2.5 JSON Schema Validation for YAML Files -- **COMPLETED**

**Priority:** High
**Effort:** Low
**Status:** **Delivered** -- JSON Schema (Draft 2020-12) validation for ontology and workflow catalog; IDE integration enabled.

Currently, YAML validation is custom Python code. Migrate to standard JSON Schema validation:
- Generate JSON Schema from ontology definitions
- Validate `capability_ontology.yaml` against its own meta-schema
- Validate `workflow_catalog.yaml` against workflow DSL schema
- Enable IDE integration (VS Code YAML extension with schema associations)

### 2.6 License Harmonization -- **COMPLETED**

**Priority:** Medium
**Effort:** Low
**Status:** **Delivered** -- Apache-2.0 aligned across `pyproject.toml`, `LICENSE`, and trove classifiers; license check in CI.

Ensure Apache-2.0 license is consistently applied:
- Add SPDX headers to all source files
- Verify LICENSE file is referenced in all package manifests
- Update CITATION.cff with complete contributor attribution
- Add license check to CI pipeline

### 2.7 Performance Optimization (Evidence Store Indexing) -- **COMPLETED**

**Priority:** Medium
**Effort:** Medium
**Status:** **Delivered** -- O(1) priority eviction with CRITICAL/NORMAL/LOW buckets; hash-based indexing.

The `EvidenceStore` currently uses linear search. Optimize for production workloads:
- Add hash-based indexing on evidence anchor IDs
- Implement bloom filter for fast negative lookups
- Add time-range queries for temporal evidence retrieval
- Benchmark with realistic evidence volumes (1K, 10K, 100K anchors)

### 2.8 Shell Hook Hardening -- **COMPLETED**

**Priority:** Medium
**Effort:** Low
**Status:** **Delivered** -- 21 shell patterns aligned with SDK; checkpoint JSON validation with timestamp freshness; HMAC chain integrity on audit log.

Align shell-based hooks (`pretooluse_require_checkpoint.sh`, `posttooluse_log_tool.sh`) with SDK regex patterns:
- Synchronize checkpoint detection regex between shell hooks and `CheckpointTracker`
- Add error handling for missing `.claude/` directory
- Validate hook JSON configuration on startup
- Add integration tests for hook invocation paths

---

## 3. Medium-Term Roadmap (v1.2.0)

**Target:** Q4 2026
**Theme:** Runtime execution, multi-agent coordination, and ecosystem growth

### 3.1 Multi-Agent Coordination Runtime

**Priority:** Critical
**Effort:** High

Build runtime support for the COORDINATE layer capabilities (delegate, synchronize, invoke, inquire):
- **Agent registry** with capability advertisement (what each agent can do)
- **Task delegation protocol** with typed contracts between agents
- **Synchronization primitives** (barriers, locks, consensus)
- **Cross-agent evidence sharing** with trust propagation
- **Agent-to-agent audit trails** with full lineage

This directly enables the `orchestrate` workflow pattern at runtime.

### 3.2 Streaming Events for Real-Time Evidence Collection

**Priority:** High
**Effort:** High

Add streaming event ingestion for real-time evidence:
- **Server-Sent Events (SSE)** for continuous evidence streams
- **Event schema** aligned with world state observation model
- **Backpressure handling** for high-volume evidence sources
- **Windowed aggregation** for evidence confidence scoring over time
- Integration with `EvidenceStore` for persistent collection

### 3.3 Trust Calibration Tooling

**Priority:** High
**Effort:** Medium

Measure actual vs. predicted trust to detect miscalibrated trust weights:
- **Calibration reports** comparing trust scores against ground truth outcomes
- **Temporal decay analysis** (are decay rates appropriate for each domain?)
- **Authority weight tuning** (suggest adjustments based on historical accuracy)
- **Calibration dashboard** for visual inspection of trust distributions
- Domain-specific calibration benchmarks for each profile

### 3.4 Workflow Execution Engine

**Priority:** Critical
**Effort:** High

Build a runtime interpreter for `workflow_catalog.yaml`:
- **Step executor** that maps capability names to tool invocations
- **Binding resolver** that threads outputs through input schemas at runtime
- **Gate evaluator** that checks conditions and routes execution
- **Recovery loop runtime** with automatic rollback on gate failure
- **Parallel group scheduler** with dependency-aware execution
- **Progress tracking** with real-time workflow state reporting
- **Replay support** for debugging failed workflow runs

### 3.5 Advanced OASF Integration

**Priority:** Medium
**Effort:** Medium

Extend the current 15-category mapping to full bidirectional synchronization:
- **Bidirectional sync** (import OASF skills, export Grounded Agency capabilities)
- **Proposed safety extensions** adoption (per `docs/proposals/OASF_SAFETY_EXTENSIONS.md`)
- **Automated mapping validation** (detect drift between OASF versions)
- **OASF conformance test suite** for interop validation
- Track OASF version updates (currently mapped to v0.8.0)

### 3.6 Domain Profile Marketplace

**Priority:** Medium
**Effort:** Medium

Enable community contribution and discovery of domain profiles:
- **Profile registry** with versioning and dependency tracking
- **Profile validation** before marketplace listing
- **Profile composition** (inherit from base, override specific settings)
- **Usage analytics** (which profiles are most adopted)
- Initial target: expand from 7 to 25+ profiles covering finance, legal, education, logistics, energy, and more

### 3.7 Automated Compliance Reporting

**Priority:** Medium
**Effort:** Medium

Generate audit-ready compliance reports from workflow executions:
- **Decision lineage reports** tracing each action to evidence and capability
- **Checkpoint coverage reports** showing mutation safety compliance
- **Trust resolution reports** documenting how conflicts were resolved
- **Conformance level reports** (L1-L4) for each workflow
- Export formats: PDF, JSON, HTML

### 3.8 Plugin SDK for Third-Party Extensions

**Priority:** Medium
**Effort:** High

Enable third-party developers to extend the standard:
- **Extension points** for custom capabilities, validators, and storage backends
- **Plugin manifest** format with dependency declarations
- **Plugin lifecycle** (install, activate, deactivate, uninstall)
- **Sandboxed execution** for untrusted plugins
- **Plugin testing framework** with mock capabilities and evidence stores

---

## 4. Long-Term Vision (v2.0+)

**Target:** 2027+
**Theme:** Industry standardization, multi-language support, and formal verification

### 4.1 Industry Standard Adoption (ISO/IEC Candidate)

Position the Agent Capability Standard for formal standardization:
- Prepare ISO/IEC 23053 (Framework for AI systems using ML) compatibility documentation
- Engage with ISO/IEC JTC 1/SC 42 (Artificial Intelligence) working groups
- Draft a formal submission package with normative references, conformance requirements, and test suite
- Establish liaison relationships with existing AI safety standards bodies (NIST AI RMF, IEEE 7000 series)
- Target timeline: ISO/IEC New Work Item Proposal (NWIP) by 2028

### 4.2 Multi-Language SDKs

Extend beyond the Python SDK to cover the primary agent development ecosystems:

| Language | Priority | Rationale |
|----------|----------|-----------|
| TypeScript | High | Dominant in web-based agent systems, MCP ecosystem |
| Rust | Medium | Performance-critical agent runtimes, safety guarantees |
| Go | Medium | Infrastructure agents, Kubernetes operators |
| Java/Kotlin | Lower | Enterprise agent deployments |

Each SDK must provide:
- Full capability registry with ontology loading
- Checkpoint/evidence management
- Workflow DSL interpreter
- Hook integration for the target platform's agent framework

### 4.3 Certification Program for AI Agents

Establish a formal certification program:
- **Level 1 (Grounded):** Agent passes L2 conformance, implements checkpoint-before-mutation
- **Level 2 (Auditable):** Agent passes L3 conformance, maintains evidence lineage, generates audit trails
- **Level 3 (Safe):** Agent passes L4 conformance, implements recovery loops, passes adversarial testing
- **Certification toolkit** with automated test harness
- **Certification registry** with public listing of certified agents
- **Annual recertification** aligned with standard version updates

### 4.4 Federated Trust Networks

Enable cross-organization trust for multi-party agent systems:
- **Trust federation protocol** for exchanging trust scores between organizations
- **Trust attestation format** (signed trust assertions with expiry)
- **Cross-domain evidence sharing** with privacy-preserving aggregation
- **Trust conflict resolution** across organizational boundaries
- **Federated identity resolution** for entity matching across systems
- Reference architecture for healthcare data exchange, supply chain coordination, and financial compliance

### 4.5 Formal Verification of Workflow Compositions

Apply formal methods to prove workflow safety properties:
- **Type-level safety proofs** for binding chains (no runtime type errors)
- **Liveness verification** (workflows always terminate or explicitly diverge)
- **Checkpoint coverage verification** (every mutation path has a checkpoint)
- **Conflict-freedom verification** (no conflicting capabilities in parallel groups)
- Integration with model checkers (TLA+, Alloy, or domain-specific verifier)
- Target: verify all 12 reference workflows as a baseline

### 4.6 Automated Capability Discovery

Detect needed capabilities from task descriptions without manual mapping:
- **Task-to-capability classifier** trained on workflow patterns
- **Gap detection** (identify when a task requires capabilities not in the ontology)
- **Capability suggestion engine** (recommend new atomic capabilities based on task analysis)
- **Workflow synthesis** (automatically compose workflow from task description)
- Integration with LLM-based planning to bridge natural language and typed contracts

### 4.7 Pluggable Safety Backends

Support different safety enforcement strategies for different deployment contexts:
- **Strict mode** (current behavior -- hard enforcement of all safety constraints)
- **Advisory mode** (log violations but don't block -- for development/testing)
- **Graduated mode** (enforcement level increases with risk level)
- **Custom backends** (organizations define their own enforcement policies)
- **Runtime safety policy negotiation** for multi-agent systems with different safety requirements

---

## 5. Competitive Landscape

### 5.1 OASF (Open Agent Skill Framework)

| Dimension | OASF | Grounded Agency |
|-----------|------|-----------------|
| **Focus** | Skill taxonomy and categorization | Capability ontology with safety semantics |
| **Safety model** | None (no checkpoint, evidence, or trust concepts) | Checkpoint-before-mutation, evidence grounding, trust-weighted resolution |
| **Composition** | Flat skill listing | Typed I/O contracts with workflow DSL |
| **Maturity** | v0.8.0 (pre-1.0) | v1.0.0 (candidate standard) |
| **Relationship** | Complementary -- we map 15 OASF categories | Grounded Agency adds the safety and composition layer OASF lacks |

**Strategic position:** Grounded Agency is not a competitor to OASF but a safety and composition layer on top. The OASF adapter (`grounded_agency/adapters/oasf.py`) enables bidirectional interoperability. OASF provides breadth of skill taxonomy; Grounded Agency provides depth of safety and formal composition.

### 5.2 LangChain / LangGraph

| Dimension | LangChain/LangGraph | Grounded Agency |
|-----------|---------------------|-----------------|
| **Focus** | Tool orchestration and chain composition | Formal capability ontology with safety contracts |
| **Safety model** | Optional callbacks/guardrails | Structural safety (checkpoints required for mutations) |
| **Composition** | Programmatic (Python/JS code) | Declarative (YAML DSL with typed bindings) |
| **Ontology** | No formal ontology; tools are arbitrary functions | 36 atomic capabilities with input/output schemas |
| **Provenance** | LangSmith tracing (separate product) | Built-in evidence anchors and audit lineage |

**Strategic position:** LangChain is an execution framework; Grounded Agency is a specification standard. They are complementary. A LangChain agent could implement Grounded Agency capabilities, gaining safety guarantees and typed contracts. The workflow execution engine (v1.2.0) will enable direct comparison of runtime features.

### 5.3 MCP (Model Context Protocol)

| Dimension | MCP | Grounded Agency |
|-----------|-----|-----------------|
| **Focus** | Transport layer for tool invocation | Capability semantics and safety model |
| **Scope** | How tools are called (protocol) | What tools mean (ontology) and how they compose safely |
| **Safety** | No safety model (transport is neutral) | Checkpoint, evidence, trust, and rollback semantics |
| **Composition** | None (single tool calls) | Workflow DSL with typed bindings and recovery loops |

**Strategic position:** MCP and Grounded Agency operate at different layers. MCP defines how tools are invoked; Grounded Agency defines what those invocations mean semantically and how they compose safely. The Claude Code plugin already uses MCP as its transport while adding Grounded Agency semantics on top.

### 5.4 AutoGen / CrewAI

| Dimension | AutoGen/CrewAI | Grounded Agency |
|-----------|----------------|-----------------|
| **Focus** | Multi-agent conversation and task delegation | Formal capability contracts and safety model |
| **Safety model** | Human-in-the-loop (optional) | Structural (checkpoints, evidence, trust) |
| **Agent definition** | Role-based (natural language descriptions) | Capability-based (typed ontology with contracts) |
| **Coordination** | Conversation-based | Formal COORDINATE layer (delegate, synchronize, invoke, inquire) |
| **Verification** | None | Conformance testing (L1-L4) |

**Strategic position:** AutoGen and CrewAI provide multi-agent execution frameworks with informal safety (human approval). Grounded Agency provides the formal specification layer that these frameworks lack. A CrewAI deployment could adopt the Grounded Agency ontology to gain typed contracts, evidence grounding, and structural safety -- transitioning from "hope-based" to "proof-based" safety.

### 5.5 Semantic Kernel (Microsoft)

| Dimension | Semantic Kernel | Grounded Agency |
|-----------|-----------------|-----------------|
| **Focus** | Enterprise AI orchestration | Open capability standard with safety model |
| **Ecosystem** | Microsoft-centric (Azure AI, Copilot) | Framework-agnostic, open standard |
| **Safety** | Azure AI Content Safety (service-based) | Structural safety (built into the ontology) |
| **Ontology** | Plugin/function model (no formal ontology) | 36 atomic capabilities with typed I/O schemas |
| **Governance** | Microsoft-controlled | Open RFC process with community input |

**Strategic position:** Semantic Kernel targets the Microsoft enterprise ecosystem. Grounded Agency is vendor-neutral and focuses on the specification layer that any orchestrator (including Semantic Kernel) could adopt. The formal ontology and safety model are the differentiators that no enterprise orchestration framework currently provides.

### 5.6 Competitive Summary Matrix

| Feature | Grounded Agency | OASF | LangChain | MCP | AutoGen | Semantic Kernel |
|---------|----------------|------|-----------|-----|---------|-----------------|
| Formal ontology | Yes (36 caps) | Partial | No | No | No | No |
| Typed I/O contracts | Yes | No | No | Partial | No | Partial |
| Checkpoint safety | Yes | No | No | No | No | No |
| Evidence grounding | Yes | No | No | No | No | No |
| Trust model | Yes | No | No | No | No | No |
| Workflow DSL | Yes | No | Yes | No | No | Yes |
| Recovery semantics | Yes | No | Partial | No | No | Partial |
| Conformance testing | Yes (L1-L4) | No | No | No | No | No |
| Multi-agent coord. | Planned | No | Yes | No | Yes | Partial |
| Open standard | Yes | Yes | OSS | Yes | OSS | OSS |

---

## 6. Strategic Priorities

### Priority 1: Safety Differentiation

**The moat is safety-by-construction.**

No other agent framework provides structural safety guarantees at the specification level. While competitors rely on optional guardrails, human-in-the-loop approval, or external safety services, Grounded Agency makes safety a structural property of the ontology itself.

Key investments:
- Checkpoint-before-mutation enforcement is non-negotiable
- Evidence grounding must be the default, not an opt-in
- Trust model with temporal decay prevents stale data from driving decisions
- Recovery loops ensure workflows can self-heal from failures
- Formal verification (v2.0+) will provide mathematical safety proofs

**Success metric:** Zero unrecoverable mutations in conformant agents.

### Priority 2: Developer Experience

**Make it easy to adopt -- or no one will adopt it.**

The current adoption path requires understanding the ontology, creating YAML files, updating capability counts across 10+ files, and running 5 separate validators. This friction must be reduced systematically.

Key investments:
- CLI scaffolder (v1.1.0) eliminates multi-file update burden
- JSON Schema integration enables IDE autocomplete and validation
- CI/CD pipeline automates quality gates
- Templates and generators reduce boilerplate
- Documentation improvements with guided tutorials and examples

**Success metric:** New capability addition takes less than 15 minutes end-to-end.

### Priority 3: Standards Track

**Position for ISO/IEC adoption to achieve lasting impact.**

The standard follows RFC 2119 normative language, has a formal governance model with SemVer versioning, and defines conformance levels (L1-L4). These are prerequisites for standards-track submission.

Key investments:
- Maintain backward compatibility across minor versions
- Build comprehensive conformance test suite (20+ fixtures in v1.1.0)
- Engage with ISO/IEC JTC 1/SC 42 and NIST AI RMF
- Publish peer-reviewed technical paper
- Build reference implementations in multiple languages

**Success metric:** ISO/IEC New Work Item Proposal submitted by 2028.

### Priority 4: Ecosystem Growth

**Domain profiles and workflow marketplace create network effects.**

The standard becomes more valuable as more domains are covered. Each new domain profile brings a community of practitioners who contribute workflows, validation rules, and trust calibration data.

Key investments:
- Domain profile marketplace (v1.2.0) enables community contribution
- Plugin SDK (v1.2.0) enables third-party extensions
- Workflow template library for common patterns
- Integration guides for popular agent frameworks
- Certification program (v2.0+) creates incentive for adoption

**Success metric:** 25+ domain profiles and 50+ community-contributed workflows by end of 2027.

### Priority 5: Enterprise Readiness

**Compliance tooling and audit reporting unlock enterprise adoption.**

Enterprise buyers need compliance documentation, audit trails, and certification. The standard's built-in audit capability and evidence lineage are strong foundations, but enterprise-grade reporting requires additional tooling.

Key investments:
- Automated compliance reporting (v1.2.0) with PDF/JSON/HTML export
- Decision lineage reports tracing every action to evidence
- Integration with enterprise audit systems (SIEM, GRC platforms)
- Certification program with public registry
- SOC 2 and ISO 27001 alignment documentation

**Success metric:** First enterprise production deployment with full audit compliance by Q1 2027.

---

## Appendix A: Release Timeline Summary

```
2026-01-24  v1.0.0  Initial publication candidate
2026-Q1     v1.0.x  Patch releases (hardening, docs, OASF integration)
2026-02-01  v1.1.0  ✓ COMPLETED — Conformance expansion (22 fixtures), CI/CD, CLI scaffolder,
                    checkpoint persistence, JSON Schema, license harmonization,
                    performance optimization, shell hook hardening
2026-Q4     v1.2.0  Workflow engine, multi-agent runtime, marketplace
2027-Q2     v1.3.0  Trust calibration, compliance reporting
2027-Q4     v2.0.0  Multi-language SDKs, certification program
2028+       v2.x    Standards track, formal verification, federation
```

## Appendix B: Risk Factors

| Risk | Impact | Mitigation |
|------|--------|------------|
| Low adoption due to learning curve | High | CLI scaffolder, templates, tutorials, IDE integration |
| Competing standards emerge | Medium | Maintain interop (OASF mapping), focus on safety differentiation |
| Breaking changes needed for v2.0 | Medium | Follow governance policy (deprecated fields accepted for 1 minor release) |
| Standards body process delays | Medium | Continue building community adoption independently |
| SDK quality issues | High | Comprehensive test suite, CI/CD, contributor guidelines |
| Domain profile quality variance | Medium | Validation tooling, marketplace review process |

## Appendix C: Key Dependencies

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| Python | 3.10+ | SDK runtime | Low (stable) |
| PyYAML | 6.x | YAML parsing | Low (stable) |
| Claude Agent SDK | Latest | Agent integration | Medium (evolving API) |
| OASF | 0.8.0 | Interoperability | Medium (pre-1.0) |
| JSON Schema | Draft 2020-12 | Schema validation | Low (stable) |

---

*This roadmap is a living document. Updates follow the open RFC process defined in `spec/GOVERNANCE.md`. Community contributions are welcomed through the standard GitHub issue and pull request workflow.*
