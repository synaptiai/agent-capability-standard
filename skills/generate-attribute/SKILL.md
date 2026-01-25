---
name: generate-attribute
description: Generate attribute values consistent with entity type, context, and constraints. Use when deriving missing attributes, creating entity profiles, or generating feature values.
argument-hint: "[entity_type] [attributes] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Generate plausible attribute values for entities based on type, context, and explicit constraints while clearly marking generated values as synthetic.

**Success criteria:**
- Generated attributes are plausible for entity type
- All constraints satisfied
- Values are internally consistent
- Generated vs known attributes clearly distinguished

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entity_type` | Yes | string | Type of entity (user, product, company, etc.) |
| `attributes` | Yes | array[string] | Attributes to generate |
| `known_values` | No | object | Known attribute values to inform generation |
| `constraints` | No | object | Rules for attribute values |
| `context` | No | string\|object | Domain or situational context |
| `count` | No | integer | Number of entities to generate attributes for |

## Procedure

1) **Understand entity type**: Map attributes to expectations
   - Common attributes for entity type
   - Valid value ranges
   - Typical distributions
   - Required vs optional attributes

2) **Apply known values**: Use existing data as anchors
   - Derive related attributes
   - Maintain consistency
   - Respect implied constraints

3) **Apply explicit constraints**: Enforce rules
   - Value ranges and formats
   - Relationships between attributes
   - Business rules and validations

4) **Generate values**: Create plausible attributes
   - Use appropriate distributions
   - Maintain internal consistency
   - Apply domain knowledge

5) **Validate coherence**: Check generated attributes
   - Internal consistency
   - Plausibility for entity type
   - Constraint satisfaction

6) **Document generation**: Clear metadata
   - Which values are generated vs known
   - Confidence in each generated value
   - Assumptions made

## Output Contract

Return a structured object:

```yaml
artifact:
  type: attribute_set
  content: object | array[object]  # Generated attributes
  format: json | yaml
  metadata:
    entity_type: string
    entities_count: integer
    attributes_generated: array[string]
    attributes_known: array[string]
generated_attributes:
  - entity_id: string | null
    attributes:
      - name: string
        value: any
        source: generated | known | derived
        confidence: number
        rationale: string | null
attribute_specifications:
  - attribute: string
    type: string
    distribution: string | null
    valid_range: object | null
    example_values: array
constraints_used:
  - constraint: string
    satisfied: boolean
    notes: string | null
coherence_checks:
  - check: string
    passed: boolean
    details: string
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
| `artifact` | object | Generated attribute sets |
| `generated_attributes` | array | Per-entity attribute details |
| `attribute_specifications` | array | Attribute type information |
| `constraints_used` | array | Constraint satisfaction |
| `coherence_checks` | array | Internal consistency validation |
| `confidence` | number | 0.0-1.0 confidence in attributes |
| `evidence_anchors` | array[string] | Sources informing generation |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Usage warnings |
| `next_actions` | array[string] | Suggested follow-ups |

## Examples

### Example 1: Generating Product Attributes

**Input:**
```yaml
entity_type: "software_product"
attributes:
  - "target_audience"
  - "key_features"
  - "pricing_tier"
  - "integration_capabilities"
  - "support_level"
known_values:
  name: "DataSync Pro"
  category: "data_integration"
  company_size_target: "enterprise"
constraints:
  pricing_tier:
    valid_values: ["free", "starter", "professional", "enterprise"]
  target_audience:
    must_align_with: "company_size_target"
context: "B2B SaaS market analysis"
count: 1
```

**Output:**
```yaml
artifact:
  type: attribute_set
  content:
    name: "DataSync Pro"
    category: "data_integration"
    company_size_target: "enterprise"
    target_audience: "IT departments and data teams in large enterprises (1000+ employees)"
    key_features:
      - "Real-time data synchronization across 50+ connectors"
      - "Enterprise-grade security (SOC2, HIPAA compliant)"
      - "Advanced transformation and mapping engine"
      - "Automated conflict resolution"
      - "Comprehensive audit logging"
    pricing_tier: "enterprise"
    integration_capabilities:
      native_integrations: ["Salesforce", "SAP", "Oracle", "Snowflake", "AWS", "Azure"]
      api_type: "REST and GraphQL"
      webhook_support: true
      custom_connector_sdk: true
    support_level:
      tiers: ["email", "phone", "dedicated_csm"]
      response_sla: "4 hours for critical issues"
      training_included: true
      professional_services: "available"
  format: json
  metadata:
    entity_type: "software_product"
    entities_count: 1
    attributes_generated:
      - "target_audience"
      - "key_features"
      - "pricing_tier"
      - "integration_capabilities"
      - "support_level"
    attributes_known:
      - "name"
      - "category"
      - "company_size_target"
generated_attributes:
  - entity_id: null
    attributes:
      - name: "target_audience"
        value: "IT departments and data teams in large enterprises (1000+ employees)"
        source: derived
        confidence: 0.9
        rationale: "Derived from company_size_target='enterprise' and category='data_integration'"
      - name: "key_features"
        value: ["Real-time sync", "Enterprise security", "Advanced transformations", "Conflict resolution", "Audit logging"]
        source: generated
        confidence: 0.8
        rationale: "Standard enterprise data integration features for target market"
      - name: "pricing_tier"
        value: "enterprise"
        source: derived
        confidence: 0.95
        rationale: "Directly aligned with company_size_target constraint"
      - name: "integration_capabilities"
        value: {"native": 6, "api_types": 2, "extensible": true}
        source: generated
        confidence: 0.85
        rationale: "Enterprise products typically have broad integration ecosystem"
      - name: "support_level"
        value: {"tiers": 3, "sla": true, "training": true}
        source: generated
        confidence: 0.85
        rationale: "Enterprise tier implies premium support expectations"
attribute_specifications:
  - attribute: "target_audience"
    type: "string"
    distribution: null
    valid_range: null
    example_values: ["SMB IT teams", "Enterprise data architects", "Startup developers"]
  - attribute: "key_features"
    type: "array[string]"
    distribution: null
    valid_range: {"min_count": 3, "max_count": 10}
    example_values: ["real-time sync", "security compliance", "API access"]
  - attribute: "pricing_tier"
    type: "enum"
    distribution: null
    valid_range: {"values": ["free", "starter", "professional", "enterprise"]}
    example_values: ["professional", "enterprise"]
  - attribute: "integration_capabilities"
    type: "object"
    distribution: null
    valid_range: null
    example_values: [{"connectors": 20}, {"connectors": 100}]
  - attribute: "support_level"
    type: "object"
    distribution: null
    valid_range: null
    example_values: [{"tiers": ["email"]}, {"tiers": ["email", "phone", "dedicated"]}]
constraints_used:
  - constraint: "pricing_tier in [free, starter, professional, enterprise]"
    satisfied: true
    notes: "Selected 'enterprise' to align with company_size_target"
  - constraint: "target_audience must_align_with company_size_target"
    satisfied: true
    notes: "Specified 'large enterprises (1000+ employees)'"
coherence_checks:
  - check: "Pricing tier matches target audience size"
    passed: true
    details: "Enterprise tier for enterprise target audience"
  - check: "Features appropriate for category"
    passed: true
    details: "Data integration features align with category"
  - check: "Support level matches pricing tier"
    passed: true
    details: "Premium support for enterprise pricing"
  - check: "Integration depth matches enterprise expectations"
    passed: true
    details: "50+ connectors, SDK available, multiple API types"
rationale: "Generated attributes based on known values (enterprise data integration) and standard market patterns. Enterprise products typically have premium pricing, broad integrations, advanced features, and comprehensive support. All generated values maintain coherence with the established product positioning."
confidence: 0.85
evidence_anchors:
  - "input:known_values"
  - "input:constraints"
  - "market:enterprise_saas_patterns"
assumptions:
  - "Product is established (not MVP/early stage)"
  - "Standard enterprise SaaS pricing model"
  - "US/international market positioning"
  - "B2B sales model (not self-service only)"
safety_notes:
  - "Generated attributes are plausible but synthetic"
  - "Do not use for competitive intelligence claims"
  - "Feature claims should be validated if used externally"
  - "Pricing tier is estimated, not actual pricing data"
next_actions:
  - "Validate features against actual product documentation"
  - "Confirm pricing alignment with sales team"
  - "Add competitor comparison if needed"
  - "Generate attributes for comparison products"
```

**Evidence pattern:** Known value analysis + constraint application + domain knowledge

## Verification

- [ ] All generated attributes are plausible
- [ ] Constraints satisfied
- [ ] Internal consistency maintained
- [ ] Generated vs known clearly marked
- [ ] Confidence levels justified

**Verification tools:** Read (for entity type references)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always distinguish generated from known attributes
- Do not generate attributes that claim factual status
- Mark synthetic attributes clearly
- Do not generate sensitive PII attributes
- Flag when generated attributes could be misleading if mistaken for real

## Composition Patterns

**Commonly follows:**
- `identify-entity` - to understand entity type
- `retrieve` - to get known attribute values
- `search` - to find similar entities

**Commonly precedes:**
- `compare-attributes` - to compare generated profiles
- `verify` - to validate attribute plausibility
- `generate-numeric-data` - for full entity generation

**Anti-patterns:**
- Never generate attributes for real identified individuals
- Avoid generating attributes that could be used for deception

**Workflow references:**
- See `workflow_catalog.json#entity_enrichment` for data enrichment
- See `workflow_catalog.json#profile_generation` for entity modeling
