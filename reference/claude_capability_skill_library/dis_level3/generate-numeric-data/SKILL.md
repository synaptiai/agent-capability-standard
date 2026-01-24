---
name: generate-numeric-data
description: Generate numeric datasets, synthetic data, or statistical samples under constraints. Use when creating test data, simulation inputs, or synthetic datasets for development and testing.
argument-hint: "[schema] [constraints] [size]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create numeric or structured data that satisfies schema requirements, statistical properties, and business constraints for use in testing, simulation, or development.

**Success criteria:**
- Data conforms to specified schema
- Statistical properties match requirements
- Constraints and business rules satisfied
- Data is clearly marked as synthetic

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `schema` | Yes | object | Data structure definition |
| `constraints` | No | object | Value ranges, distributions, correlations |
| `size` | No | integer | Number of records to generate (default: 10) |
| `relationships` | No | array | Cross-field dependencies |
| `seed` | No | integer | Random seed for reproducibility |
| `format` | No | string | Output format: json, csv, yaml, sql (default: json) |

## Procedure

1) **Parse schema**: Understand data structure
   - Field names and types
   - Required vs optional fields
   - Nested structures
   - Unique constraints

2) **Apply constraints**: Map business rules
   - Value ranges (min/max)
   - Allowed values (enums)
   - Format patterns (regex)
   - Distribution requirements (normal, uniform, etc.)

3) **Handle relationships**: Cross-field dependencies
   - Correlations between fields
   - Conditional values
   - Referential integrity
   - Derived fields

4) **Generate data**: Create records
   - Apply random distributions
   - Enforce constraints
   - Maintain relationships
   - Ensure uniqueness where required

5) **Validate output**: Check data quality
   - Schema compliance
   - Constraint satisfaction
   - Statistical property verification

6) **Document properties**: Describe generated data
   - Actual distributions achieved
   - Any constraint relaxations
   - Known limitations

## Output Contract

Return a structured object:

```yaml
artifact:
  type: numeric_data
  content: string | object  # The generated data
  format: json | csv | yaml | sql
  metadata:
    record_count: integer
    field_count: integer
    schema_ref: string | null
data_properties:
  - field: string
    type: string
    distribution: string
    min: number | null
    max: number | null
    unique_count: integer
    null_count: integer
statistical_summary:
  - field: string
    mean: number | null
    median: number | null
    std_dev: number | null
    quartiles: array[number] | null
constraints_used:
  - constraint: string
    satisfied: boolean
    actual_result: string
relationships_enforced:
  - description: string
    fields: array[string]
    satisfied: boolean
rationale: string
reproducibility:
  seed_used: integer | null
  algorithm: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `artifact` | object | Generated data with format info |
| `data_properties` | array | Per-field statistics |
| `statistical_summary` | array | Aggregate statistics |
| `constraints_used` | array | Constraint satisfaction report |
| `relationships_enforced` | array | Cross-field relationship status |
| `reproducibility` | object | How to recreate this data |
| `confidence` | number | 0.0-1.0 confidence in data quality |
| `evidence_anchors` | array[string] | Schema and constraint sources |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Data usage warnings |
| `next_actions` | array[string] | Suggested follow-ups |

## Examples

### Example 1: Generating E-commerce Test Data

**Input:**
```yaml
schema:
  orders:
    - field: order_id
      type: string
      format: "ORD-{uuid}"
      unique: true
    - field: customer_id
      type: string
      format: "CUST-{int:5}"
    - field: order_date
      type: datetime
    - field: total_amount
      type: decimal
      precision: 2
    - field: item_count
      type: integer
    - field: status
      type: enum
      values: ["pending", "processing", "shipped", "delivered", "cancelled"]
constraints:
  total_amount:
    min: 9.99
    max: 2500.00
    distribution: "log-normal"
  item_count:
    min: 1
    max: 20
    correlation_with: "total_amount"
    correlation_strength: 0.7
  order_date:
    min: "2024-01-01"
    max: "2024-01-31"
  status:
    distribution:
      pending: 0.10
      processing: 0.15
      shipped: 0.25
      delivered: 0.45
      cancelled: 0.05
size: 10
seed: 42
format: "json"
```

**Output:**
```yaml
artifact:
  type: numeric_data
  content: |
    [
      {
        "order_id": "ORD-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "customer_id": "CUST-00142",
        "order_date": "2024-01-15T14:23:45Z",
        "total_amount": 156.78,
        "item_count": 4,
        "status": "delivered"
      },
      {
        "order_id": "ORD-b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "customer_id": "CUST-00089",
        "order_date": "2024-01-03T09:12:33Z",
        "total_amount": 42.50,
        "item_count": 2,
        "status": "delivered"
      },
      {
        "order_id": "ORD-c3d4e5f6-a7b8-9012-cdef-123456789012",
        "customer_id": "CUST-00256",
        "order_date": "2024-01-22T18:45:12Z",
        "total_amount": 789.99,
        "item_count": 12,
        "status": "shipped"
      },
      {
        "order_id": "ORD-d4e5f6a7-b8c9-0123-defa-234567890123",
        "customer_id": "CUST-00033",
        "order_date": "2024-01-08T11:30:00Z",
        "total_amount": 23.99,
        "item_count": 1,
        "status": "delivered"
      },
      {
        "order_id": "ORD-e5f6a7b8-c9d0-1234-efab-345678901234",
        "customer_id": "CUST-00178",
        "order_date": "2024-01-29T16:55:22Z",
        "total_amount": 1245.00,
        "item_count": 15,
        "status": "processing"
      },
      {
        "order_id": "ORD-f6a7b8c9-d0e1-2345-fabc-456789012345",
        "customer_id": "CUST-00091",
        "order_date": "2024-01-12T08:15:45Z",
        "total_amount": 67.25,
        "item_count": 3,
        "status": "delivered"
      },
      {
        "order_id": "ORD-a7b8c9d0-e1f2-3456-abcd-567890123456",
        "customer_id": "CUST-00204",
        "order_date": "2024-01-19T13:42:18Z",
        "total_amount": 324.50,
        "item_count": 7,
        "status": "shipped"
      },
      {
        "order_id": "ORD-b8c9d0e1-f2a3-4567-bcde-678901234567",
        "customer_id": "CUST-00067",
        "order_date": "2024-01-25T20:08:33Z",
        "total_amount": 99.99,
        "item_count": 4,
        "status": "pending"
      },
      {
        "order_id": "ORD-c9d0e1f2-a3b4-5678-cdef-789012345678",
        "customer_id": "CUST-00312",
        "order_date": "2024-01-06T07:22:11Z",
        "total_amount": 549.75,
        "item_count": 9,
        "status": "cancelled"
      },
      {
        "order_id": "ORD-d0e1f2a3-b4c5-6789-defa-890123456789",
        "customer_id": "CUST-00145",
        "order_date": "2024-01-17T15:33:27Z",
        "total_amount": 187.25,
        "item_count": 5,
        "status": "delivered"
      }
    ]
  format: json
  metadata:
    record_count: 10
    field_count: 6
    schema_ref: "input:schema:orders"
data_properties:
  - field: "order_id"
    type: "string"
    distribution: "uuid"
    min: null
    max: null
    unique_count: 10
    null_count: 0
  - field: "customer_id"
    type: "string"
    distribution: "uniform integer (5 digits)"
    min: null
    max: null
    unique_count: 10
    null_count: 0
  - field: "order_date"
    type: "datetime"
    distribution: "uniform"
    min: "2024-01-03"
    max: "2024-01-29"
    unique_count: 10
    null_count: 0
  - field: "total_amount"
    type: "decimal"
    distribution: "log-normal"
    min: 23.99
    max: 1245.00
    unique_count: 10
    null_count: 0
  - field: "item_count"
    type: "integer"
    distribution: "correlated with total_amount"
    min: 1
    max: 15
    unique_count: 9
    null_count: 0
  - field: "status"
    type: "enum"
    distribution: "weighted random"
    min: null
    max: null
    unique_count: 5
    null_count: 0
statistical_summary:
  - field: "total_amount"
    mean: 348.70
    median: 172.02
    std_dev: 392.45
    quartiles: [52.87, 172.02, 549.75]
  - field: "item_count"
    mean: 6.2
    median: 4.5
    std_dev: 4.69
    quartiles: [2.5, 4.5, 10.5]
constraints_used:
  - constraint: "total_amount: min 9.99, max 2500.00"
    satisfied: true
    actual_result: "Range: 23.99 - 1245.00"
  - constraint: "total_amount: log-normal distribution"
    satisfied: true
    actual_result: "Right-skewed with most values in lower range"
  - constraint: "item_count: correlation 0.7 with total_amount"
    satisfied: true
    actual_result: "Pearson r = 0.72"
  - constraint: "status: weighted distribution"
    satisfied: true
    actual_result: "delivered: 50%, shipped: 20%, processing: 10%, pending: 10%, cancelled: 10%"
relationships_enforced:
  - description: "Item count correlates with total amount"
    fields: ["item_count", "total_amount"]
    satisfied: true
  - description: "Order IDs are unique"
    fields: ["order_id"]
    satisfied: true
rationale: "Generated 10 records with realistic e-commerce patterns. Used log-normal distribution for amounts (common in purchase data). Maintained correlation between item count and total. Status distribution approximates typical order lifecycle."
reproducibility:
  seed_used: 42
  algorithm: "Mersenne Twister PRNG with constraint-based rejection sampling"
confidence: 0.9
evidence_anchors:
  - "input:schema"
  - "input:constraints"
assumptions:
  - "Log-normal parameters inferred from min/max constraints"
  - "Correlation achieved via copula method"
  - "Status distribution based on typical e-commerce funnel"
safety_notes:
  - "DATA IS SYNTHETIC - DO NOT USE AS REAL BUSINESS DATA"
  - "Customer IDs are random, not real customers"
  - "Order IDs use fake UUIDs"
  - "Amounts are realistic but fabricated"
  - "Not suitable for financial reporting or compliance"
next_actions:
  - "Validate schema against actual database"
  - "Adjust distributions based on real data analysis if needed"
  - "Generate larger dataset for load testing"
  - "Add additional related tables (customers, items)"
```

**Evidence pattern:** Schema parsing + constraint application + statistical generation

## Verification

- [ ] All records conform to schema
- [ ] Constraints satisfied within tolerance
- [ ] Relationships preserved
- [ ] No real PII generated
- [ ] Reproducible with seed

**Verification tools:** Read (for schema validation)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- NEVER generate real PII (use clearly fake data)
- Always mark data as synthetic
- Do not generate data that could pass as real for fraud
- Include warnings about appropriate use
- Ensure generated data cannot be used to train models on fake patterns

## Composition Patterns

**Commonly follows:**
- `retrieve` - to get schema definitions
- `identify-attribute` - to understand data types
- `search` - to find example data patterns

**Commonly precedes:**
- `verify` - to validate generated data
- `transform` - to convert formats
- `act` - to insert into test database

**Anti-patterns:**
- Never generate data that could pass as real financial records
- Avoid generating realistic-looking credentials

**Workflow references:**
- See `workflow_catalog.json#test_data_setup` for testing workflows
- See `workflow_catalog.json#data_simulation` for analytics
