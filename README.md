# Agent Capability Standard

> **Grounded Agency**: A framework for building AI agents that know what they don't know.

[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet?logo=anthropic)](https://github.com/synaptiai/synapti-marketplace)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Spec](https://img.shields.io/badge/Spec-v1.2.0_Candidate_Standard-blue.svg)](spec/STANDARD-v1.2.0.md)
[![Plugin](https://img.shields.io/badge/Plugin-v2.0.0-green.svg)](CHANGELOG.md)

**Documentation:** [acs.synapti.ai](https://acs.synapti.ai/) has the specification, a page for every capability, workflow and domain, and search. Coding agents can start from [acs.synapti.ai/llms.txt](https://acs.synapti.ai/llms.txt).

> **Versioning:** The spec version tracks the standard itself: v1.2.0 is a Candidate Standard, accepted by RFC-0005 to RFC-0011 and not yet released; [v1.1.0](spec/STANDARD-v1.1.0.md) is the released Standard; [v1.0.0](spec/STANDARD-v1.0.0.md) is Supported. The plugin version (v2.0.0) tracks the Claude Code implementation. The Python package (`grounded-agency`) uses its own SemVer. See [GOVERNANCE.md](spec/GOVERNANCE.md) for the versioning policy.

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

### What Standard 1.2.0 Adds

[Standard 1.2.0](spec/STANDARD-v1.2.0.md) is a Candidate Standard, accepted
by [RFC-0005](spec/RFC-0005-tool-calling-hosts.md) to
[RFC-0011](spec/RFC-0011-shell-like-tools-and-os-boundary.md), with
capability ontology 2.2.0. A workflow valid under 1.1.0 validates and runs
as before. It adds:

- **Tool-calling hosts** ([§5.18](spec/STANDARD-v1.2.0.md#518-tool-calling-hosts)):
  the ontology's rules applied to the tool calls a model chooses, a
  host-neutral tool binding record, and a conformance class for safety
  layers, SL ([§10.4](spec/STANDARD-v1.2.0.md#104-safety-layer-conformance)),
  which the [Python SDK adapter](docs/integrations/claude_agent_sdk.md) and
  the [Standard Agents binding](docs/integrations/standard_agents.md) claim.
  The Standard also carries the rule of
  [RFC-0011](spec/RFC-0011-shell-like-tools-and-os-boundary.md): a layer gives every call of a shell-like tool (a shell, an
  interpreter) the tool's worst case unless the call runs under an
  operating-system boundary the layer declares and verifies. The adapter
  runs Bash under Claude Code's sandbox by default and relaxes a Bash call
  only while it has verified that sandbox.
- **The host protocol** ([§5.19](spec/STANDARD-v1.2.0.md#519-host-protocol)):
  the actions, responses and run operations between an executor and its
  host as a published schema, with cancellation, run records and a
  conformance class for executors, EX
  ([§10.5](spec/STANDARD-v1.2.0.md#105-executor-conformance)).
- **Approval and delegation**: the approval digest stated in full, attested
  approvers and resuming a deferred run
  ([§5.14.1](spec/STANDARD-v1.2.0.md#5141-resuming-a-deferred-run)); agent
  manifests and delegation targets
  ([§5.15.2](spec/STANDARD-v1.2.0.md#5152-delegation-targets)); catalog
  manifests with qualified names
  ([§5.1.1](spec/STANDARD-v1.2.0.md#511-catalog-manifests-and-qualified-names)).
- **Evidence and secrets**: one evidence anchor
  ([§6.5](spec/STANDARD-v1.2.0.md#65-evidence-anchors)), grounding the
  executor checks ([§5.20](spec/STANDARD-v1.2.0.md#520-grounding)), and
  secrets kept out of records
  ([§6.7](spec/STANDARD-v1.2.0.md#67-secrets-in-records)).
- **Effects**: what a checkpoint captures and a rollback restores
  ([§4.4.1](spec/STANDARD-v1.2.0.md#441-checkpoints-and-rollback)),
  idempotent transmissions with destination policies
  ([§4.4.2](spec/STANDARD-v1.2.0.md#442-transmissions)), and memory scopes
  ([§4.5](spec/STANDARD-v1.2.0.md#45-memory)).
- **Domain profiles that take effect**
  ([§5.21](spec/STANDARD-v1.2.0.md#521-domain-profiles)): the executor, the
  safety layers and the validator apply a profile's flags, person
  requirements, grounding, confidence and destination rules.
- **[`@synaptiai/acs-core`](packages/acs-core/README.md)**: the ontology,
  effective flags and approval digest in TypeScript, and the Rust core
  through WebAssembly.

[Appendix D](spec/STANDARD-v1.2.0.md#appendix-d-changes-from-110) lists
every change from 1.1.0, and the [CHANGELOG](CHANGELOG.md) says what changes
for users of the SDK, the plugin and the binding.

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
- `/grounded-setup`, which turns on Claude Code's strict sandbox in your user settings

Then run `/grounded-setup` in Claude Code, in each project you use the
plugin in. Until the sandbox is on, the hooks refuse every Bash call, so
the first time it gives you a command to run in a terminal outside Claude
Code, and the write always happens there; start Claude Code again after
it. That command shows the settings it would add to
`~/.claude/settings.json` as a diff and writes them only when you agree: the sandbox on with no way
around it, a network allowlist (the hosts your domain profile's
`allowed_destinations` name, given with `--profile`, and the package
registries your project uses), deny rules that keep the agent's commands
and file tools from the hooks' records, your credentials (the keychain on
macOS, `~/.ssh`, gh's and git's tokens, the package registries' tokens,
the audit key) and the project's Claude Code settings. It needs the
system's `/usr/bin/python3`, 3.9 or later: the one in Apple's command line tools, or in a
current Linux distribution, is enough. A sandboxed `gh` or `git push` then cannot authenticate, and neither
can a publish to a package registry. A repository's own settings can still turn the sandbox off,
exclude commands or widen its write scope; only managed settings prevent
that. On native Windows, which has no sandbox, it writes nothing. See
[Setting up the sandbox](hooks/README.md#setting-up-the-sandbox).

Until Claude Code's strict sandbox is set up in your user settings ([The strict sandbox](hooks/README.md#the-strict-sandbox)), the hooks treat every Bash call, read-only commands included, as a change that needs a checkpoint and approval, so Bash calls are refused.

### Option 2: Standalone Validation

Use the validator independently:

```bash
# Clone the repository
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard

# Set up Python environment (Python >= 3.14; builds the Rust core, so Rust >= 1.88 is required)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt

# Validate workflows (defaults to schemas/workflow_catalog.yaml; --catalog PATH for another file)
python tools/validate_workflows.py
# → VALIDATION PASS

# Run conformance tests
python scripts/run_conformance.py
# → Conformance PASSED
```

**Next:** See [QUICKSTART.md](docs/QUICKSTART.md) for a guided walkthrough.

## Choose Your Path

| I want to... | Start here |
|--------------|------------|
| **Evaluate** if this fits my needs | [FAQ](docs/FAQ.md) → [Whitepaper](spec/WHITEPAPER.md) |
| **Use** this in Claude Code | [Quickstart](docs/QUICKSTART.md) (10 min) |
| **Build** agents with the Python SDK | [SDK Guide](docs/integrations/claude_agent_sdk.md) |
| **Read** the formal specification | [STANDARD-v1.2.0.md](spec/STANDARD-v1.2.0.md) |
| **Create** custom workflows | [Tutorial](docs/TUTORIAL.md) (30 min) |
| **Contribute** to the standard | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **Deploy** in a regulated industry | [Compliance Suite](docs/compliance/) |

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

Reference workflow compositions defined in the [workflow catalog](schemas/workflow_catalog.yaml), with gates, failure modes that roll back on error, and typed bindings. Four of these have a [composed skill](skills/README.md#composed-skills-6) that runs them: `debug_code_change`, `capability_gap_analysis`, `digital_twin_bootstrap` and `digital_twin_sync_loop`.

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
| `data_quality_pipeline` | Detect, classify, and clean data quality issues | Low |
| `model_deployment` | Safely deploy ML model to production | High |

### Domain Profiles

Example profiles of trust weights, risk thresholds and checkpoint rules for specific industries. A profile takes effect where a host, a safety layer or the validator applies it (Standard v1.2 §5.21): the reference executor, the Python adapter and the Standard Agents binding apply every example below, its grounding policy, minimum confidence and destination policy included ([status](docs/domains/README.md#status-of-domain-profiles)):

| Domain | Key Feature | Profile |
|--------|------------|---------|
| Healthcare | A person approves every step when applied; declares 7-year audit retention (informative) | [Guide](docs/domains/healthcare/) |
| Manufacturing | Sensor trust (0.92-0.95); `mutate` and `send` need a person when applied | [Guide](docs/domains/manufacturing/) |
| Data Analysis | Lineage grounding and a confidence floor when applied | [Guide](docs/domains/data-analysis/) |
| Personal Assistant | Highest user trust (0.98); `send` needs a person each time when applied | [Guide](docs/domains/personal-assistant/) |
| Vision / Audio / Multimodal | Cross-modal consistency, spatial/temporal grounding | [Guide](docs/guides/MODALITY_HANDLING.md) |

### Canonical Schemas

- **Capability Ontology** — 36 atomic capabilities with I/O contracts ([ontology](schemas/capability_ontology.yaml))
- **Workflow DSL** — Typed bindings, gates, failure modes and recovery loops (no reference workflow uses a loop; see [STANDARD §5.12](spec/STANDARD-v1.2.0.md#512-recovery-and-escalation))
- **World State** — Observations with provenance and uncertainty
- **Trust Model** — Authority ranking with time decay

### Safety Hooks

The plugin's hooks (see [hooks/README.md](hooks/README.md)):

| Hook | Event | Purpose |
|------|-------|---------|
| `pretooluse_require_checkpoint.sh` | PreToolUse (every tool) | Classify the call (an unbound tool, MCP tools included, is a gated `mutate`; Bash is read by command only under Claude Code's strict sandbox, verified from the settings files, and is otherwise a gated `mutate`); one checkpoint per gated call (F501); ask for approval (F502); let a restore of a recorded checkpoint run as a `rollback` |
| `posttooluse_take_checkpoint.sh` | PostToolUse (`Bash`) | Take the checkpoint after a successful `git stash create`: write the marker, with its commit recorded for a later rollback |
| `stop_end_checkpoints.sh` | Stop, StopFailure, UserPromptSubmit, SessionStart, SessionEnd | End the marker's validity when a turn or a session ends or starts, filing it under `.claude/checkpoints/ended/` |
| `posttooluse_log_tool.sh` | PostToolUse, PostToolUseFailure | The plugin's log of tool calls: one action record per call (§6.4), HMAC-chained, with a digest in place of its input; it is not an `audit` step |

## Documentation

### For Users

| Document | Purpose |
|----------|---------|
| [QUICKSTART.md](docs/QUICKSTART.md) | Validate a workflow in 10 minutes |
| [TUTORIAL.md](docs/TUTORIAL.md) | Build your first workflow (30 min) |
| [GLOSSARY.md](docs/GLOSSARY.md) | Key terms and definitions |
| [FAQ.md](docs/FAQ.md) | Common questions |
| [MODALITY_HANDLING.md](docs/guides/MODALITY_HANDLING.md) | Working with vision, audio, and multimodal domains |
| [ORCHESTRATION_EXTENSIONS.md](docs/guides/ORCHESTRATION_EXTENSIONS.md) | Triggers, escalation, waiting, approval, delegation, quorum and sender identity (Standard v1.1) |
| [RUNNING_WORKFLOWS.md](docs/guides/RUNNING_WORKFLOWS.md) | Running workflows on the reference executor with a host |
| [PERSPECTIVE_VALIDATION_CHECKLIST.md](skills/perspective-validation/CHECKLIST.md) | Socio-technical and governance review checklist (PVC) |

### For Implementers

| Document | Purpose |
|----------|---------|
| [STANDARD-v1.2.0.md](spec/STANDARD-v1.2.0.md) | Formal specification (Candidate Standard, accepted by [RFC-0005](spec/RFC-0005-tool-calling-hosts.md) to [RFC-0011](spec/RFC-0011-shell-like-tools-and-os-boundary.md)) |
| [STANDARD-v1.1.0.md](spec/STANDARD-v1.1.0.md) | Released specification (Standard) |
| [STANDARD-v1.0.0.md](spec/STANDARD-v1.0.0.md) | Earlier specification (Supported) |
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
├── skills/                  # 36 capability skills and 6 composed skills (flat structure)
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
│   └── ...                  # (42 skills: 36 capabilities, 6 composed)
├── schemas/                 # Ontology + workflow + world state schemas
│   ├── capability_ontology.yaml     # 36-capability ontology
│   ├── workflow_catalog.yaml
│   ├── world_state_schema.yaml
│   ├── interop/                       # Framework interoperability mappings
│   │   └── oasf_mapping.yaml          # OASF skill code mapping
│   └── transforms/          # Type coercion mappings
├── core/                    # Rust crate: validator and executor, compiled into grounded_agency._core
├── packages/acs-core/       # TypeScript package: ontology table, flags, digest; the core through WebAssembly
├── grounded_agency/         # Python package (SDK integration)
├── hooks/                   # Safety hooks (checkpoint, audit)
├── commands/                # Plugin commands (/grounded-setup)
├── tools/                   # Validator CLI (thin wrapper over core/)
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
- **Checkpoint recording** that records a checkpoint when a call that saves the state succeeds (`git stash create` under the verified sandbox, or a tool bound to `checkpoint`); a `Skill` call takes none
- **Audit trails** for compliance and debugging

See [docs/integrations/claude_agent_sdk.md](docs/integrations/claude_agent_sdk.md) for the full integration guide.

**Install the Python package:** it is not on PyPI yet. Install it from a clone; the install compiles its Rust core, so it needs Python >= 3.14 and Rust >= 1.88:

```bash
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[sdk]"
```

The adapter relaxes Bash calls only with the `claude-agent-sdk` release that `constraints.txt` pins (0.2.189, which bundles Claude Code 2.1.332), and only in the `bypassPermissions` permission mode; under another release or in another mode every Bash call needs a checkpoint and approval (`pip install claude-agent-sdk==0.2.189`).

To adopt the standard in stages, from the validator in CI to a safety layer and an executor, see the [adoption guide](docs/guides/ADOPTION.md).

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
| **42 Skills** | 36 atomic capability skills organized by cognitive layer, and 6 composed skills that run workflows |
| **Workflow Patterns** | Reusable compositions (analyze, mitigate, optimize, orchestrate) |
| **Safety Hooks** | Pre-tool hooks that enforce checkpoints before mutations |
| **Audit Hooks** | Post-tool hooks that maintain action lineage |
| **Setup command** | `/grounded-setup`: turns on Claude Code's strict sandbox in your user settings, after showing the change ([Setting up the sandbox](hooks/README.md#setting-up-the-sandbox)) |
| **Validator** | Design-time validation for custom workflows |
| **Remote writes** | An MCP server with typed tools for push, tag, pull request, merge, release and issue writes, each a gated change a person approves, to the origin a person recorded ([hooks/README.md](hooks/README.md#remote-writes)) |

Until Claude Code's strict sandbox is set up in your user settings ([The strict sandbox](hooks/README.md#the-strict-sandbox)), the hooks treat every Bash call, read-only commands included, as a change that needs a checkpoint and approval, so Bash calls are refused.

The hooks need Claude Code 2.1.295 or later, the first version that honours `onFailure: "block"`: an older one runs a call whose hook failed or timed out.

### Local Development

```bash
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt   # needs Python >= 3.14 and Rust >= 1.88
```

## Validation

```bash
# Validate workflow definitions (writes tools/validator_suggestions.json)
python tools/validate_workflows.py

# Validate another catalog; --strict makes warnings fail
python tools/validate_workflows.py --catalog path/to/catalog.yaml --strict

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

**Status:** Candidate Standard v1.2.0 (accepted by RFC-0005 to RFC-0011, not yet released); v1.1.0, released 2026-10-28, is the released Standard; v1.0.0, released 2026-01-24, is Supported. [GOVERNANCE](spec/GOVERNANCE.md#standard-versions) defines these statuses.
