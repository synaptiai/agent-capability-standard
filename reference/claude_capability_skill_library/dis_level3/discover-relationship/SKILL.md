---
name: discover-relationship
description: Discover previously unknown or implicit relationships between entities through analysis of data, code, or documents. Use when exploring connections, finding dependencies, or mapping entity interactions.
argument-hint: "[entity_set] [relationship_types] [depth]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Uncover relationships between entities that are not explicitly documented by analyzing patterns, references, co-occurrences, and structural connections in available data.

**Success criteria:**
- Discovered relationships are grounded in observable evidence
- Relationship types are categorized (dependency, association, causation, etc.)
- Novelty of discovery is assessed (known vs surprising)
- Significance and actionability of findings are evaluated

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entities` | Yes | array[string\|object] | Entities to analyze for relationships |
| `relationship_types` | No | array[string] | Types to look for (dependency, calls, owns, references, etc.) |
| `search_space` | No | string\|object | Where to look (codebase, documents, data) |
| `depth` | No | integer | Levels of indirect relationships to explore (default: 2) |
| `constraints` | No | object | Filters (min_strength, specific_types) |

## Procedure

1) **Enumerate entities**: Identify all entities in scope
   - Extract entity identifiers and types
   - Note known relationships as baseline
   - Define relationship vocabulary for the domain

2) **Scan for direct connections**: First-order relationships
   - Code: imports, calls, inheritance, composition
   - Documents: references, citations, hyperlinks
   - Data: foreign keys, shared identifiers, co-occurrence

3) **Analyze indirect connections**: Multi-hop relationships
   - Transitive dependencies (A->B->C implies A~~>C)
   - Shared neighbors (A->X and B->X implies A~B)
   - Structural equivalence (A and B have similar connections)

4) **Classify relationship types**: Categorize each discovery
   - Structural: contains, depends_on, extends
   - Behavioral: calls, triggers, produces
   - Semantic: related_to, similar_to, contradicts
   - Temporal: precedes, follows, concurrent_with

5) **Assess significance**: Evaluate each finding
   - Novelty: Was this known or surprising?
   - Strength: How strong is the evidence?
   - Impact: What does this relationship enable/block?

6) **Map the network**: If multiple relationships found
   - Identify clusters of strongly connected entities
   - Find bridges between clusters
   - Highlight unexpected connections

## Output Contract

Return a structured object:

```yaml
discoveries:
  - id: string
    type: dependency | association | causation | containment | semantic
    subtype: string | null  # More specific type
    source_entity: string
    target_entity: string
    direction: unidirectional | bidirectional
    description: string
    strength: weak | moderate | strong
    significance: low | medium | high
    novelty: known | suspected | surprising
    evidence:
      - type: direct | inferred | pattern
        location: string  # file:line or reference
        snippet: string
methodology: string  # How discovery was made
search_space: string
network_summary:
  total_entities: integer
  total_relationships: integer
  clusters: array[object]  # Groups of related entities
  key_bridges: array[string]  # Entities connecting clusters
unexpected_findings: array[string]  # Surprising discoveries
recommendations:
  - action: string
    rationale: string
    priority: low | medium | high
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `discoveries` | array | Individual relationships found |
| `methodology` | string | Approach used for discovery |
| `search_space` | string | What was analyzed |
| `network_summary` | object | Overview of relationship network |
| `unexpected_findings` | array | Particularly surprising discoveries |
| `recommendations` | array | Suggested actions based on findings |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | All evidence locations |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Discovering Service Dependencies

**Input:**
```yaml
entities:
  - name: "user-service"
    type: "microservice"
  - name: "order-service"
    type: "microservice"
  - name: "payment-service"
    type: "microservice"
  - name: "inventory-service"
    type: "microservice"
  - name: "notification-service"
    type: "microservice"
relationship_types:
  - "calls"
  - "depends_on"
  - "shares_data"
search_space: "src/"
depth: 2
```

**Output:**
```yaml
discoveries:
  - id: "rel-001"
    type: dependency
    subtype: "synchronous_call"
    source_entity: "order-service"
    target_entity: "user-service"
    direction: unidirectional
    description: "order-service calls user-service to validate user existence before order creation"
    strength: strong
    significance: high
    novelty: known
    evidence:
      - type: direct
        location: "src/order-service/handlers/create_order.go:45"
        snippet: "user, err := userClient.GetUser(ctx, req.UserID)"
  - id: "rel-002"
    type: dependency
    subtype: "synchronous_call"
    source_entity: "order-service"
    target_entity: "payment-service"
    direction: unidirectional
    description: "order-service calls payment-service to process payments"
    strength: strong
    significance: high
    novelty: known
    evidence:
      - type: direct
        location: "src/order-service/handlers/create_order.go:78"
        snippet: "result, err := paymentClient.ProcessPayment(ctx, paymentReq)"
  - id: "rel-003"
    type: dependency
    subtype: "event_driven"
    source_entity: "order-service"
    target_entity: "inventory-service"
    direction: unidirectional
    description: "order-service publishes OrderCreated events consumed by inventory-service"
    strength: moderate
    significance: medium
    novelty: suspected
    evidence:
      - type: pattern
        location: "src/order-service/events/publisher.go:32"
        snippet: "publisher.Publish('order.created', orderEvent)"
      - type: inferred
        location: "src/inventory-service/events/consumer.go:18"
        snippet: "consumer.Subscribe('order.created', handleOrderCreated)"
  - id: "rel-004"
    type: dependency
    subtype: "undocumented_direct_call"
    source_entity: "notification-service"
    target_entity: "user-service"
    direction: unidirectional
    description: "UNEXPECTED: notification-service directly queries user-service DB for email addresses"
    strength: strong
    significance: high
    novelty: surprising
    evidence:
      - type: direct
        location: "src/notification-service/db/queries.go:89"
        snippet: "db.Query('SELECT email FROM users.users WHERE id = $1', userID)"
  - id: "rel-005"
    type: association
    subtype: "shared_database"
    source_entity: "user-service"
    target_entity: "notification-service"
    direction: bidirectional
    description: "Both services access the same users database"
    strength: strong
    significance: high
    novelty: surprising
    evidence:
      - type: pattern
        location: "src/user-service/config/db.go:12"
        snippet: "connectionString: 'postgres://users-db:5432/users'"
      - type: pattern
        location: "src/notification-service/config/db.go:15"
        snippet: "connectionString: 'postgres://users-db:5432/users'"
  - id: "rel-006"
    type: dependency
    subtype: "transitive"
    source_entity: "notification-service"
    target_entity: "payment-service"
    direction: unidirectional
    description: "Transitive: notification-service depends on payment-service via order-service events"
    strength: weak
    significance: low
    novelty: suspected
    evidence:
      - type: inferred
        location: "derived from rel-003 chain"
        snippet: "order-service -> notification-service and order-service -> payment-service"
methodology: "Static code analysis: import scanning, function call tracing, configuration analysis, event pattern matching"
search_space: "src/ directory (5 microservices, 342 source files)"
network_summary:
  total_entities: 5
  total_relationships: 6
  clusters:
    - name: "order_processing"
      entities: ["order-service", "payment-service", "inventory-service"]
      cohesion: high
    - name: "user_management"
      entities: ["user-service", "notification-service"]
      cohesion: medium
  key_bridges:
    - "order-service (connects both clusters)"
    - "user-service (accessed by order-service and notification-service)"
unexpected_findings:
  - "notification-service bypasses user-service API and directly accesses its database (rel-004, rel-005)"
  - "No circuit breaker pattern detected in any service-to-service calls"
  - "inventory-service has no dependencies - potential orphan or planned expansion"
recommendations:
  - action: "Refactor notification-service to use user-service API instead of direct DB access"
    rationale: "Direct DB access creates tight coupling and bypasses user-service business logic"
    priority: high
  - action: "Document event-driven dependencies between order and inventory services"
    rationale: "Event relationships are implicit and undocumented"
    priority: medium
  - action: "Implement circuit breakers for synchronous service calls"
    rationale: "Current calls have no failure isolation"
    priority: high
confidence: 0.85
evidence_anchors:
  - "src/order-service/handlers/create_order.go:45"
  - "src/order-service/handlers/create_order.go:78"
  - "src/order-service/events/publisher.go:32"
  - "src/inventory-service/events/consumer.go:18"
  - "src/notification-service/db/queries.go:89"
  - "src/user-service/config/db.go:12"
  - "src/notification-service/config/db.go:15"
assumptions:
  - "Code in src/ represents production deployment"
  - "Event topics follow consistent naming convention"
  - "Database connection strings indicate actual dependencies"
  - "No external service dependencies outside codebase"
```

**Evidence pattern:** Static code analysis + configuration inspection + event pattern matching

## Verification

- [ ] All discovered relationships have evidence anchors
- [ ] Relationship directions are correct
- [ ] Transitive relationships are clearly marked as inferred
- [ ] Surprising findings are flagged appropriately
- [ ] Network summary accurately reflects discoveries

**Verification tools:** Read (for code inspection), Grep (for pattern searching)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Mark inferred relationships distinctly from directly observed ones
- Do not claim causation without strong evidence
- Flag when search space may be incomplete
- Stop if entity identification is ambiguous

## Composition Patterns

**Commonly follows:**
- `identify-entity` - to identify entities to analyze
- `search` - to find relevant data sources
- `retrieve` - to gather relationship data

**Commonly precedes:**
- `critique` - to evaluate discovered dependencies
- `generate-plan` - to plan remediation of problematic relationships
- `summarize` - to create relationship documentation

**Anti-patterns:**
- Never claim all relationships discovered (search space is always bounded)
- Avoid deep transitive chains without strong intermediate evidence

**Workflow references:**
- See `workflow_catalog.json#dependency_analysis` for architecture review
- See `workflow_catalog.json#codebase_exploration` for code discovery
