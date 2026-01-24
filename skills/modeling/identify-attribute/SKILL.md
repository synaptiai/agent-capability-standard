---
name: identify-attribute
description: Identify and classify an attribute, determining its value, type, and semantic meaning. Use when determining attribute values, classifying properties, resolving metadata, or interpreting field contents.
argument-hint: "[target-attribute] [value-context] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and determine the value and meaning of an attribute based on available evidence. This answers "what is this attribute's value and what does it mean?" rather than just confirming attribute presence.

**Success criteria:**
- Clear attribute value identification with type classification
- Match quality assessment (exact, probable, possible, no match)
- Semantic interpretation when applicable
- Alternative values with probabilities when uncertain

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The attribute to identify (field reference, property path, key) |
| `context` | No | string\|object | Context for interpretation (schema, documentation, domain) |
| `constraints` | No | object | Identification parameters: require_value, parse_format, validate_schema |

## Procedure

1) **Locate attribute value**: Find the actual value of the attribute
   - Read from configuration files
   - Extract from structured data
   - Parse from source code
   - Query from metadata

2) **Determine value type**: Classify the data type
   - Primitive: string, number, boolean, null
   - Composite: array, object, map
   - Domain-specific: date, URL, email, UUID, enum

3) **Interpret semantic meaning**: Understand what the value represents
   - Match against known enumerations
   - Parse structured formats (dates, versions, URIs)
   - Apply domain knowledge for interpretation
   - Reference documentation for meaning

4) **Validate value constraints**: Check if value is valid
   - Type constraints
   - Range constraints
   - Format constraints
   - Enumeration constraints

5) **Assess identification confidence**: Determine match quality
   - Exact: value clearly identified with confirmed type
   - Probable: value found but type/meaning ambiguous
   - Possible: partial value or uncertain interpretation
   - No match: value cannot be determined

6) **Ground claims**: Attach evidence anchors to identification
   - Format: `file:line` or `path.to.attribute`
   - Quote the actual value found

7) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Attribute path or key
  type: string  # Data type classification
  canonical_name: string  # Attribute name
  attributes:
    value: any  # The actual value
    raw_value: string | null  # Original string representation
    data_type: string  # primitive type
    semantic_type: string | null  # domain type (email, url, date)
    unit: string | null  # unit of measurement
    valid: boolean  # Whether value passes validation
  namespace: string | null  # Configuration or schema context
match_quality: exact | probable | possible | no_match
alternatives:
  - entity:
      id: string
      type: string
      attributes:
        value: any
    probability: number  # 0.0-1.0
disambiguation_signals: array[string]  # Why this interpretation
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified attribute with value and type |
| `match_quality` | enum | Confidence category for the identification |
| `alternatives` | array | Other possible values or interpretations |
| `disambiguation_signals` | array | Reasons supporting the identification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to attribute location |
| `assumptions` | array[string] | Stated assumptions about value interpretation |

## Examples

### Example 1: Identifying Configuration Value

**Input:**
```yaml
target: "database.connection_timeout"
context: "/config/app.yaml"
```

**Output:**
```yaml
entity:
  id: "database.connection_timeout"
  type: duration
  canonical_name: "Connection Timeout"
  attributes:
    value: 30000
    raw_value: "30s"
    data_type: "integer"
    semantic_type: "duration"
    unit: "milliseconds"
    valid: true
  namespace: "config/database"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Value '30s' parsed as 30 seconds = 30000ms"
  - "Field name 'timeout' confirms duration interpretation"
  - "Standard database configuration pattern"
confidence: 0.96
evidence_anchors:
  - "app.yaml:15"
assumptions:
  - "'s' suffix indicates seconds"
  - "Internal representation uses milliseconds"
```

**Evidence pattern:** Configuration parsing with unit conversion.

---

### Example 2: Identifying Enumeration Value

**Input:**
```yaml
target: "user.status"
context:
  schema:
    status:
      enum: ["active", "inactive", "pending", "suspended"]
```

**Output:**
```yaml
entity:
  id: "user.status"
  type: enum
  canonical_name: "User Status"
  attributes:
    value: "active"
    raw_value: "active"
    data_type: "string"
    semantic_type: "user_status_enum"
    unit: null
    valid: true
  namespace: "users"
match_quality: exact
alternatives:
  - entity:
      attributes:
        value: "Active"
    probability: 0.05
disambiguation_signals:
  - "Value 'active' matches enum definition exactly"
  - "Case matches schema (lowercase)"
  - "Valid enumeration value"
confidence: 0.98
evidence_anchors:
  - "users/123.json:status"
  - "schema:user:status:enum"
assumptions:
  - "Enum values are case-sensitive"
  - "Schema is authoritative"
```

**Evidence pattern:** Schema-based enumeration validation.

---

### Example 3: Identifying Ambiguous Date Value

**Input:**
```yaml
target: "record.date"
context: "data import file"
constraints:
  parse_format: true
```

**Output:**
```yaml
entity:
  id: "record.date"
  type: date
  canonical_name: "Record Date"
  attributes:
    value: "2024-01-15"
    raw_value: "01/15/24"
    data_type: "string"
    semantic_type: "date"
    unit: null
    valid: true
  namespace: "records"
match_quality: probable
alternatives:
  - entity:
      attributes:
        value: "2024-03-15"
        interpretation: "DD/MM/YY format"
    probability: 0.30
  - entity:
      attributes:
        value: "2024-01-15"
        interpretation: "January 15, 2024"
    probability: 0.70
disambiguation_signals:
  - "Assumed MM/DD/YY format (US convention)"
  - "No locale context provided"
  - "15 could be day (DD/MM) or invalid month (MM/DD)"
  - "Since 15 > 12, likely DD/MM if European context"
confidence: 0.70
evidence_anchors:
  - "import.csv:line:45"
assumptions:
  - "US date format (MM/DD/YY) assumed"
  - "Two-digit year is 2024"
next_actions:
  - "Confirm date format with data source"
  - "Check other date fields for format consistency"
```

**Evidence pattern:** Date parsing with format ambiguity handling.

---

### Example 4: Identifying Computed Attribute

**Input:**
```yaml
target: "order.total_with_tax"
context: "/models/order.py"
```

**Output:**
```yaml
entity:
  id: "order.total_with_tax"
  type: computed_property
  canonical_name: "Total With Tax"
  attributes:
    value: null
    raw_value: "@property def total_with_tax(self): return self.subtotal * (1 + self.tax_rate)"
    data_type: "float"
    semantic_type: "currency"
    unit: "currency_default"
    valid: true
  namespace: "models/order"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Attribute is @property decorator (computed)"
  - "Formula: subtotal * (1 + tax_rate)"
  - "Returns float/Decimal for currency"
confidence: 0.92
evidence_anchors:
  - "models/order.py:45-47"
assumptions:
  - "Property is deterministic (same inputs = same output)"
  - "subtotal and tax_rate are available at access time"
```

**Evidence pattern:** Code analysis for computed property identification.

---

### Example 5: Unable to Identify Value

**Input:**
```yaml
target: "config.secret_key"
context: "/config/app.yaml"
```

**Output:**
```yaml
entity:
  id: "config.secret_key"
  type: secret
  canonical_name: "Secret Key"
  attributes:
    value: "[REDACTED]"
    raw_value: "${SECRET_KEY}"
    data_type: "string"
    semantic_type: "secret"
    unit: null
    valid: null
  namespace: "config"
match_quality: possible
alternatives: []
disambiguation_signals:
  - "Value references environment variable ${SECRET_KEY}"
  - "Cannot access environment variable value"
  - "Semantic type 'secret' based on field name"
confidence: 0.50
evidence_anchors:
  - "app.yaml:3"
assumptions:
  - "Environment variable is set at runtime"
  - "Actual value intentionally not exposed"
next_actions:
  - "Check environment for SECRET_KEY variable"
  - "Verify secret is properly configured"
```

**Evidence pattern:** Environment variable reference with redaction.

## Verification

- [ ] Attribute value is extracted from correct location
- [ ] Data type classification is accurate
- [ ] Semantic type interpretation is justified
- [ ] Validation status reflects constraint checking
- [ ] Alternatives listed for ambiguous values

**Verification tools:** Read (for data inspection), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive attribute values (secrets, passwords, tokens)
- Redact PII when reporting attribute values
- Note when attribute values require runtime evaluation
- If attribute contains credentials, report presence but not value

## Composition Patterns

**Commonly follows:**
- `detect-attribute` - After confirming attribute presence, identify its value
- `inspect` - After examining structure to locate attributes

**Commonly precedes:**
- `compare-attributes` - When comparing attribute values across sources
- `transform` - When converting attribute values
- `verify` - When validating attribute values

**Anti-patterns:**
- Never expose secret values in output
- Avoid interpreting values without understanding schema

**Workflow references:**
- See `workflow_catalog.json#configuration-audit` for config value identification
- See `workflow_catalog.json#data-validation` for attribute validation
