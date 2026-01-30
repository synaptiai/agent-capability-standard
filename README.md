# Agent Capability Standard

> **Grounded Agency**: A framework for building AI agents that know what they don't know.

[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet?logo=anthropic)](https://github.com/synaptiai/synapti-marketplace)
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

## The Periodic Table of Agent Capabilities

Just as chemistry has ~118 elements that compose into infinite molecules, this standard defines **36 atomic capabilities** that compose into **infinite workflows**.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CAPABILITIES (atoms)              →  WORKFLOWS (molecules)              │
│                                                                         │
│  observe + search + plan          →  debug_code_change                  │
│  + checkpoint + execute                                                 │
│  + verify + rollback                                                    │
│                                                                         │
│  receive + transform + integrate  →  digital_twin_sync_loop             │
│  + detect + plan                                                        │
│  + checkpoint + mutate + audit                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Capabilities are atoms**: Irreducible primitives with defined I/O contracts.

**Workflows are molecules**: Compositions that solve real problems.

**The goal isn't more atoms—it's better molecules.**

### Why 36?

The 36 capabilities were systematically derived from first principles:

1. **Cognitive architecture analysis** (BDI, SOAR, ReAct patterns)
2. **Industry tool patterns** (MCP, LangChain, Claude Skills)
3. **Rigorous atomicity testing** (cannot be decomposed further)

Each capability:
- Performs exactly one irreducible cognitive operation
- Has a well-defined I/O contract with evidence anchors
- Maps to how agents actually work in production

**Domain specializations become parameters**, not separate capabilities. `detect(domain: anomaly)` rather than `detect-anomaly`.

For the full derivation methodology, see [docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md](docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md).

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
- 36 atomic capability skills organized by layer
- Workflow patterns that compose capabilities
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

### 36 Atomic Capabilities

Organized across 9 cognitive layers with explicit input/output schemas:

| Layer | Count | Capabilities |
|-------|-------|--------------|
| **PERCEIVE** | 4 | retrieve, search, observe, receive |
| **UNDERSTAND** | 6 | detect, classify, measure, predict, compare, discover |
| **REASON** | 4 | plan, decompose, critique, explain |
| **MODEL** | 5 | state, transition, attribute, ground, simulate |
| **SYNTHESIZE** | 3 | generate, transform, integrate |
| **EXECUTE** | 3 | execute, mutate, send |
| **VERIFY** | 5 | verify, checkpoint, rollback, constrain, audit |
| **REMEMBER** | 2 | persist, recall |
| **COORDINATE** | 4 | delegate, synchronize, invoke, inquire |

### Workflow Patterns

Capabilities compose into reusable workflow patterns:

| Pattern | Purpose | Key Capabilities |
|---------|---------|------------------|
| **analyze** | Examine data thoroughly | retrieve → detect → classify → explain |
| **mitigate** | Reduce identified risks | detect → measure → plan → execute → verify |
| **optimize** | Iteratively improve | observe → discover → compare → mutate → verify |
| **orchestrate** | Coordinate multiple agents | decompose → delegate → synchronize → integrate |

See [WORKFLOW_PATTERNS.md](docs/WORKFLOW_PATTERNS.md) for the complete pattern catalog.

### 12 Composed Workflows

Production-ready workflow compositions with gates, recovery loops, and typed bindings:

| Workflow | Goal | Risk |
|----------|------|------|
| `monitor_and_replan` | Detect world changes and trigger replanning | Medium |
| `clarify_intent` | Resolve ambiguous user requests | Low |
| `debug_code_change` | Safely diagnose and fix bugs | Medium |
| `world_model_build` | Construct grounded world model | Low |
| `capability_gap_analysis` | Identify missing capabilities | Low |
| `digital_twin_sync_loop` | Synchronize digital twin state | High |
| `digital_twin_bootstrap` | Initialize and run first sync | High |
| `rag_pipeline` | Retrieve and generate grounded response | Low |
| `security_assessment` | Assess vulnerabilities with risk scoring | Low |
| `multi_agent_orchestration` | Coordinate agents for complex tasks | Medium |
| `data_quality_pipeline` | Detect, classify, and clean data quality issues | Medium |
| `model_deployment` | Safely deploy ML model to production | High |

### Canonical Schemas

- **Capability Ontology** — 36 atomic capabilities with I/O contracts ([ontology](schemas/capability_ontology.yaml))
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
| [MODALITY_HANDLING.md](docs/guides/MODALITY_HANDLING.md) | Working with vision, audio, and multimodal domains |
| [PERSPECTIVE_VALIDATION_CHECKLIST.md](skills/perspective-validation/CHECKLIST.md) | Socio-technical and governance review checklist (PVC) |

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

### Methodology

| Document | Purpose |
|----------|---------|
| [FIRST_PRINCIPLES_REASSESSMENT.md](docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md) | How 36 capabilities were derived |
| [AGENT_ARCHITECTURE_RESEARCH.md](docs/methodology/AGENT_ARCHITECTURE_RESEARCH.md) | Industry patterns research |
| [SKILLS_ALIGNMENT_EVALUATION.md](docs/methodology/SKILLS_ALIGNMENT_EVALUATION.md) | Validation against Claude Skills |
| [WORKFLOW_PATTERNS.md](docs/WORKFLOW_PATTERNS.md) | Reusable composition patterns |
| [EXTENSION_GOVERNANCE.md](docs/methodology/EXTENSION_GOVERNANCE.md) | When to add new capabilities |
| [OASF_SAFETY_EXTENSIONS.md](docs/proposals/OASF_SAFETY_EXTENSIONS.md) | OASF safety property integration proposal |

### Background

| Document | Purpose |
|----------|---------|
| [WHITEPAPER.md](spec/WHITEPAPER.md) | Design rationale and philosophy |
| [RFC-0001](spec/RFC-0001-agent-capability-ontology-and-workflow-dsl.md) | Original proposal |

## Directory Structure

```
agent-capability-standard/
├── skills/                  # 36 atomic capability skills (flat structure)
│   ├── retrieve/SKILL.md    # PERCEIVE layer
│   ├── search/SKILL.md
│   ├── observe/SKILL.md
│   ├── detect/SKILL.md      # UNDERSTAND layer
│   ├── classify/SKILL.md
│   ├── plan/SKILL.md        # REASON layer
│   ├── state/SKILL.md       # MODEL layer
│   ├── generate/SKILL.md    # SYNTHESIZE layer
│   ├── mutate/SKILL.md      # EXECUTE layer
│   ├── verify/SKILL.md      # VERIFY layer
│   ├── checkpoint/SKILL.md
│   ├── persist/SKILL.md     # REMEMBER layer
│   ├── delegate/SKILL.md    # COORDINATE layer
│   └── ...                  # (36 total skills)
├── schemas/                 # Ontology + workflow + world state schemas
│   ├── capability_ontology.yaml     # 36-capability ontology
│   ├── workflow_catalog.yaml
│   ├── world_state_schema.yaml
│   ├── interop/                       # Framework interoperability mappings
│   │   └── oasf_mapping.yaml          # OASF skill code mapping
│   └── transforms/          # Type coercion mappings
├── hooks/                   # Safety hooks (checkpoint, audit)
├── tools/                   # Validator CLI
├── tests/                   # Conformance fixtures
├── spec/                    # Standard documentation
├── docs/                    # User documentation + methodology
│   ├── guides/                        # User guides
│   └── proposals/                     # Extension proposals
├── examples/                # Usage examples
└── templates/               # Skill templates
```

## Claude Agent SDK Integration

The Grounded Agency capability standard integrates with the Claude Agent SDK to provide safety-first agent execution:

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

# Create adapter with strict checkpoint enforcement
adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))

# Create checkpoint before mutations
adapter.create_checkpoint(scope=["src/*.py"], reason="Before refactoring")

# Wrap SDK options with safety layer
options = adapter.wrap_options(
    ClaudeAgentOptions(allowed_tools=["Read", "Write", "Edit", "Bash"])
)

# Use SDK as normal - safety is enforced automatically
async with ClaudeSDKClient(options) as client:
    await client.query("Refactor the authentication module")
```

**Features:**
- **Permission callbacks** that block mutations without checkpoints
- **Evidence anchors** that track provenance for grounded decisions
- **Skill tracking** that updates checkpoint state when `checkpoint` skill is invoked
- **Audit trails** for compliance and debugging

See [docs/integrations/claude_agent_sdk.md](docs/integrations/claude_agent_sdk.md) for the full integration guide.

**Install the Python package:**

```bash
pip install grounded-agency
# Or with SDK support:
pip install grounded-agency[sdk]
```

---

## Installation

### Claude Code Plugin
Add the [Synapti marketplace](https://github.com/synaptiai/synapti-marketplace) to your Claude Code setup.
```bash
# Add the Synapti marketplace (one-time)
claude plugin marketplace add synaptiai/synapti-marketplace

# Install the plugin
claude plugin install agent-capability-standard
```

**What the plugin provides:**

| Component | Description |
|-----------|-------------|
| **36 Skills** | Atomic capability implementations organized by cognitive layer |
| **Workflow Patterns** | Reusable compositions (analyze, mitigate, optimize, orchestrate) |
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
