# Agent Capability Standard

> **Grounded Agency**: A framework for building AI agents that know what they don't know.

[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet?logo=anthropic)](https://github.com/synaptiai/synapti-marketplace)
[![Conformance](https://github.com/synaptiai/agent-capability-standard/actions/workflows/conformance.yml/badge.svg)](https://github.com/synaptiai/agent-capability-standard/actions/workflows/conformance.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](spec/STANDARD-v1.0.0.md)

```bash
# Install as Claude Code plugin
claude plugin marketplace add synaptiai/synapti-marketplace
claude plugin install agent-capability-standard
```

---

## What Is This?

**Agent Capability Standard** is the technical specification. **Grounded Agency** is the philosophy behind it.

Most AI agent systems fail in production because:
- Composition is implicit (no contracts between capabilities)
- State is ungrounded (no provenance for claims)
- Conflict resolution is undefined (no trust model)
- Safety is retrofitted (no checkpoints or rollback)

This standard fixes that by making reliability *structural*—not optional.

### The Core Idea

Every agent action should be:
1. **Grounded** — backed by evidence, not hallucination
2. **Auditable** — with provenance and lineage
3. **Safe** — mutations require checkpoints
4. **Composable** — typed contracts between capabilities

---

## Why This Matters

### The Problem

AI agents in production fail silently. When a retrieval step hallucinates, downstream actions proceed with bad data. When conflicts arise between sources, there's no resolution strategy. When mutations fail, there's no rollback.

These aren't edge cases—they're the norm. Most agent systems lack structural safeguards, so failures are discovered after the damage is done.

### The Cost

- **Debug time**: Hours tracing why an agent made a decision with no audit trail
- **Data corruption**: Unrecoverable state from failed mutations without checkpoints
- **Trust erosion**: Users lose confidence after unexplained failures
- **Compliance risk**: Auditors ask "why did the agent do X?" and you can't answer

### The Solution

This standard makes failures **visible and recoverable**:

- **Every claim traces to evidence** (or explicitly marks uncertainty)
- **Every mutation has a checkpoint** (rollback is always possible)
- **Every conflict has a resolution strategy** (trust model decides)
- **Every decision has lineage** (audit answers "why")

### When to Use This

| If you have... | This standard provides... |
|----------------|---------------------------|
| Agents that sometimes give wrong answers | Grounding with provenance trails |
| Workflows that fail mid-execution | Checkpoints and recovery loops |
| Multiple data sources that conflict | Trust-weighted conflict resolution |
| Compliance/audit requirements | Complete action lineage |
| Complex multi-step agent pipelines | Typed contracts between capabilities |
| Production systems where failures are costly | Safety by construction, not by hope |

---

## Quick Start

### Option 1: Claude Code Plugin (Recommended)

Install from the Synapti marketplace:

```bash
# Add the marketplace (one-time)
claude plugin marketplace add synaptiai/synapti-marketplace

# Install the plugin
claude plugin install agent-capability-standard
```

This gives you:
- 99 capability skills organized by layer
- Workflow validation commands
- Safety hooks (checkpoint enforcement, audit logging)

### Option 2: Standalone Validation

Use the validator independently:

```bash
# Clone the repository
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard

# Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install pyyaml

# Validate workflows
python tools/validate_workflows.py
# → VALIDATION PASS

# Run conformance tests
python scripts/run_conformance.py
# → Conformance PASSED (5/5)
```

**Next:** See [QUICKSTART.md](docs/QUICKSTART.md) for a guided walkthrough.

## What's Included

### 99 Atomic Capabilities

Organized across 8 layers with explicit input/output schemas and prerequisites:

| Layer | Count | Examples |
|-------|-------|----------|
| **PERCEPTION** | 4 | inspect, search, retrieve, receive |
| **MODELING** | 45 | detect-*, identify-*, estimate-*, world-state |
| **REASONING** | 20 | compare-*, plan, decide, critique, explain |
| **ACTION** | 12 | act-plan, generate-*, transform, send |
| **SAFETY** | 7 | verify, checkpoint, rollback, audit, constrain, mitigate, improve |
| **META** | 6 | discover-*, prioritize |
| **MEMORY** | 2 | persist, recall |
| **COORDINATION** | 3 | delegate, synchronize, invoke-workflow |

### 5 Reference Workflows

Production-ready workflow compositions with gates, recovery loops, and typed bindings:

| Workflow | Goal | Risk |
|----------|------|------|
| `debug_code_change` | Safely diagnose and fix bugs | High |
| `world_model_build` | Construct grounded world model | Low |
| `capability_gap_analysis` | Identify missing capabilities | Medium |
| `digital_twin_sync_loop` | Synchronize digital twin state | High |
| `digital_twin_bootstrap` | Initialize and run first sync | High |

### Canonical Schemas

- **Capability Ontology** — 99 capabilities with I/O contracts
- **Workflow DSL** — Typed bindings, gates, recovery loops
- **World State** — Observations with provenance and uncertainty
- **Trust Model** — Authority ranking with time decay

### Safety Hooks

Hooks implementing SAFETY layer capabilities:

| Hook | Capability | Purpose |
|------|------------|---------|
| `pretooluse_require_checkpoint.sh` | `checkpoint` | Enforce checkpoint before mutations |
| `posttooluse_log_tool.sh` | `audit` | Maintain audit trail |

## Documentation

### For Users

| Document | Purpose |
|----------|---------|
| [QUICKSTART.md](docs/QUICKSTART.md) | Validate a workflow in 10 minutes |
| [TUTORIAL.md](docs/TUTORIAL.md) | Build your first workflow (30 min) |
| [GLOSSARY.md](docs/GLOSSARY.md) | Key terms and definitions |
| [FAQ.md](docs/FAQ.md) | Common questions |

### For Implementers

| Document | Purpose |
|----------|---------|
| [STANDARD-v1.0.0.md](spec/STANDARD-v1.0.0.md) | Formal specification |
| [CONFORMANCE.md](spec/CONFORMANCE.md) | Conformance levels and testing |
| [SECURITY.md](spec/SECURITY.md) | Threat model and mitigations |

### For Contributors

| Document | Purpose |
|----------|---------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [GOVERNANCE.md](spec/GOVERNANCE.md) | RFC process |
| [ROADMAP.md](spec/ROADMAP.md) | Future plans |

### Background

| Document | Purpose |
|----------|---------|
| [WHITEPAPER.md](spec/WHITEPAPER.md) | Design rationale and philosophy |
| [RFC-0001](spec/RFC-0001-agent-capability-ontology-and-workflow-dsl.md) | Original proposal |

## Directory Structure

```
agent-capability-standard/
├── skills/                  # 99+ capability skills by layer
│   ├── perception/          # inspect, search, retrieve, receive
│   ├── modeling/            # detect, identify, estimate, forecast...
│   ├── reasoning/           # compare, plan, decide, critique...
│   ├── action/              # act, generate, transform, send
│   ├── safety/              # verify, checkpoint, rollback, audit
│   ├── meta/                # discover, prioritize
│   ├── memory/              # recall
│   ├── coordination/        # delegate, synchronize, invoke-workflow
│   └── workflows/           # Composed multi-step workflows
├── schemas/                 # Ontology + workflow + world state schemas
│   ├── capability_ontology.json
│   ├── workflow_catalog.yaml
│   ├── world_state_schema.yaml
│   └── transforms/          # Type coercion mappings
├── hooks/                   # Safety hooks (checkpoint, audit)
├── tools/                   # Validator CLI
├── tests/                   # Conformance fixtures
├── spec/                    # Standard documentation
├── docs/                    # User documentation
├── examples/                # Usage examples
└── templates/               # Skill templates
```

## Installation

### Claude Code Plugin

```bash
# Add the Synapti marketplace (one-time)
claude plugin marketplace add synaptiai/synapti-marketplace

# Install the plugin
claude plugin install agent-capability-standard
```

**What the plugin provides:**

| Component | Description |
|-----------|-------------|
| **99 Skills** | Capability implementations organized by layer (perception, modeling, reasoning, action, safety, meta, memory, coordination) |
| **Workflows** | 5 production-ready workflow compositions with gates and recovery |
| **Safety Hooks** | Pre-tool hooks that enforce checkpoints before mutations |
| **Audit Hooks** | Post-tool hooks that maintain action lineage |
| **Validator** | Design-time validation for custom workflows |

### Local Development

```bash
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard
python -m venv .venv && source .venv/bin/activate
pip install pyyaml
```

## Validation

```bash
# Validate workflow definitions
python tools/validate_workflows.py

# Generate patch suggestions
python tools/validate_workflows.py --emit-patch

# Run conformance tests
python scripts/run_conformance.py
```

## Design Philosophy

This standard embodies the **Grounded Agency** approach:

1. **Grounded Claims** — Every claim is evidence-backed or explicitly inferred
2. **Auditable Transforms** — Deterministic or documented loss
3. **Safety by Construction** — Mutation requires checkpoints; actions require plans
4. **Composable Atoms** — Workflows orchestrate; capabilities do one thing
5. **Explicit Contracts** — I/O schemas are first-class

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.

## Citation

If you use this standard in research, please cite:

```bibtex
@misc{agentcapabilitystandard2026,
  title={Agent Capability Standard: A Framework for Grounded Agency},
  author={Bentes, Daniel},
  year={2026},
  url={https://github.com/synaptiai/agent-capability-standard}
}
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and [spec/GOVERNANCE.md](spec/GOVERNANCE.md) for the RFC process.

---

**Status:** Candidate Standard v1.0.0 | **Released:** 2026-01-24
