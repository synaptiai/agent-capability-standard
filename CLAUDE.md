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

This is a **Claude Code plugin** that defines a formal capability ontology for AI agents with **36 atomic capabilities** across **9 cognitive layers**, plus 6 composed workflow patterns.

### Core Philosophy: Grounded Agency

Every agent action must be:
1. **Grounded** — backed by evidence anchors, not hallucination
2. **Auditable** — with provenance and lineage
3. **Safe** — mutations require checkpoints
4. **Composable** — typed contracts between capabilities

### Key Files

| File | Purpose |
|------|---------|
| `schemas/capability_ontology.json` | Master ontology defining all 36 capabilities with I/O contracts, risk levels, and edges |
| `schemas/workflow_catalog.yaml` | Reference workflows that compose capabilities |
| `skills/<name>/SKILL.md` | Individual skill implementations (flat structure, no nesting) |
| `hooks/hooks.json` | Claude Code hooks for safety enforcement |
| `templates/SKILL_TEMPLATE_ENHANCED.md` | Template for creating new skills |
| `_archive/` | Archived files from v1 (99-capability model) |

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
| COORDINATE | Multi-agent interaction | 4 | delegate, synchronize, invoke, inquire |

### Skill Structure

Skills are at `skills/<skill-name>/SKILL.md` (flat structure, not nested by category). Each skill has:

- YAML frontmatter with `name`, `description`, `allowed-tools`, `agent` type, and `layer`
- Intent and success criteria
- Input/output contracts with `domain` parameter for specialization
- Procedure steps with evidence grounding
- Safety constraints from ontology

### Domain Parameterization

The 36-capability model uses **domain parameters** instead of domain-specific variants:

| Old (99 model) | New (35 model) |
|----------------|----------------|
| `detect-anomaly`, `detect-entity` | `detect` with `domain: anomaly`, `domain: entity` |
| `estimate-risk`, `estimate-impact` | `measure` with `domain: risk`, `domain: impact` |
| `forecast-risk`, `forecast-time` | `predict` with `domain: risk`, `domain: time` |

### Hooks

The plugin enforces safety through Claude Code hooks:
- **PreToolUse (Write|Edit)**: Requires checkpoint marker before mutations
- **PostToolUse (Skill)**: Logs skill invocations to `.claude/audit.log`

### Ontology Edge Types

Relationships between capabilities (in `capability_ontology.json`):
- `requires`: Hard dependency (must be satisfied)
- `soft_requires`: Recommended but not mandatory
- `enables`: Unlocks other capabilities

## Creating New Skills

1. Use `templates/SKILL_TEMPLATE_ENHANCED.md` as the starting template
2. Place skill at `skills/<name>/SKILL.md` (kebab-case name)
3. Add corresponding node to `schemas/capability_ontology.json`
4. Add edges connecting to related capabilities
5. Run `python tools/validate_workflows.py` to verify

## Safety Model

High-risk capabilities (`mutate`, `send`) have:
- `mutation: true`
- `requires_checkpoint: true`
- `risk: "high"`

Medium-risk capabilities (`execute`, `delegate`, `invoke`) have:
- `requires_approval: true`
- `risk: "medium"`

These are enforced structurally—not by convention.
