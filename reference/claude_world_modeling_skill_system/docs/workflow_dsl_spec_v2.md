# Workflow DSL spec v2 (composition-safe)

This extends the workflow DSL with:
- `input_bindings`: explicit step inputs wired from previous outputs
- `condition`: conditional execution (skip if false)
- `parallel_group`: mark steps that can execute in parallel
- `join`: join strategy for parallel groups
- `recovery.goto_step`: loop-back semantics with max loops
- `gates`: explicit stop/pause rules per step

## Step schema (extended)

```yaml
- capability: <capability-id>
  purpose: string
  store_as: string

  # NEW
  input_bindings:
    <input_field>: "${previous_step_out.some_field}"

  condition: "${inspect_out.confidence} < 0.8"
  skip_if_false: true

  parallel_group: context_gathering
  join: all_complete | first_complete | quorum

  gates:
    - when: "${inspect_out.confidence} < 0.5"
      action: stop
      message: "Low confidence; request clarification."

  failure_modes:
    - condition: "Verdict == FAIL"
      action: rollback
      recovery:
        goto_step: critique
        inject_context:
          failure_evidence: "${verify_out.failures}"
        max_loops: 3
```

## Execution semantics (high-level)

- Evaluate `condition` before running step.
- If `skip_if_false=true`, skip step and write `store_as` as `{skipped:true}`.
- Steps with same `parallel_group` may run concurrently.
- `join` controls when to proceed.
- `input_bindings` defines step inputs explicitly.
- `gates` are checked after step completes. If triggered, halt/pause.
- `recovery.goto_step` restarts execution at named capability or step alias.


## Typed binding annotations
See `docs/typed_binding_annotations.md`.
