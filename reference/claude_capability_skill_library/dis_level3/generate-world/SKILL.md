---
name: generate-world
description: Generate world-state scenarios consistent with constraints for simulation, testing, or creative purposes. Use when creating test scenarios, simulation environments, or hypothetical situations.
argument-hint: "[domain] [constraints] [entities]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create coherent world-state scenarios including entities, relationships, rules, and conditions that satisfy specified constraints for use in simulations, testing, or scenario planning.

**Success criteria:**
- World state is internally consistent
- All constraints satisfied
- Entities and relationships form coherent model
- State is suitable for intended use (testing, simulation, planning)

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `domain` | Yes | string | Domain for the world (business, technical, social, fictional) |
| `constraints` | No | object | Rules and limitations for the world |
| `entities` | No | array | Required entities to include |
| `relationships` | No | array | Required relationships between entities |
| `scenario_type` | No | string | normal, edge_case, stress_test, failure (default: normal) |
| `complexity` | No | string | simple, moderate, complex (default: moderate) |

## Procedure

1) **Define domain boundaries**: Establish scope
   - What aspects of reality to model
   - What simplifications are acceptable
   - What level of detail is needed
   - What time frame is represented

2) **Generate entities**: Create world inhabitants
   - Required entities from input
   - Supporting entities needed for coherence
   - Entity attributes and states
   - Entity identifiers and types

3) **Establish relationships**: Connect entities
   - Required relationships from input
   - Implied relationships for coherence
   - Relationship types and strengths
   - Bidirectional vs unidirectional

4) **Define rules**: World mechanics
   - Invariants that must hold
   - Constraints on state transitions
   - Business rules or physics
   - Boundary conditions

5) **Set initial state**: Snapshot the world
   - Current values for all entities
   - Active relationships
   - Pending events or conditions
   - Historical context if relevant

6) **Validate coherence**: Check consistency
   - No contradictory states
   - All relationships valid
   - Rules not violated
   - Scenario is plausible

## Output Contract

Return a structured object:

```yaml
artifact:
  type: world_state
  content: object  # The world model
  format: yaml | json
  metadata:
    domain: string
    scenario_type: string
    complexity: string
    entity_count: integer
    relationship_count: integer
world_state:
  id: string
  domain: string
  timestamp: string  # When this state represents
  description: string
  entities:
    - id: string
      type: string
      name: string
      attributes: object
      state: object
  relationships:
    - id: string
      source: string
      target: string
      type: string
      attributes: object
  rules:
    - id: string
      description: string
      condition: string
      enforcement: strict | soft
  observations:
    - id: string
      type: string
      value: object
      source: string
      timestamp: string
  pending_events:
    - id: string
      type: string
      trigger_condition: string
      expected_time: string | null
constraints_applied:
  - constraint: string
    satisfied: boolean
    notes: string | null
coherence_validation:
  - check: string
    passed: boolean
    details: string
scenario_properties:
  realistic: boolean
  edge_cases_present: array[string]
  stress_factors: array[string]
usage_notes:
  - purpose: string
    guidance: string
rationale: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `artifact` | object | Generated world state |
| `world_state` | object | Complete world model |
| `constraints_applied` | array | Constraint satisfaction |
| `coherence_validation` | array | Consistency checks |
| `scenario_properties` | object | Characteristics of scenario |
| `usage_notes` | array | Guidance for using the scenario |
| `confidence` | number | 0.0-1.0 confidence in coherence |
| `evidence_anchors` | array[string] | Sources informing world design |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Usage considerations |
| `next_actions` | array[string] | Suggested follow-ups |

## Examples

### Example 1: Generating E-commerce Test Scenario

**Input:**
```yaml
domain: "e-commerce_platform"
constraints:
  inventory_rule: "cannot sell more than available stock"
  payment_rule: "order total must match sum of items"
  time_constraint: "all orders within last 7 days"
entities:
  - type: "customer"
    count: 5
  - type: "product"
    count: 10
  - type: "order"
    count: 15
scenario_type: "edge_case"
complexity: "moderate"
```

**Output:**
```yaml
artifact:
  type: world_state
  content: "See world_state object below"
  format: yaml
  metadata:
    domain: "e-commerce_platform"
    scenario_type: "edge_case"
    complexity: "moderate"
    entity_count: 30
    relationship_count: 45
world_state:
  id: "ws-ecom-edge-001"
  domain: "e-commerce_platform"
  timestamp: "2024-01-15T12:00:00Z"
  description: "E-commerce platform state with edge cases: near-zero inventory, high-value orders, mixed payment states"
  entities:
    # Customers
    - id: "cust-001"
      type: "customer"
      name: "Alice Johnson"
      attributes:
        email: "alice@example.com"
        tier: "premium"
        account_created: "2022-03-15"
      state:
        cart_items: 2
        pending_orders: 1
        lifetime_value: 4500.00
    - id: "cust-002"
      type: "customer"
      name: "Bob Smith"
      attributes:
        email: "bob@example.com"
        tier: "standard"
        account_created: "2023-06-20"
      state:
        cart_items: 0
        pending_orders: 0
        lifetime_value: 250.00
    - id: "cust-003"
      type: "customer"
      name: "Carol White"
      attributes:
        email: "carol@example.com"
        tier: "premium"
        account_created: "2021-01-10"
      state:
        cart_items: 5
        pending_orders: 2
        lifetime_value: 12000.00
    - id: "cust-004"
      type: "customer"
      name: "David Brown"
      attributes:
        email: "david@example.com"
        tier: "standard"
        account_created: "2024-01-05"
      state:
        cart_items: 1
        pending_orders: 3
        lifetime_value: 75.00
    - id: "cust-005"
      type: "customer"
      name: "Eve Davis"
      attributes:
        email: "eve@example.com"
        tier: "vip"
        account_created: "2020-05-22"
      state:
        cart_items: 0
        pending_orders: 0
        lifetime_value: 45000.00
    # Products (sample)
    - id: "prod-001"
      type: "product"
      name: "Premium Widget"
      attributes:
        sku: "WGT-PREM-001"
        category: "electronics"
        price: 299.99
      state:
        inventory: 2  # EDGE CASE: Low stock
        reserved: 1
        available: 1
    - id: "prod-002"
      type: "product"
      name: "Basic Gadget"
      attributes:
        sku: "GDG-BASIC-002"
        category: "electronics"
        price: 49.99
      state:
        inventory: 500
        reserved: 15
        available: 485
    - id: "prod-003"
      type: "product"
      name: "Luxury Item"
      attributes:
        sku: "LUX-ITEM-003"
        category: "premium"
        price: 1999.99
      state:
        inventory: 0  # EDGE CASE: Out of stock
        reserved: 0
        available: 0
    # Orders (sample)
    - id: "order-001"
      type: "order"
      name: null
      attributes:
        order_number: "ORD-2024-0001"
        customer_id: "cust-001"
        created_at: "2024-01-10T14:30:00Z"
      state:
        status: "pending_payment"  # EDGE CASE: Stuck payment
        total: 349.98
        items_count: 2
        payment_attempts: 3
    - id: "order-002"
      type: "order"
      name: null
      attributes:
        order_number: "ORD-2024-0002"
        customer_id: "cust-003"
        created_at: "2024-01-12T09:15:00Z"
      state:
        status: "shipped"
        total: 4299.97  # EDGE CASE: High value order
        items_count: 3
        tracking_number: "1Z999AA10123456784"
  relationships:
    - id: "rel-001"
      source: "order-001"
      target: "cust-001"
      type: "placed_by"
      attributes:
        timestamp: "2024-01-10T14:30:00Z"
    - id: "rel-002"
      source: "order-001"
      target: "prod-001"
      type: "contains"
      attributes:
        quantity: 1
        unit_price: 299.99
    - id: "rel-003"
      source: "order-001"
      target: "prod-002"
      type: "contains"
      attributes:
        quantity: 1
        unit_price: 49.99
    - id: "rel-004"
      source: "prod-001"
      target: "order-001"
      type: "reserved_for"
      attributes:
        quantity: 1
        reserved_at: "2024-01-10T14:30:00Z"
  rules:
    - id: "rule-001"
      description: "Cannot sell more than available inventory"
      condition: "order.items.quantity <= product.available"
      enforcement: strict
    - id: "rule-002"
      description: "Order total equals sum of line items"
      condition: "order.total == SUM(items.quantity * items.unit_price)"
      enforcement: strict
    - id: "rule-003"
      description: "Premium customers get priority fulfillment"
      condition: "IF customer.tier IN ['premium', 'vip'] THEN order.priority = 'high'"
      enforcement: soft
    - id: "rule-004"
      description: "Orders over $1000 require fraud check"
      condition: "IF order.total > 1000 THEN require_fraud_check"
      enforcement: strict
  observations:
    - id: "obs-001"
      type: "inventory_alert"
      value:
        product_id: "prod-001"
        current_stock: 2
        threshold: 5
        alert_level: "warning"
      source: "inventory_system"
      timestamp: "2024-01-15T08:00:00Z"
    - id: "obs-002"
      type: "payment_failure"
      value:
        order_id: "order-001"
        attempt: 3
        reason: "card_declined"
        last_attempt: "2024-01-14T16:45:00Z"
      source: "payment_gateway"
      timestamp: "2024-01-14T16:45:00Z"
  pending_events:
    - id: "evt-001"
      type: "inventory_replenishment"
      trigger_condition: "prod-003.inventory == 0"
      expected_time: "2024-01-18T00:00:00Z"
    - id: "evt-002"
      type: "order_auto_cancel"
      trigger_condition: "order-001.payment_attempts >= 5"
      expected_time: null
constraints_applied:
  - constraint: "inventory_rule: cannot sell more than available stock"
    satisfied: true
    notes: "All orders respect available inventory; prod-003 is out of stock and has no orders"
  - constraint: "payment_rule: order total must match sum of items"
    satisfied: true
    notes: "Verified for order-001: 299.99 + 49.99 = 349.98"
  - constraint: "time_constraint: all orders within last 7 days"
    satisfied: true
    notes: "Current time 2024-01-15, orders from 2024-01-10 onwards"
coherence_validation:
  - check: "Customer references exist"
    passed: true
    details: "All order.customer_id values reference existing customers"
  - check: "Product references exist"
    passed: true
    details: "All order items reference existing products"
  - check: "Inventory math consistent"
    passed: true
    details: "inventory = reserved + available for all products"
  - check: "Order totals accurate"
    passed: true
    details: "All order totals match sum of line items"
  - check: "Timeline consistent"
    passed: true
    details: "All timestamps in logical order"
scenario_properties:
  realistic: true
  edge_cases_present:
    - "Near-zero inventory (prod-001: 2 units)"
    - "Out of stock product (prod-003)"
    - "Stuck payment state (order-001: 3 failed attempts)"
    - "High-value order requiring fraud check (order-002: $4,299.97)"
    - "New customer with multiple pending orders (cust-004)"
    - "VIP customer with no recent activity (cust-005)"
  stress_factors:
    - "Payment failure handling"
    - "Low inventory race conditions"
    - "High-value order processing"
usage_notes:
  - purpose: "Integration testing"
    guidance: "Test payment retry logic with order-001"
  - purpose: "Inventory edge cases"
    guidance: "Attempt to order prod-001 to test low-stock handling"
  - purpose: "Out of stock handling"
    guidance: "Test backorder or waitlist with prod-003"
  - purpose: "Fraud detection"
    guidance: "Use order-002 pattern for fraud check triggers"
rationale: "Generated edge case scenario covering common e-commerce failure modes: payment issues, inventory constraints, high-value orders, and customer tier variations. All entities maintain referential integrity and business rules are respected while creating testable edge conditions."
confidence: 0.9
evidence_anchors:
  - "input:constraints"
  - "input:entities"
  - "domain:ecommerce_best_practices"
assumptions:
  - "Standard e-commerce platform architecture"
  - "Payment gateway returns standard decline codes"
  - "Inventory is centralized (not multi-warehouse)"
  - "Currency is USD"
safety_notes:
  - "All data is synthetic - do not use as real customer data"
  - "Customer names and emails are fictional"
  - "Order patterns designed for testing, not analytics"
  - "Do not train ML models on generated patterns"
next_actions:
  - "Add more edge cases for returns and refunds"
  - "Generate time-series version for state transitions"
  - "Create companion test cases for each edge case"
  - "Add multi-warehouse inventory variant"
```

**Evidence pattern:** Domain modeling + constraint satisfaction + edge case injection

## Verification

- [ ] All entities have valid types and attributes
- [ ] All relationships reference existing entities
- [ ] Rules are not violated by current state
- [ ] Scenario matches requested type (edge_case)
- [ ] World is internally consistent

**Verification tools:** Read (for domain references)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Generated entities must be clearly synthetic
- Do not generate scenarios that model harmful activities
- Ensure generated PII is clearly fake
- Flag scenarios that could be misused
- Include usage guidance for testing scenarios

## Composition Patterns

**Commonly follows:**
- `identify-entity` - to understand entity types
- `discover-relationship` - to understand relationship patterns
- `retrieve` - to get domain schemas

**Commonly precedes:**
- `simulate` - to run scenarios
- `forecast-outcome` - to predict scenario evolution
- `verify` - to validate scenario coherence

**Anti-patterns:**
- Never generate scenarios modeling illegal activities
- Avoid generating realistic personal data

**Workflow references:**
- See `workflow_catalog.json#test_scenario_generation` for testing
- See `workflow_catalog.json#simulation_setup` for simulations
