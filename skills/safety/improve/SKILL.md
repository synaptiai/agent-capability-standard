---
name: improve
description: Iteratively refine an artifact using feedback loops and verification gates. Use when enhancing code quality, optimizing performance, or incrementally improving outputs through multiple iterations.
argument-hint: "[artifact] [improvement_goal] [max_iterations] [verification_spec]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit, Bash, Grep
context: fork
agent: general-purpose
---

## Intent

Execute **improve** to iteratively enhance an artifact through a controlled loop of modification, verification, and refinement. Each iteration applies targeted improvements while maintaining safety through checkpoints and verification gates.

**Success criteria:**
- Measurable improvement toward stated goal
- All iterations verified against specification
- Checkpoint before each modification cycle
- Clear stopping criteria met (goal achieved or max iterations)

**Compatible schemas:**
- `docs/schemas/improvement_result.yaml`
- `docs/schemas/iteration_log.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `artifact` | Yes | string | Path to artifact being improved (file, directory) |
| `improvement_goal` | Yes | string\|object | What to improve: performance, quality, coverage, readability |
| `max_iterations` | No | integer | Maximum improvement cycles (default: 5) |
| `verification_spec` | No | string\|object | How to verify improvement (tests, benchmarks, lint) |
| `stopping_criteria` | No | object | When to stop: threshold reached, no improvement, max_iterations |
| `constraints` | No | object | What to preserve while improving (API compatibility, behavior) |

## Procedure

1) **Establish baseline**: Measure current state of artifact
   - Run verification_spec to get baseline metrics
   - Document current quality/performance/coverage
   - Identify specific areas for improvement
   - Record baseline for comparison

2) **Plan iteration**: Determine focused improvement for this cycle
   - Analyze gap between current state and goal
   - Identify highest-impact improvement opportunity
   - Plan minimal change to address one issue
   - Verify change respects constraints

3) **Create checkpoint**: Safety gate before modification
   - Call `checkpoint` for files in scope
   - Record pre-modification state hash
   - Ensure rollback path is available

4) **Apply improvement**: Make targeted modification
   - Execute the planned change via Edit
   - Keep changes minimal and focused
   - Document what was changed and why

5) **Verify improvement**: Confirm change is beneficial
   - Run verification_spec again
   - Compare metrics to previous iteration
   - Check constraints are still satisfied
   - If regression: rollback and try different approach

6) **Evaluate stopping criteria**: Decide whether to continue
   - Goal achieved? Stop with success
   - No improvement? Stop, return best state
   - Max iterations reached? Stop, document progress
   - Otherwise: continue to next iteration

7) **Ground claims**: Document improvement evidence
   - Format: metrics comparison, test results, benchmark output
   - Include iteration-by-iteration progress

## Output Contract

Return a structured object:

```yaml
improved: boolean  # Was artifact improved?
artifact: string  # Path to improved artifact
improvement_summary:
  initial_metrics: object  # Baseline measurements
  final_metrics: object  # Final measurements
  improvement_percentage: number  # Overall improvement
  goal_achieved: boolean  # Did we reach the target?
iterations:
  - iteration: integer
    action: string  # What was done
    metrics_before: object
    metrics_after: object
    improvement: number  # Delta this iteration
    checkpoint_id: string
    status: improved | no_change | regression | rolled_back
total_iterations: integer
stopping_reason: goal_achieved | no_improvement | max_iterations | constraint_violation
changes_made:
  - file: string
    summary: string
    lines_changed: integer
verification:
  spec_used: string
  final_result: PASS | FAIL
rollbacks_performed: integer  # How many regressions were reverted
confidence: number  # 0.0-1.0
evidence_anchors: ["tool:bash:...", "file:..."]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `improved` | boolean | Whether artifact was improved overall |
| `improvement_summary` | object | Before/after metrics comparison |
| `iterations` | array | Log of each improvement attempt |
| `stopping_reason` | enum | Why improvement loop terminated |
| `changes_made` | array | Files modified with summaries |
| `verification` | object | Final verification result |
| `rollbacks_performed` | integer | Number of reverted regressions |
| `confidence` | number | 0.0-1.0 based on verification results |
| `evidence_anchors` | array | Proof of improvements |
| `assumptions` | array | What was assumed during improvement |

## Examples

### Example 1: Improve Test Coverage

**Input:**
```yaml
artifact: "src/api/handlers/"
improvement_goal:
  metric: "test_coverage"
  target: 80
  current: 62
verification_spec: "pytest --cov=src/api/handlers --cov-report=term-missing"
max_iterations: 5
constraints:
  preserve_behavior: true
  no_mocking_core_logic: true
```

**Output:**
```yaml
improved: true
artifact: "src/api/handlers/"
improvement_summary:
  initial_metrics:
    coverage_percentage: 62
    uncovered_lines: 156
    untested_functions: 8
  final_metrics:
    coverage_percentage: 83
    uncovered_lines: 71
    untested_functions: 2
  improvement_percentage: 33.9
  goal_achieved: true
iterations:
  - iteration: 1
    action: "Added tests for user.py:get_user_by_id"
    metrics_before: { coverage_percentage: 62 }
    metrics_after: { coverage_percentage: 68 }
    improvement: 6
    checkpoint_id: "chk_improve_iter1"
    status: improved
  - iteration: 2
    action: "Added tests for auth.py:validate_token edge cases"
    metrics_before: { coverage_percentage: 68 }
    metrics_after: { coverage_percentage: 75 }
    improvement: 7
    checkpoint_id: "chk_improve_iter2"
    status: improved
  - iteration: 3
    action: "Added tests for error handling paths"
    metrics_before: { coverage_percentage: 75 }
    metrics_after: { coverage_percentage: 83 }
    improvement: 8
    checkpoint_id: "chk_improve_iter3"
    status: improved
total_iterations: 3
stopping_reason: goal_achieved
changes_made:
  - file: "tests/test_handlers.py"
    summary: "Added 12 new test cases"
    lines_changed: 245
verification:
  spec_used: "pytest --cov=src/api/handlers"
  final_result: PASS
rollbacks_performed: 0
confidence: 0.95
evidence_anchors:
  - "tool:bash:pytest --cov - Coverage: 83%"
  - "tests/test_handlers.py:45"
  - "tests/test_handlers.py:89"
assumptions:
  - "Coverage tool accurately measures executed lines"
  - "New tests don't introduce flaky behavior"
```

**Evidence pattern:** Coverage reports from each iteration, test file changes.

---

### Example 2: Improve Performance with Regression Rollback

**Input:**
```yaml
artifact: "src/data/processor.py"
improvement_goal:
  metric: "processing_time_ms"
  target: 50
  current: 120
  direction: "lower_is_better"
verification_spec: "python benchmarks/bench_processor.py"
max_iterations: 4
stopping_criteria:
  min_improvement_per_iteration: 5
```

**Output:**
```yaml
improved: true
artifact: "src/data/processor.py"
improvement_summary:
  initial_metrics:
    processing_time_ms: 120
    memory_mb: 45
  final_metrics:
    processing_time_ms: 65
    memory_mb: 48
  improvement_percentage: 45.8
  goal_achieved: false
iterations:
  - iteration: 1
    action: "Replaced list comprehension with generator"
    metrics_before: { processing_time_ms: 120 }
    metrics_after: { processing_time_ms: 95 }
    improvement: 25
    checkpoint_id: "chk_perf_iter1"
    status: improved
  - iteration: 2
    action: "Added caching for repeated lookups"
    metrics_before: { processing_time_ms: 95 }
    metrics_after: { processing_time_ms: 145 }
    improvement: -50
    checkpoint_id: "chk_perf_iter2"
    status: rolled_back
  - iteration: 3
    action: "Optimized string concatenation"
    metrics_before: { processing_time_ms: 95 }
    metrics_after: { processing_time_ms: 65 }
    improvement: 30
    checkpoint_id: "chk_perf_iter3"
    status: improved
  - iteration: 4
    action: "Attempted batch processing"
    metrics_before: { processing_time_ms: 65 }
    metrics_after: { processing_time_ms: 62 }
    improvement: 3
    checkpoint_id: "chk_perf_iter4"
    status: no_change  # Below min_improvement threshold
total_iterations: 4
stopping_reason: no_improvement
changes_made:
  - file: "src/data/processor.py"
    summary: "Generator optimization and string handling"
    lines_changed: 28
verification:
  spec_used: "python benchmarks/bench_processor.py"
  final_result: PASS
rollbacks_performed: 1
confidence: 0.9
evidence_anchors:
  - "tool:bash:bench - 65ms average"
  - "src/data/processor.py:34"
  - "tool:bash:rollback iter2 - cache regression"
assumptions:
  - "Benchmark is representative of production load"
  - "Memory increase is acceptable tradeoff"
```

## Verification

Apply the following verification patterns:

- [ ] **State Assertion**: Each iteration has valid checkpoint before modification
- [ ] **Rollback Verification**: Regressions were properly reverted
- [ ] **Evidence Grounding**: All metrics linked to verification output
- [ ] **Contract Validation**: Final output matches improvement schema

**Verification tools:** Bash (for benchmarks/tests), Read (for code review)

## Safety Constraints

- `mutation`: true (modifies artifact through iterations)
- `requires_checkpoint`: true (CRITICAL: checkpoint before each iteration)
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- CRITICAL: Create checkpoint before every modification iteration
- CRITICAL: Rollback immediately on regression detection
- Never exceed max_iterations without explicit override
- Preserve constraints (API, behavior) across all iterations
- Stop if no improvement for 2 consecutive iterations
- Always run verification after each change

## Composition Patterns

**Commonly follows:**
- `critique` - Identify improvement opportunities before starting
- `plan` - Plan the improvement strategy
- `checkpoint` - Initial checkpoint before improvement loop

**Commonly precedes:**
- `verify` - Final verification of improved artifact
- `audit` - Record all changes made during improvement
- `summarize` - Summarize improvement results

**Internal composition (per iteration):**
```
checkpoint -> edit -> verify -> (improved: continue | regression: rollback)
```

**Anti-patterns:**
- CRITICAL: Never skip checkpoint before modification
- Never continue after regression without rollback
- Never exceed max_iterations silently
- Never make multiple unrelated changes per iteration

**Workflow references:**
- See `composition_patterns.md#debug-code-change` for improve in fix flow
- See `composition_patterns.md#checkpoint-act-verify-rollback` for iteration pattern
