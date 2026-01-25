---
name: detect-entity
description: Detect whether an entity (object, class, component, or named thing) exists in the given data. Use when searching for objects, checking component presence, validating references, or confirming entity existence.
argument-hint: "[target-data] [entity-type] [detection-constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine whether one or more entities (classes, objects, components, services, resources) are present or referenced in the target data. This is an existence check that answers "does this entity exist?" rather than classifying what it is.

**Success criteria:**
- Binary detection result (detected/not detected) with supporting signals
- Evidence anchors pointing to specific locations where entity indicators were found
- Clear enumeration of detected entity instances

**Compatible schemas:**
- `docs/schemas/detect_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The data to scan for entity presence (file path, codebase, config, API spec) |
| `entity_type` | No | string | Type of entity to detect: class, function, service, resource, component, any (default: any) |
| `entity_name` | No | string | Specific entity name or pattern to search for |
| `constraints` | No | object | Detection parameters: include_deprecated, min_confidence, scope |

## Procedure

1) **Define entity signatures**: Determine what constitutes an entity in the target context
   - Code entities: class definitions, function declarations, module exports
   - Infrastructure: service definitions, resource blocks, endpoint registrations
   - Data entities: schema definitions, table structures, document types

2) **Scan for entity markers**: Search the target data for entity indicators
   - Declaration keywords: `class`, `def`, `function`, `resource`, `service`
   - Configuration blocks: YAML/JSON keys that define entities
   - Import/export statements referencing entities
   - Documentation or comments naming entities

3) **Validate entity existence**: Confirm detected markers represent real entities
   - Check for complete definitions vs. mere references
   - Distinguish declarations from usages
   - Verify entities are not commented out or deprecated (unless include_deprecated=true)

4) **Extract entity metadata**: Gather attributes of detected entities
   - Name, namespace, type
   - Location in source
   - Relationships to other entities (imports, extends, uses)

5) **Ground claims**: Attach evidence anchors to all detections
   - Format: `file:line` for source code
   - Quote the declaration or definition line

6) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
detected: boolean  # True if entity/entities found
target_type: entity
instances:
  - id: string | null  # Entity identifier (name, qualified name)
    type: string  # class, function, service, resource, etc.
    attributes:
      namespace: string | null
      visibility: public | private | internal | null
      deprecated: boolean
    location: string  # file:line reference
    confidence: number  # 0.0-1.0 for this instance
signals:
  - signal: string  # Detection indicator
    strength: low | medium | high
    location: string
false_positive_risk: low | medium | high
confidence: number  # 0.0-1.0 overall
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `detected` | boolean | Whether any entity was found |
| `instances` | array | List of detected entities with metadata |
| `signals` | array | Raw indicators that suggest entity presence |
| `false_positive_risk` | enum | Risk that detection is incorrect |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | File:line references to entity definitions |
| `assumptions` | array[string] | Stated assumptions about entity indicators |

## Examples

### Example 1: Detecting Classes in Python Module

**Input:**
```yaml
target: "/project/src/models/"
entity_type: "class"
constraints:
  include_deprecated: false
```

**Output:**
```yaml
detected: true
target_type: entity
instances:
  - id: "models.User"
    type: class
    attributes:
      namespace: "models"
      visibility: public
      deprecated: false
    location: "models/user.py:15"
    confidence: 0.98
  - id: "models.Order"
    type: class
    attributes:
      namespace: "models"
      visibility: public
      deprecated: false
    location: "models/order.py:8"
    confidence: 0.98
  - id: "models.BaseModel"
    type: class
    attributes:
      namespace: "models"
      visibility: public
      deprecated: false
    location: "models/base.py:3"
    confidence: 0.98
signals:
  - signal: "class User(BaseModel):"
    strength: high
    location: "models/user.py:15"
  - signal: "class Order(BaseModel):"
    strength: high
    location: "models/order.py:8"
  - signal: "class BaseModel:"
    strength: high
    location: "models/base.py:3"
false_positive_risk: low
confidence: 0.97
evidence_anchors:
  - "models/user.py:15"
  - "models/order.py:8"
  - "models/base.py:3"
assumptions:
  - "Python class keyword indicates class entity"
  - "Files in models/ directory contain model definitions"
```

**Evidence pattern:** Grep for class declarations, Read to verify complete definitions.

---

### Example 2: Detecting API Endpoints in OpenAPI Spec

**Input:**
```yaml
target: "/api/openapi.yaml"
entity_type: "service"
entity_name: "/users*"
```

**Output:**
```yaml
detected: true
target_type: entity
instances:
  - id: "GET /users"
    type: endpoint
    attributes:
      namespace: "users"
      visibility: public
      deprecated: false
    location: "openapi.yaml:45"
    confidence: 0.95
  - id: "POST /users"
    type: endpoint
    attributes:
      namespace: "users"
      visibility: public
      deprecated: false
    location: "openapi.yaml:78"
    confidence: 0.95
  - id: "GET /users/{id}"
    type: endpoint
    attributes:
      namespace: "users"
      visibility: public
      deprecated: false
    location: "openapi.yaml:112"
    confidence: 0.95
signals:
  - signal: "paths: /users: get:"
    strength: high
    location: "openapi.yaml:45"
  - signal: "paths: /users: post:"
    strength: high
    location: "openapi.yaml:78"
  - signal: "paths: /users/{id}: get:"
    strength: high
    location: "openapi.yaml:112"
false_positive_risk: low
confidence: 0.94
evidence_anchors:
  - "openapi.yaml:45"
  - "openapi.yaml:78"
  - "openapi.yaml:112"
assumptions:
  - "OpenAPI paths section defines API endpoints"
  - "Pattern /users* matches user-related endpoints"
```

**Evidence pattern:** YAML parsing of OpenAPI paths with pattern matching.

---

### Example 3: Entity Not Found

**Input:**
```yaml
target: "/project/src/services/"
entity_type: "class"
entity_name: "PaymentProcessor"
```

**Output:**
```yaml
detected: false
target_type: entity
instances: []
signals:
  - signal: "No class definition matching 'PaymentProcessor' found"
    strength: high
    location: "services/*.py"
  - signal: "Found reference in import but no definition"
    strength: medium
    location: "services/checkout.py:3"
false_positive_risk: low
confidence: 0.88
evidence_anchors:
  - "tool:Grep:PaymentProcessor:services/"
  - "services/checkout.py:3"
assumptions:
  - "Entity should exist as class definition, not just import"
  - "Search scope limited to services/ directory"
next_actions:
  - "Expand search to entire codebase"
  - "Check if PaymentProcessor is defined in external dependency"
```

**Evidence pattern:** Grep search with negative result, import reference analysis.

## Verification

- [ ] Output contains `detected` boolean field
- [ ] If detected=true, at least one instance with valid location is provided
- [ ] Entity type matches requested entity_type or is valid subtype
- [ ] Evidence anchors reference actual file locations
- [ ] Deprecated entities excluded when include_deprecated=false

**Verification tools:** Read (for definition verification), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not execute code to detect entities; use static analysis only
- Respect .gitignore and similar exclusion patterns when scanning
- Do not follow symlinks outside the target scope
- If detecting entities in compiled/binary files, note reduced confidence

## Composition Patterns

**Commonly follows:**
- `inspect` - After examining project structure to determine scan targets
- `search` - After locating files that may contain entities

**Commonly precedes:**
- `identify-entity` - When detection confirms presence, identify the specific entity
- `compare-entities` - When comparing detected entities across sources
- `plan` - When building dependency graphs for planning

**Anti-patterns:**
- Never use to detect entities in obfuscated malicious code
- Avoid combining with `act` to modify detected entities without user confirmation

**Workflow references:**
- See `workflow_catalog.json#dependency-analysis` for entity detection in dependencies
- See `workflow_catalog.json#api-discovery` for endpoint detection
