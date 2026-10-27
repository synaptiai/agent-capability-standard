# Tutorial: Build Your First Workflow

This tutorial walks you through creating a custom workflow from scratch. By the end, you'll understand how capabilities compose, how bindings work, and how safety mechanisms protect your workflows.

**Prerequisites:**
- Completed the [Quickstart Guide](QUICKSTART.md)
- Python 3.10+ with the package installed (`pip install -e ".[dev]" -c constraints.txt`, which needs Rust 1.86+)
- Basic YAML knowledge

---

## Part 1: Understanding the Building Blocks (10 min)

### 1.1 What is a Capability?

A capability is an atomic action an agent can perform. Each capability has:
- **Input schema**: What data it accepts
- **Output schema**: What data it produces
- **Prerequisites**: What must happen first

Let's look at a simple capability:

```json
{
  "id": "observe",
  "layer": "PERCEIVE",
  "description": "Observe and report on artifacts without modifying them",
  "input_schema": {
    "type": "object",
    "properties": {
      "target": { "type": "string" },
      "aspects": { "type": "array", "items": { "type": "string" } }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "findings": { "type": "array" },
      "metadata": { "type": "object" }
    }
  },
  "requires": [],
  "soft_requires": []
}
```

Key observations:
- `observe` is in the PERCEIVE layer (observation, no mutation)
- It takes a target and aspects to examine
- It outputs findings and metadata
- It has no prerequisites

### 1.2 What is a Workflow?

A workflow is a sequence of capability invocations. Each step:
- Invokes one capability
- Stores its output for later reference
- Can reference outputs from earlier steps

### 1.3 The Safety Contract

Some capabilities depend on others running first. The ontology's edges say how strictly:

| Capability | Needs first | Edge | If missing |
|------------|-------------|------|------------|
| `mutate`, `send`, `rollback` | `checkpoint` | `requires` | Error V102 — need a recovery point |
| `execute`, `mutate`, `send` | `constrain` | `soft_requires` | Warning W601 — act within stated limits |
| `ground` | one of `observe`, `detect`, `predict`, `attribute`, `explain` | `soft_requires` | Warning W601 — need something to ground |
| `verify` | `execute`, `mutate`, `send` (when present) | `precedes` | Error V102 if they appear in the wrong order |

A `precedes` edge only orders capabilities that are both in the workflow; a step in the same `parallel_group` does not count as running before another.

---

## Part 2: Create a Simple Workflow (10 min)

### Why Workflows Matter

**Without workflows:**
- Agent capabilities are invoked ad-hoc, with no guarantees about order
- Outputs from one step may not match inputs of the next
- Failures happen silently—no structured recovery

**With workflows:**
- Capabilities compose predictably through typed bindings
- Prerequisites are enforced automatically (e.g., `checkpoint` before `mutate`)
- Failures trigger documented recovery paths

The workflow DSL makes these guarantees structural, not aspirational.

---

Let's create a workflow that analyzes a file and reports findings.

### 2.1 Create the Workflow File

Create `examples/my_first_workflow.yaml`:

```yaml
# Standard version: 1.1.0
analyze_file:
  goal: Analyze a file and report findings with recommendations.
  risk: low

  steps:
    - capability: observe
      purpose: Examine the file structure and content.
      store_as: observe_out
      input_bindings:
        target: ${user_input.file_path}

    - capability: detect
      purpose: Find unusual patterns in the file.
      store_as: anomaly_out
      input_bindings:
        data: ${observe_out}
        pattern: anomaly

    - capability: explain
      purpose: Create a readable report of findings.
      store_as: summary_out
      input_bindings:
        conclusion: ${anomaly_out}

  success:
    - File analyzed
    - Anomalies detected if present
    - Summary produced

  inputs:
    user_input:
      type: object
      properties:
        file_path:
          type: string
```

### 2.2 Understand the Structure

| Field | Purpose |
|-------|---------|
| `goal` | What this workflow achieves (required) |
| `risk` | How dangerous is this? (low = read-only) (required) |
| `steps` | Ordered list of capability invocations (required) |
| `success` | How to know it worked (optional) |
| `inputs` | What external data is needed (optional) |

The `# Standard version: 1.1.0` header declares which version of the standard the file follows; a per-workflow `spec_version: "1.1"` field does the same. Without either, the validator warns (W605).

### 2.3 Understand Bindings

```yaml
input_bindings:
  data: ${observe_out}
```

This tells `detect` to analyse the output of `observe` (its `data` input). The validator checks:
1. `data` is one of `detect`'s inputs in the ontology (else W604)
2. `observe_out` exists (from a prior step)
3. The type is compatible with what `detect` expects

### 2.4 Validate Your Workflow

```bash
python tools/validate_workflows.py --catalog examples/my_first_workflow.yaml
```

Expected output:
```
VALIDATION PASS
```

If you get errors, check:
- Capability names are spelled correctly
- `store_as` is unique for each step
- Bindings reference existing `store_as` values

---

## Part 3: Add Safety Mechanisms (10 min)

### Why Checkpoints Matter

**Without checkpoints:**
- Workflow fails at step 7 of 10
- Steps 1-6 already modified state (files, databases, APIs)
- Manual cleanup required—error-prone and time-consuming
- Users see inconsistent data during recovery

**With checkpoints:**
- Workflow fails at step 7
- Automatic rollback to last checkpoint
- State is consistent within seconds
- Users never see partial updates

**When to use checkpoints:**

| Scenario | Recommendation |
|----------|----------------|
| Read-only workflow | Skip checkpoints (no mutations to recover from) |
| Single mutation at end | Checkpoint immediately before the mutation |
| Multiple sequential mutations | Checkpoint before each mutation |
| Idempotent operations | Optional—can safely retry without rollback |
| High-value data modifications | Checkpoint + verify + audit for full protection |

The cost of a checkpoint (saving state) is almost always less than the cost of manual recovery from a failed mutation.

---

Now let's create a workflow that modifies files. This requires safety mechanisms.

### 3.1 Create a Modification Workflow

Create `examples/fix_and_verify.yaml`:

```yaml
# Standard version: 1.1.0
fix_and_verify:
  goal: Fix a detected issue and verify the fix worked.
  risk: high

  steps:
    # 1. Understand the problem
    - capability: observe
      purpose: Examine current state.
      store_as: observe_out
      input_bindings:
        target: ${user_input.target}

    - capability: detect
      purpose: Identify the issue.
      store_as: anomaly_out
      input_bindings:
        data: ${observe_out}
        pattern: defect

    # 2. Plan the fix
    - capability: plan
      purpose: Create a fix plan.
      store_as: plan_out
      input_bindings:
        goal: Fix the defect found in ${user_input.target}
        context: ${anomaly_out}

    # 3. Define what success looks like
    - capability: constrain
      purpose: Define invariants the fix must satisfy.
      store_as: schema_out
      input_bindings:
        target: "${plan_out.steps: array<object>}"
        constraints: [tests_pass, public_interfaces_unchanged]

    # 4. Save state before mutation (REQUIRED)
    - capability: checkpoint
      purpose: Save state for potential rollback.
      store_as: checkpoint_out
      mutation: true
      input_bindings:
        scope: ${user_input.target}

    # 5. Execute the fix (REQUIRES checkpoint)
    - capability: mutate
      purpose: Apply the fix.
      store_as: action_out
      mutation: true
      requires_checkpoint: true
      input_bindings:
        target: ${user_input.target}
        operation:
          apply: "${plan_out.steps: array<object>}"
      gates:
        - when: ${checkpoint_out.checkpoint_id} == null
          action: stop
          message: "Cannot proceed without checkpoint"

    # 6. Verify the fix worked (must come after mutate)
    - capability: verify
      purpose: Check that fix satisfies invariants.
      store_as: verify_out
      input_bindings:
        target: ${user_input.target}
        conditions: [tests_pass, public_interfaces_unchanged, defect_absent]
      failure_modes:
        - condition: The fix does not satisfy the invariants.
          when: ${verify_out.passed} == false
          action: rollback
          recovery:
            goto_step: plan_out
            max_loops: 3

    # 7. Record what happened
    - capability: audit
      purpose: Log the change for accountability.
      store_as: audit_out
      input_bindings:
        event:
          type: fix_applied
          target: ${user_input.target}
          verified: ${verify_out.passed}

  success:
    - Issue fixed
    - Verification passed
    - Audit trail created

  inputs:
    user_input:
      type: object
      properties:
        target:
          type: string
```

### 3.2 Key Safety Elements

**Checkpoint before mutation:**
```yaml
- capability: checkpoint
  purpose: Save state for potential rollback.
  store_as: checkpoint_out
  mutation: true
  input_bindings:
    scope: src/parser.py
```

**Gate that blocks without checkpoint:**
```yaml
gates:
  - when: ${checkpoint_out.checkpoint_id} == null
    action: stop
    message: "Cannot proceed without checkpoint"
```

**Recovery on failure:**
```yaml
failure_modes:
  - condition: The fix does not satisfy the invariants.
    when: ${verify_out.passed} == false   # fires after verify, on its output
    action: rollback
    recovery:
      goto_step: plan_out                 # loop back to the plan step
      max_loops: 3
```

### 3.3 Validate the Safety Workflow

```bash
python tools/validate_workflows.py --catalog examples/fix_and_verify.yaml
```

The validator ensures:
- `checkpoint` comes before `mutate` (error V102 otherwise)
- `verify` comes after `mutate` (error V102 otherwise)
- `constrain` comes before `mutate` (warning W601 otherwise)
- All bindings are valid

Add `--strict` to make warnings fail the run too.

---

## Part 4: Advanced Patterns (10 min)

### Why Typed Bindings Matter

**Without typed bindings:**
- Step A produces `{items: [...]}`, Step B expects `items` to be strings
- Error surfaces at runtime: "Expected string, got object"
- Debugging requires tracing data through multiple steps

**With typed bindings:**
- Validator catches: "B203: TYPE_MISMATCH at step 5, binding 'items'"
- Error message suggests: "Expected array<string>, got array<object>. Consider projecting a field."
- Fix applied before any code runs

Typed bindings shift debugging from runtime (production) to validation (development). The few seconds spent adding type annotations save hours of runtime debugging.

---

### 4.1 Parallel Execution

Some steps can run concurrently:

```yaml
steps:
  - capability: search
    purpose: Search logs
    store_as: log_search
    parallel_group: gather_context
    input_bindings:
      query: ${user_input.error_message}
      scope: logs

  - capability: search
    purpose: Search code
    store_as: code_search
    parallel_group: gather_context
    join: all_complete
    input_bindings:
      query: ${user_input.error_message}
      scope: src

  - capability: integrate
    purpose: Combine search results
    store_as: integrated
    input_bindings:
      sources:
        - ${log_search}
        - ${code_search}
```

### 4.2 Conditional Execution

Skip steps based on conditions:

```yaml
- capability: mutate
  purpose: Apply fix only if approved.
  store_as: action_out
  condition: ${approval_out.approved} == true
  skip_if_false: true
  input_bindings:
    target: ${user_input.target}
    operation:
      apply: "${plan_out.steps: array<object>}"
```

### 4.3 Typed Bindings

When types are ambiguous, add annotations. Quote typed references: unquoted, the `: ` inside them stops the file loading when the reference is a mapping value, and makes YAML read a list item as a mapping (W612):

```yaml
input_bindings:
  observations: "${integrate_out.merged.observations: array<object>}"
  domain: "${integrate_out.merged.meta.world_id: string}"
```

### 4.4 Transform Mappings

Reference external transform definitions:

```yaml
- capability: transform
  purpose: Normalize data format.
  store_as: transform_out
  input_bindings:
    input: ${retrieve_out.data}
    target_format: event
  mapping_ref: schemas/transforms/my_transform.yaml
  output_conforms_to: schemas/event_schema.yaml#/event
```

---

## Part 5: Debug Common Issues

### 5.1 Unknown Capability (V101)

**Error:**
```
[my_workflow] step 1 (detect-anamoly): V101 capability 'detect-anamoly' not found in ontology
```

**Fix:** Check spelling. It's `detect`, not `detect-anamoly`.

### 5.2 Missing Prerequisite (V102)

**Error:**
```
[my_workflow] step 3 (mutate): V102 capability 'mutate' missing required prerequisite 'checkpoint' before it
```

**Fix:** Add a `checkpoint` step before `mutate`.

### 5.3 Unknown Store Reference (B202)

**Error:**
```
[my_workflow] step 2 (explain): B202 unknown reference store 'insepct_out' in ${insepct_out.findings}
```

**Fix:** Check the `store_as` name. It's `observe_out`, not `insepct_out`. (If the store exists but the path after it is not in the producer's output schema, the error is B201 INVALID_BINDING_PATH.)

### 5.4 Ambiguous Type (B204)

**Error:**
```
[my_workflow] step 1 (compare): B204 ambiguous type for ${data.items}: inferred array<unknown> is ambiguous or unknown; add a typed annotation
```

**Fix:** Add a (quoted) type annotation:
```yaml
input_bindings:
  items: "${data.items: array<object>}"
```

---

## Part 6: Best Practices

### 6.1 Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Workflow | snake_case | `debug_code_change` |
| Step store_as | snake_case with _out | `observe_out` |
| Capability | kebab-case | `detect` |

### 6.2 Safety Checklist

Before any mutation:
- [ ] Add `checkpoint` step
- [ ] Leave safety flags (`mutation`, `requires_checkpoint`, ...) to the ontology — steps inherit them, and a weaker step value is ignored with warning W602
- [ ] Add gate to verify checkpoint exists
- [ ] Add `verify` step after mutation
- [ ] Add `failure_modes` with recovery

### 6.3 Documentation

Every step should have:
- [ ] Clear `purpose` explaining why it exists
- [ ] Meaningful `store_as` name
- [ ] Comments for complex logic

---

## What's Next?

| Goal | Resource |
|------|----------|
| Understand all 36 capabilities | [Capability Ontology](../schemas/capability_ontology.yaml) |
| See production workflows | [Workflow Catalog](../schemas/workflow_catalog.yaml) |
| Work with images, audio, and video | [Modality Handling Guide](guides/MODALITY_HANDLING.md) |
| Read the full spec | [STANDARD-v1.1.0.md](../spec/STANDARD-v1.1.0.md) |
| Understand error codes | [STANDARD Section 9](../spec/STANDARD-v1.1.0.md#9-diagnostic-model) |

---

## Exercises

### Exercise 1: Add Error Handling
Modify `analyze_file` to include a failure mode that requests more context if no anomalies are found.

### Exercise 2: Add Parallel Steps
Create a workflow that searches three different sources in parallel, then integrates the results.

### Exercise 3: Create a Safe Update Workflow
Build a workflow that:
1. Inspects a configuration file
2. Plans changes
3. Checkpoints
4. Applies changes
5. Verifies the configuration still works
6. Rolls back if verification fails

---

**Time to complete:** ~30 minutes
