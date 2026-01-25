---
name: spatial-reasoning
description: Reason over spatial dimensions including geometry, proximity, containment, layout, and topological relationships. Use when analyzing architecture diagrams, network topology, physical layouts, or abstract spatial relationships in code/data.
argument-hint: "[entities] [query: proximity|containment|layout|topology] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Perform **spatial analysis** on entities with positions, boundaries, or topological relationships to answer questions about space: what is near what, what contains what, how things are laid out, what is connected to what.

**Success criteria:**
- Spatial relationships are correctly identified (contains, adjacent, overlaps, connected)
- Distances and proximities are calculated or estimated
- Containment hierarchies are properly nested
- Topological invariants are preserved
- Layout constraints are validated

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entities` | Yes | array | Entities with spatial attributes (positions, bounds, connections) |
| `query` | Yes | string | Type of spatial analysis: `proximity`, `containment`, `layout`, `topology`, `path` |
| `space_type` | No | string | `physical`, `logical`, `abstract` (default: infer from data) |
| `constraints` | No | object | Distance thresholds, containment rules, layout preferences |

## Procedure

1) **Identify space type**: Determine the nature of spatial relationships
   - **Physical**: Coordinates, distances, areas (e.g., infrastructure, floor plans)
   - **Logical**: Containment hierarchies, namespaces (e.g., code modules, org charts)
   - **Abstract**: Graph topology, connectivity (e.g., network diagrams, dependencies)
   - Note: Some domains mix types (e.g., cloud regions are logical but have physical implications)

2) **Extract spatial attributes**: For each entity, identify spatial properties
   - Position: coordinates, address, path, level
   - Bounds: area, volume, extent, boundary
   - Connections: edges, links, ports, interfaces
   - Properties: movable, fixed, scalable, overlappable

3) **Apply query-specific analysis**:

   For `proximity`:
   - Calculate pairwise distances (Euclidean, Manhattan, hops)
   - Identify nearest neighbors
   - Cluster by proximity threshold
   - Detect isolated entities

   For `containment`:
   - Build containment tree (parent-child relationships)
   - Validate proper nesting (no overlapping siblings)
   - Identify orphans (entities without containers)
   - Check containment capacity constraints

   For `layout`:
   - Analyze arrangement patterns (grid, hierarchy, radial)
   - Detect alignment and spacing regularity
   - Identify layout violations or anomalies
   - Suggest optimizations if requested

   For `topology`:
   - Build connectivity graph
   - Compute graph properties (connected components, cycles, bridges)
   - Identify critical nodes (single points of failure)
   - Analyze reachability between entities

   For `path`:
   - Find paths between entities
   - Calculate shortest path (by hops, distance, or cost)
   - Identify alternative routes
   - Detect blocked or broken paths

4) **Apply spatial constraints**: Validate against rules
   - Minimum/maximum distances
   - Required/forbidden adjacencies
   - Capacity limits
   - Connectivity requirements

5) **Quantify spatial uncertainty**: Assess confidence in spatial claims
   - Position accuracy (exact vs. approximate)
   - Boundary precision
   - Missing spatial data

6) **Ground findings**: Attach evidence for each spatial relationship
   - Reference source diagrams, configs, or measurements
   - Show calculation methodology

## Output Contract

Return a structured object:

```yaml
spatial_analysis:
  query_type: string  # proximity, containment, layout, topology, path
  space_type: string  # physical, logical, abstract
  entities:
    - id: string
      position: object | null  # {x, y, z} or {path} or {level}
      bounds: object | null  # {width, height} or {extent}
      connections: array[string] | null
  results:
    # Query-specific results
    proximity: object | null
    containment: object | null
    layout: object | null
    topology: object | null
    path: object | null
  spatial_relations:
    - entity_a: string
      relation: string  # contains, adjacent, overlaps, connected, above, below, inside
      entity_b: string
      attributes: object | null  # distance, direction, etc.
      confidence: number
  constraint_violations: array[object]  # Any violated spatial rules
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entities` | array | Entities with normalized spatial attributes |
| `results` | object | Query-specific analysis results |
| `spatial_relations` | array | Pairwise spatial relationships |
| `constraint_violations` | array | Spatial rules that were violated |
| `confidence` | number | Based on position/boundary data quality |

## Examples

### Example 1: Code Module Containment

**Input:**
```yaml
entities:
  - id: "src/"
    type: "directory"
    path: "src"
  - id: "src/services/"
    type: "directory"
    path: "src/services"
  - id: "src/services/auth.ts"
    type: "file"
    path: "src/services/auth.ts"
  - id: "src/utils/"
    type: "directory"
    path: "src/utils"
  - id: "tests/"
    type: "directory"
    path: "tests"
query: containment
space_type: logical
```

**Output:**
```yaml
spatial_analysis:
  query_type: "containment"
  space_type: "logical"
  entities:
    - id: "src/"
      position: { level: 0, path: "src" }
      bounds: null
      connections: null
    - id: "src/services/"
      position: { level: 1, path: "src/services" }
    - id: "src/services/auth.ts"
      position: { level: 2, path: "src/services/auth.ts" }
    - id: "src/utils/"
      position: { level: 1, path: "src/utils" }
    - id: "tests/"
      position: { level: 0, path: "tests" }
  results:
    containment:
      tree:
        - id: "root"
          children:
            - id: "src/"
              children:
                - id: "src/services/"
                  children:
                    - id: "src/services/auth.ts"
                - id: "src/utils/"
            - id: "tests/"
      depth: 3
      orphans: []
      violations: []
  spatial_relations:
    - entity_a: "src/"
      relation: "contains"
      entity_b: "src/services/"
      attributes: { depth: 1 }
      confidence: 1.0
    - entity_a: "src/services/"
      relation: "contains"
      entity_b: "src/services/auth.ts"
      attributes: { depth: 1 }
      confidence: 1.0
    - entity_a: "src/services/"
      relation: "sibling"
      entity_b: "src/utils/"
      attributes: { common_parent: "src/" }
      confidence: 1.0
  constraint_violations: []
confidence: 1.0
evidence_anchors:
  - "filesystem:src/"
  - "filesystem:tests/"
assumptions:
  - "Directory structure reflects logical containment"
```

**Evidence pattern:** Traversed file system structure, built containment hierarchy from paths.

---

### Example 2: Network Topology Analysis

**Input:**
```yaml
entities:
  - id: "load_balancer"
    type: "lb"
    connections: ["web_1", "web_2", "web_3"]
  - id: "web_1"
    type: "server"
    connections: ["db_primary"]
  - id: "web_2"
    type: "server"
    connections: ["db_primary"]
  - id: "web_3"
    type: "server"
    connections: ["db_primary"]
  - id: "db_primary"
    type: "database"
    connections: ["db_replica"]
  - id: "db_replica"
    type: "database"
    connections: []
query: topology
```

**Output:**
```yaml
spatial_analysis:
  query_type: "topology"
  space_type: "abstract"
  entities: [...]
  results:
    topology:
      graph_type: "directed"
      connected_components: 1
      is_connected: true
      cycles: []
      critical_nodes:
        - id: "db_primary"
          type: "single_point_of_failure"
          impact: "All web servers lose database access"
          severity: high
        - id: "load_balancer"
          type: "entry_point"
          impact: "All traffic blocked"
          severity: high
      bridges:
        - from: "db_primary"
          to: "db_replica"
          impact: "Replica becomes unreachable"
      layers:
        - name: "entry"
          entities: ["load_balancer"]
        - name: "compute"
          entities: ["web_1", "web_2", "web_3"]
        - name: "data"
          entities: ["db_primary", "db_replica"]
  spatial_relations:
    - entity_a: "load_balancer"
      relation: "connected"
      entity_b: "web_1"
      attributes: { direction: "downstream", hops: 1 }
      confidence: 1.0
    - entity_a: "web_1"
      relation: "connected"
      entity_b: "db_primary"
      attributes: { direction: "downstream", hops: 1 }
      confidence: 1.0
  constraint_violations:
    - rule: "database_redundancy"
      description: "Primary database is single point of failure"
      entities: ["db_primary"]
      severity: high
confidence: 0.95
evidence_anchors:
  - "network_config:topology.yaml"
  - "infrastructure:terraform/main.tf"
assumptions:
  - "Connection list represents active network paths"
  - "Bidirectional connections are represented as two entries"
```

## Verification

- [ ] All entities have consistent spatial attributes for their space type
- [ ] Containment trees have no cycles
- [ ] Topology graphs have valid edges (both endpoints exist)
- [ ] Distances are non-negative
- [ ] Spatial relations are symmetric where appropriate (adjacency)

**Verification tools:** Graph validation libraries, geometry validators

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not assume physical proximity implies logical relationship
- Flag entities with missing spatial data rather than inferring positions
- When topology shows single points of failure, include in output even if not queried
- Handle disconnected components gracefully

## Composition Patterns

**Commonly follows:**
- `world-state` - Spatial reasoning operates on state entities
- `inspect` - Observe structure before spatial analysis
- `map-relationships` - Relationship mapping feeds topology analysis

**Commonly precedes:**
- `causal-model` - Spatial proximity may influence causation
- `simulation` - Spatial constraints affect simulation dynamics
- `plan` - Layout optimization informs planning
- `detect-anomaly` - Spatial anomalies (isolation, unexpected proximity)

**Anti-patterns:**
- Never mix physical and logical distances without explicit conversion
- Avoid assuming graph connectivity implies physical connectivity

**Workflow references:**
- See `composition_patterns.md#world-model-build` for state-space integration
- See `composition_patterns.md#capability-gap-analysis` for relationship mapping
