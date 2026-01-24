---
name: diff-world-state
description: Compare two world state snapshots to identify changes in entities, attributes, relationships, and rules. Use when detecting drift, auditing changes, understanding evolution, or debugging state transitions.
argument-hint: "[state_before] [state_after] [comparison_scope]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Perform **world state diff** to identify what changed between two snapshots of a world model. This is essential for drift detection, change auditing, debugging, and understanding system evolution.

**Success criteria:**
- All changes are identified (added, removed, modified)
- Changes are categorized by type and significance
- Root causes are suggested for unexpected changes
- Diff is grounded in evidence from both states
- Summary statistics quantify change magnitude

**World Modeling Context:**
Diff-world-state operates on the output of `world-state` capability. It supports `digital-twin` drift detection, `provenance` tracking, and debugging of `state-transition` models.

**Hard dependencies:**
- Requires two `world-state` outputs to compare

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `state_before` | Yes | object | Earlier world state snapshot |
| `state_after` | Yes | object | Later world state snapshot |
| `comparison_scope` | No | string | `full`, `entities`, `relationships`, `rules` (default: full) |
| `ignore_attributes` | No | array | Attributes to exclude from comparison (e.g., timestamps) |
| `significance_threshold` | No | number | Minimum change magnitude to report (default: 0) |

## Procedure

1) **Validate inputs**: Ensure states are comparable
   - Both states have compatible schemas
   - Time ordering is correct (before < after)
   - Both states are complete (no missing required fields)

2) **Extract comparison keys**: Determine how to match entities
   - Primary: Entity IDs (most reliable)
   - Secondary: Canonical identifiers (for ID changes)
   - Tertiary: Attribute-based matching (when IDs unavailable)

3) **Compute entity changes**: Compare entities between states
   - **Added**: Entities in after but not before
   - **Removed**: Entities in before but not after
   - **Unchanged**: Entities with no differences
   - **Modified**: Entities with attribute changes

4) **Detail attribute changes**: For modified entities
   - Per-attribute diff (old value, new value)
   - Calculate change magnitude where applicable
   - Classify change type (increment, state change, replacement)
   - Note which attributes changed vs. remained stable

5) **Compare relationships**: Analyze connection changes
   - Added relationships
   - Removed relationships
   - Modified relationship attributes
   - Structural changes (topology shifts)

6) **Compare rules and constraints**: Diff domain rules
   - Added/removed rules
   - Modified rule conditions or effects
   - Constraint violations appearing/resolving

7) **Compute summary statistics**: Quantify overall change
   - Entity counts (added, removed, modified)
   - Change rate (% of entities changed)
   - Attribute volatility (which attributes change most)
   - Structural stability (relationship changes)

8) **Analyze change patterns**: Identify meaningful patterns
   - Correlated changes (multiple entities changing together)
   - Cascading changes (one change triggering others)
   - Unexpected changes (flagged for investigation)
   - Missing expected changes

9) **Suggest root causes**: For significant or unexpected changes
   - Temporal correlation (what happened at change time)
   - Causal hypotheses (what could have caused this)
   - Known patterns (deployment, scaling, failure)

## Output Contract

Return a structured object:

```yaml
diff:
  id: string  # Diff identifier
  before_state_id: string  # Reference to before state
  after_state_id: string  # Reference to after state
  before_timestamp: string  # ISO 8601
  after_timestamp: string  # ISO 8601
  time_delta: string  # Duration between states
entities:
  added:
    - id: string
      type: string
      attributes: object
  removed:
    - id: string
      type: string
      attributes: object  # Final state before removal
      removal_reason: string | null  # If determinable
  modified:
    - id: string
      type: string
      changes:
        - attribute: string
          before: any
          after: any
          change_type: increment | decrement | state_change | replacement
          magnitude: number | null  # For numeric changes
          significance: low | medium | high
  unchanged: integer  # Count only
relationships:
  added:
    - source: string
      target: string
      type: string
      attributes: object | null
  removed:
    - source: string
      target: string
      type: string
  modified:
    - source: string
      target: string
      type: string
      changes: array[object]
rules:
  added: array[object]
  removed: array[object]
  modified: array[object]
summary:
  total_entities_before: integer
  total_entities_after: integer
  entities_added: integer
  entities_removed: integer
  entities_modified: integer
  entities_unchanged: integer
  change_rate: number  # 0.0-1.0
  most_volatile_attributes: array[string]
  structural_changes: boolean  # Were relationships significantly altered?
patterns:
  correlated_changes:
    - entities: array[string]
      attributes: array[string]
      correlation: string  # Description of correlation
  cascading_changes:
    - trigger: string  # What started the cascade
      affected: array[string]
      chain: array[string]  # Sequence of changes
  unexpected_changes:
    - entity_id: string
      change: string
      reason: string  # Why unexpected
      suggested_investigation: string
root_cause_hypotheses:
  - hypothesis: string
    confidence: number
    supporting_evidence: array[string]
    contradicting_evidence: array[string]
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entities.added` | array | New entities in after state |
| `entities.removed` | array | Entities no longer present |
| `entities.modified` | array | Entities with changed attributes |
| `summary` | object | Aggregate statistics |
| `patterns` | object | Identified change patterns |
| `root_cause_hypotheses` | array | Suggested explanations |

## Examples

### Example 1: Kubernetes Cluster State Diff

**Input:**
```yaml
state_before:
  id: "ws_k8s_t1"
  timestamp: "2025-01-24T10:00:00Z"
state_after:
  id: "ws_k8s_t2"
  timestamp: "2025-01-24T10:30:00Z"
comparison_scope: full
```

**Output:**
```yaml
diff:
  id: "diff_k8s_t1_t2"
  before_state_id: "ws_k8s_t1"
  after_state_id: "ws_k8s_t2"
  before_timestamp: "2025-01-24T10:00:00Z"
  after_timestamp: "2025-01-24T10:30:00Z"
  time_delta: "30m"
entities:
  added:
    - id: "pod_api_gateway_8c9f5"
      type: "pod"
      attributes:
        namespace: "production"
        status: "Running"
        image: "api-gateway:2.3.2"
  removed:
    - id: "pod_api_gateway_7b4e3"
      type: "pod"
      attributes:
        namespace: "production"
        status: "Running"
        image: "api-gateway:2.3.1"
      removal_reason: "Replaced during rolling update"
  modified:
    - id: "deployment_api_gateway"
      type: "deployment"
      changes:
        - attribute: "image"
          before: "api-gateway:2.3.1"
          after: "api-gateway:2.3.2"
          change_type: replacement
          magnitude: null
          significance: high
        - attribute: "replicas_ready"
          before: 3
          after: 3
          change_type: unchanged
          magnitude: 0
          significance: low
    - id: "node_worker_01"
      type: "node"
      changes:
        - attribute: "cpu_utilization"
          before: 0.45
          after: 0.52
          change_type: increment
          magnitude: 0.07
          significance: low
        - attribute: "memory_utilization"
          before: 0.60
          after: 0.65
          change_type: increment
          magnitude: 0.05
          significance: low
  unchanged: 42
relationships:
  added:
    - source: "pod_api_gateway_8c9f5"
      target: "node_worker_01"
      type: "scheduled_on"
      attributes: null
  removed:
    - source: "pod_api_gateway_7b4e3"
      target: "node_worker_01"
      type: "scheduled_on"
  modified: []
rules:
  added: []
  removed: []
  modified: []
summary:
  total_entities_before: 45
  total_entities_after: 45
  entities_added: 1
  entities_removed: 1
  entities_modified: 2
  entities_unchanged: 42
  change_rate: 0.089
  most_volatile_attributes: ["cpu_utilization", "memory_utilization"]
  structural_changes: true
patterns:
  correlated_changes:
    - entities: ["deployment_api_gateway", "pod_api_gateway_*"]
      attributes: ["image"]
      correlation: "Deployment image change triggered pod replacement"
  cascading_changes:
    - trigger: "deployment_api_gateway.image change"
      affected: ["pod_api_gateway_7b4e3", "pod_api_gateway_8c9f5"]
      chain: ["deployment updated", "old pod terminated", "new pod created"]
  unexpected_changes: []
root_cause_hypotheses:
  - hypothesis: "Rolling deployment of api-gateway v2.3.2"
    confidence: 0.95
    supporting_evidence:
      - "Deployment image changed from 2.3.1 to 2.3.2"
      - "Pod with old image removed, new pod with new image added"
      - "Replicas stayed at 3 (rolling, not scaled)"
    contradicting_evidence: []
confidence: 0.95
evidence_anchors:
  - "ws_k8s_t1:entities"
  - "ws_k8s_t2:entities"
  - "deployment_log:2025-01-24T10:15:00Z"
assumptions:
  - "Both states captured complete cluster state"
  - "No intermediate states between t1 and t2"
```

**Evidence pattern:** Compared entity lists, detected pod replacement pattern, correlated with deployment change.

---

### Example 2: Service Health Drift Detection

**Input:**
```yaml
state_before:
  id: "ws_service_baseline"
  timestamp: "2025-01-23T00:00:00Z"
state_after:
  id: "ws_service_current"
  timestamp: "2025-01-24T16:00:00Z"
comparison_scope: entities
significance_threshold: 0.1
```

**Output:**
```yaml
diff:
  id: "diff_service_drift"
  before_state_id: "ws_service_baseline"
  after_state_id: "ws_service_current"
  before_timestamp: "2025-01-23T00:00:00Z"
  after_timestamp: "2025-01-24T16:00:00Z"
  time_delta: "40h"
entities:
  added: []
  removed: []
  modified:
    - id: "api_gateway"
      type: "service"
      changes:
        - attribute: "latency_p99"
          before: 45
          after: 78
          change_type: increment
          magnitude: 33
          significance: high
        - attribute: "error_rate"
          before: 0.001
          after: 0.015
          change_type: increment
          magnitude: 0.014
          significance: high
        - attribute: "request_rate"
          before: 1500
          after: 2200
          change_type: increment
          magnitude: 700
          significance: medium
  unchanged: 4
summary:
  total_entities_before: 5
  total_entities_after: 5
  entities_modified: 1
  change_rate: 0.2
  most_volatile_attributes: ["latency_p99", "error_rate", "request_rate"]
  structural_changes: false
patterns:
  correlated_changes:
    - entities: ["api_gateway"]
      attributes: ["latency_p99", "error_rate", "request_rate"]
      correlation: "All metrics degraded together, possibly load-related"
  unexpected_changes:
    - entity_id: "api_gateway"
      change: "latency_p99 increased 73%"
      reason: "Exceeds typical variation range"
      suggested_investigation: "Check for slow queries, resource exhaustion"
root_cause_hypotheses:
  - hypothesis: "Service under increased load causing degradation"
    confidence: 0.7
    supporting_evidence:
      - "Request rate up 47%"
      - "Latency and errors correlated with load"
    contradicting_evidence:
      - "Similar load spikes before without this degradation"
  - hypothesis: "Database performance issue"
    confidence: 0.6
    supporting_evidence:
      - "Latency pattern consistent with slow queries"
    contradicting_evidence:
      - "No database changes detected"
confidence: 0.8
evidence_anchors:
  - "datadog:metrics/api_gateway:40h"
  - "baseline:ws_service_baseline"
assumptions:
  - "Baseline represents healthy state"
  - "Metrics are accurate"
```

## Verification

- [ ] All entities are accounted for (added + removed + modified + unchanged = total)
- [ ] Change types are correctly classified
- [ ] Magnitude calculations are accurate for numeric changes
- [ ] Patterns identified are supported by evidence
- [ ] Root cause hypotheses are falsifiable

**Verification tools:** Arithmetic validators, pattern detectors

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not modify either state during comparison
- Flag when states have incompatible schemas
- Mark assumptions when inferring root causes
- Distinguish observation from interpretation

## Composition Patterns

**Commonly follows:**
- `world-state` - Creates the states to diff
- `digital-twin` - Provides twin snapshots
- `retrieve` - Get historical state snapshots

**Commonly precedes:**
- `explain` - Explain what the diff means
- `alert` - Notify on significant drift
- `causal-model` - Investigate causes of changes
- `plan` - Plan response to drift

**Anti-patterns:**
- Never compare states with different schemas without mapping
- Avoid diffing states too far apart (intermediate changes lost)

**Workflow references:**
- See `composition_patterns.md#digital-twin-sync-loop` for drift detection
- See `composition_patterns.md#debug-code-change` for change analysis
