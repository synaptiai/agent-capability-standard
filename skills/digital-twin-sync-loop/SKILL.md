---
name: digital-twin-sync-workflow
description: Run the digital twin sync loop to synchronize real-world signals with a digital model. Use when updating digital twins, detecting drift, managing real-time state synchronization, or maintaining model-reality alignment.
argument-hint: "[user_input] [previous_world_state]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Web, Bash, Edit, Git
context: fork
agent: general-purpose
---

## Intent

Run the composed workflow **digital_twin_sync_loop** (`reference/workflow_catalog.yaml`) to synchronize a **digital twin** with incoming signals and keep it **grounded, safe, and auditable**: detect drift, decide and execute safe actions, and record provenance.

This workflow is designed to **model both real and digital systems** using the canonical world-state schema:
- `reference/world_state_schema.yaml`

**Success criteria:**
- Twin snapshot updated and grounded
- Drift assessed with risk score
- Any actions are approved/checkpointed/verified
- Audit trail produced
- Rollback runs only when verification fails

**Compatible schemas:**
- `reference/world_state_schema.yaml`
- `reference/event_schema.yaml`
- `reference/workflow_catalog.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `user_input` | No | object | `domain` and `constraints`. The catalog accepts both but no step binds them: the policy check uses the fixed constraints `least_privilege` and `change_policy`, and no drift threshold gates any step |
| `previous_world_state` | No | object | The twin snapshot before this sync (`reference/world_state_schema.yaml#/world_state`). Merged with the new events and diffed against the updated snapshot; without it there is no baseline (run `/digital-twin-bootstrap` instead) |

## Preconditions (hard gates)

1. **Policy constraints must pass** (`/constrain`): `mutate` runs only if `${constrain_out.compliant} == true`
2. **Checkpoint before mutation** (`/checkpoint`): `mutate` stops if `${checkpoint_out.checkpoint_id} == null`
3. Any external side effects require explicit approval (do not `send` without approval); `mutate` and `execute` require approval

## Procedure

0) **Ensure baseline exists**: If no twin snapshot exists, run `/digital-twin-bootstrap` instead: it builds the world model and then runs this loop

Then execute the sync loop:

1) **Invoke `/receive`** and store output as `receive_out`
   - Ingest new signals/events from sources (logs/APIs/messages); retry up to 3 times

2) **Invoke `/search`** for `receive_out.source` and store output as `search_out`
   - Parallel enrichment (`parallel_group: context_gathering`): search for the existing twin snapshot or relevant context

3) **Invoke `/transform`** on `receive_out.data` to `canonical_event` and store output as `transform_out`
   - Normalize raw signals into canonical events (`reference/transform_mapping_rawlog_to_observation.yaml`, output conforms to `reference/event_schema.yaml#/event`)

4) **Invoke `/integrate`** with `transform_out.output` and `previous_world_state`, and store output as `integrate_out`
   - Merge canonical events with the existing twin snapshot; resolve conflicts with `prefer_authoritative_sources`

5) **Invoke `/detect`** (domain: entity) on `integrate_out.merged` and store output as `detect_entity_out`
   - Detect entities in integrated data

6) **Invoke `/classify`** on `detect_entity_out.matches` and store output as `classify_out`
   - Classify and resolve entity identities

7) **Invoke `/state`** with `integrate_out.merged.observations`, scoped to `integrate_out.merged.meta.world_id`, and store output as `state_out`
   - Produce the updated canonical world-state snapshot with uncertainty + provenance

8) **Invoke `/compare`** (domain: state_diff) on `previous_world_state` and `state_out`, and store output as `compare_state_out`
   - Compute the diff between the previous and the updated snapshot

9) **Invoke `/transition`** from `state_out.state` and store output as `transition_out`
   - Apply transition rules triggered by new observations; compute next states

10) **Invoke `/detect`** (domain: anomaly) on `state_out` for `drift` and store output as `detect_anomaly_out`
    - Detect drift/anomalies between expected and observed state

11) **Invoke `/measure`** (domain: risk) on `detect_anomaly_out` and store output as `measure_risk_out`
    - Estimate risk impact/probability from drift and transitions

12) **Invoke `/predict`** (domain: risk) for `near_term_risk` and store output as `predict_out`
    - Forecast near-term risk trajectory and triggers

13) **Invoke `/plan`** with `predict_out` as context and store output as `plan_out`
    - Plan safe action(s) to reduce the detected drift and risk, with verification criteria and rollback plan

14) **Invoke `/constrain`** on `plan_out.steps` (`least_privilege`, `change_policy`) and store output as `constrain_out`
    - Enforce policy and least privilege for planned actions

15) **Invoke `/checkpoint`** on `twin_state` and store output as `checkpoint_out`
    - Create the checkpoint marker before any mutation/side-effect step

16) **Invoke `/mutate`** on `twin_state`, applying `plan_out.steps`, if `constrain_out.compliant` is true, and store output as `mutate_out`
    - Execute mutations from the action plan (if approved); stop if no checkpoint was created

17) **Invoke `/execute`** with `run_verification_suite` and store output as `execute_out`
    - Run verification tests and commands

18) **Invoke `/verify`** (`drift_resolved`, `no_policy_violation`) and store output as `verify_out`
    - Verify outcome: PASS/FAIL with evidence. On FAIL, roll back and return to step 13 with `verify_out.violations` as failure evidence (at most 3 loops)

19) **Invoke `/audit`** and store output as `audit_out`
    - Record provenance, tool usage, diffs, and decision rationale

20) **Invoke `/rollback`** to `checkpoint_out.checkpoint_id` if `verify_out.passed` is false, and store output as `rollback_out`
    - The step is skipped when verification passes

21) **Invoke `/explain`** and store output as `explain_out`
    - Produce a decision-ready sync report: drift, actions, verification, next steps

## Output Contract

Return a structured object:

```yaml
workflow_id: string  # Unique sync execution ID
user_input: object  # The input as given
status: synced | action_taken | rolled_back | failed
steps:
  receive_out:
    data: array[object]  # Received items, each with its sender
    source: string
    evidence_anchors: array[string]
  search_out:
    results: array[object]
    evidence_anchors: array[string]
  transform_out:
    output: object  # One canonical event (reference/event_schema.yaml#/event)
    evidence_anchors: array[string]
  integrate_out:
    merged: object  # Includes observations and meta.world_id
    conflicts: array[object]
    evidence_anchors: array[string]
  detect_entity_out:
    detected: boolean
    matches: array[object]
    evidence_anchors: array[string]
  classify_out:
    labels: array[object]
    evidence_anchors: array[string]
  state_out:
    state: object  # Canonical world state
    evidence_anchors: array[string]
  compare_state_out:
    ranking: array[object]
    tradeoffs: array[object]  # Differences between the snapshots
    evidence_anchors: array[string]
  transition_out:
    rules: array[object]
    effects: array[object]
    evidence_anchors: array[string]
  detect_anomaly_out:
    detected: boolean
    matches: array[object]
    evidence_anchors: array[string]
  measure_risk_out:
    value: number  # 0.0-1.0
    uncertainty: object  # lower, upper
    evidence_anchors: array[string]
  predict_out:
    prediction: object
    probability: number
    evidence_anchors: array[string]
  plan_out:
    steps: array[object]
    evidence_anchors: array[string]
  constrain_out:
    compliant: boolean
    violations: array[object]
    evidence_anchors: array[string]
  checkpoint_out:
    checkpoint_id: string
    evidence_anchors: array[string]
  mutate_out:  # null when the step was skipped (constrain_out.compliant was false)
    success: boolean
    previous_state: object
    new_state: object
    evidence_anchors: array[string]
  execute_out:
    result: any
    evidence_anchors: array[string]
  verify_out:
    passed: boolean
    violations: array[object]
    evidence_anchors: array[string]
  audit_out:
    audit_id: string
    evidence_anchors: array[string]
  rollback_out:  # null when verification passed and the step was skipped
    restored: boolean
    evidence_anchors: array[string]
  explain_out:
    explanation: string
    evidence_anchors: array[string]
verification: PASS | FAIL
audit_log_pointer: string  # Path to .claude/audit.log
next_sync:
  recommended_interval: string  # e.g., "5m", "1h"
  triggers: array[string]  # Conditions for immediate resync
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | Unique identifier for this sync execution |
| `status` | enum | Final workflow status |
| `steps` | object | Each step's output, keyed by its `store_as`; a skipped step is null |
| `verification` | enum | Final PASS/FAIL |
| `audit_log_pointer` | string | Where the audit trail was written |
| `next_sync` | object | Recommended timing for next synchronization |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array | All evidence references collected |
| `assumptions` | array | Explicit assumptions made during sync |

## Examples

### Example 1: IoT Sensor Sync with Drift Correction

**Input:**
```yaml
user_input:
  domain: "building floor 3 HVAC"
previous_world_state:
  meta:
    world_id: "building-floor-3-twin"
    as_of: "2024-01-15T15:55:00Z"
    timezone: "UTC"
    version_id: "v46"
    lineage: []
  entities:
    - id: "hvac-unit-3a"
      type: "hvac_controller"
  # relationships, state_variables, observations, transition_rules, actions, indexes elided
```

**Output:**
```yaml
workflow_id: "sync_20240115_160000_floor3"
user_input:
  domain: "building floor 3 HVAC"
status: action_taken
steps:
  receive_out:
    data:
      - sender: "gateway-floor-3"
        topic: "floor-3/hvac-unit-3a"
        payload:
          sensor-temp-301: 24.1
          hvac-unit-3a: {temperature: 23.5, setpoint: 22.0, status: "cooling"}
    source: "mqtt://sensors.example.com/floor-3"
    evidence_anchors:
      - "tool:mqtt:sensors.example.com/floor-3"
  search_out:
    results:
      - {path: "state/floor-3-twin-v46.yaml", version_id: "v46"}
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml"
  transform_out:
    output:
      event_id: "evt_7f3a91"
      timestamp: "2024-01-15T16:00:00Z"
      source: {kind: "sensor", name: "gateway-floor-3", channel: "floor-3/hvac-unit-3a"}
      event_type: "hvac_telemetry"
      entity_refs: [{entity_id: "sensor-temp-301"}, {entity_id: "hvac-unit-3a"}]
      raw:
        sensor-temp-301: 24.1
        hvac-unit-3a: {temperature: 23.5, setpoint: 22.0, status: "cooling"}
      canonical:
        readings:
          - {entity: "sensor-temp-301", variable: "reading", value: 24.1}
          - {entity: "hvac-unit-3a", variable: "temperature", value: 23.5}
      anchors: [{ref: "mqtt://sensors.example.com/floor-3", kind: "sensor"}]
      provenance: {transformer: "transform", transform_version: "1.0.0", ruleset_id: "raw_log_to_observation_event"}
    evidence_anchors:
      - "file:reference/transform_mapping_rawlog_to_observation.yaml"
  integrate_out:
    merged:
      meta: {world_id: "building-floor-3-twin"}
      observations:
        - event_id: "evt_5c20d4"  # carried over from v46
          timestamp: "2024-01-15T15:55:00Z"
          source: "sensor"
          payload:
            readings:
              - {entity: "sensor-temp-301", variable: "reading", value: 23.0}
              - {entity: "hvac-unit-3a", variable: "temperature", value: 22.4}
          anchors: [{ref: "file:state/floor-3-twin-v46.yaml", kind: "file"}]
        - event_id: "evt_7f3a91"  # new, from transform_out.output
          timestamp: "2024-01-15T16:00:00Z"
          source: "sensor"
          payload:
            readings:
              - {entity: "sensor-temp-301", variable: "reading", value: 24.1}
              - {entity: "hvac-unit-3a", variable: "temperature", value: 23.5}
          anchors: [{ref: "mqtt://sensors.example.com/floor-3", kind: "sensor"}]
    conflicts: []
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml"
  detect_entity_out:
    detected: true
    matches: [{id: "hvac-unit-3a"}, {id: "sensor-temp-301"}]
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml"
  classify_out:
    labels:
      - {id: "hvac-unit-3a", type: "hvac_controller"}
      - {id: "sensor-temp-301", type: "temperature_sensor"}
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml"
  state_out:
    state:
      meta: {world_id: "building-floor-3-twin", version_id: "v47", parent_version_id: "v46"}
    evidence_anchors:
      - "file:state/floor-3-twin-v47.yaml"
  compare_state_out:
    ranking: [{option: "v47", changed_entities: 2}]
    tradeoffs:
      - {field: "sensor-temp-301.reading", from: 23.0, to: 24.1}
      - {field: "hvac-unit-3a.temperature", from: 22.4, to: 23.5}
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml"
      - "file:state/floor-3-twin-v47.yaml"
  transition_out:
    rules: [{trigger: "temperature > setpoint for 10m", next: "cooling_degraded"}]
    effects: [{entity: "hvac-unit-3a", status: "cooling_degraded"}]
    evidence_anchors:
      - "file:state/floor-3-twin-v47.yaml"
  detect_anomaly_out:
    detected: true
    matches:
      - entity: "hvac-unit-3a"
        pattern: "drift"
        description: "Temperature 1.5°C above setpoint for >10 minutes"
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml:temperature_history"
  measure_risk_out:
    value: 0.35
    uncertainty: {lower: 0.3, upper: 0.4}
    evidence_anchors:
      - "file:state/floor-3-twin-v47.yaml"
  predict_out:
    prediction: {risk: 0.45, horizon: "1h", trigger: "comfort threshold breach"}
    probability: 0.6
    evidence_anchors:
      - "file:state/floor-3-twin-v46.yaml:temperature_history"
  plan_out:
    steps:
      - action: "Lower hvac-unit-3a setpoint to 21.5°C"
        verification: "Zone temperature within 0.5°C of setpoint in 15m"
        rollback: "Restore setpoint 22.0°C"
    evidence_anchors:
      - "file:state/floor-3-twin-v47.yaml"
  constrain_out:
    compliant: true
    violations: []
    evidence_anchors:
      - "policy:change_policy:setpoint_bounds"
  checkpoint_out:
    checkpoint_id: "chk_20240115_160500"
    evidence_anchors:
      - "file:.checkpoints/chk_20240115_160500/manifest.json"
  mutate_out:
    success: true
    previous_state: {setpoint: 22.0}
    new_state: {setpoint: 21.5}
    evidence_anchors:
      - "tool:api:building.api/hvac/hvac-unit-3a/setpoint"
  execute_out:
    result: "verification suite: 6 passed"
    evidence_anchors:
      - "tool:bash:run_verification_suite"
  verify_out:
    passed: true
    violations: []
    evidence_anchors:
      - "tool:bash:run_verification_suite"
  audit_out:
    audit_id: "audit_20240115_162000"
    evidence_anchors:
      - "file:.claude/audit.log"
  rollback_out: null  # skipped: verification passed
  explain_out:
    explanation: "Drift of 1.5°C detected on zone 3a; setpoint lowered to 21.5°C after policy check and checkpoint; verification passed"
    evidence_anchors:
      - "file:.claude/audit.log"
verification: PASS
audit_log_pointer: ".claude/audit.log"
next_sync:
  recommended_interval: "5m"
  triggers:
    - "Temperature exceeds 25°C"
    - "HVAC status changes"
confidence: 0.88
evidence_anchors:
  - "tool:mqtt:sensors.example.com/floor-3"
  - "file:state/floor-3-twin-v47.yaml"
  - "file:.claude/audit.log"
assumptions:
  - "Sensor readings are accurate within ±0.1°C"
  - "MQTT connection is reliable"
  - "Building API returns real-time status"
```

**Evidence pattern:** Multi-source signal ingestion, anomaly detection against historical baseline, risk forecasting with trend analysis, checkpointed and verified action.

## Verification

- [ ] **Step Completeness**: All 21 workflow steps executed with output (mutate skipped if not compliant, rollback skipped when verification passed)
- [ ] **Transform Success**: `transform_out.output` conforms to the canonical event schema
- [ ] **Identity Resolved**: No unresolved entity references in `classify_out`
- [ ] **Drift Detection**: `detect_anomaly_out` completed with evidence
- [ ] **Risk Assessment**: Both `measure_risk_out` and `predict_out` computed
- [ ] **Policy Compliance**: `constrain_out` evaluated before `mutate`
- [ ] **Checkpoint Valid**: `checkpoint_out.checkpoint_id` exists before `mutate`
- [ ] **Audit Complete**: `audit_out` recorded
- [ ] **Next Sync Scheduled**: Recommended interval provided

**Verification tools:** Web (for API checks), Bash (for MQTT), Read (for state files)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: true (for `mutate` and `execute`)
- `risk`: high

**Capability-specific rules:**
- STOP on low confidence from any perception step
- NEVER execute mutation without checkpoint
- NEVER emit external side effects without explicit approval
- Validate all source data before integration
- Preserve previous snapshot for rollback
- Rate-limit sync frequency to prevent thrashing

## Composition Patterns

**Commonly follows:**
- `digital-twin-bootstrap` - Initial twin creation and first sync
- `receive` - When triggered by external event

**Commonly precedes:**
- `explain` - Create executive report after sync
- `send` - Notify stakeholders of drift or actions
- Self (recursive) - Next sync iteration

**Anti-patterns:**
- Never sync without prior world model established
- Never skip anomaly detection to proceed directly to action
- Never execute actions without policy constraint check
- Never delete audit logs before retention period

**Workflow references:**
- See `reference/workflow_catalog.yaml#digital_twin_sync_loop` for step definitions
- See `reference/world_state_schema.yaml` for canonical state format
- See `reference/composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
- See `reference/composition_patterns.md#digital-twin-sync-loop` for gates, data flow and recovery
