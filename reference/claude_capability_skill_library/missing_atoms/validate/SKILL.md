---
name: validate
description: Check whether inputs, outputs, or states conform to schemas, constraints, or policies. Use when checking data integrity, verifying compliance, or ensuring contract adherence.
argument-hint: "[target] [schema] [rules]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Verify that data, configurations, or outputs conform to defined schemas, constraints, policies, or business rules. Produce a pass/fail verdict with detailed violation reports.

**Success criteria:**
- All rules checked systematically
- Violations clearly identified with location
- Severity levels appropriate
- False positives minimized
- Actionable fix suggestions provided

**Compatible schemas:**
- `docs/schemas/validation_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string or object | Data/config/output to validate |
| `schema` | No | object | JSON Schema or similar for structural validation |
| `rules` | No | array | Business rules, constraints, policies |
| `strict` | No | boolean | Fail on any warning (default: false) |
| `context` | No | object | Background for rule interpretation |

## Procedure

1) **Parse target**: Load and understand the data
   - Identify data type and format
   - Parse into internal representation
   - Note any parsing errors
   - Establish data structure

2) **Load validation rules**: Gather all constraints
   - Schema rules (types, required fields, formats)
   - Business rules (relationships, ranges, conditions)
   - Policy rules (compliance, security, standards)
   - Custom rules provided

3) **Validate structure**: Check schema conformance
   - Required fields present
   - Types match schema
   - Formats valid (dates, emails, etc.)
   - Nested structures correct

4) **Check constraints**: Verify value constraints
   - Range checks (min, max)
   - Pattern matches (regex)
   - Enum values valid
   - Cross-field dependencies

5) **Apply business rules**: Check domain logic
   - Relationship integrity
   - State consistency
   - Business invariants
   - Domain-specific rules

6) **Classify violations**: Categorize findings
   - ERROR: Must fix, validation fails
   - WARNING: Should fix, may pass in non-strict mode
   - INFO: Note for awareness

7) **Generate report**: Produce detailed output
   - Overall pass/fail
   - Each violation with location and fix
   - Summary statistics
   - Confidence in validation

## Output Contract

Return a structured object:

```yaml
validation:
  target: string  # What was validated
  schema_ref: string | null  # Schema used
  rules_applied: integer  # Number of rules checked
  timestamp: string
result:
  valid: boolean  # Overall pass/fail
  strict_valid: boolean  # Pass in strict mode?
  error_count: integer
  warning_count: integer
  info_count: integer
violations:
  - id: string  # Unique violation ID
    rule: string  # Rule that was violated
    severity: error | warning | info
    location: string  # Path to violation (e.g., "$.users[0].email")
    expected: string  # What was expected
    actual: string  # What was found
    message: string  # Human-readable description
    fix: string | null  # Suggested fix
rules_checked:
  - rule: string
    passed: boolean
    violations: integer
summary:
  total_rules: integer
  passed_rules: integer
  failed_rules: integer
  coverage: number  # Percentage of rules that could be checked
confidence: 0..1
evidence_anchors: ["schema:ref", "rule:id"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `validation` | object | Validation metadata |
| `result` | object | Overall validation outcome |
| `violations` | array | Detailed violation list |
| `rules_checked` | array | Rules and their results |
| `summary` | object | Validation statistics |
| `confidence` | number | 0.0-1.0 based on coverage |

## Examples

### Example 1: API Request Validation

**Input:**
```yaml
target:
  user_id: 12345
  email: "invalid-email"
  age: -5
  role: "superadmin"
  preferences:
    theme: "dark"
schema:
  type: object
  required: [user_id, email]
  properties:
    user_id: { type: integer, minimum: 1 }
    email: { type: string, format: email }
    age: { type: integer, minimum: 0, maximum: 150 }
    role: { type: string, enum: [admin, user, guest] }
    preferences: { type: object }
rules:
  - id: "ROLE_AGE"
    description: "Admins must be 18+"
    condition: "if role == 'admin' then age >= 18"
```

**Output:**
```yaml
validation:
  target: "API request payload"
  schema_ref: "user_update_v2"
  rules_applied: 6
  timestamp: "2024-01-15T10:00:00Z"
result:
  valid: false
  strict_valid: false
  error_count: 3
  warning_count: 0
  info_count: 1
violations:
  - id: "V001"
    rule: "email format"
    severity: error
    location: "$.email"
    expected: "valid email format"
    actual: "invalid-email"
    message: "Email does not match required format"
    fix: "Provide email in format: user@domain.com"
  - id: "V002"
    rule: "age minimum"
    severity: error
    location: "$.age"
    expected: "integer >= 0"
    actual: "-5"
    message: "Age cannot be negative"
    fix: "Provide age as non-negative integer"
  - id: "V003"
    rule: "role enum"
    severity: error
    location: "$.role"
    expected: "one of: admin, user, guest"
    actual: "superadmin"
    message: "Invalid role value"
    fix: "Use one of the allowed values: admin, user, guest"
  - id: "V004"
    rule: "preferences structure"
    severity: info
    location: "$.preferences"
    expected: "defined schema"
    actual: "unvalidated object"
    message: "Preferences object not validated (no schema defined)"
    fix: null
rules_checked:
  - rule: "user_id required"
    passed: true
    violations: 0
  - rule: "email required"
    passed: true
    violations: 0
  - rule: "email format"
    passed: false
    violations: 1
  - rule: "age range"
    passed: false
    violations: 1
  - rule: "role enum"
    passed: false
    violations: 1
  - rule: "ROLE_AGE business rule"
    passed: true
    violations: 0
summary:
  total_rules: 6
  passed_rules: 3
  failed_rules: 3
  coverage: 1.0
confidence: 0.95
evidence_anchors:
  - "schema:user_update_v2"
assumptions:
  - "Email format follows RFC 5322"
```

**Evidence pattern:** Each violation includes location, expected vs actual, and suggested fix.

---

### Example 2: Configuration Validation

**Input:**
```yaml
target:
  database:
    host: "localhost"
    port: "5432"
    ssl: true
  logging:
    level: "DEBUG"
    retention_days: 0
  security:
    api_key: ""
    rate_limit: 1000
schema:
  type: object
  required: [database, security]
  properties:
    database:
      type: object
      properties:
        port: { type: integer }
rules:
  - id: "API_KEY_REQUIRED"
    severity: error
    condition: "security.api_key must not be empty"
  - id: "RETENTION_POSITIVE"
    severity: warning
    condition: "logging.retention_days > 0"
  - id: "PROD_SSL_REQUIRED"
    severity: error
    condition: "if ENV=production then database.ssl=true"
```

**Output:**
```yaml
validation:
  target: "Application configuration"
  schema_ref: "app_config_v3"
  rules_applied: 5
  timestamp: "2024-01-15T11:00:00Z"
result:
  valid: false
  strict_valid: false
  error_count: 2
  warning_count: 1
  info_count: 0
violations:
  - id: "V001"
    rule: "port type"
    severity: error
    location: "$.database.port"
    expected: "integer"
    actual: "string ('5432')"
    message: "Port must be an integer, not a string"
    fix: "Change port: '5432' to port: 5432"
  - id: "V002"
    rule: "API_KEY_REQUIRED"
    severity: error
    location: "$.security.api_key"
    expected: "non-empty string"
    actual: "empty string"
    message: "API key is required but empty"
    fix: "Set security.api_key to a valid API key"
  - id: "V003"
    rule: "RETENTION_POSITIVE"
    severity: warning
    location: "$.logging.retention_days"
    expected: "positive integer"
    actual: "0"
    message: "Log retention of 0 days means no logs retained"
    fix: "Set retention_days to positive value (recommended: 30)"
rules_checked:
  - rule: "database required"
    passed: true
    violations: 0
  - rule: "security required"
    passed: true
    violations: 0
  - rule: "port type"
    passed: false
    violations: 1
  - rule: "API_KEY_REQUIRED"
    passed: false
    violations: 1
  - rule: "RETENTION_POSITIVE"
    passed: false
    violations: 1
summary:
  total_rules: 5
  passed_rules: 2
  failed_rules: 3
  coverage: 1.0
confidence: 0.9
evidence_anchors:
  - "schema:app_config_v3"
  - "rule:API_KEY_REQUIRED"
assumptions:
  - "ENV is not production (PROD_SSL_REQUIRED not checked)"
```

## Verification

- [ ] All rules were checked
- [ ] Violations have clear locations
- [ ] Severity levels are appropriate
- [ ] Fixes are actionable
- [ ] Pass/fail matches violations

**Verification tools:** Read (for data inspection)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always report all violations found
- Never hide security-related violations
- Provide actionable fixes when possible
- Note when validation is incomplete
- Be careful with false positives

## Bundled Scripts

This skill includes utility scripts for schema validation:

### validate-schema.sh

Located at: `scripts/validate-schema.sh`

**Usage:**
```bash
./scripts/validate-schema.sh <schema_file> <data_file> [options]
```

**Options:**
- `--format json|yaml` - Specify data format (default: auto-detect)
- `--verbose` - Show detailed validation output
- `--help` - Show help message

**Supported Tools (auto-detected):**
- `ajv-cli` - Full JSON Schema validation
- `jsonschema` (Python) - JSON Schema validation
- `jq` - Basic JSON syntax validation
- `yq` - YAML validation and conversion

**Examples:**
```bash
# Validate JSON against schema
./scripts/validate-schema.sh schemas/user.json data/user-input.json

# Validate YAML configuration
./scripts/validate-schema.sh schemas/config.yaml config/production.yaml --format yaml

# Verbose output
./scripts/validate-schema.sh schema.json data.json --verbose
```

**Exit Codes:**
- `0` - Validation passed
- `1` - Validation failed
- `2` - Missing validation tool

## Composition Patterns

**Commonly follows:**
- `receive` - Validate incoming data
- `transform` - Validate transformation output
- `retrieve` - Validate retrieved data

**Commonly precedes:**
- `integrate` - Only integrate valid data
- `send` - Validate before sending
- `persist` - Validate before storing
- `act-plan` - Validate plan before execution

**Anti-patterns:**
- Never skip validation for external input
- Never ignore security violations
- Never proceed after ERROR violations

**Workflow references:**
- Data pipeline validation
- API request validation
