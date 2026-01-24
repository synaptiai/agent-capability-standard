---
name: identify-entity
description: Identify and classify an entity (object, class, component, or service) from available evidence. Use when determining what something is, classifying types, resolving references, or categorizing components.
argument-hint: "[target-entity] [identification-context] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and name an entity based on available evidence, determining what it is within the given context. This answers "what is this entity?" rather than just confirming entity presence.

**Success criteria:**
- Clear identification with canonical name and type classification
- Match quality assessment (exact, probable, possible, no match)
- Alternative classifications with probabilities when uncertain
- Disambiguation signals explaining the identification rationale

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The entity reference to identify (name, partial reference, symbol) |
| `context` | No | string\|object | Context for identification (codebase, API, schema, dependency) |
| `constraints` | No | object | Identification parameters: max_alternatives, include_external, type_filter |

## Procedure

1) **Extract entity signals**: Gather all available identifiers from the target
   - Names: class name, function name, variable name, module path
   - Types: declared type, inferred type, interface implementations
   - Relationships: imports, exports, dependencies, inheritance
   - Location: file path, package, namespace

2) **Search for entity definitions**: Look for canonical definitions
   - Source code: class/function definitions
   - Configuration: resource definitions, service declarations
   - Documentation: API specs, schema definitions
   - Dependencies: external package manifests

3) **Classify entity type**: Determine the category of entity
   - Code entities: class, function, method, module, variable
   - Infrastructure: service, resource, endpoint, database
   - Data entities: model, schema, type, interface
   - External: library, package, API, dependency

4) **Assess match quality**: Determine confidence in identification
   - Exact: definition found with clear type and attributes
   - Probable: strong signals but some ambiguity
   - Possible: weak signals or multiple candidates
   - No match: entity cannot be identified

5) **Generate alternatives**: List other possible identifications when uncertain
   - Same-named entities in different namespaces
   - Similar entities with different types
   - Deprecated versions or aliases

6) **Ground claims**: Attach evidence anchors to identification
   - Format: `file:line` or `package:module:entity`
   - Quote the definition or declaration

7) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Fully qualified identifier
  type: string  # class, function, service, resource, etc.
  canonical_name: string  # Display/short name
  attributes:
    namespace: string | null
    visibility: public | private | internal | null
    deprecated: boolean
    version: string | null
    language: string | null
  namespace: string | null  # Package or module context
match_quality: exact | probable | possible | no_match
alternatives:
  - entity:
      id: string
      type: string
      canonical_name: string
      attributes: object
    probability: number  # 0.0-1.0
disambiguation_signals: array[string]  # Why this identification
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified entity with attributes |
| `match_quality` | enum | Confidence category for the identification |
| `alternatives` | array | Other possible identifications with probabilities |
| `disambiguation_signals` | array | Reasons supporting the primary identification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to identification evidence |
| `assumptions` | array[string] | Stated assumptions about entity matching |

## Examples

### Example 1: Identifying Class from Import Statement

**Input:**
```yaml
target: "UserService"
context: "/project/src/"
```

**Output:**
```yaml
entity:
  id: "project.services.user.UserService"
  type: class
  canonical_name: "UserService"
  attributes:
    namespace: "project.services.user"
    visibility: public
    deprecated: false
    version: null
    language: "python"
  namespace: "project.services"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Class definition found at services/user.py:15"
  - "Matches import pattern from project.services.user"
  - "Only one UserService class in codebase"
confidence: 0.98
evidence_anchors:
  - "services/user.py:15"
  - "services/__init__.py:3"
assumptions:
  - "Import path reflects actual module location"
  - "No shadowed definitions in local scope"
```

**Evidence pattern:** Class definition lookup with namespace verification.

---

### Example 2: Identifying API Endpoint from Path

**Input:**
```yaml
target: "/api/v2/users/{id}"
context: "REST API specification"
constraints:
  type_filter: "endpoint"
```

**Output:**
```yaml
entity:
  id: "api.v2.users.get_user_by_id"
  type: endpoint
  canonical_name: "GET /api/v2/users/{id}"
  attributes:
    namespace: "api.v2.users"
    visibility: public
    deprecated: false
    version: "v2"
    language: null
  namespace: "api.v2"
match_quality: exact
alternatives:
  - entity:
      id: "api.v1.users.get_user"
      type: endpoint
      canonical_name: "GET /api/v1/users/{id}"
      attributes:
        namespace: "api.v1.users"
        visibility: public
        deprecated: true
        version: "v1"
    probability: 0.10
disambiguation_signals:
  - "Path matches OpenAPI spec paths./api/v2/users/{id}.get"
  - "Operand ID is 'get_user_by_id'"
  - "V1 endpoint deprecated per x-deprecated annotation"
confidence: 0.95
evidence_anchors:
  - "openapi.yaml:145"
  - "routes/users.py:42"
assumptions:
  - "OpenAPI spec is authoritative"
  - "Route implementation matches spec"
```

**Evidence pattern:** OpenAPI specification lookup with route verification.

---

### Example 3: Identifying Ambiguous Function Reference

**Input:**
```yaml
target: "validate"
context: "/project/"
constraints:
  max_alternatives: 5
```

**Output:**
```yaml
entity:
  id: "project.validators.validate"
  type: function
  canonical_name: "validate"
  attributes:
    namespace: "project.validators"
    visibility: public
    deprecated: false
    version: null
    language: "python"
  namespace: "project.validators"
match_quality: possible
alternatives:
  - entity:
      id: "project.forms.validate"
      type: method
      canonical_name: "Form.validate"
      attributes:
        namespace: "project.forms"
        visibility: public
        deprecated: false
    probability: 0.30
  - entity:
      id: "project.models.User.validate"
      type: method
      canonical_name: "User.validate"
      attributes:
        namespace: "project.models"
        visibility: public
        deprecated: false
    probability: 0.25
  - entity:
      id: "pydantic.validate"
      type: function
      canonical_name: "pydantic.validate"
      attributes:
        namespace: "pydantic"
        visibility: public
        deprecated: false
    probability: 0.15
disambiguation_signals:
  - "Most imports use 'from validators import validate'"
  - "validators.validate is the standalone function"
  - "Form.validate and User.validate are instance methods"
confidence: 0.45
evidence_anchors:
  - "validators/__init__.py:8"
  - "forms/base.py:34"
  - "models/user.py:67"
assumptions:
  - "Context does not specify import source"
  - "Standalone function more likely than methods without context"
next_actions:
  - "Provide calling context to disambiguate"
  - "Specify the import statement used"
```

**Evidence pattern:** Multi-location search with ambiguity handling.

---

### Example 4: Identifying External Dependency

**Input:**
```yaml
target: "lodash.debounce"
context: "package.json"
constraints:
  include_external: true
```

**Output:**
```yaml
entity:
  id: "npm:lodash/debounce"
  type: function
  canonical_name: "debounce"
  attributes:
    namespace: "lodash"
    visibility: public
    deprecated: false
    version: "4.17.21"
    language: "javascript"
  namespace: "npm:lodash"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "lodash@4.17.21 in package.json dependencies"
  - "debounce is exported function in lodash package"
  - "Import pattern: import { debounce } from 'lodash'"
confidence: 0.97
evidence_anchors:
  - "package.json:15"
  - "node_modules/lodash/package.json"
assumptions:
  - "package.json reflects installed version"
  - "lodash export structure is standard"
```

**Evidence pattern:** Package manifest with dependency resolution.

## Verification

- [ ] Entity has valid fully-qualified id
- [ ] Type classification is accurate for the entity kind
- [ ] Match quality accurately reflects evidence strength
- [ ] Alternatives listed when match_quality is not "exact"
- [ ] Disambiguation signals explain the identification rationale

**Verification tools:** Read (for definition verification), Grep (for reference search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not execute code to identify runtime behavior; use static analysis only
- Note when identified entity is deprecated or has known vulnerabilities
- Do not follow external URLs or fetch remote package metadata without approval
- If entity identification reveals security-sensitive information, flag for review

## Composition Patterns

**Commonly follows:**
- `detect-entity` - After confirming entity presence, identify what it is
- `search` - After finding entity references

**Commonly precedes:**
- `compare-entities` - When comparing identified entities
- `explain` - When explaining what an identified entity does
- `plan` - When planning changes involving the entity

**Anti-patterns:**
- Never use to identify entities in obfuscated or suspicious code
- Avoid combining with `act` to modify entities without understanding

**Workflow references:**
- See `workflow_catalog.json#dependency-analysis` for external entity identification
- See `workflow_catalog.json#refactoring` for entity identification before changes
