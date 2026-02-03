# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Validate workflows against the ontology
```bash
python tools/validate_workflows.py
```

### Validate domain profiles against schema
```bash
python tools/validate_profiles.py
```

### Validate skill file references (no phantom paths)
```bash
python tools/validate_skill_refs.py
```

### Validate ontology graph (orphans, cycles, symmetry)
```bash
python tools/validate_ontology.py
```

### Validate YAML utility sync (safe_yaml.py ↔ yaml_util.py)
```bash
python tools/validate_yaml_util_sync.py
```

### Validate transform mapping_ref paths (no broken refs)
```bash
python tools/validate_transform_refs.py
```

### Validate benchmark deps against ontology
```bash
python tools/validate_benchmark_deps.py
```

### Sync skill-local schemas from ontology
```bash
python tools/sync_skill_schemas.py
```

### Run conformance tests (optional, local only)
```bash
python scripts/run_conformance.py
```

### Setup Python environment (one-time)
```bash
python -m venv .venv && source .venv/bin/activate
pip install pyyaml
```

## Architecture

This is a **Claude Code plugin** that defines a formal capability ontology for AI agents with **36 atomic capabilities** across **9 cognitive layers**, plus 12 composed workflow patterns.

### Core Philosophy: Grounded Agency

Every agent action must be:
1. **Grounded** — backed by evidence anchors, not hallucination
2. **Auditable** — with provenance and lineage
3. **Safe** — mutations require checkpoints
4. **Composable** — typed contracts between capabilities

### Key Files

| File | Purpose |
|------|---------|
| `schemas/capability_ontology.yaml` | Master ontology defining all 36 capabilities with I/O contracts, risk levels, and edges |
| `schemas/workflow_catalog.yaml` | Reference workflows that compose capabilities |
| `schemas/profiles/*.yaml` | Domain-specific profiles (trust weights, risk thresholds, checkpoint/evidence policies) |
| `schemas/profiles/profile_schema.yaml` | Schema defining structure for domain profiles |
| `skills/<name>/SKILL.md` | Individual skill implementations (flat structure, no nesting) |
| `hooks/hooks.json` | Claude Code hooks for safety enforcement |
| `templates/SKILL_TEMPLATE_ENHANCED.md` | Template for creating new skills |
| `_archive/` | Archived files from v1 (99-capability model) |
| `schemas/interop/oasf_mapping.yaml` | OASF skill-code-to-capability mapping |
| `docs/guides/MODALITY_HANDLING.md` | Modality handling guide (vision, audio, multimodal) |
| `docs/proposals/OASF_SAFETY_EXTENSIONS.md` | OASF safety extension proposal |

### Layer Architecture

Capabilities are organized into 9 cognitive layers (defined in ontology):

| Layer | Purpose | Count | Capabilities |
|-------|---------|-------|--------------|
| PERCEIVE | Information acquisition | 4 | retrieve, search, observe, receive |
| UNDERSTAND | Making sense of information | 6 | detect, classify, measure, predict, compare, discover |
| REASON | Planning and analysis | 4 | plan, decompose, critique, explain |
| MODEL | World representation | 5 | state, transition, attribute, ground, simulate |
| SYNTHESIZE | Content creation | 3 | generate, transform, integrate |
| EXECUTE | Changing the world | 3 | execute, mutate, send |
| VERIFY | Correctness assurance | 5 | verify, checkpoint, rollback, constrain, audit |
| REMEMBER | State persistence | 2 | persist, recall |
| COORDINATE | Multi-agent and user interaction | 4 | delegate, synchronize, invoke, inquire |

### Skill Structure

Skills are at `skills/<skill-name>/SKILL.md` (flat structure, not nested by category). Each skill has:

- YAML frontmatter with `name`, `description`, `allowed-tools`, `agent` type, and `layer`
- Intent and success criteria
- Input/output contracts with `domain` parameter for specialization
- Procedure steps with evidence grounding
- Safety constraints from ontology

### Domain Parameterization

The 36-capability model uses **domain parameters** instead of domain-specific variants:

| Old (99 model) | New (36 model) |
|----------------|----------------|
| `detect-anomaly`, `detect-entity` | `detect` with `domain: anomaly`, `domain: entity` |
| `estimate-risk`, `estimate-impact` | `measure` with `domain: risk`, `domain: impact` |
| `forecast-risk`, `forecast-time` | `predict` with `domain: risk`, `domain: time` |

### Hooks

The plugin enforces safety through Claude Code hooks:
- **PreToolUse (Write|Edit|MultiEdit|NotebookEdit|Bash)**: Requires checkpoint marker before mutations
- **PostToolUse (Skill)**: Logs skill invocations to `.claude/audit.log`

### Ontology Edge Types

Relationships between capabilities (in `capability_ontology.yaml`):
- `requires`: Hard dependency (must be satisfied)
- `soft_requires`: Recommended but not mandatory
- `enables`: Unlocks other capabilities
- `precedes`: Temporal ordering (must complete before target)
- `conflicts_with`: Mutual exclusivity (cannot coexist in workflow)
- `alternative_to`: Substitutable capabilities
- `specializes`: Parent-child inheritance

See [spec/EDGE_TYPES.md](spec/EDGE_TYPES.md) for full edge type documentation.

## Creating New Capabilities

When adding a new atomic capability, you MUST complete ALL of these steps:

### 1. Update the Ontology
- Add capability node to `schemas/capability_ontology.yaml` with full input/output schemas
- Add edges connecting to related capabilities (`requires`, `soft_requires`, `enables`)
- Update the layer's `capabilities` array in the `layers` section
- Update the `meta.description` count (e.g., "36 atomic capabilities" → "37 atomic capabilities")

### 2. Create the Skill
- Use `templates/SKILL_TEMPLATE_ENHANCED.md` as the starting template
- Place skill at `skills/<name>/SKILL.md` (kebab-case name)

### 3. Update ALL Capability Count References
Search and update capability counts in these files:
- `CLAUDE.md` — Architecture section and layer table
- `README.md` — Multiple references throughout
- `spec/WHITEPAPER.md` — Summary and derivation sections
- `docs/GROUNDED_AGENCY.md` — Capability ontology section
- `docs/FAQ.md` — Capability count references
- `docs/GLOSSARY.md` — Layer descriptions
- `docs/WORKFLOW_PATTERNS.md` — Pattern references
- `docs/TUTORIAL.md` — Tutorial references
- `docs/methodology/EXTENSION_GOVERNANCE.md` — Governance references
- `skills/README.md` — Layer counts and totals
- `.claude-plugin/plugin.json` — Description field

**Tip:** Use `grep -r "N atomic capabilit" .` and `grep -r "N capabilities" .` to find all references (where N is the old count).

### 4. Validate
```bash
python tools/validate_workflows.py
python tools/validate_profiles.py
python -c "import yaml; yaml.safe_load(open('schemas/capability_ontology.yaml'))"
```

### 5. Update Workflow Catalog (if adding workflow patterns)
- Add workflow to `schemas/workflow_catalog.yaml`
- Update workflow count in `skills/README.md`

### 6. Generate Local Schema
```bash
python tools/sync_skill_schemas.py
```
This generates `skills/<name>/schemas/output_schema.yaml` from the ontology.

## Claude Agent SDK Integration

The `grounded_agency/` Python package provides SDK integration:

### Install
```bash
pip install -e ".[sdk]"  # From repo root
```

### Run SDK integration tests
```bash
pytest tests/test_sdk_integration.py -v
```

### Run examples
```bash
python examples/grounded_agent_demo.py
python examples/checkpoint_enforcement_demo.py
python examples/capability_skills_demo.py
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `GroundedAgentAdapter` | Main entry point - wraps SDK options with safety layer |
| `CapabilityRegistry` | Loads and queries `capability_ontology.yaml` |
| `ToolCapabilityMapper` | Maps SDK tools to capability metadata |
| `CheckpointTracker` | Manages checkpoint lifecycle for mutation safety |
| `EvidenceStore` | Collects evidence anchors from tool executions |

### Example Usage

```python
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
adapter.create_checkpoint(["*.py"], "Before changes")
options = adapter.wrap_options(base_options)
```

See [docs/integrations/claude_agent_sdk.md](docs/integrations/claude_agent_sdk.md) for full documentation.

## Safety Model

High-risk capabilities (`mutate`, `send`) have:
- `mutation: true`
- `requires_checkpoint: true`
- `requires_approval: true`
- `risk: "high"`

Medium-risk capabilities (`execute`, `rollback`, `delegate`, `synchronize`, `invoke`) have:
- `risk: "medium"`
- `execute` also has `requires_approval: true`

Other mutation capabilities (`checkpoint`, `audit`, `persist`) have:
- `mutation: true`
- Lower risk levels (low or medium)

These are enforced structurally—not by convention.

## Workflow Orchestration

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user: update 'tasks/lessons.md" with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **PLan First**: Write plan to 'tasks/todo.md" with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to tasks/todo.md*
6. **Capture Lessons**: Update "tasks/lessons.md" after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.