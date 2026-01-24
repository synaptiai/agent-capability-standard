---
name: invoke-workflow
description: Invoke another workflow by ID with input bindings and capture outputs. Use when composing workflows, bootstrapping complex operations, or orchestrating multi-step processes.
argument-hint: "[workflow_id] [inputs] [timeout]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read
context: fork
agent: explore
---

## Intent

Execute **invoke-workflow** to call another workflow by its identifier, passing inputs and capturing outputs for workflow composition.

**Success criteria:**
- Target workflow is located and validated
- Input bindings are correctly mapped to workflow parameters
- Workflow execution status is tracked (running, completed, failed, paused)
- Outputs are captured and available for downstream use
- Failures are logged with recovery suggestions

**Compatible schemas:**
- `docs/schemas/workflow_catalog.json`
- `docs/schemas/workflow_invocation.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `workflow_id` | Yes | string | Identifier of workflow to invoke (e.g., "world_model_build", "debug_code_change") |
| `inputs` | Yes | object | Input bindings to pass to the workflow (key-value pairs matching workflow input schema) |
| `timeout` | No | string | Maximum execution time (e.g., "5m", "1h"). Default: workflow-specific or "30m" |
| `on_failure` | No | enum | Failure handling: `abort`, `retry`, `continue`, `fallback`. Default: `abort` |
| `context_passthrough` | No | array[string] | List of context keys to pass through to child workflow |

## Procedure

1) **Locate workflow definition**: Find workflow in catalog
   - Search workflow_catalog.json for workflow_id
   - Validate workflow exists and is enabled
   - Extract input/output schema requirements

2) **Validate inputs**: Check inputs match workflow schema
   - Map provided inputs to workflow parameters
   - Identify missing required inputs
   - Apply default values where specified
   - Type-check all input values

3) **Check preconditions**: Verify workflow can execute
   - Check any `gate` conditions from workflow definition
   - Verify required context is available
   - Confirm no blocking dependencies

4) **Execute workflow**: Invoke the target workflow
   - Pass validated inputs
   - Start execution tracking
   - Monitor for status changes

5) **Capture step outputs**: Record outputs from each workflow step
   - Map step outputs to `store_as` keys
   - Validate output types match schema
   - Accumulate results for final output

6) **Handle completion/failure**:
   - On success: Return final_result and all step outputs
   - On failure: Log error, attempt recovery per on_failure setting
   - On pause: Record current_step and resumption context

7) **Ground claims**: Attach evidence to execution record
   - Format: `workflow:<workflow_id>:<step_id>` for each executed step
   - Include timing information

## Output Contract

Return a structured object:

```yaml
workflow_invocation:
  workflow_id: string  # ID of invoked workflow
  inputs: object  # Inputs passed to workflow
  status: running | completed | failed | paused
  current_step: string | null  # Current/last step ID if paused or failed
  started_at: string  # ISO timestamp
  completed_at: string | null  # ISO timestamp if completed
  duration_ms: integer | null  # Execution time
outputs:
  - step_id: string  # Workflow step that produced output
    store_as: string  # Key name for this output
    result: object  # Actual output value
final_result: object | null  # Final workflow output if completed
failures:
  - step_id: string  # Step that failed
    error: string  # Error message
    error_type: string  # Error classification
    recovery_action: string | null  # Suggested or taken recovery action
    recoverable: boolean  # Whether retry might succeed
retry_info:
  attempts: integer  # Number of retry attempts
  last_attempt_at: string | null  # Timestamp of last retry
  next_retry_at: string | null  # Scheduled retry if applicable
confidence: number  # 0.0-1.0 based on execution success
evidence_anchors: array[string]  # Step execution references
assumptions: array[string]  # Explicit assumptions about workflow behavior
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_invocation.workflow_id` | string | The invoked workflow identifier |
| `workflow_invocation.status` | enum | Current execution status |
| `outputs` | array[object] | Captured outputs from workflow steps |
| `final_result` | object | Terminal output of completed workflow |
| `failures` | array[object] | Error details if workflow failed |
| `confidence` | number | 1.0 if completed successfully; lower for failures |

## Examples

### Example 1: Successful Workflow Invocation

**Input:**
```yaml
workflow_id: "world_model_build"
inputs:
  domain: "supply_chain"
  sources:
    - "inventory_db"
    - "shipping_logs"
  output_format: "yaml"
timeout: "10m"
```

**Output:**
```yaml
workflow_invocation:
  workflow_id: "world_model_build"
  inputs:
    domain: "supply_chain"
    sources: ["inventory_db", "shipping_logs"]
    output_format: "yaml"
  status: completed
  current_step: null
  started_at: "2024-01-16T10:00:00Z"
  completed_at: "2024-01-16T10:07:32Z"
  duration_ms: 452000
outputs:
  - step_id: "retrieve"
    store_as: "retrieve_out"
    result:
      retrieved_count: 1247
      sources: ["inventory_db", "shipping_logs"]
  - step_id: "world-state"
    store_as: "world_state_out"
    result:
      entities: 156
      relationships: 423
  - step_id: "summarize"
    store_as: "summarize_out"
    result:
      summary: "Supply chain model with 156 entities..."
final_result:
  world_model:
    domain: "supply_chain"
    entities: 156
    relationships: 423
    confidence: 0.87
  format: "yaml"
  location: "models/supply_chain_2024-01-16.yaml"
failures: []
retry_info:
  attempts: 0
  last_attempt_at: null
  next_retry_at: null
confidence: 1.0
evidence_anchors:
  - "workflow:world_model_build:retrieve"
  - "workflow:world_model_build:inspect"
  - "workflow:world_model_build:identity-resolution"
  - "workflow:world_model_build:world-state"
  - "workflow:world_model_build:summarize"
assumptions:
  - "Source databases are accessible and up-to-date"
  - "Workflow definition has not changed since invocation"
```

**Evidence pattern:** Each workflow step generates an evidence anchor; outputs captured at each step with timing.

---

### Example 2: Failed Workflow with Recovery

**Input:**
```yaml
workflow_id: "digital_twin_sync_loop"
inputs:
  twin_id: "factory_floor_1"
  signals: ["sensor_batch_2024-01-16"]
on_failure: retry
timeout: "5m"
```

**Output:**
```yaml
workflow_invocation:
  workflow_id: "digital_twin_sync_loop"
  inputs:
    twin_id: "factory_floor_1"
    signals: ["sensor_batch_2024-01-16"]
  status: failed
  current_step: "transform"
  started_at: "2024-01-16T11:00:00Z"
  completed_at: "2024-01-16T11:02:15Z"
  duration_ms: 135000
outputs:
  - step_id: "receive"
    store_as: "receive_out"
    result:
      events_ingested: 5420
failures:
  - step_id: "transform"
    error: "Schema validation failed: missing required field 'sensor_type'"
    error_type: "validation_error"
    recovery_action: "Retry with schema-lenient mode"
    recoverable: true
final_result: null
retry_info:
  attempts: 2
  last_attempt_at: "2024-01-16T11:02:15Z"
  next_retry_at: null
confidence: 0.2
evidence_anchors:
  - "workflow:digital_twin_sync_loop:receive"
  - "workflow:digital_twin_sync_loop:transform:FAILED"
assumptions:
  - "Sensor data format may have changed"
  - "Transform step requires schema update"
next_actions:
  - "Review sensor data schema for changes"
  - "Update transform mapping for new format"
  - "Retry with corrected schema"
```

---

### Example 3: Workflow Composition (Bootstrap)

**Input:**
```yaml
workflow_id: "digital_twin_bootstrap"
inputs:
  domain: "manufacturing"
  initial_sources: ["equipment_registry", "process_specs"]
context_passthrough: ["user_session", "audit_context"]
```

**Output:**
```yaml
workflow_invocation:
  workflow_id: "digital_twin_bootstrap"
  inputs:
    domain: "manufacturing"
    initial_sources: ["equipment_registry", "process_specs"]
  status: completed
  current_step: null
  started_at: "2024-01-16T12:00:00Z"
  completed_at: "2024-01-16T12:25:00Z"
  duration_ms: 1500000
outputs:
  - step_id: "invoke-workflow:world_model_build"
    store_as: "world_model_out"
    result:
      world_model: { entities: 89, relationships: 234 }
  - step_id: "invoke-workflow:digital_twin_sync_loop"
    store_as: "sync_out"
    result:
      synchronized: true
      entities_affected: 89
final_result:
  twin_id: "manufacturing_twin_001"
  baseline_model: "world_model_out"
  initial_sync: "sync_out"
  ready: true
failures: []
confidence: 0.95
evidence_anchors:
  - "workflow:digital_twin_bootstrap:invoke-workflow:world_model_build"
  - "workflow:digital_twin_bootstrap:invoke-workflow:digital_twin_sync_loop"
assumptions:
  - "Child workflows use same context as parent"
  - "World model build completes before sync loop starts"
```

## Verification

- [ ] workflow_id exists in workflow_catalog.json
- [ ] All required inputs provided and type-valid
- [ ] status accurately reflects execution state
- [ ] outputs contains entry for each completed step
- [ ] failures logged with actionable recovery suggestions

**Verification tools:** Read (to access workflow catalog and definitions)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- Do not invoke workflows that require higher permissions than current context
- Respect workflow-level gates and conditions; do not bypass
- Stop if child workflow requests human approval; surface to parent
- Log all workflow invocations for audit trail
- Do not pass sensitive credentials through context_passthrough

## Composition Patterns

**Commonly follows:**
- `plan` - Generates workflow to execute
- `decide` - Selects which workflow to invoke based on conditions
- `constrain` - Applies policy checks before workflow execution

**Commonly precedes:**
- `audit` - Records workflow execution for compliance (soft_requires in ontology)
- `synchronize` - Merges outputs from multiple workflow invocations
- `verify` - Validates workflow outputs meet expectations

**Anti-patterns:**
- Never invoke workflow without validating inputs against schema
- Never invoke high-risk workflows without prior checkpoint in parent
- Avoid recursive workflow invocation without depth limits

**Workflow references:**
- See `composition_patterns.md#digital-twin-bootstrap` for nested workflow invocation
- See `workflow_catalog.json` for available workflow definitions
- Enables `digital-twin-sync-workflow` per ontology edge
