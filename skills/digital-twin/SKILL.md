---
name: digital-twin
description: Model real-world assets, processes, or systems as synchronized digital representations with sync rules, drift detection, and reconciliation strategies. Use when building live mirrors of physical or operational systems.
argument-hint: "[domain] [physical_entities] [sync_rules]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Build a **digital twin** - a synchronized digital representation of a physical or operational system that can be queried, simulated, and used for decision-making while staying current with reality.

**Success criteria:**
- Physical entities have complete digital representations
- Sync rules ensure twins track their physical counterparts
- Drift is detected and quantified
- Reconciliation strategies handle divergence
- Twin state is queryable and simulatable

**World Modeling Context:**
Digital twins are the culmination of world modeling capabilities. They combine `world-state`, `state-transition`, `causal-model`, and `simulation` into a living model synchronized with reality. The `diff-world-state` capability detects drift between twin and reality.

**Soft dependencies:**
- Benefits from `world-state` - Foundation for twin structure
- Benefits from `state-transition` - Dynamics modeling
- Benefits from `simulation` - What-if analysis
- Benefits from `temporal-reasoning` - Time-based sync

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `domain` | Yes | string | Domain being twinned (e.g., "factory-floor", "kubernetes-cluster") |
| `physical_entities` | Yes | array | Real-world entities to create twins for |
| `data_sources` | Yes | array | Sources for sync (sensors, APIs, logs) |
| `sync_rules` | No | object | How often to sync, what triggers updates |
| `fidelity` | No | string | `low`, `medium`, `high` - level of detail (default: medium) |

## Procedure

1) **Identify twinnable entities**: Determine what to model
   - Physical assets (machines, infrastructure, vehicles)
   - Processes (workflows, pipelines, operations)
   - Systems (software, networks, supply chains)
   - Note: Not everything needs twinning - focus on value

2) **Define twin schema**: Structure for digital representations
   - Static attributes (serial number, location, capacity)
   - Dynamic state (status, metrics, health)
   - Relationships (connections, dependencies, containment)
   - Historical state (for temporal queries)

3) **Map data sources**: Connect to real-world signals
   - **Sensors**: IoT, monitoring agents, metrics
   - **APIs**: System APIs, management interfaces
   - **Logs**: Event streams, audit trails
   - **Manual**: Inspection reports, tickets
   - Document latency and reliability per source

4) **Establish sync rules**: How twins stay current
   - **Frequency**: How often to sync (real-time, periodic, on-demand)
   - **Triggers**: What events force immediate sync
   - **Scope**: Full refresh vs. incremental updates
   - **Priority**: Which attributes matter most

5) **Build initial twin state**: Create baseline
   - Collect current state from all sources
   - Apply `integrate` to combine sources
   - Validate against schema
   - Establish timestamp baseline

6) **Define drift detection**: How to notice divergence
   - **Threshold drift**: Metric exceeds acceptable range
   - **Structural drift**: Missing or extra entities
   - **Temporal drift**: Updates not received in expected time
   - **Semantic drift**: Behavior doesn't match model

7) **Create reconciliation strategies**: How to handle drift
   - **Auto-correct**: Twin updates to match reality
   - **Alert**: Notify humans of significant drift
   - **Investigate**: Drift may indicate real problem
   - **Ignore**: Some drift is acceptable

8) **Enable twin operations**: What can be done with the twin
   - **Query**: Answer questions about current state
   - **Simulate**: Run what-if scenarios
   - **Predict**: Forecast future states
   - **Compare**: Diff against historical states
   - **Optimize**: Suggest improvements

## Output Contract

Return a structured object:

```yaml
digital_twin:
  id: string  # Twin identifier
  domain: string
  created: string  # ISO 8601
  last_sync: string  # Last successful sync
  fidelity: low | medium | high
  schema_ref: string  # Reference to schema used
  entities:
    - physical_id: string  # Real-world identifier
      twin_id: string  # Twin identifier
      type: string  # Entity type
      static_attributes: object  # Rarely changing properties
      dynamic_state: object  # Current state variables
      last_updated: string  # When this entity was last synced
      source_attribution:  # Where each attribute came from
        attribute_name: string  # Data source
      health: healthy | degraded | stale | unknown
  relationships:
    - source_twin_id: string
      target_twin_id: string
      type: string
      attributes: object | null
sync_configuration:
  data_sources:
    - id: string
      type: sensor | api | log | manual
      endpoint: string | null
      frequency: string  # e.g., "1m", "5m", "on_change"
      latency: string  # Typical latency
      reliability: number  # 0.0-1.0
      last_success: string
      last_failure: string | null
  rules:
    - entity_type: string
      attribute: string | "*"
      source: string
      frequency: string
      on_change_triggers: array[string] | null
drift_detection:
  thresholds:
    - attribute: string
      warning: number | string
      critical: number | string
  staleness_limit: string  # How old before considered stale
  structural_checks: array[string]  # Invariants to check
current_drift:
  entities_stale: integer
  entities_drifted: integer
  last_check: string
  issues:
    - entity_id: string
      type: threshold | structural | temporal | semantic
      description: string
      severity: warning | critical
      detected_at: string
reconciliation:
  strategy: auto_correct | alert | investigate | ignore
  recent_actions:
    - timestamp: string
      entity_id: string
      action: string
      result: success | failed
operations:
  query_enabled: boolean
  simulation_enabled: boolean
  prediction_enabled: boolean
  last_query: string | null
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entities` | array | All twinned entities with current state |
| `sync_configuration` | object | How and when to sync |
| `drift_detection` | object | Rules for detecting divergence |
| `current_drift` | object | Current drift status |
| `reconciliation` | object | How drift is handled |
| `operations` | object | What the twin can do |

## Examples

### Example 1: Kubernetes Cluster Digital Twin

**Input:**
```yaml
domain: "kubernetes-cluster"
physical_entities:
  - type: "node"
    identifiers: ["node-1", "node-2", "node-3"]
  - type: "pod"
    identifiers: ["auto-discover"]
data_sources:
  - type: "api"
    endpoint: "kubectl"
  - type: "api"
    endpoint: "prometheus"
sync_rules:
  frequency: "30s"
  on_change: ["pod_status", "node_status"]
fidelity: high
```

**Output:**
```yaml
digital_twin:
  id: "twin_k8s_prod_20250124"
  domain: "kubernetes-cluster"
  created: "2025-01-24T10:00:00Z"
  last_sync: "2025-01-24T16:30:00Z"
  fidelity: high
  schema_ref: "kubernetes_schema_v1"
  entities:
    - physical_id: "node-1"
      twin_id: "twin_node_1"
      type: "node"
      static_attributes:
        hostname: "node-1.cluster.local"
        cpu_cores: 8
        memory_gb: 32
        zone: "us-east-1a"
      dynamic_state:
        status: "Ready"
        cpu_utilization: 0.45
        memory_utilization: 0.62
        pod_count: 15
        conditions:
          ready: true
          memory_pressure: false
          disk_pressure: false
      last_updated: "2025-01-24T16:30:00Z"
      source_attribution:
        status: "kubectl"
        cpu_utilization: "prometheus"
        memory_utilization: "prometheus"
      health: healthy
    - physical_id: "api-gateway-7b9f4-xyz"
      twin_id: "twin_pod_api_gateway_1"
      type: "pod"
      static_attributes:
        namespace: "production"
        deployment: "api-gateway"
        image: "api-gateway:2.3.1"
      dynamic_state:
        status: "Running"
        restarts: 0
        cpu_usage: 0.35
        memory_usage: 0.50
        ready_containers: 1
        total_containers: 1
      last_updated: "2025-01-24T16:30:00Z"
      source_attribution:
        status: "kubectl"
        cpu_usage: "prometheus"
      health: healthy
  relationships:
    - source_twin_id: "twin_pod_api_gateway_1"
      target_twin_id: "twin_node_1"
      type: "scheduled_on"
      attributes: null
sync_configuration:
  data_sources:
    - id: "kubectl"
      type: api
      endpoint: "kubectl get pods,nodes -o json"
      frequency: "30s"
      latency: "2s"
      reliability: 0.99
      last_success: "2025-01-24T16:30:00Z"
      last_failure: null
    - id: "prometheus"
      type: api
      endpoint: "prometheus:9090/api/v1/query"
      frequency: "15s"
      latency: "1s"
      reliability: 0.98
      last_success: "2025-01-24T16:30:00Z"
      last_failure: "2025-01-24T14:22:00Z"
  rules:
    - entity_type: "pod"
      attribute: "*"
      source: "kubectl"
      frequency: "30s"
      on_change_triggers: ["status_change", "restart"]
    - entity_type: "*"
      attribute: "cpu_utilization"
      source: "prometheus"
      frequency: "15s"
      on_change_triggers: null
drift_detection:
  thresholds:
    - attribute: "cpu_utilization"
      warning: 0.8
      critical: 0.95
    - attribute: "memory_utilization"
      warning: 0.85
      critical: 0.95
    - attribute: "restarts"
      warning: 3
      critical: 10
  staleness_limit: "5m"
  structural_checks:
    - "All pods have nodes"
    - "No orphan services"
current_drift:
  entities_stale: 0
  entities_drifted: 1
  last_check: "2025-01-24T16:30:00Z"
  issues:
    - entity_id: "twin_node_2"
      type: threshold
      description: "Memory utilization 87% exceeds warning threshold 85%"
      severity: warning
      detected_at: "2025-01-24T16:15:00Z"
reconciliation:
  strategy: alert
  recent_actions:
    - timestamp: "2025-01-24T16:15:00Z"
      entity_id: "twin_node_2"
      action: "alert_sent"
      result: success
operations:
  query_enabled: true
  simulation_enabled: true
  prediction_enabled: false
  last_query: "2025-01-24T16:25:00Z"
confidence: 0.95
evidence_anchors:
  - "kubectl:cluster_state_snapshot"
  - "prometheus:metrics_query"
assumptions:
  - "kubectl and prometheus are authoritative sources"
  - "30s sync interval sufficient for operational decisions"
```

**Evidence pattern:** Created twin from kubernetes API and prometheus metrics, established sync rules for continuous updates.

---

### Example 2: Software Service Twin

**Input:**
```yaml
domain: "microservice"
physical_entities:
  - type: "service"
    identifier: "api-gateway"
data_sources:
  - type: "file"
    path: "package.json"
  - type: "api"
    endpoint: "datadog"
  - type: "log"
    path: "application.log"
fidelity: medium
```

**Output:**
```yaml
digital_twin:
  id: "twin_api_gateway"
  domain: "microservice"
  created: "2025-01-24T12:00:00Z"
  last_sync: "2025-01-24T16:30:00Z"
  fidelity: medium
  entities:
    - physical_id: "api-gateway"
      twin_id: "twin_svc_api_gateway"
      type: "service"
      static_attributes:
        name: "api-gateway"
        version: "2.3.1"
        language: "typescript"
        repository: "github.com/company/api-gateway"
      dynamic_state:
        health: "healthy"
        latency_p99: 45
        error_rate: 0.001
        request_rate: 1500
        active_connections: 234
        last_deployment: "2025-01-22T10:00:00Z"
      last_updated: "2025-01-24T16:30:00Z"
      health: healthy
  relationships: []
sync_configuration:
  data_sources:
    - id: "package_json"
      type: file
      endpoint: "package.json"
      frequency: "on_change"
      reliability: 1.0
    - id: "datadog"
      type: api
      frequency: "1m"
      reliability: 0.98
    - id: "app_log"
      type: log
      frequency: "real_time"
      reliability: 0.95
current_drift:
  entities_stale: 0
  entities_drifted: 0
  last_check: "2025-01-24T16:30:00Z"
  issues: []
operations:
  query_enabled: true
  simulation_enabled: true
  prediction_enabled: true
  last_query: null
confidence: 0.9
evidence_anchors:
  - "package.json"
  - "datadog:services/api-gateway"
assumptions:
  - "Datadog metrics reflect actual service behavior"
```

## Verification

- [ ] All physical entities have corresponding twins
- [ ] Sync sources are accessible and functional
- [ ] Drift thresholds are reasonable
- [ ] Reconciliation strategy handles all drift types
- [ ] Twin state is queryable

**Verification tools:** Source connectivity tests, schema validators, drift simulators

## Safety Constraints

- `mutation`: false (for read operations)
- `requires_checkpoint`: true (for sync operations)
- `requires_approval`: false
- `risk`: medium (sync can have side effects)

**Capability-specific rules:**
- Never let twin state be authoritative over reality
- Alert humans when drift exceeds critical thresholds
- Maintain audit trail of all sync operations
- Design for eventual consistency, not perfect sync

## Composition Patterns

**Commonly follows:**
- `world-state` - Build initial twin from state snapshot
- `model-schema` - Define twin structure
- `integrate` - Combine sources for initial twin

**Commonly precedes:**
- `simulation` - Run what-if on twin state
- `diff-world-state` - Detect drift over time
- `forecast-*` - Predict future states from twin
- `plan` - Use twin for planning

**Anti-patterns:**
- Never treat twin as ground truth over reality
- Avoid high-fidelity twins for rapidly changing systems (sync can't keep up)

**Workflow references:**
- See `composition_patterns.md#digital-twin-sync-loop` for sync workflow
- See `composition_patterns.md#world-model-build` for initial construction
