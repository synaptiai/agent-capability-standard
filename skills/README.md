# Agent Capability Skills

This directory contains 103 skills organized according to the capability ontology's 8 layers plus composed workflows.

## Skill Layers (Ontology-Aligned)

| Layer | Count | Purpose |
|-------|-------|---------|
| [perception/](./perception) | 4 | Observe the world |
| [modeling/](./modeling) | 45 | Build understanding |
| [reasoning/](./reasoning) | 20 | Think and decide |
| [action/](./action) | 12 | Change things |
| [safety/](./safety) | 8 | Protect and verify |
| [meta/](./meta) | 6 | Self-reflection |
| [memory/](./memory) | 1 | Persistence |
| [coordination/](./coordination) | 3 | Multi-agent operations |
| [workflows/](./workflows) | 4 | Composed multi-step skills |

**Total: 99 atomic capabilities + 4 composed workflows = 103 skills**

## Layer Descriptions

### PERCEPTION (4)
Observe the world through sensors and inputs.

| Skill | Description |
|-------|-------------|
| `inspect` | Examine objects in detail |
| `receive` | Receive and process incoming messages |
| `retrieve` | Retrieve data from external sources |
| `search` | Search for information across sources |

### MODELING (45)
Build understanding through detection, identification, estimation, and forecasting.

**Core Primitives (4):**
- `detect` - Detect presence or absence
- `identify` - Determine identity or classification
- `estimate` - Produce approximate values
- `forecast` - Predict future states

**Detection Family (6):**
- `detect-activity`, `detect-anomaly`, `detect-attribute`, `detect-entity`, `detect-person`, `detect-world`

**Identification Family (7):**
- `identify-activity`, `identify-anomaly`, `identify-attribute`, `identify-entity`, `identify-human-attribute`, `identify-person`, `identify-world`

**Estimation Family (7):**
- `estimate-activity`, `estimate-attribute`, `estimate-impact`, `estimate-outcome`, `estimate-relationship`, `estimate-risk`, `estimate-world`

**Forecasting Family (6):**
- `forecast-attribute`, `forecast-impact`, `forecast-outcome`, `forecast-risk`, `forecast-time`, `forecast-world`

**World Modeling (15):**
- `causal-model` - Build and query causal models
- `diff-world-state` - Compute state differences
- `digital-twin` - Manage digital twin representations
- `grounding` - Ground abstract concepts to reality
- `identity-resolution` - Resolve entity identities
- `integrate` - Integrate multiple data sources
- `map-relationships` - Map relationships between entities
- `model-schema` - Define and validate schemas
- `provenance` - Track data lineage
- `simulation` - Run simulations
- `spatial-reasoning` - Reason about spatial relationships
- `state-transition` - Model state transitions
- `temporal-reasoning` - Reason about temporal relationships
- `uncertainty-model` - Model and propagate uncertainty
- `world-state` - Manage world state representation

### REASONING (20)
Think and decide through comparison, evaluation, and planning.

**Comparison (7):**
- `compare` - Compare two or more items
- `compare-attributes`, `compare-documents`, `compare-entities`, `compare-impact`, `compare-people`, `compare-plans`

**Evaluation & Decision (6):**
- `critique` - Provide critical feedback
- `decide` - Make decisions between options
- `decompose` - Break down complex tasks
- `evaluate` - Evaluate options or outcomes
- `optimize` - Optimize parameters or processes
- `validate` - Validate data against rules

**Planning & Scheduling (3):**
- `plan` - Create execution plans
- `prioritize` - Prioritize tasks or items
- `schedule` - Schedule future actions

**Communication (4):**
- `explain` - Explain concepts or decisions
- `generalize` - Abstract to general principles
- `summarize` - Summarize content
- `translate` - Translate between representations

### ACTION (12)
Change things through execution and generation.

**Execution (3):**
- `act` - Execute an action in the environment
- `act-plan` - Plan and execute actions
- `send` - Send messages to targets

**Generation (8):**
- `generate` - Create new content
- `generate-attribute`, `generate-audio`, `generate-image`, `generate-numeric-data`, `generate-plan`, `generate-text`, `generate-world`

**Transformation (1):**
- `transform` - Transform data between formats

### SAFETY (8)
Protect and verify through checkpointing, auditing, and constraints.

| Skill | Description |
|-------|-------------|
| `audit` | Audit data or operations |
| `checkpoint` | Create execution checkpoints |
| `constrain` | Apply constraints to operations |
| `improve` | Suggest improvements |
| `mitigate` | Apply mitigation strategies |
| `persist` | Persist data to storage |
| `rollback` | Rollback to previous state |
| `verify` | Verify conditions or results |

### META (6)
Self-reflection through discovery and introspection.

| Skill | Description |
|-------|-------------|
| `discover` | Find previously unknown information |
| `discover-activity` | Discover new activities |
| `discover-anomaly` | Discover anomalies |
| `discover-human-attribute` | Discover human traits |
| `discover-outcome` | Discover potential outcomes |
| `discover-relationship` | Discover relationships |

### MEMORY (1)
Persistence through recall.

| Skill | Description |
|-------|-------------|
| `recall` | Recall previously stored data |

### COORDINATION (3)
Multi-agent operations through delegation and synchronization.

| Skill | Description |
|-------|-------------|
| `delegate` | Delegate to other agents |
| `invoke-workflow` | Invoke workflow execution |
| `synchronize` | Synchronize state across systems |

### WORKFLOWS (4)
Composed multi-step workflow skills that orchestrate multiple capabilities.

| Workflow | Description |
|----------|-------------|
| `debug-workflow` | Systematic debugging workflow |
| `digital-twin-sync-workflow` | Synchronize digital twin state |
| `gap-analysis-workflow` | Perform gap analysis |
| `world-model-workflow` | Build and maintain world models |

## Skill Structure

Each skill follows the standard SKILL.md format:

```markdown
---
name: skill-name
description: Brief description
layer: LAYER_NAME
---

## Purpose
What this skill accomplishes

## When to Use
Trigger conditions

## Workflow
Step-by-step execution

## Inputs/Outputs
Schema definitions
```

## Layer Execution Order

The ontology defines a natural flow through layers:

```
PERCEPTION → MODELING → REASONING → ACTION
     ↓           ↓          ↓          ↓
   MEMORY ←→ COORDINATION ←→ SAFETY ←→ META
```

- **PERCEPTION** feeds observations to **MODELING**
- **MODELING** provides understanding to **REASONING**
- **REASONING** drives **ACTION**
- **SAFETY** can intercept at any point
- **META** reflects on the entire process
- **MEMORY** persists across cycles
- **COORDINATION** enables multi-agent operations

## Usage

Skills can be invoked via:
1. Claude Code plugin skill invocation
2. Direct SKILL.md reading and execution
3. Workflow composition via `invoke-workflow`

See the [plugin.json](../plugin.json) for plugin registration details.
