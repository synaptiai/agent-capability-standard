---
name: detect-attribute
description: Detect whether a specific attribute or property exists in the given data. Use when checking for property presence, validating field existence, confirming attribute availability, or verifying metadata.
argument-hint: "[target-data] [attribute-name] [attribute-constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine whether specific attributes, properties, or metadata fields exist in the target data. This is an existence check that answers "is this attribute present?" rather than what the attribute's value is.

**Success criteria:**
- Binary detection result (detected/not detected) for each queried attribute
- Evidence anchors pointing to attribute locations
- Clear indication of attribute presence vs. value availability

**Compatible schemas:**
- `docs/schemas/detect_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The data to scan for attributes (file, object, configuration, schema) |
| `attribute_name` | No | string\|array | Specific attribute(s) to detect; omit to detect all attributes |
| `attribute_path` | No | string | JSONPath or dot-notation path to attribute location |
| `constraints` | No | object | Detection parameters: include_null, include_empty, recursive |

## Procedure

1) **Identify attribute search space**: Determine where to look for attributes
   - File metadata: timestamps, permissions, ownership
   - Structured data: JSON/YAML keys, XML attributes, object properties
   - Code artifacts: class fields, function parameters, annotations
   - Configuration: settings, options, feature flags

2) **Search for attribute presence**: Scan target for attribute indicators
   - Key/property names in structured data
   - Field declarations in code
   - Metadata fields in files
   - Header/annotation markers

3) **Validate attribute existence**: Confirm attribute is truly present
   - Distinguish between "attribute exists with null value" vs "attribute missing"
   - Check for attribute aliases or alternative names
   - Verify attribute is not commented out or deprecated

4) **Extract attribute context**: Gather supporting information
   - Data type of the attribute
   - Path/location where attribute was found
   - Whether attribute has a value vs. just declared

5) **Ground claims**: Attach evidence anchors to detected attributes
   - Format: `file:line` or `path.to.attribute`
   - Quote the attribute declaration or key

6) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
detected: boolean  # True if attribute(s) found
target_type: attribute
instances:
  - id: string  # Attribute name/key
    type: string  # string, number, boolean, object, array, null, unknown
    attributes:
      path: string  # Full path to attribute
      has_value: boolean  # Whether attribute has a non-null value
      data_type: string  # Detected data type
      nullable: boolean | null  # Whether null is allowed
    location: string  # file:line or data path
    confidence: number  # 0.0-1.0 for this instance
signals:
  - signal: string  # Attribute indicator
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
| `detected` | boolean | Whether requested attribute(s) were found |
| `instances` | array | List of detected attributes with metadata |
| `signals` | array | Raw indicators of attribute presence |
| `false_positive_risk` | enum | Risk that detection is incorrect |
| `confidence` | number | 0.0-1.0 based on evidence clarity |
| `evidence_anchors` | array[string] | References to attribute locations |
| `assumptions` | array[string] | Stated assumptions about attribute indicators |

## Examples

### Example 1: Detecting Configuration Attributes

**Input:**
```yaml
target: "/config/app.yaml"
attribute_name: ["database.ssl", "database.timeout", "database.pool_size"]
```

**Output:**
```yaml
detected: true
target_type: attribute
instances:
  - id: "database.ssl"
    type: boolean
    attributes:
      path: "database.ssl"
      has_value: true
      data_type: "boolean"
      nullable: false
    location: "app.yaml:12"
    confidence: 0.98
  - id: "database.timeout"
    type: number
    attributes:
      path: "database.timeout"
      has_value: true
      data_type: "integer"
      nullable: false
    location: "app.yaml:13"
    confidence: 0.98
signals:
  - signal: "Key 'ssl' found under 'database' section"
    strength: high
    location: "app.yaml:12"
  - signal: "Key 'timeout' found under 'database' section"
    strength: high
    location: "app.yaml:13"
  - signal: "Key 'pool_size' NOT found under 'database' section"
    strength: high
    location: "app.yaml:10-20"
false_positive_risk: low
confidence: 0.90
evidence_anchors:
  - "app.yaml:12"
  - "app.yaml:13"
assumptions:
  - "YAML structure uses dot notation for nested paths"
  - "Attribute presence means key exists regardless of value"
next_actions:
  - "Add 'pool_size' to configuration if required"
```

**Evidence pattern:** YAML key search at specified paths.

---

### Example 2: Detecting Class Field Attributes

**Input:**
```yaml
target: "/src/models/User.py"
attribute_name: ["email", "created_at", "last_login"]
constraints:
  recursive: true
```

**Output:**
```yaml
detected: true
target_type: attribute
instances:
  - id: "email"
    type: string
    attributes:
      path: "User.email"
      has_value: true
      data_type: "str"
      nullable: false
    location: "User.py:15"
    confidence: 0.95
  - id: "created_at"
    type: datetime
    attributes:
      path: "User.created_at"
      has_value: true
      data_type: "datetime"
      nullable: false
    location: "User.py:18"
    confidence: 0.95
  - id: "last_login"
    type: datetime
    attributes:
      path: "User.last_login"
      has_value: false
      data_type: "Optional[datetime]"
      nullable: true
    location: "User.py:19"
    confidence: 0.92
signals:
  - signal: "email: str = Field(...)"
    strength: high
    location: "User.py:15"
  - signal: "created_at: datetime = Field(default_factory=datetime.utcnow)"
    strength: high
    location: "User.py:18"
  - signal: "last_login: Optional[datetime] = None"
    strength: high
    location: "User.py:19"
false_positive_risk: low
confidence: 0.94
evidence_anchors:
  - "User.py:15"
  - "User.py:18"
  - "User.py:19"
assumptions:
  - "Class field definitions indicate attribute presence"
  - "Optional type annotation indicates nullable"
```

**Evidence pattern:** Python class field parsing with type annotation extraction.

---

### Example 3: Detecting API Response Attributes

**Input:**
```yaml
target: "/api/responses/user.json"
attribute_name: "permissions"
attribute_path: "$.data.user.permissions"
```

**Output:**
```yaml
detected: false
target_type: attribute
instances: []
signals:
  - signal: "Path $.data.user exists but has no 'permissions' key"
    strength: high
    location: "user.json:15-25"
  - signal: "Closest match: 'roles' array at $.data.user.roles"
    strength: medium
    location: "user.json:22"
false_positive_risk: low
confidence: 0.88
evidence_anchors:
  - "user.json:15-25"
  - "user.json:22"
assumptions:
  - "JSONPath query targets exact attribute name"
  - "'permissions' and 'roles' are distinct attributes"
next_actions:
  - "Check if 'permissions' was renamed to 'roles'"
  - "Verify API documentation for correct attribute name"
```

**Evidence pattern:** JSONPath traversal with negative result.

---

### Example 4: Detecting File Metadata Attributes

**Input:**
```yaml
target: "/data/report.pdf"
attribute_name: ["author", "creation_date", "encrypted"]
```

**Output:**
```yaml
detected: true
target_type: attribute
instances:
  - id: "author"
    type: string
    attributes:
      path: "metadata.author"
      has_value: true
      data_type: "string"
      nullable: true
    location: "file:metadata"
    confidence: 0.90
  - id: "creation_date"
    type: string
    attributes:
      path: "metadata.creation_date"
      has_value: true
      data_type: "datetime"
      nullable: true
    location: "file:metadata"
    confidence: 0.90
signals:
  - signal: "PDF metadata contains Author field: 'Jane Doe'"
    strength: high
    location: "file:metadata"
  - signal: "PDF metadata contains CreationDate field"
    strength: high
    location: "file:metadata"
  - signal: "'encrypted' attribute not available via static analysis"
    strength: low
    location: "file:metadata"
false_positive_risk: medium
confidence: 0.78
evidence_anchors:
  - "file:metadata:Author"
  - "file:metadata:CreationDate"
assumptions:
  - "PDF metadata extraction provides accurate attributes"
  - "Encryption status may require document parsing"
```

**Evidence pattern:** File metadata extraction.

## Verification

- [ ] Output contains `detected` boolean field
- [ ] All queried attribute names are addressed (found or not found)
- [ ] Attribute paths are valid for the data format
- [ ] Evidence anchors reference actual attribute locations
- [ ] Null vs. missing distinction is correctly reported when constraints specify

**Verification tools:** Read (for data inspection), Grep (for key/field search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive attribute values (passwords, keys) in output
- Note when attribute detection requires parsing binary formats
- If detecting security-relevant attributes (permissions, encryption), flag for review
- Do not follow external references or URLs embedded in attributes

## Composition Patterns

**Commonly follows:**
- `inspect` - After examining overall structure to identify attribute targets
- `retrieve` - After fetching data containing attributes

**Commonly precedes:**
- `identify-attribute` - When detection confirms presence, identify the value
- `compare-attributes` - When comparing attribute presence across sources
- `transform` - When preparing data for transformation

**Anti-patterns:**
- Never use to detect attributes in encrypted/protected data without authorization
- Avoid detecting attributes in very large files without pagination

**Workflow references:**
- See `workflow_catalog.json#schema-validation` for attribute completeness checks
- See `workflow_catalog.json#data-mapping` for attribute discovery
