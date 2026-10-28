---
name: digital-twin-bootstrap
description: Initialize a digital twin from scratch, building a grounded world model with state, dynamics, uncertainty and provenance, then run a first sync loop. Use when creating digital twins, constructing system representations, building simulation foundations, or establishing a baseline world state.
argument-hint: "[user_input] [world_state_out]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent

Run the composed workflow **digital_twin_bootstrap** (`reference/workflow_catalog.yaml`) to initialize a digital twin from scratch and then run a first sync loop. When no world state is passed in, it invokes **world_model_build** to construct a grounded baseline and then **digital_twin_sync_loop** from that baseline; when a world state is passed in, it skips the build and syncs from it.

A world model captures:
- **State**: Current entity states and attributes
- **Dynamics**: How the system evolves over time
- **Uncertainty**: Confidence bounds and unknowns
- **Provenance**: Source and lineage of all facts

**Success criteria:**
- World model built (or the given world state used as the baseline)
- First sync completed
- Audit produced
- Every claim in the model is grounded with evidence anchors

**Compatible schemas:**
- `reference/world_state_schema.yaml`
- `reference/event_schema.yaml`
- `reference/workflow_catalog.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `user_input` | No | object | `domain` (the system to model), passed to both invoked workflows; `world_model_build` binds it. `constraints` is accepted but no step binds it |
| `world_state_out` | No | object | An existing world state (`reference/world_state_schema.yaml#/world_state`). When given, the build is skipped and the first sync starts from it |

## Procedure

0) **Create checkpoint marker** if mutation might occur:
   - Create `.claude/checkpoint.ok` after confirming rollback strategy (the sync loop mutates the twin)

1) **Invoke `/invoke`** with workflow `world_model_build` and input `user_input`, if `world_state_out` is null, and store output as `world_model_out`
   - Build the initial world model baseline. The invoked workflow's stores land in `world_model_out.result`:
     `retrieve_out` → `observe_out` → `detect_out` (domain: entity) → `classify_out` → `integrate_out` → `state_out` → `transition_out` → `attribute_out` (domain: causation) → `measure_out` (domain: uncertainty) → `audit_out` → `ground_out` → `simulate_out` → `explain_out`

2) **Invoke `/invoke`** with workflow `digital_twin_sync_loop`, if `world_state_out` is null, and store output as `sync_out`
   - Input: `user_input`, and the baseline world state (`world_model_out.result.state_out.state`) as `previous_world_state`
   - Run the initial sync loop using the baseline just built

3) **Invoke `/invoke`** with workflow `digital_twin_sync_loop`, if `world_state_out` is not null, and store output as `sync_existing_out`
   - Input: `user_input`, and `world_state_out` as `previous_world_state`: a world state, the same shape step 2 passes (the `state` step's output wraps the world state in its `state` field)
   - Run the initial sync loop from the world state passed in

Every step has `skip_if_false: true`, so exactly one branch runs: steps 1-2, or step 3.

## Output Contract

Return a structured object:

```yaml
workflow_id: string  # Unique bootstrap execution ID
user_input: object  # The input as given
status: completed | partial | failed | rolled_back
steps:
  world_model_out:  # null when world_state_out was given and the step was skipped
    result:  # world_model_build's stores, keyed by store_as
      state_out:
        state: object  # The baseline world state
        entities: array[object]
        relationships: array[object]
        evidence_anchors: array[string]
      transition_out:
        rules: array[object]
        evidence_anchors: array[string]
      attribute_out:
        causes: array[object]
        strengths: object  # Causal strength per cause
        evidence_anchors: array[string]
      measure_out:
        value: number
        uncertainty: object  # lower, upper
        evidence_anchors: array[string]
      ground_out:
        grounded: boolean
        gaps: array[string]
        evidence_anchors: array[string]
      simulate_out:
        outcomes: array[object]
        evidence_anchors: array[string]
      explain_out:
        explanation: string
        evidence_anchors: array[string]
    steps_executed: array[string]  # store_as names of the steps that ran, in step order
    evidence_anchors: array[string]
  sync_out:  # null when world_state_out was given and the step was skipped
    result:  # digital_twin_sync_loop's stores, keyed by store_as
      state_out:
        state: object  # The synced twin snapshot
        evidence_anchors: array[string]
      verify_out:
        passed: boolean
        evidence_anchors: array[string]
      audit_out:
        audit_id: string
        evidence_anchors: array[string]
      explain_out:
        explanation: string
        evidence_anchors: array[string]
    steps_executed: array[string]  # store_as names of the steps that ran, in step order
    evidence_anchors: array[string]
  sync_existing_out:  # null when the baseline was built (steps 1-2 ran)
    result: object  # digital_twin_sync_loop's stores, as in sync_out
    steps_executed: array[string]  # store_as names of the steps that ran, in step order
    evidence_anchors: array[string]
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | Unique identifier for this bootstrap |
| `status` | enum | Final workflow status |
| `steps` | object | Each step's output, keyed by its `store_as`; a skipped step is null |
| `steps.*.result` | object | The invoked workflow's stores, keyed by their `store_as` |
| `confidence` | number | 0.0-1.0 based on evidence completeness |
| `evidence_anchors` | array | All evidence references collected |
| `assumptions` | array | Explicit assumptions made during modeling |

## Examples

### Example 1: Bootstrap a Supply Chain Twin

**Input:**
```yaml
user_input:
  domain: "electronics supply chain, Asia-Pacific"
world_state_out: null
```

**Output:**
```yaml
workflow_id: "bootstrap_20240115_100000_supplychain"
user_input:
  domain: "electronics supply chain, Asia-Pacific"
status: completed
steps:
  world_model_out:
    result:
      state_out:
        state:
          timestamp: "2024-01-15T10:00:00Z"
          entities: "[1247 entities - see state/supply_chain_world.yaml]"
        entities:
          - id: "supplier-taiwan-001"
            type: "supplier"
            location: "Hsinchu, Taiwan"
            lead_time_days: 45
          - id: "mfg-shenzhen-005"
            type: "manufacturer"
            location: "Shenzhen, China"
        relationships:
          - subject: "supplier-taiwan-001"
            predicate: "supplies_to"
            object: "mfg-shenzhen-005"
        evidence_anchors:
          - "tool:database:supply-chain-db/entities"
          - "tool:api:logistics.api/shipments"
      transition_out:
        rules:
          - trigger: "supplier shutdown"
            effect: "downstream inventory drawdown"
        evidence_anchors:
          - "tool:database:supply-chain-db/orders"
      attribute_out:
        causes:
          - id: single_source_taiwan
            cause: "Single-source dependency on Taiwan for 45% of semiconductor supply"
        strengths:
          single_source_taiwan: 0.8
        evidence_anchors:
          - "tool:database:supply-chain-db/suppliers"
      measure_out:
        value: 0.82  # overall confidence in the model
        uncertainty: {lower: 0.75, upper: 0.88}
        evidence_anchors:
          - "tool:api:logistics.api/shipments"
      ground_out:
        grounded: true
        gaps:
          - "Supplier capacity utilization (estimated from public data)"
          - "Shipping delays (historical average, not real-time)"
          - "Competitor orders affecting supplier allocation"
        evidence_anchors:
          - "file:state/supply_chain_world.yaml"
      simulate_out:
        outcomes:
          - scenario: "Taiwan supplier shutdown"
            outcome: "67% production halt within 2 weeks"
          - scenario: "Shipping route disruption"
            outcome: "12-day average delay added"
        evidence_anchors:
          - "file:state/supply_chain_world.yaml"
      explain_out:
        explanation: "Baseline covers 156 suppliers and 23 manufacturers; the largest risk is semiconductor source concentration"
        evidence_anchors:
          - "file:state/supply_chain_world.yaml"
    steps_executed: [retrieve_out, observe_out, detect_out, classify_out, integrate_out, state_out, transition_out, attribute_out, measure_out, audit_out, ground_out, simulate_out, explain_out]
    evidence_anchors:
      - "file:state/supply_chain_world.yaml"
  sync_out:
    result:
      state_out:
        state:
          timestamp: "2024-01-15T10:20:00Z"
          entities: "[1251 entities - 4 new shipments]"
        evidence_anchors:
          - "tool:api:logistics.api/shipments"
      verify_out:
        passed: true
        evidence_anchors:
          - "tool:bash:run_verification_suite"
      audit_out:
        audit_id: "audit_20240115_102000"
        evidence_anchors:
          - "file:.claude/audit/records.jsonl"
      explain_out:
        explanation: "First sync ingested 4 shipments; lead-time drift on supplier-taiwan-001 was planned for, passed the policy check and was applied after a checkpoint; verification passed, so rollback was skipped"
        evidence_anchors:
          - "file:.claude/audit/records.jsonl"
    steps_executed: [receive_out, search_out, transform_out, integrate_out, detect_entity_out, classify_out, state_out, compare_state_out, transition_out, detect_anomaly_out, measure_risk_out, predict_out, plan_out, constrain_out, checkpoint_out, mutate_out, execute_out, verify_out, audit_out, explain_out]  # rollback_out absent: skipped because verify_out.passed was true
    evidence_anchors:
      - "file:.claude/audit/records.jsonl"
  sync_existing_out: null  # skipped: no world state was passed in
confidence: 0.82
evidence_anchors:
  - "tool:database:supply-chain-db"
  - "tool:api:logistics.api"
  - "file:state/supply_chain_world.yaml"
  - "file:.claude/audit/records.jsonl"
assumptions:
  - "Database reflects current operational state"
  - "API provides accurate shipment tracking"
  - "Public capacity data is within 20% of actual"
```

**Evidence pattern:** Multi-source data integration, entity resolution across databases, causal analysis from transaction patterns, uncertainty from data freshness and coverage, then a first verified and audited sync.

## Verification

- [ ] **One Branch Ran**: Either `world_model_out` and `sync_out` are set, or `sync_existing_out` is
- [ ] **Entity Coverage**: All entities in scope identified (`detect_out` → `classify_out` → `integrate_out`)
- [ ] **State Validity**: The baseline world state (`state_out.state`) conforms to the world state schema
- [ ] **Dynamics Defined**: `transition_out.rules` and `attribute_out.causes` documented
- [ ] **Uncertainty Quantified**: `measure_out.uncertainty` present
- [ ] **Grounded**: `ground_out.grounded` is true, gaps listed
- [ ] **Simulation Run**: `simulate_out.outcomes` has at least one scenario
- [ ] **First Sync Verified**: The sync's `verify_out.passed` is true, or its rollback ran
- [ ] **Audit Trail**: The sync's `audit_out` was recorded

**Verification tools:** Read (for state files), Bash (for simulation), Web (for API validation)

## Safety Constraints

- `mutation`: true (the first sync may mutate the twin)
- `requires_checkpoint`: true
- `requires_approval`: true (for mutations in the sync loop)
- `risk`: high

**Capability-specific rules:**
- Do not modify source data during modeling
- Flag entities with confidence < threshold
- Document all assumptions explicitly
- Preserve raw data alongside derived state
- Validate schema conformance before the first sync
- Rate-limit API calls to respect source limits

## Composition Patterns

**Commonly follows:**
- `retrieve` - After gathering raw data
- `receive` - After ingesting real-time signals
- `observe` - After initial data quality assessment

**Commonly precedes:**
- `digital-twin-sync-workflow` - Later sync iterations start from the bootstrapped twin
- `simulate` - To run what-if scenarios
- `predict` (domain: risk) - To predict future states
- `explain` - To generate executive reports

**Anti-patterns:**
- Never skip identity resolution (`detect` → `classify` → `integrate`) before state construction
- Never omit uncertainty modeling for production use
- Never finalize without grounding and audit
- Never run the first sync from an empty baseline

**Workflow references:**
- See `reference/workflow_catalog.yaml#digital_twin_bootstrap` for step definitions
- See `reference/workflow_catalog.yaml#world_model_build` for the baseline build
- See `reference/world_state_schema.yaml` for canonical state format
