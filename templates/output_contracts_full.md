# Output Contracts (Full Specification)

Complete YAML schema definitions for all capability layer output contracts.

---

## PERCEPTION Layer Contracts

### inspect

```yaml
identity:
  id: string | null
  type: string  # file, directory, endpoint, entity, etc.
  name: string
  namespace: string | null
structure:
  kind: string  # tree, flat, nested, graph
  shape: string  # description of organization
  key_parts: array[string]  # significant components
properties:
  high_signal: object  # most important attributes
  other: object  # secondary attributes
relationships:
  - src: string
    relation: string  # depends_on, owns, located_in, calls, etc.
    dst: string
    attributes: object | null
condition:
  status: healthy | degraded | unknown
  signals: array[string]  # observed health indicators
  risks: array[string]  # potential issues
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### search

```yaml
matches:
  - id: string
    type: string  # file, function, class, endpoint, etc.
    relevance_score: number  # 0.0-1.0
    snippet: string  # matched content preview
    location: string  # file:line or URL
query_interpretation: string  # how the query was understood
total_matches: integer
search_scope: string  # what was searched
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### retrieve

```yaml
retrieved:
  - source: string  # URI, path, or identifier
    content: string | object  # raw or parsed content
    format: string  # text, json, yaml, html, etc.
    freshness: string  # timestamp or relative age
    authority: low | medium | high  # source reliability
provenance:
  sources: array[string]
  retrieval_method: string  # api, file_read, web_fetch, etc.
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## MODELING Layer Contracts

### detect (base verb)

```yaml
detected: boolean
target_type: string  # what was being detected
signals:
  - signal: string  # what was found
    strength: low | medium | high
    location: string  # file:line or path
false_positive_risk: low | medium | high
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
next_actions: array[string]  # 0-3 suggested if uncertain
```

### detect-entity / detect-person / detect-activity / detect-anomaly / detect-attribute / detect-world

```yaml
detected: boolean
target_type: string  # entity, person, activity, anomaly, attribute, world
instances:
  - id: string | null
    type: string
    attributes: object
    location: string
    confidence: number
signals:
  - signal: string
    strength: low | medium | high
    location: string
false_positive_risk: low | medium | high
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### identify (base verb)

```yaml
entity:
  id: string
  type: string
  canonical_name: string
  attributes: object
match_quality: exact | probable | possible | no_match
alternatives:
  - entity: object
    probability: number
disambiguation_signals: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### identify-entity / identify-person / identify-anomaly / identify-attribute / identify-human-attribute / identify-world

```yaml
entity:
  id: string
  type: string  # entity, person, anomaly, attribute, human-attribute, world
  canonical_name: string
  attributes: object
  namespace: string | null
match_quality: exact | probable | possible | no_match
alternatives:
  - entity: object
    probability: number
disambiguation_signals: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### estimate (base verb)

```yaml
estimate:
  value: number | string | object
  unit: string | null
  range:
    low: number
    high: number
  distribution: string | null  # normal, uniform, etc.
methodology: string  # how estimate was derived
inputs_used: array[string]
sensitivity:
  - factor: string
    impact: low | medium | high
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### estimate-activity / estimate-outcome / estimate-impact / estimate-relationship / estimate-risk / estimate-attribute / estimate-world

```yaml
estimate:
  target_type: string  # activity, outcome, impact, relationship, risk, attribute, world
  value: number | string | object
  unit: string | null
  range:
    low: number
    high: number
methodology: string
inputs_used: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### forecast (base verb)

```yaml
forecast:
  prediction: string | object
  time_horizon: string  # e.g., "7 days", "Q1 2025"
  probability: number  # 0.0-1.0
  scenarios:
    - name: string
      probability: number
      outcome: string | object
drivers:
  - factor: string
    direction: positive | negative | neutral
    magnitude: low | medium | high
uncertainties: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### forecast-time / forecast-outcome / forecast-impact / forecast-risk / forecast-attribute / forecast-world

```yaml
forecast:
  target_type: string  # time, outcome, impact, risk, attribute, world
  prediction: string | object
  time_horizon: string
  probability: number
  scenarios:
    - name: string
      probability: number
      outcome: object
drivers:
  - factor: string
    direction: positive | negative | neutral
    magnitude: low | medium | high
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## REASONING Layer Contracts

### compare (base verb)

```yaml
options:
  - id: string
    summary: string
criteria:
  - name: string
    weight: number  # 0.0-1.0
    type: quantitative | qualitative
comparison_matrix:
  - option_id: string
    scores:
      - criterion: string
        score: number
        rationale: string
recommendation:
  choice: string
  rationale: string
  confidence: number
tradeoffs:
  - option: string
    pros: array[string]
    cons: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### compare-entities / compare-people / compare-attributes / compare-plans / compare-documents / compare-impact

```yaml
options:
  - id: string
    type: string  # entity, person, attribute, plan, document, impact
    summary: string
criteria:
  - name: string
    weight: number
comparison_matrix:
  - option_id: string
    scores: array[object]
recommendation:
  choice: string
  rationale: string
tradeoffs:
  - option: string
    pros: array[string]
    cons: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### discover (base verb)

```yaml
discoveries:
  - type: string  # relationship, pattern, anomaly, etc.
    description: string
    significance: low | medium | high
    novelty: known | suspected | surprising
    location: string
methodology: string  # how discovery was made
search_space: string  # what was explored
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### discover-relationship / discover-anomaly / discover-outcome / discover-activity / discover-human-attribute

```yaml
discoveries:
  - type: string  # relationship, anomaly, outcome, activity, human-attribute
    description: string
    significance: low | medium | high
    entities_involved: array[string]
    location: string
methodology: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### plan

```yaml
plan:
  id: string
  goal: string
  steps:
    - id: string
      action: string
      target: string
      dependencies: array[string]
      verification_criteria: string
      rollback_action: string | null
  checkpoints:
    - after_step: string
      type: string
  estimated_risk: low | medium | high
validation:
  preconditions: array[string]
  postconditions: array[string]
alternatives_considered: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### critique

```yaml
findings:
  - type: failure_mode | edge_case | ambiguity | exploit | gap
    description: string
    severity: low | medium | high | critical
    location: string
    evidence: string
risk_summary:
  overall_risk: low | medium | high | critical
  mitigations_possible: boolean
  urgent_issues: array[string]
recommendations:
  - finding_ref: string
    suggestion: string
    effort: low | medium | high
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### explain

```yaml
explanation:
  summary: string  # 1-2 sentence overview
  detailed: string  # full explanation
  level: beginner | intermediate | expert
  analogies: array[string]  # helpful comparisons
key_concepts:
  - term: string
    definition: string
causal_chain: array[string]  # sequence of causes/effects
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### summarize

```yaml
summary:
  brief: string  # 1-2 sentences
  detailed: string  # full summary
  key_points: array[string]  # bullet points
  structure: string  # how content was organized
omitted:
  - topic: string
    reason: string
original_length: integer
compression_ratio: number
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## ACTION Layer Contracts

### act (base verb)

```yaml
actions_taken:
  - action: string
    target: string
    result: success | failure | partial
    output: string | null
changes:
  - file: string
    operation: create | modify | delete
    summary: string
    diff_anchor: string
verification:
  checks_run: array[string]
  overall: PASS | FAIL
  failures: array[string]
side_effects: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### act-plan

```yaml
plan_executed:
  id: string
  goal: string
  steps:
    - id: string
      action: string
      target: string
      result: success | failure | skipped
      checkpoint_id: string | null
      output: string | null
changes:
  - file: string
    operation: create | modify | delete
    summary: string
    diff_anchor: string
verification:
  checks:
    - name: string
      result: PASS | FAIL
      evidence: string
  overall: PASS | FAIL
checkpoints:
  - id: string
    type: git_stash | file_backup | state_snapshot
    restore_command: string
risks_encountered:
  - risk: string
    mitigation: string
    outcome: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### generate (base verb)

```yaml
artifact:
  type: string  # text, code, image, audio, plan, etc.
  content: string | object
  format: string  # markdown, json, yaml, etc.
constraints_used:
  - constraint: string
    satisfied: boolean
    notes: string
rationale: string  # why this generation approach
alternatives_considered: array[string]
quality_signals:
  - metric: string
    value: number | string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
```

### generate-text / generate-image / generate-audio / generate-numeric-data / generate-attribute / generate-plan / generate-world

```yaml
artifact:
  type: string  # text, image, audio, numeric-data, attribute, plan, world
  content: string | object
  format: string
  metadata: object
constraints_used:
  - constraint: string
    satisfied: boolean
rationale: string
quality_signals: array[object]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### transform

```yaml
transformed:
  input_type: string
  output_type: string
  content: object
  mapping_applied: string  # reference to mapping spec
validation:
  input_valid: boolean
  output_valid: boolean
  schema_ref: string
losses:
  - field: string
    reason: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### send

```yaml
sent:
  destination: string
  payload_type: string
  payload_summary: string
  timestamp: string
  message_id: string | null
delivery:
  status: sent | queued | failed
  confirmation: string | null
  retry_count: integer
constraints_applied:
  - constraint: string
    enforced: boolean
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## SAFETY Layer Contracts

### verify

```yaml
verdict: PASS | FAIL | INCONCLUSIVE
checks_run:
  - name: string
    type: assertion | invariant | regression | schema
    target: string
    result: PASS | FAIL
    evidence: string
failures:
  - check: string
    expected: string
    actual: string
    severity: low | medium | high | critical
fix_suggestions:
  - failure_ref: string
    suggestion: string
    confidence: number
coverage:
  checked: integer
  total: integer
  percentage: number
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### checkpoint

```yaml
checkpoint_created: boolean
checkpoint:
  id: string
  type: git_stash | file_backup | state_snapshot | database_savepoint
  created_at: string  # ISO timestamp
  scope:
    files: array[string]
    state_keys: array[string]
  restore_command: string
  expiry: string | null
pre_mutation_state:
  hash: string | null
  summary: string
next_safe_actions: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### rollback

```yaml
rolled_back: boolean
restored_to:
  checkpoint_id: string
  checkpoint_type: string
  timestamp: string
changes_reverted:
  - file: string
    operation: string
    summary: string
verification:
  pre_state_hash: string
  post_state_hash: string
  match: boolean
warnings: array[string]
next_actions: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### audit

```yaml
audit_record:
  id: string
  timestamp: string
  actor: string
  action_type: string
  targets: array[string]
  outcome: success | failure | partial
changes:
  - type: string
    before: string | null
    after: string | null
    location: string
tool_usage:
  - tool: string
    invocation_count: integer
    success_rate: number
decision_rationale: string
provenance:
  inputs: array[string]
  outputs: array[string]
  dependencies: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### constrain

```yaml
constraints_applied:
  - name: string
    type: policy | permission | rate_limit | scope
    target: string
    enforced: boolean
    violation_action: block | warn | log
policy_evaluation:
  policy_id: string
  result: allow | deny | conditional
  conditions_met: array[string]
  conditions_failed: array[string]
scope_reduction:
  original_scope: object
  constrained_scope: object
  removed_permissions: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### mitigate

```yaml
mitigations_applied:
  - risk: string
    mitigation: string
    effectiveness: low | medium | high
    status: applied | partial | failed
residual_risks:
  - risk: string
    severity: low | medium | high
    reason_unmitigated: string
verification:
  checks_run: array[string]
  overall: PASS | FAIL
recommendations: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## WORLD MODELING Layer Contracts

### world-state

```yaml
world_state:
  id: string
  domain: string
  timestamp: string
  entities:
    - id: string
      type: string
      attributes: object
      relationships: array[object]
  observations:
    - id: string
      type: string
      value: object
      source: string
      timestamp: string
      confidence: number
  rules:
    - id: string
      condition: string
      effect: string
  uncertainty:
    - entity_id: string
      attribute: string
      distribution: string
      parameters: object
provenance:
  sources: array[string]
  last_updated: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### state-transition

```yaml
transition:
  from_state: string
  to_state: string
  trigger: string
  guard_conditions: array[string]
  actions: array[string]
affected_entities:
  - entity_id: string
    changes: object
probability: number  # 0.0-1.0
side_effects: array[string]
reversible: boolean
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### causal-model

```yaml
causal_graph:
  nodes:
    - id: string
      type: variable | intervention | outcome
      description: string
  edges:
    - from: string
      to: string
      type: causes | correlates | mediates
      strength: low | medium | high
interventions:
  - target: string
    effect: string
    confidence: number
confounders: array[string]
assumptions:
  - assumption: string
    testable: boolean
confidence: number
evidence_anchors: array[string]
```

### identity-resolution

```yaml
resolved_entity:
  canonical_id: string
  type: string
  name: string
  attributes: object
aliases:
  - source: string
    id: string
    confidence: number
merge_conflicts:
  - attribute: string
    values: array[object]
    resolution: string
provenance:
  sources: array[string]
  resolution_method: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### provenance

```yaml
lineage:
  entity_id: string
  origin:
    source: string
    timestamp: string
    actor: string | null
  transformations:
    - step: string
      input: string
      output: string
      tool: string
      timestamp: string
  current_location: string
integrity:
  hash: string | null
  verified: boolean
  chain_of_custody: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### grounding

```yaml
claims:
  - claim: string
    grounded: boolean
    evidence:
      - type: direct | inferred | cited
        source: string
        confidence: number
    ungrounded_reason: string | null
overall_grounding:
  grounded_count: integer
  total_claims: integer
  percentage: number
weak_groundings:
  - claim: string
    issue: string
    suggestion: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### simulation

```yaml
simulation:
  id: string
  model_ref: string
  parameters: object
  time_steps: integer
results:
  trajectories:
    - variable: string
      values: array[number | object]
  final_state: object
  metrics:
    - name: string
      value: number
sensitivity:
  - parameter: string
    impact: low | medium | high
    direction: positive | negative
validation:
  calibrated: boolean
  validation_data: string | null
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### uncertainty-model

```yaml
uncertainties:
  - entity_id: string | null
    attribute: string
    type: aleatoric | epistemic | model
    distribution: normal | uniform | beta | custom
    parameters: object
    source: string
aggregated_uncertainty:
  method: string  # monte_carlo, analytical, etc.
  result: object
reduction_opportunities:
  - uncertainty_ref: string
    method: string
    expected_reduction: number
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## META Layer Contracts

### discover (META variant)

```yaml
meta_discoveries:
  - type: pattern | relationship | gap | opportunity
    description: string
    across: array[string]  # what was examined
    significance: low | medium | high
synthesis: string  # how discoveries connect
recommendations: array[string]
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## COORDINATION Layer Contracts

### delegate

```yaml
delegation:
  task: string
  delegated_to: string  # agent, tool, or workflow
  constraints_passed: object
  timeout: string | null
status: pending | running | completed | failed
result: object | null
handoff_context:
  - key: string
    value: object
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### invoke-workflow

```yaml
workflow_invocation:
  workflow_id: string
  inputs: object
  status: running | completed | failed | paused
  current_step: string | null
outputs:
  - step_id: string
    store_as: string
    result: object
final_result: object | null
failures:
  - step_id: string
    error: string
    recovery_action: string | null
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### synchronize

```yaml
synchronization:
  sources: array[string]
  strategy: merge | replace | conflict_resolve
  timestamp: string
changes:
  - source: string
    type: add | modify | delete
    entity: string
conflicts:
  - sources: array[string]
    attribute: string
    values: array[object]
    resolution: string | null
result:
  synchronized: boolean
  entities_affected: integer
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

---

## Usage Notes

1. **Required fields**: `confidence`, `evidence_anchors`, `assumptions` are required in all contracts
2. **Confidence scoring**: 0.0-1.0 based on evidence quality, completeness, and certainty
3. **Evidence anchors**: Use `file:line`, URLs, or `tool:<name>:<ref>` format
4. **Assumptions**: Always explicit; never implicit
5. **Contract validation**: Skills should validate output against these schemas before returning
