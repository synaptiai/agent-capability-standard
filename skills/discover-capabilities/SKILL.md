---
name: discover-capabilities
description: >-
  Analyze a task description to detect required capabilities from the ontology,
  identify gaps, and synthesize a valid workflow automatically.
  Trigger: "discover capabilities", "what capabilities do I need",
  "analyze task", "synthesize workflow"
argument-hint: "[task-description]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash
context: fork
agent: general-purpose
layer: REASON
---

## Intent

Execute **discover-capabilities** to analyze a natural language task description and automatically:
1. Detect which ontology capabilities are needed
2. Identify gaps where the ontology lacks coverage
3. Synthesize a valid workflow DAG from matched capabilities

This skill bridges the gap between "I want to do X" and "here are the specific
capabilities and workflow steps needed to do X safely."

**Success criteria:**
- All atomic actions in the task are identified
- Each action maps to an ontology capability with confidence score
- Missing capabilities are flagged with proposed extensions
- A valid workflow is synthesized with proper safety steps
- Evidence anchors trace the discovery reasoning

**Compatible schemas:**
- `schemas/capability_ontology.yaml`
- `schemas/workflow_catalog.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `task_description` | Yes | string | Natural language description of the task to analyze |
| `domain` | No | string | Domain context for specialization (e.g., "security", "data-pipeline") |

## Procedure

1) **Load ontology context**: Read the capability ontology to understand available capabilities
   - Load `schemas/capability_ontology.yaml` via CapabilityRegistry
   - Load `schemas/workflow_catalog.yaml` via WorkflowEngine
   - Note: 36 atomic capabilities across 9 cognitive layers

2) **Analyze task**: Decompose the task into atomic capability requirements
   - Parse the task description for action verbs and targets
   - Map each action to the closest ontology capability
   - Assign confidence scores based on semantic match quality
   - Identify domain parameters where applicable

3) **Classify matches**: Validate and filter capability matches
   - Accept matches with confidence >= 0.6
   - Route low-confidence matches to gap detection
   - Identify unmatched requirements

4) **Detect gaps**: For unmatched requirements
   - Find nearest existing capabilities by semantic similarity
   - If available, generate proposed new capabilities with:
     - Suggested layer, risk level, and schemas
     - Edges to related existing capabilities
     - Rationale for the proposal

5) **Synthesize workflow**: Build a valid workflow from matched capabilities
   - Resolve transitive dependency chains (`requires` edges)
   - Insert safety steps (`checkpoint` before mutations, `audit` at end)
   - Topological sort respecting `precedes` edge ordering
   - Check for `conflicts_with` violations
   - Generate data flow bindings between steps

6) **Present results**: Format and display the discovery output
   - List detected capabilities with confidence and reasoning
   - Show any gaps with proposals
   - Display synthesized workflow steps
   - Offer to validate workflow against ontology
   - Offer to scaffold gap capabilities if needed

## Output Contract

Return a structured object:

```yaml
capabilities:
  - id: string          # ontology capability ID
    confidence: number  # 0.0-1.0
    reasoning: string   # why this capability was matched
    domain: string      # domain parameter if applicable
gaps:
  - description: string
    proposed_capability:
      id: string
      layer: string
      risk: string
workflow:
  name: string
  steps: array          # ordered workflow steps
  confidence: number    # overall workflow confidence
confidence: number      # overall discovery confidence 0.0-1.0
evidence_anchors: array # provenance trail
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `capabilities` | array | Matched ontology capabilities with scores |
| `gaps` | array | Unmatched requirements with proposals |
| `workflow` | object | Synthesized or matched existing workflow |
| `confidence` | number | Overall confidence (0.0-1.0) |
| `evidence_anchors` | array | Discovery provenance trail |

## Examples

### Example 1: Simple Analysis Task

**Input:**
```yaml
task_description: "Find all Python files with TODO comments"
```

**Output:**
```yaml
capabilities:
  - id: search
    confidence: 0.95
    reasoning: "'Find' maps to search capability for discovering items under uncertainty"
  - id: detect
    confidence: 0.85
    reasoning: "'TODO comments' requires pattern detection within found files"
    domain: pattern
gaps: []
workflow:
  name: find_python_files_with_todo
  steps:
    - capability: search
      purpose: Find Python files in the codebase
      store_as: search_out
    - capability: detect
      purpose: Detect TODO patterns in found files
      domain: pattern
      store_as: detect_out
      input_bindings:
        source: ${search_out}
  confidence: 0.9
confidence: 0.9
```

### Example 2: Mutation Task with Safety

**Input:**
```yaml
task_description: "Delete old log files older than 30 days"
```

**Output:**
```yaml
capabilities:
  - id: search
    confidence: 0.9
    reasoning: "'log files' requires searching for matching files"
  - id: detect
    confidence: 0.8
    reasoning: "'older than 30 days' requires date-based detection"
    domain: time
  - id: checkpoint
    confidence: 1.0
    reasoning: "Auto-added: mutation requires checkpoint for safety"
  - id: mutate
    confidence: 0.95
    reasoning: "'Delete' is a persistent state mutation"
  - id: audit
    confidence: 1.0
    reasoning: "Auto-added: mutation operations require audit trail"
gaps: []
workflow:
  name: delete_old_log_files
  steps:
    - capability: search
      purpose: Find log files in the system
      store_as: search_out
    - capability: detect
      purpose: Filter files older than 30 days
      domain: time
      store_as: detect_out
    - capability: checkpoint
      purpose: Create safety checkpoint before deletion
      store_as: checkpoint_out
    - capability: mutate
      purpose: Delete the identified old log files
      store_as: mutate_out
      requires_checkpoint: true
    - capability: audit
      purpose: Record deletion actions for audit trail
      store_as: audit_out
  confidence: 0.93
confidence: 0.93
```

## Verification

- [ ] All action verbs in the task description are identified
- [ ] Each capability match has confidence score and reasoning
- [ ] Safety steps (checkpoint, audit) are automatically added for mutations
- [ ] Workflow respects ontology edge constraints (requires, precedes, conflicts_with)
- [ ] Binding references between steps are valid (no undefined variables)

**Verification tools:** Read, Grep, Bash

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Discovery is read-only: it analyzes and proposes but never modifies the ontology
- Gap proposals are suggestions only; they require governance review before adoption
- Workflow synthesis validates against ontology constraints but does not execute

## Composition Patterns

**Commonly follows:**
- `inquire` - User provides task description via prompt
- `retrieve` - Load ontology and workflow catalog

**Commonly precedes:**
- `plan` - Use discovered capabilities to plan implementation
- `invoke` - Execute the synthesized workflow
- `generate` - Scaffold new capability files for gap proposals

**Anti-patterns:**
- Do not execute synthesized workflows without human review
- Do not add proposed capabilities to the ontology without governance
- Do not bypass gap detection by forcing low-confidence matches

**Workflow references:**
- See `schemas/workflow_catalog.yaml` for existing workflow patterns
- See `schemas/capability_ontology.yaml` for the full ontology
