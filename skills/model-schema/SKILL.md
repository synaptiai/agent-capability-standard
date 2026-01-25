---
name: model-schema
description: Create or extend a schema/ontology for a domain including entity types, attributes, relationships, and invariants. Use when defining data models, establishing domain vocabulary, or creating type systems.
argument-hint: "[domain] [entities] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Build a **domain schema** that defines the vocabulary, structure, and constraints for modeling a domain. This establishes what kinds of things exist, what properties they have, and what rules govern them.

**Success criteria:**
- Entity types are well-defined with clear boundaries
- Attributes have appropriate types and constraints
- Relationships are properly typed and constrained
- Invariants are explicit and verifiable
- Schema is extensible for future needs

**World Modeling Context:**
Model-schema provides the meta-level structure for all world modeling. It defines what can exist in a `world-state`, what relationships `map-relationships` can capture, and what transitions `state-transition` can model.

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `domain` | Yes | string | Domain being modeled (e.g., "e-commerce", "microservices") |
| `entities` | No | array | Initial entities to include in schema |
| `existing_schema` | No | object | Schema to extend (for incremental development) |
| `constraints` | No | object | Required types, naming conventions, compatibility |

## Procedure

1) **Analyze domain**: Understand the conceptual space
   - Identify key concepts and their boundaries
   - Find natural categories and hierarchies
   - Understand domain terminology
   - Identify existing standards or conventions

2) **Define entity types**: Establish the "nouns" of the domain
   - Name each entity type clearly
   - Define what distinguishes this type from others
   - Identify required vs. optional attributes
   - Establish naming conventions

3) **Specify attributes**: For each entity type, define properties
   - **Name**: Clear, consistent identifier
   - **Type**: Primitive (string, number, boolean) or reference
   - **Constraints**: Required, unique, range, pattern
   - **Default**: Default value if not specified
   - **Documentation**: What the attribute represents

4) **Define relationships**: How entity types connect
   - **Name**: Verb-like relationship identifier
   - **Source/Target**: Which types can participate
   - **Cardinality**: one-to-one, one-to-many, many-to-many
   - **Constraints**: Required, conditional, exclusive

5) **Establish invariants**: Rules that must always hold
   - **Entity invariants**: Properties of a single entity
   - **Relationship invariants**: Properties of connections
   - **Global invariants**: Properties of the entire model
   - **Temporal invariants**: Properties over time

6) **Define enumerations**: Constrained value sets
   - Status codes, types, categories
   - Ensure exhaustive where appropriate
   - Document each value's meaning

7) **Plan for extension**: Design for future needs
   - Identify likely extension points
   - Consider versioning strategy
   - Document breaking vs. non-breaking changes

8) **Validate schema**: Check internal consistency
   - All references resolve
   - No contradictory constraints
   - Naming is consistent
   - Invariants are satisfiable

## Output Contract

Return a structured object:

```yaml
schema:
  id: string  # Schema identifier
  version: string  # Semantic version
  domain: string  # Domain name
  description: string
  entity_types:
    - name: string  # Type name (PascalCase recommended)
      description: string
      abstract: boolean  # Can be instantiated directly?
      extends: string | null  # Parent type if inheritance
      attributes:
        - name: string  # Attribute name (camelCase recommended)
          type: string  # Type (string, number, boolean, Date, EntityRef, etc.)
          required: boolean
          unique: boolean  # Unique within type?
          constraints: object | null  # min, max, pattern, enum, etc.
          default: any | null
          description: string
      invariants: array[string]  # Rules for this entity type
  relationships:
    - name: string  # Relationship name (snake_case recommended)
      source_type: string  # Entity type at source
      target_type: string  # Entity type at target
      cardinality: one-to-one | one-to-many | many-to-one | many-to-many
      required: boolean  # Must every source have this relationship?
      description: string
      constraints: array[string]  # Relationship-specific rules
  enumerations:
    - name: string  # Enum name
      values:
        - value: string
          description: string
      extensible: boolean  # Can new values be added?
  global_invariants:
    - id: string
      rule: string  # Invariant description
      enforcement: strict | warning  # How to handle violations
      verifiable: boolean  # Can be automatically checked?
compatibility:
  extends: string | null  # Schema this extends
  breaking_changes: array[string] | null  # From previous version
  deprecations: array[string] | null
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity_types` | array | All entity types in the schema |
| `relationships` | array | Valid relationship types |
| `enumerations` | array | Constrained value sets |
| `global_invariants` | array | Rules spanning the entire model |
| `compatibility` | object | Version and extension information |

## Examples

### Example 1: Microservices Domain Schema

**Input:**
```yaml
domain: "microservices"
entities:
  - "Service"
  - "Database"
  - "API"
  - "Deployment"
```

**Output:**
```yaml
schema:
  id: "microservices_v1"
  version: "1.0.0"
  domain: "microservices"
  description: "Schema for modeling microservices architectures"
  entity_types:
    - name: "Service"
      description: "A deployable software component"
      abstract: false
      extends: null
      attributes:
        - name: "id"
          type: "string"
          required: true
          unique: true
          constraints: { pattern: "^[a-z][a-z0-9-]*$" }
          description: "Unique service identifier"
        - name: "name"
          type: "string"
          required: true
          unique: false
          description: "Human-readable service name"
        - name: "language"
          type: "ProgrammingLanguage"
          required: false
          description: "Primary implementation language"
        - name: "port"
          type: "number"
          required: false
          constraints: { min: 1, max: 65535 }
          description: "Primary listening port"
        - name: "status"
          type: "ServiceStatus"
          required: true
          default: "unknown"
          description: "Current operational status"
      invariants:
        - "Service must have at least one API or event consumer"
    - name: "Database"
      description: "A data storage system"
      abstract: false
      attributes:
        - name: "id"
          type: "string"
          required: true
          unique: true
        - name: "engine"
          type: "DatabaseEngine"
          required: true
        - name: "version"
          type: "string"
          required: false
      invariants: []
    - name: "API"
      description: "A service interface definition"
      abstract: false
      attributes:
        - name: "id"
          type: "string"
          required: true
          unique: true
        - name: "path"
          type: "string"
          required: true
          constraints: { pattern: "^/.*" }
        - name: "methods"
          type: "array[HTTPMethod]"
          required: true
        - name: "authentication"
          type: "AuthType"
          required: true
          default: "none"
      invariants: []
  relationships:
    - name: "depends_on"
      source_type: "Service"
      target_type: "Service"
      cardinality: many-to-many
      required: false
      description: "Service A requires Service B to function"
      constraints:
        - "No circular dependencies of length 1 (self-dependency)"
    - name: "uses"
      source_type: "Service"
      target_type: "Database"
      cardinality: many-to-many
      required: false
      description: "Service reads from or writes to database"
    - name: "exposes"
      source_type: "Service"
      target_type: "API"
      cardinality: one-to-many
      required: false
      description: "Service provides this API"
  enumerations:
    - name: "ServiceStatus"
      values:
        - value: "healthy"
          description: "All health checks passing"
        - value: "degraded"
          description: "Partially functional"
        - value: "unhealthy"
          description: "Not functioning"
        - value: "unknown"
          description: "Status not determined"
      extensible: false
    - name: "DatabaseEngine"
      values:
        - value: "postgresql"
        - value: "mysql"
        - value: "mongodb"
        - value: "redis"
      extensible: true
    - name: "HTTPMethod"
      values:
        - value: "GET"
        - value: "POST"
        - value: "PUT"
        - value: "DELETE"
        - value: "PATCH"
      extensible: false
  global_invariants:
    - id: "no_orphan_databases"
      rule: "Every Database must be used by at least one Service"
      enforcement: warning
      verifiable: true
    - id: "unique_api_paths"
      rule: "No two APIs exposed by the same Service can have identical paths"
      enforcement: strict
      verifiable: true
compatibility:
  extends: null
  breaking_changes: null
  deprecations: null
confidence: 0.95
evidence_anchors:
  - "industry_patterns:microservices"
  - "existing_codebase:service_definitions"
assumptions:
  - "Single-language services (no polyglot within one service)"
  - "HTTP-based APIs only"
```

**Evidence pattern:** Analyzed existing codebase patterns, incorporated industry-standard terminology.

---

### Example 2: Extending an Existing Schema

**Input:**
```yaml
domain: "microservices"
existing_schema: "microservices_v1"
entities:
  - "Queue"
  - "Consumer"
```

**Output:**
```yaml
schema:
  id: "microservices_v1.1"
  version: "1.1.0"
  domain: "microservices"
  description: "Schema for microservices with async messaging"
  entity_types:
    # ... existing types unchanged ...
    - name: "Queue"
      description: "A message queue for async communication"
      abstract: false
      attributes:
        - name: "id"
          type: "string"
          required: true
          unique: true
        - name: "broker"
          type: "MessageBroker"
          required: true
        - name: "topic"
          type: "string"
          required: true
      invariants: []
    - name: "Consumer"
      description: "A service that processes queue messages"
      abstract: false
      attributes:
        - name: "id"
          type: "string"
          required: true
          unique: true
        - name: "group"
          type: "string"
          required: false
          description: "Consumer group for load balancing"
      invariants: []
  relationships:
    # ... existing relationships unchanged ...
    - name: "publishes_to"
      source_type: "Service"
      target_type: "Queue"
      cardinality: many-to-many
      required: false
      description: "Service sends messages to queue"
    - name: "subscribes_to"
      source_type: "Consumer"
      target_type: "Queue"
      cardinality: many-to-many
      required: true
      description: "Consumer receives messages from queue"
  enumerations:
    # ... existing enums ...
    - name: "MessageBroker"
      values:
        - value: "kafka"
        - value: "rabbitmq"
        - value: "sqs"
      extensible: true
compatibility:
  extends: "microservices_v1"
  breaking_changes: null
  deprecations: null
confidence: 0.9
evidence_anchors:
  - "microservices_v1:schema"
  - "async_patterns:event_driven"
assumptions:
  - "Backward compatible with v1"
```

## Verification

- [ ] All attribute types are valid (primitives or defined types)
- [ ] All relationship source/target types exist
- [ ] Enumeration values are unique within each enum
- [ ] Invariants are logically consistent
- [ ] No orphan references

**Verification tools:** Schema validators, type checkers

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not remove types in non-breaking version updates
- Flag circular type dependencies
- Document breaking changes explicitly
- Ensure invariants are satisfiable

## Composition Patterns

**Commonly follows:**
- Domain analysis or requirements gathering
- `inspect` - Understand existing data structures

**Commonly precedes:**
- `world-state` - Schema defines what state can contain
- `state-transition` - Schema constrains valid transitions
- `integrate` - Schema guides data transformation

**Anti-patterns:**
- Never create schema without domain understanding
- Avoid overly restrictive invariants that prevent valid states

**Workflow references:**
- See `composition_patterns.md#world-model-build` for schema in model construction
- Schema definition is often a prerequisite step
