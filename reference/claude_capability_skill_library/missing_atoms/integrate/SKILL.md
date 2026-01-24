---
name: integrate
description: Combine heterogeneous data sources into a unified model with conflict resolution, schema alignment, and provenance tracking. Use when merging data from multiple systems, consolidating information, or building comprehensive views.
argument-hint: "[sources] [target_schema] [conflict_strategy]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Perform **data integration** to combine information from multiple heterogeneous sources into a unified, coherent model. This handles schema differences, resolves conflicts, and preserves provenance.

**Success criteria:**
- All sources are incorporated or explicitly excluded
- Schema mismatches are resolved consistently
- Conflicts are documented with resolution rationale
- Provenance traces every value to its source
- Information loss is minimized and documented

**World Modeling Context:**
Integrate is essential for building comprehensive `world-state` from multiple observation sources. It combines outputs from `retrieve`, `search`, and `inspect` into unified models, and depends on `identity-resolution` for entity deduplication.

**Hard dependencies:**
- Requires `identity-resolution` when sources contain overlapping entities

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `sources` | Yes | array | Data sources to integrate (files, API outputs, retrieved data) |
| `target_schema` | No | object | Schema the integrated data should conform to |
| `conflict_strategy` | No | string | `prefer_recent`, `prefer_authoritative`, `merge`, `manual` (default: prefer_authoritative) |
| `constraints` | No | object | Required fields, validation rules |

## Procedure

1) **Analyze sources**: Understand what each source contains
   - Inventory entities and attributes per source
   - Identify source schemas (explicit or inferred)
   - Note data freshness and authority
   - Detect overlapping vs. unique content

2) **Align schemas**: Map source schemas to target
   - Identify equivalent fields (same meaning, different names)
   - Map types (handle type conversions)
   - Handle missing fields (default values, nulls)
   - Document unmappable fields (information loss)

3) **Resolve entity identity**: Determine which records refer to same entity
   - Apply `identity-resolution` for overlapping entities
   - Assign canonical IDs
   - Track all source IDs as aliases

4) **Merge attributes**: For each entity, combine attributes from sources
   - Non-overlapping: Simply include from source
   - Overlapping, matching: Confirm consistency
   - Overlapping, conflicting: Apply conflict strategy

5) **Apply conflict strategy**:

   For `prefer_recent`:
   - Use the most recently updated value
   - Requires reliable timestamps

   For `prefer_authoritative`:
   - Rank sources by authority
   - Use value from most authoritative source

   For `merge`:
   - Combine values where possible (lists, sets)
   - For scalars, may require manual resolution

   For `manual`:
   - Flag all conflicts for human review
   - Do not auto-resolve

6) **Validate integrated data**: Check against target schema
   - Required fields present
   - Type constraints satisfied
   - Relationship integrity maintained
   - Custom invariants hold

7) **Document integration**: Record what happened
   - Per-field provenance (which source)
   - Conflict resolutions with rationale
   - Information loss (unmapped fields)
   - Transformation applied

8) **Produce output**: Generate integrated model
   - Conforms to target schema
   - Includes provenance metadata
   - Documents confidence levels

## Output Contract

Return a structured object:

```yaml
integrated_data:
  schema: string | object  # Target schema reference or inline
  entities:
    - id: string  # Canonical ID
      type: string  # Entity type
      attributes: object  # Integrated attributes
      source_map:  # Where each attribute came from
        attribute_name:
          source: string
          original_value: any | null  # If transformed
          confidence: number
  relationships:
    - source: string
      target: string
      type: string
      provenance: string
integration_report:
  sources_used: array[string]
  sources_excluded: array[string]
  entity_count:
    total: integer
    from_single_source: integer
    merged: integer
  field_mapping:
    - source_field: string
      target_field: string
      transformation: string | null
  conflicts:
    - entity_id: string
      field: string
      values:
        - source: string
          value: any
      resolution: string
      resolved_value: any
      confidence: number
  information_loss:
    - source: string
      field: string
      reason: string  # unmappable, filtered, etc.
      impact: low | medium | high
  validation_results:
    passed: boolean
    errors: array[string]
    warnings: array[string]
provenance:
  sources: array[object]  # Source metadata
  integration_timestamp: string
  confidence: number
confidence: number  # 0.0-1.0 overall
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `integrated_data` | object | The unified data model |
| `source_map` | object | Per-attribute source tracking |
| `integration_report.conflicts` | array | All conflicts and resolutions |
| `information_loss` | array | Data that couldn't be integrated |

## Examples

### Example 1: Integrating Service Data from Multiple Sources

**Input:**
```yaml
sources:
  - name: "kubernetes"
    type: "api"
    data:
      - id: "api-gateway-deployment"
        status: "Running"
        replicas: 3
        last_updated: "2025-01-24T10:00:00Z"
  - name: "datadog"
    type: "api"
    data:
      - service_name: "api-gateway"
        health: "healthy"
        latency_p99: 45
        last_updated: "2025-01-24T10:05:00Z"
  - name: "package.json"
    type: "file"
    data:
      - name: "api-gateway"
        version: "2.3.1"
        dependencies: ["express", "cors"]
target_schema: "microservices_v1"
conflict_strategy: prefer_recent
```

**Output:**
```yaml
integrated_data:
  schema: "microservices_v1"
  entities:
    - id: "api-gateway"
      type: "Service"
      attributes:
        name: "api-gateway"
        version: "2.3.1"
        status: "healthy"
        replicas: 3
        latency_p99: 45
        dependencies: ["express", "cors"]
      source_map:
        name:
          source: "package.json"
          original_value: null
          confidence: 1.0
        version:
          source: "package.json"
          original_value: null
          confidence: 1.0
        status:
          source: "datadog"
          original_value: "healthy"
          confidence: 0.9
        replicas:
          source: "kubernetes"
          original_value: null
          confidence: 1.0
        latency_p99:
          source: "datadog"
          original_value: null
          confidence: 0.95
        dependencies:
          source: "package.json"
          original_value: null
          confidence: 1.0
  relationships: []
integration_report:
  sources_used: ["kubernetes", "datadog", "package.json"]
  sources_excluded: []
  entity_count:
    total: 1
    from_single_source: 0
    merged: 1
  field_mapping:
    - source_field: "kubernetes.status"
      target_field: "status"
      transformation: "Mapped 'Running' to 'healthy'"
    - source_field: "datadog.service_name"
      target_field: "name"
      transformation: null
  conflicts:
    - entity_id: "api-gateway"
      field: "status"
      values:
        - source: "kubernetes"
          value: "Running"
        - source: "datadog"
          value: "healthy"
      resolution: "prefer_recent (datadog more recent)"
      resolved_value: "healthy"
      confidence: 0.85
  information_loss:
    - source: "kubernetes"
      field: "labels"
      reason: "No target schema field for Kubernetes labels"
      impact: low
  validation_results:
    passed: true
    errors: []
    warnings:
      - "Service has no APIs defined"
provenance:
  sources:
    - name: "kubernetes"
      authority: high
      freshness: "2025-01-24T10:00:00Z"
    - name: "datadog"
      authority: medium
      freshness: "2025-01-24T10:05:00Z"
    - name: "package.json"
      authority: high
      freshness: "2025-01-20T00:00:00Z"
  integration_timestamp: "2025-01-24T12:00:00Z"
  confidence: 0.9
confidence: 0.9
evidence_anchors:
  - "kubernetes_api:deployments/api-gateway-deployment"
  - "datadog:services/api-gateway"
  - "package.json:1-20"
assumptions:
  - "All sources refer to the same service"
  - "Datadog health status more accurate than K8s Running state"
```

**Evidence pattern:** Mapped fields from three sources to unified schema, resolved status conflict using recency.

---

### Example 2: Integrating Documentation with Code Analysis

**Input:**
```yaml
sources:
  - name: "code_analysis"
    data:
      functions:
        - name: "processOrder"
          file: "src/orders.ts"
          parameters: ["orderId", "options"]
  - name: "api_docs"
    data:
      endpoints:
        - path: "/orders/process"
          method: "POST"
          description: "Process a pending order"
          parameters:
            - name: "order_id"
              required: true
target_schema: "api_documentation"
conflict_strategy: merge
```

**Output:**
```yaml
integrated_data:
  schema: "api_documentation"
  entities:
    - id: "endpoint_process_order"
      type: "Endpoint"
      attributes:
        path: "/orders/process"
        method: "POST"
        description: "Process a pending order"
        implementation: "src/orders.ts:processOrder"
        parameters:
          - name: "order_id"
            code_name: "orderId"
            required: true
            source: "body"
      source_map:
        path: { source: "api_docs" }
        method: { source: "api_docs" }
        description: { source: "api_docs" }
        implementation: { source: "code_analysis" }
        parameters: { source: "merged" }
integration_report:
  sources_used: ["code_analysis", "api_docs"]
  entity_count:
    total: 1
    merged: 1
  conflicts:
    - entity_id: "endpoint_process_order"
      field: "parameters[0].name"
      values:
        - source: "code_analysis"
          value: "orderId"
        - source: "api_docs"
          value: "order_id"
      resolution: "merge - both names preserved (code vs API)"
      resolved_value: { name: "order_id", code_name: "orderId" }
      confidence: 0.95
  information_loss: []
confidence: 0.95
evidence_anchors:
  - "src/orders.ts:processOrder"
  - "api_docs:endpoints/process"
```

## Verification

- [ ] All source entities are accounted for (integrated or documented as excluded)
- [ ] Conflicts have documented resolutions
- [ ] Output validates against target schema
- [ ] Provenance traces every attribute to source
- [ ] Information loss is documented

**Verification tools:** Schema validators, provenance checkers

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never silently drop data - document all information loss
- When confidence < 0.5 on a merge, flag for review
- Preserve source identifiers for traceability
- Apply `identity-resolution` before merging overlapping entities

## Composition Patterns

**Commonly follows:**
- `retrieve` - Get data from sources before integrating
- `search` - Discover relevant sources to integrate
- `identity-resolution` - Resolve entity identity before merge

**Commonly precedes:**
- `world-state` - Integration produces unified state
- `grounding` - Integrated data needs grounding
- `diff-world-state` - Compare integrated states over time

**Anti-patterns:**
- Never integrate without understanding source schemas
- Avoid ignoring conflicts - always resolve or flag

**Workflow references:**
- See `composition_patterns.md#world-model-build` for integration in model construction
- See `composition_patterns.md#digital-twin-sync-loop` for ongoing integration
