# Agent Capability Skills

This directory contains **36 atomic capability skills** organized according to the capability ontology's **9 cognitive layers**, plus a small set of composed workflow/governance skills.

## Skill Layers

| Layer | Count | Purpose |
|-------|-------|---------|
| PERCEIVE | 4 | Acquire information from the world |
| UNDERSTAND | 6 | Make sense of information |
| REASON | 4 | Plan and analyze |
| MODEL | 5 | Represent the world |
| SYNTHESIZE | 3 | Create content |
| EXECUTE | 3 | Change the world |
| VERIFY | 5 | Ensure correctness |
| REMEMBER | 2 | Persist state |
| COORDINATE | 4 | Multi-agent and user interaction |
| Composed | 6 | Composed multi-step skills |

**Total: 36 atomic capabilities + 6 composed skills = 42 skills**

## The 36 Atomic Capabilities

### PERCEIVE (4)
Information acquisition from the world.

| Skill | Description |
|-------|-------------|
| `retrieve` | Get specific data by reference (ID, path, URI) |
| `search` | Query for data matching criteria |
| `observe` | Watch and report current state |
| `receive` | Accept pushed data or events |

### UNDERSTAND (6)
Making sense of information.

| Skill | Description |
|-------|-------------|
| `detect` | Find patterns or occurrences in data |
| `classify` | Assign labels or categories to items |
| `measure` | Quantify values with uncertainty |
| `predict` | Forecast future states or outcomes |
| `compare` | Evaluate alternatives against criteria |
| `discover` | Find previously unknown patterns |

### REASON (4)
Planning and analysis.

| Skill | Description |
|-------|-------------|
| `plan` | Create action sequence to achieve goal |
| `decompose` | Break problem into subproblems |
| `critique` | Identify weaknesses and issues |
| `explain` | Justify conclusions with reasoning |

### MODEL (5)
World representation.

| Skill | Description |
|-------|-------------|
| `state` | Create representation of current world state |
| `transition` | Define how state changes over time |
| `attribute` | Establish cause-effect relationships |
| `ground` | Anchor claims to evidence |
| `simulate` | Run what-if scenarios |

### SYNTHESIZE (3)
Content creation.

| Skill | Description |
|-------|-------------|
| `generate` | Produce new content |
| `transform` | Convert between formats |
| `integrate` | Merge data from multiple sources |

### EXECUTE (3)
Changing the world.

| Skill | Description |
|-------|-------------|
| `execute` | Run code or script deterministically |
| `mutate` | Change persistent state |
| `send` | Transmit data to external system |

### VERIFY (5)
Correctness assurance.

| Skill | Description |
|-------|-------------|
| `verify` | Check that conditions are met |
| `checkpoint` | Save state for potential recovery |
| `rollback` | Restore to previous checkpoint |
| `constrain` | Enforce limits and policies |
| `audit` | Record what happened and why |

### REMEMBER (2)
State persistence.

| Skill | Description |
|-------|-------------|
| `persist` | Store data durably |
| `recall` | Retrieve previously stored data |

### COORDINATE (4)
Multi-agent and user interaction.

| Skill | Description |
|-------|-------------|
| `delegate` | Assign task to another agent |
| `synchronize` | Achieve state agreement across agents |
| `invoke` | Execute a composed workflow |
| `inquire` | Request clarification when input is ambiguous |

## Composed Skills (6)

> **Note:** Four of these skills run one of the [12 reference workflows](../schemas/workflow_catalog.yaml): `debug-workflow`, `gap-analysis-workflow`, `digital-twin-bootstrap` and `digital-twin-sync-workflow`. `perspective-validation` and `discover-capabilities` run no catalog workflow. Additional workflows can be composed by following the [Tutorial](../docs/TUTORIAL.md).

| Skill | Description |
|-------|-------------|
| `debug-workflow` | Execute a safe, auditable debugging workflow |
| `gap-analysis-workflow` | Identify missing capabilities and propose additions |
| `digital-twin-bootstrap` | Initialize a digital twin from scratch |
| `digital-twin-sync-workflow` | Synchronize digital twin state with reality |
| `perspective-validation` | Generate a PVC report for socio-technical review |
| `discover-capabilities` | Detect the capabilities a task needs and synthesize a workflow |

## Domain Parameterization

The 36-capability model uses **domain parameters** instead of many domain-specific skills:

```yaml
# Old model (99 capabilities)
- detect-anomaly
- detect-entity
- detect-person

# New model (36 capabilities)
- detect (domain: anomaly)
- detect (domain: entity)
- detect (domain: person)
```

Similarly:
- `measure` replaces: estimate-risk, estimate-impact, estimate-outcome
- `predict` replaces: forecast-risk, forecast-time, forecast-world
- `compare` replaces: compare-plans, compare-entities, prioritize

## Skill Structure

Each skill is a directory `skills/<name>/` that holds a `SKILL.md`: YAML
frontmatter, then the instructions.

```markdown
---
name: skill-name
description: Brief description with trigger keywords
argument-hint: "[argument] [argument]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, ...
context: fork
agent: explore | general-purpose
---

## Intent
What this skill accomplishes

## Inputs
Parameter table

## Procedure
Step-by-step execution

## Output Contract
YAML schema for outputs

## Safety Constraints
Risk level and rules
```

The eight frontmatter keys shown are in all 42 skills, and so are the five
sections. Two more keys are in some skills only:

| Key | In | What it holds |
|-----|----|---------------|
| `layer` | 13 skills: 12 capability skills and `discover-capabilities` | A cognitive layer. The other 29 skills have no such key, and neither does the template (`templates/SKILL_TEMPLATE_ENHANCED.md`). A capability's layer is the one the ontology gives it (`layers` in `schemas/capability_ontology.yaml`), which each capability skill's generated `schemas/output_schema.yaml` repeats; do not read it from the frontmatter |
| `hooks` | 6 skills: `audit`, `checkpoint`, `persist`, `rollback`, `send`, `transform` | Claude Code hooks the skill declares |

No skill declares a version.

The frontmatter `name` is the directory name, except in two composed skills:
`skills/capability-gap-analysis/` declares `gap-analysis-workflow`, and
`skills/digital-twin-sync-loop/` declares `digital-twin-sync-workflow`. The
[Composed Skills](#composed-skills-6) table lists the frontmatter names.

## Layer Execution Flow

```
PERCEIVE → UNDERSTAND → REASON → EXECUTE
    ↓           ↓          ↓        ↓
  MODEL ←→ SYNTHESIZE ←→ VERIFY ←→ COORDINATE
    ↓           ↓
REMEMBER ←→ (persistence)
```

- **PERCEIVE** feeds observations to **UNDERSTAND**
- **UNDERSTAND** provides patterns to **REASON**
- **REASON** drives **EXECUTE** through plans
- **MODEL** represents world state
- **VERIFY** can intercept mutations
- **COORDINATE** enables multi-agent operations
- **REMEMBER** persists across cycles

## Migration from v1 (99 capabilities)

Domain-specific skills from v1 are archived in `_archive/skills/`. The capability mapping is documented in:
- `schemas/workflow_catalog.yaml` (header comment)
- `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md`

## Usage

Skills can be invoked via:
1. Claude Code plugin skill invocation
2. Direct SKILL.md reading and execution
3. Workflow composition via `invoke`

See `schemas/capability_ontology.yaml` for the authoritative ontology definition.
