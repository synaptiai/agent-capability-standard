# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Validate workflows against the ontology
```bash
python tools/validate_workflows.py
```

### Run conformance tests
```bash
python scripts/run_conformance.py
```

### Setup Python environment (one-time)
```bash
python -m venv .venv && source .venv/bin/activate
pip install pyyaml
```

## Architecture

This is a **Claude Code plugin** that defines a formal capability ontology for AI agents with 99 atomic capabilities across 8 layers, plus 4 composed workflow skills.

### Core Philosophy: Grounded Agency

Every agent action must be:
1. **Grounded** — backed by evidence anchors, not hallucination
2. **Auditable** — with provenance and lineage
3. **Safe** — mutations require checkpoints
4. **Composable** — typed contracts between capabilities

### Key Files

| File | Purpose |
|------|---------|
| `schemas/capability_ontology.json` | Master ontology defining all 99 capabilities with I/O contracts, risk levels, and edges |
| `schemas/workflow_catalog.yaml` | Reference workflows that compose capabilities |
| `skills/<name>/SKILL.md` | Individual skill implementations (flat structure, no nesting) |
| `hooks/hooks.json` | Claude Code hooks for safety enforcement |
| `templates/SKILL_TEMPLATE_ENHANCED.md` | Template for creating new skills |

### Layer Architecture

Capabilities are organized into 8 layers (defined in ontology):

| Layer | Purpose | Count |
|-------|---------|-------|
| PERCEPTION | Input/sensing (retrieve, search, inspect, receive) | 4 |
| MODELING | World understanding (detect-*, identify-*, estimate-*, forecast-*) | 45 |
| REASONING | Analysis/planning (compare-*, plan, decide, critique) | 20 |
| ACTION | Execution (act-plan, generate-*, transform, send) | 12 |
| SAFETY | Guardrails (verify, checkpoint, rollback, audit) | 7 |
| META | Discovery (discover-*) | 6 |
| MEMORY | Persistence (persist, recall) | 2 |
| COORDINATION | Multi-agent (delegate, synchronize, invoke-workflow) | 3 |

### Skill Structure

Skills are at `skills/<skill-name>/SKILL.md` (flat structure, not nested by category). Each skill has:

- YAML frontmatter with `name`, `description`, `allowed-tools`, `agent` type
- Intent and success criteria
- Input/output contracts
- Procedure steps with evidence grounding
- Safety constraints from ontology

### Hooks

The plugin enforces safety through Claude Code hooks:
- **PreToolUse (Write|Edit)**: Requires checkpoint marker before mutations
- **PostToolUse (Skill)**: Logs skill invocations to `.claude/audit.log`

### Ontology Edge Types

Relationships between capabilities (in `capability_ontology.json`):
- `requires`: Hard dependency
- `enables`: Unlocks other capabilities
- `governed_by`: Safety constraint
- `verifies`, `soft_requires`, `documented_by`

## Creating New Skills

1. Use `templates/SKILL_TEMPLATE_ENHANCED.md` as the starting template
2. Place skill at `skills/<name>/SKILL.md` (kebab-case name)
3. Add corresponding node to `schemas/capability_ontology.json`
4. Add edges connecting to related capabilities
5. Run `python tools/validate_workflows.py` to verify

## Safety Model

High-risk capabilities (`act`, `act-plan`, `send`) have:
- `mutation: true`
- `requires_checkpoint: true`
- `risk: "high"`

These are enforced structurally—not by convention.
