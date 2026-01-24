---
name: world-state
description: Construct a structured representation of current world/system state including entities, observations, rules, and uncertainty. Use when building domain models, initializing digital twins, or capturing system snapshots.
argument-hint: "[domain] [observations] [scope: shallow|deep]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Build a **canonical world state snapshot** that captures what exists now in a domain. This is the foundation for all world modeling - other capabilities like `state-transition`, `causal-model`, and `simulation` depend on a well-defined world state.

**Success criteria:**
- All significant entities in scope are identified with unique IDs
- Current observations are timestamped and attributed to sources
- Domain rules and constraints are explicit
- Uncertainty is quantified for each state variable
- Output conforms to `world_state_schema.yaml`

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`
- `docs/schemas/event_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `domain` | Yes | string | The domain being modeled (e.g., "codebase", "infrastructure", "workflow") |
| `observations` | Yes | array\|object | Raw observations, signals, or data sources to incorporate |
| `scope` | No | string | `shallow` (top-level only) or `deep` (recursive); default: `deep` |
| `constraints` | No | object | Domain-specific constraints (time bounds, entity filters) |

## Procedure

1) **Identify domain boundaries**: Determine what is in-scope vs out-of-scope for this world state
   - Read domain documentation or specifications
   - List entity types expected in this domain
   - Define the observation window (time range)

2) **Extract entities**: For each observation source, identify distinct entities
   - Assign stable IDs (prefer existing IDs; generate UUID if none)
   - Classify entity type (file, service, person, resource, etc.)
   - Extract key attributes and relationships
   - Flag entities that may have aliases (for `identity-resolution`)

3) **Collect observations**: Transform raw signals into structured observations
   - Timestamp each observation (use source timestamp if available)
   - Record observation source and confidence
   - Link observations to entities they describe

4) **Derive state variables**: From entities and observations, define measurable state
   - Identify quantifiable attributes (counts, statuses, metrics)
   - Establish baseline values with timestamps
   - Note which variables are directly observed vs. inferred

5) **Document rules and constraints**: Capture domain invariants
   - Business rules that must hold
   - Physical constraints (capacity, ordering)
   - Logical constraints (dependencies, exclusions)

6) **Quantify uncertainty**: For each entity/variable, assess confidence
   - Type: aleatoric (inherent randomness) vs. epistemic (knowledge gaps)
   - Distribution parameters where applicable
   - List what additional data would reduce uncertainty

7) **Ground all claims**: Attach evidence anchors to every non-trivial assertion
   - Format: `file:line`, `url`, or `tool:<tool_name>:<output_ref>`

## Output Contract

Return a structured object:

```yaml
world_state:
  id: string  # Unique snapshot ID (e.g., "ws_20250124_143022")
  domain: string  # Domain name
  timestamp: string  # ISO 8601 timestamp
  entities:
    - id: string  # Unique entity identifier
      type: string  # Entity type (file, service, person, etc.)
      attributes: object  # Key-value pairs of entity properties
      relationships:
        - target_id: string
          relation: string  # depends_on, owns, located_in, etc.
          attributes: object | null
  observations:
    - id: string  # Observation ID
      type: string  # Observation type
      value: object  # Observed value
      source: string  # Where this came from
      timestamp: string  # When observed
      confidence: number  # 0.0-1.0
  rules:
    - id: string  # Rule ID
      condition: string  # When rule applies
      effect: string  # What the rule enforces
  uncertainty:
    - entity_id: string | null  # null for global uncertainty
      attribute: string
      distribution: string  # normal, uniform, beta, unknown
      parameters: object  # mean, std, min, max, etc.
provenance:
  sources: array[string]  # Data sources used
  last_updated: string  # ISO timestamp
confidence: number  # 0.0-1.0 overall confidence
evidence_anchors: array[string]  # ["file:line", "url", ...]
assumptions: array[string]  # Explicit assumptions made
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `world_state.id` | string | Unique identifier for this snapshot |
| `world_state.entities` | array | All entities in the current state |
| `world_state.observations` | array | Timestamped observations with sources |
| `world_state.rules` | array | Domain rules and constraints |
| `world_state.uncertainty` | array | Uncertainty specifications per attribute |
| `provenance.sources` | array | List of data sources consulted |
| `confidence` | number | 0.0-1.0 based on evidence completeness |

## Examples

### Example 1: Codebase World State

**Input:**
```yaml
domain: "microservices-codebase"
observations:
  - source: "package.json"
    type: "dependency_manifest"
  - source: "src/"
    type: "source_directory"
scope: deep
```

**Output:**
```yaml
world_state:
  id: "ws_microservices_20250124"
  domain: "microservices-codebase"
  timestamp: "2025-01-24T14:30:00Z"
  entities:
    - id: "svc_api_gateway"
      type: "service"
      attributes:
        language: "typescript"
        port: 3000
        health: "healthy"
      relationships:
        - target_id: "svc_auth"
          relation: "depends_on"
          attributes: { critical: true }
    - id: "svc_auth"
      type: "service"
      attributes:
        language: "typescript"
        port: 3001
        health: "healthy"
  observations:
    - id: "obs_001"
      type: "test_result"
      value: { passed: 142, failed: 0, skipped: 3 }
      source: "npm test output"
      timestamp: "2025-01-24T14:25:00Z"
      confidence: 1.0
  rules:
    - id: "rule_001"
      condition: "service.health == 'unhealthy'"
      effect: "block_deployment"
  uncertainty:
    - entity_id: "svc_api_gateway"
      attribute: "request_latency_p99"
      distribution: "normal"
      parameters: { mean: 45, std: 12 }
provenance:
  sources: ["package.json:1-50", "src/services/", "test-results.json"]
  last_updated: "2025-01-24T14:30:00Z"
confidence: 0.85
evidence_anchors:
  - "package.json:1-50"
  - "src/services/api-gateway/index.ts:1"
  - "src/services/auth/index.ts:1"
assumptions:
  - "All services listed in package.json workspaces are active"
  - "Test results from last CI run are current"
```

**Evidence pattern:** Read package.json for service definitions, traverse src/ for implementation details, correlate with recent test output.

---

### Example 2: Infrastructure World State

**Input:**
```yaml
domain: "kubernetes-cluster"
observations:
  - source: "kubectl get pods -A"
    type: "pod_status"
  - source: "kubectl get nodes"
    type: "node_status"
```

**Output:**
```yaml
world_state:
  id: "ws_k8s_prod_20250124"
  domain: "kubernetes-cluster"
  timestamp: "2025-01-24T15:00:00Z"
  entities:
    - id: "node_worker_01"
      type: "node"
      attributes:
        status: "Ready"
        cpu_capacity: "8"
        memory_capacity: "32Gi"
    - id: "pod_api_abc123"
      type: "pod"
      attributes:
        status: "Running"
        restarts: 0
        namespace: "production"
      relationships:
        - target_id: "node_worker_01"
          relation: "scheduled_on"
  observations:
    - id: "obs_node_01"
      type: "node_condition"
      value: { ready: true, memory_pressure: false, disk_pressure: false }
      source: "kubectl get nodes"
      timestamp: "2025-01-24T15:00:00Z"
      confidence: 0.95
  rules:
    - id: "rule_pod_restart"
      condition: "pod.restarts > 5"
      effect: "alert_oncall"
  uncertainty:
    - entity_id: null
      attribute: "cluster_capacity_utilization"
      distribution: "beta"
      parameters: { alpha: 3, beta: 2 }
provenance:
  sources: ["kubectl:pods", "kubectl:nodes"]
  last_updated: "2025-01-24T15:00:00Z"
confidence: 0.95
evidence_anchors:
  - "tool:kubectl:get_pods_output"
  - "tool:kubectl:get_nodes_output"
assumptions:
  - "kubectl output reflects current cluster state"
  - "No network partition affecting API server connectivity"
```

## Verification

- [ ] All entities have unique IDs within this world state
- [ ] Every observation has a timestamp and source
- [ ] Confidence scores are between 0.0 and 1.0
- [ ] At least one evidence anchor per entity
- [ ] Rules reference valid entity types/attributes
- [ ] Uncertainty distributions have valid parameters

**Verification tools:** `jq` for JSON validation, schema validator for `world_state_schema.yaml`

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not access paths outside the specified domain scope
- Do not invent entities without evidence
- If confidence < 0.3 for critical entities, explicitly flag and suggest data sources
- Clearly mark inferred vs. observed attributes

## Composition Patterns

**Commonly follows:**
- `retrieve` - Gather raw data before building state
- `inspect` - Observe individual artifacts before aggregating
- `identity-resolution` - Resolve entity aliases first

**Commonly precedes:**
- `state-transition` - Define dynamics on top of state (requires world-state)
- `causal-model` - Build causal relationships (requires world-state)
- `diff-world-state` - Compare snapshots over time
- `simulation` - Run scenarios using this state as initial conditions

**Anti-patterns:**
- Never create world-state without at least one concrete observation
- Avoid combining with `act-plan` in same step (state capture should be read-only)

**Workflow references:**
- See `composition_patterns.md#world-model-build` for full workflow
- See `composition_patterns.md#digital-twin-sync-loop` for sync context
