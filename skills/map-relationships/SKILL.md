---
name: map-relationships
description: Build a relationship graph capturing entities, edges, and constraints. Use when understanding dependencies, modeling connections, or analyzing structure in systems, data, or organizations.
argument-hint: "[entities] [relationship_types] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Construct a **relationship graph** that captures how entities in a domain are connected. This is essential for understanding system architecture, dependency analysis, and any task requiring structural understanding.

**Success criteria:**
- All significant relationships are captured
- Edge types are properly classified
- Relationship directionality is correct
- Graph is consistent (no orphan references)
- Constraints and invariants are documented

**World Modeling Context:**
Map-relationships is foundational for the **State Layer** (entity relationships in `world-state`) and **Dynamics Layer** (identifying causal pathways for `causal-model`). It also supports `spatial-reasoning` topology analysis.

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entities` | Yes | array | Entities to map relationships between |
| `relationship_types` | No | array | Types to detect: `depends_on`, `contains`, `uses`, `produces`, etc. |
| `depth` | No | integer | Relationship traversal depth; default: 1 (direct only) |
| `constraints` | No | object | Required relationships, forbidden patterns |

## Procedure

1) **Enumerate entities**: Establish the nodes of the graph
   - Extract from provided entity list
   - Verify entity IDs are unique
   - Note entity types for relationship type inference

2) **Define relationship types**: Establish edge vocabulary
   - **Structural**: `contains`, `part_of`, `parent_of`
   - **Functional**: `uses`, `calls`, `invokes`
   - **Dependency**: `depends_on`, `requires`, `imports`
   - **Data flow**: `produces`, `consumes`, `transforms`
   - **Temporal**: `precedes`, `triggers`, `follows`
   - **Association**: `related_to`, `associated_with`

3) **Detect relationships**: For each entity pair, identify connections
   - **Code analysis**: Parse imports, function calls, inheritance
   - **Config analysis**: Dependencies, references, mappings
   - **Documentation**: Stated relationships, diagrams
   - **Inference**: Naming conventions, proximity, co-occurrence

4) **Classify relationship properties**: For each edge
   - **Direction**: uni-directional, bi-directional, none
   - **Cardinality**: one-to-one, one-to-many, many-to-many
   - **Strength**: required, optional, weak
   - **Transitivity**: does A->B->C imply A->C?

5) **Build graph structure**: Assemble the relationship graph
   - Nodes: entities with attributes
   - Edges: typed, directed relationships
   - Metadata: timestamps, sources, confidence

6) **Validate graph**: Check for consistency
   - No orphan nodes (entities with no relationships)
   - No dangling edges (referencing non-existent entities)
   - Relationship types are appropriate for entity types
   - No cycles where forbidden

7) **Identify patterns**: Look for structural patterns
   - Hubs: highly connected entities
   - Bridges: entities connecting clusters
   - Cycles: circular dependencies
   - Clusters: tightly connected groups

8) **Document constraints**: Capture relationship rules
   - Required relationships (every X must have Y)
   - Forbidden relationships (X cannot relate to Y)
   - Cardinality constraints (X has at most N of Y)

## Output Contract

Return a structured object:

```yaml
relationship_graph:
  id: string  # Graph identifier
  timestamp: string  # When graph was built
  nodes:
    - id: string  # Entity identifier
      type: string  # Entity type
      attributes: object  # Entity metadata
  edges:
    - id: string  # Edge identifier
      source: string  # Source entity ID
      target: string  # Target entity ID
      type: string  # Relationship type
      direction: forward | backward | bidirectional
      properties:
        cardinality: string  # one-to-one, one-to-many, etc.
        strength: required | optional | weak
        transitive: boolean
      confidence: number  # 0.0-1.0
      evidence: string  # Where this relationship was found
graph_properties:
  node_count: integer
  edge_count: integer
  density: number  # edges / possible_edges
  connected_components: integer
  has_cycles: boolean
patterns:
  hubs:
    - node_id: string
      degree: integer
      centrality: number
  bridges:
    - node_id: string
      components_connected: array[string]
  cycles:
    - path: array[string]
      severity: low | medium | high
  clusters:
    - nodes: array[string]
      cohesion: number
constraints:
  - type: string  # required, forbidden, cardinality
    rule: string  # Description
    entities: array[string]
    violations: array[object] | null
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `nodes` | array | Entities in the graph |
| `edges` | array | Relationships between entities |
| `graph_properties` | object | Structural metrics |
| `patterns` | object | Detected structural patterns |
| `constraints` | array | Relationship rules and violations |

## Examples

### Example 1: Service Dependency Graph

**Input:**
```yaml
entities:
  - id: "api-gateway"
    type: "service"
  - id: "user-service"
    type: "service"
  - id: "auth-service"
    type: "service"
  - id: "postgres"
    type: "database"
  - id: "redis"
    type: "cache"
relationship_types: ["depends_on", "uses"]
```

**Output:**
```yaml
relationship_graph:
  id: "rg_services_20250124"
  timestamp: "2025-01-24T16:00:00Z"
  nodes:
    - id: "api-gateway"
      type: "service"
      attributes: { language: "typescript", port: 3000 }
    - id: "user-service"
      type: "service"
      attributes: { language: "typescript", port: 3001 }
    - id: "auth-service"
      type: "service"
      attributes: { language: "typescript", port: 3002 }
    - id: "postgres"
      type: "database"
      attributes: { version: "15" }
    - id: "redis"
      type: "cache"
      attributes: { version: "7" }
  edges:
    - id: "e1"
      source: "api-gateway"
      target: "user-service"
      type: "depends_on"
      direction: forward
      properties:
        cardinality: "one-to-one"
        strength: required
        transitive: false
      confidence: 1.0
      evidence: "docker-compose.yml:15"
    - id: "e2"
      source: "api-gateway"
      target: "auth-service"
      type: "depends_on"
      direction: forward
      properties:
        cardinality: "one-to-one"
        strength: required
        transitive: false
      confidence: 1.0
      evidence: "docker-compose.yml:16"
    - id: "e3"
      source: "user-service"
      target: "postgres"
      type: "uses"
      direction: forward
      properties:
        cardinality: "many-to-one"
        strength: required
        transitive: false
      confidence: 1.0
      evidence: "src/user-service/database.ts:5"
    - id: "e4"
      source: "auth-service"
      target: "redis"
      type: "uses"
      direction: forward
      properties:
        cardinality: "many-to-one"
        strength: required
        transitive: false
      confidence: 1.0
      evidence: "src/auth-service/cache.ts:10"
graph_properties:
  node_count: 5
  edge_count: 4
  density: 0.4
  connected_components: 1
  has_cycles: false
patterns:
  hubs:
    - node_id: "api-gateway"
      degree: 2
      centrality: 0.8
  bridges:
    - node_id: "user-service"
      components_connected: ["api-gateway", "postgres"]
  cycles: []
  clusters:
    - nodes: ["api-gateway", "user-service", "auth-service"]
      cohesion: 0.67
constraints:
  - type: required
    rule: "Every service must depend on at least one data store"
    entities: ["api-gateway"]
    violations:
      - entity: "api-gateway"
        issue: "No direct data store dependency"
        severity: low
confidence: 0.95
evidence_anchors:
  - "docker-compose.yml:1-50"
  - "src/*/database.ts"
  - "src/*/cache.ts"
assumptions:
  - "docker-compose dependencies reflect runtime dependencies"
  - "Code imports reflect actual usage"
```

**Evidence pattern:** Analyzed docker-compose for service dependencies, code imports for data store usage.

---

### Example 2: Module Import Graph

**Input:**
```yaml
entities:
  - id: "src/index.ts"
    type: "module"
  - id: "src/utils/helpers.ts"
    type: "module"
  - id: "src/services/api.ts"
    type: "module"
  - id: "src/models/user.ts"
    type: "module"
relationship_types: ["imports"]
depth: 2
```

**Output:**
```yaml
relationship_graph:
  id: "rg_imports_20250124"
  timestamp: "2025-01-24T16:15:00Z"
  nodes:
    - id: "src/index.ts"
      type: "module"
      attributes: { lines: 50, exports: ["main"] }
    - id: "src/utils/helpers.ts"
      type: "module"
      attributes: { lines: 120, exports: ["formatDate", "parseJSON"] }
    - id: "src/services/api.ts"
      type: "module"
      attributes: { lines: 200, exports: ["ApiClient"] }
    - id: "src/models/user.ts"
      type: "module"
      attributes: { lines: 80, exports: ["User", "UserAttributes"] }
  edges:
    - id: "e1"
      source: "src/index.ts"
      target: "src/services/api.ts"
      type: "imports"
      direction: forward
      properties:
        cardinality: "one-to-many"
        strength: required
        transitive: false
      confidence: 1.0
      evidence: "src/index.ts:3"
    - id: "e2"
      source: "src/services/api.ts"
      target: "src/models/user.ts"
      type: "imports"
      direction: forward
      confidence: 1.0
      evidence: "src/services/api.ts:5"
    - id: "e3"
      source: "src/services/api.ts"
      target: "src/utils/helpers.ts"
      type: "imports"
      direction: forward
      confidence: 1.0
      evidence: "src/services/api.ts:6"
graph_properties:
  node_count: 4
  edge_count: 3
  density: 0.5
  connected_components: 1
  has_cycles: false
patterns:
  hubs:
    - node_id: "src/services/api.ts"
      degree: 3
      centrality: 0.75
  cycles: []
confidence: 1.0
evidence_anchors:
  - "src/index.ts:1-10"
  - "src/services/api.ts:1-10"
assumptions:
  - "TypeScript imports reflect actual dependencies"
```

## Verification

- [ ] All node IDs in edges exist in nodes list
- [ ] No duplicate edges (same source, target, type)
- [ ] Relationship types are from defined vocabulary
- [ ] Graph properties computed correctly
- [ ] Constraint violations are accurate

**Verification tools:** Graph validators, cycle detection

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not infer relationships without evidence
- Flag circular dependencies as patterns, not errors
- Mark inferred vs. explicit relationships
- Limit depth to avoid explosion on large graphs

## Composition Patterns

**Commonly follows:**
- `world-state` - Build relationships after identifying entities
- `inspect` - Discover entities before mapping relationships
- `search` - Find related entities to include

**Commonly precedes:**
- `spatial-reasoning` - Topology analysis on the graph
- `causal-model` - Relationships inform causal structure
- `simulation` - Relationships define interaction patterns
- `plan` - Dependencies inform planning order

**Anti-patterns:**
- Never map relationships without entity identification first
- Avoid deep traversal without clear bounds

**Workflow references:**
- See `composition_patterns.md#world-model-build` for relationship mapping in model construction
- See `composition_patterns.md#capability-gap-analysis` for dependency analysis
