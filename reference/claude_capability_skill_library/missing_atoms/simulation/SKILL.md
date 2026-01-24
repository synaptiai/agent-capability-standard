---
name: simulation
description: Run or describe simulations and scenarios to stress-test world models, explore what-if questions, and validate assumptions. Use when testing hypotheses, planning interventions, or understanding system behavior under different conditions.
argument-hint: "[model] [scenarios] [parameters] [time_steps]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash
context: fork
agent: general-purpose
---

## Intent

Execute **simulations** on world models to explore dynamics, test hypotheses, and understand system behavior. This capability runs state machines forward, evaluates causal interventions, and stress-tests assumptions.

**Success criteria:**
- Simulation faithfully executes model rules
- Results include trajectories over time
- Sensitivity to parameters is analyzed
- Edge cases and failure modes are explored
- Results are reproducible (seeded randomness)

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

**Soft dependencies:**
- Benefits from `causal-model` - Intervention simulation
- Benefits from `state-transition` - State machine execution

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `model` | Yes | object | World model to simulate (world-state + transitions + causal) |
| `scenarios` | Yes | array | Scenarios to run (baseline, interventions, edge cases) |
| `parameters` | No | object | Override model parameters for sensitivity analysis |
| `time_steps` | No | integer | Number of simulation steps (default: 100) |
| `seed` | No | integer | Random seed for reproducibility |
| `output_variables` | No | array | Variables to track (default: all) |

## Procedure

1) **Validate model**: Check that model is simulatable
   - World-state has initial conditions defined
   - State transitions have computable guards and actions
   - Causal model (if present) has specified mechanisms
   - No missing required parameters

2) **Configure scenarios**: Set up each scenario to run
   - **Baseline**: Run with default parameters
   - **Intervention**: Apply do(X=x) operations to causal model
   - **Stress test**: Push parameters to extremes
   - **Monte Carlo**: Run with sampled uncertainty

3) **Initialize simulation**: Set starting state
   - Load initial world-state
   - Set random seed for reproducibility
   - Initialize tracking variables
   - Set simulation clock to t=0

4) **Execute simulation loop**: For each time step
   - Evaluate transition guards (which transitions are enabled)
   - Select transitions to fire (deterministic or probabilistic)
   - Execute transition actions (update state variables)
   - Apply causal mechanisms (propagate effects)
   - Record state snapshot for trajectory
   - Check termination conditions

5) **Collect results**: For each scenario
   - **Trajectories**: Time series of tracked variables
   - **Final state**: End state of simulation
   - **Events**: Significant state changes that occurred
   - **Metrics**: Aggregate measures (time to goal, resource usage)

6) **Analyze sensitivity**: Compare across scenarios
   - Parameter sensitivity: Which inputs most affect outputs?
   - Bifurcations: Do small changes cause large outcome differences?
   - Stability: Does system return to equilibrium after perturbation?

7) **Validate results**: Check simulation quality
   - Conservation laws respected
   - No impossible states reached
   - Results consistent with known behaviors
   - Numerical stability (no explosions)

8) **Ground findings**: Link results to model assumptions
   - Which assumptions most affect results
   - Where uncertainty is highest
   - What additional data would improve predictions

## Output Contract

Return a structured object:

```yaml
simulation:
  id: string  # Simulation run ID
  model_ref: string  # Reference to source model
  parameters: object  # Parameters used
  time_steps: integer
  seed: integer | null
results:
  scenarios:
    - id: string  # Scenario ID
      type: baseline | intervention | stress_test | monte_carlo
      description: string
      parameters: object  # Scenario-specific overrides
      trajectory:
        - t: integer  # Time step
          state: object  # State snapshot
          events: array[string]  # Events at this step
      final_state: object
      metrics:
        - name: string
          value: number | string
          unit: string | null
      outcome: string  # Summary of what happened
  comparison:
    baseline_scenario: string
    differences:
      - scenario: string
        variable: string
        baseline_value: number | string
        scenario_value: number | string
        percent_change: number | null
sensitivity:
  - parameter: string
    impact: low | medium | high
    direction: positive | negative | non_monotonic
    threshold: number | null  # Value where behavior changes
validation:
  calibrated: boolean
  validation_data: string | null
  anomalies: array[string]  # Unexpected behaviors observed
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `results.scenarios` | array | Results for each simulated scenario |
| `trajectory` | array | Time series of state snapshots |
| `metrics` | array | Aggregate outcome measures |
| `sensitivity` | array | Parameter sensitivity analysis |
| `validation` | object | Simulation quality checks |

## Examples

### Example 1: Service Scaling Simulation

**Input:**
```yaml
model:
  world_state_ref: "ws_k8s_cluster"
  transitions_ref: "tr_autoscaler"
scenarios:
  - id: "baseline"
    type: baseline
    description: "Normal traffic pattern"
  - id: "traffic_spike"
    type: stress_test
    description: "10x traffic spike"
    parameters:
      traffic_multiplier: 10
  - id: "slow_scale"
    type: intervention
    description: "What if scaling is slower?"
    parameters:
      scale_up_delay: 300  # 5 minutes instead of 1
time_steps: 60  # 60 minutes
```

**Output:**
```yaml
simulation:
  id: "sim_scaling_20250124"
  model_ref: "ws_k8s_cluster + tr_autoscaler"
  parameters:
    initial_replicas: 3
    max_replicas: 20
    target_cpu: 0.7
    scale_up_delay: 60
  time_steps: 60
  seed: 42
results:
  scenarios:
    - id: "baseline"
      type: baseline
      description: "Normal traffic pattern"
      parameters: {}
      trajectory:
        - t: 0
          state: { replicas: 3, cpu_util: 0.4, requests_queued: 0 }
          events: []
        - t: 15
          state: { replicas: 3, cpu_util: 0.65, requests_queued: 0 }
          events: []
        - t: 30
          state: { replicas: 3, cpu_util: 0.5, requests_queued: 0 }
          events: []
      final_state: { replicas: 3, cpu_util: 0.45, requests_queued: 0 }
      metrics:
        - name: "max_cpu_utilization"
          value: 0.68
          unit: "ratio"
        - name: "max_queue_depth"
          value: 0
          unit: "requests"
        - name: "scaling_events"
          value: 0
      outcome: "System handled normal load without scaling"
    - id: "traffic_spike"
      type: stress_test
      description: "10x traffic spike"
      parameters: { traffic_multiplier: 10 }
      trajectory:
        - t: 0
          state: { replicas: 3, cpu_util: 0.4, requests_queued: 0 }
        - t: 5
          state: { replicas: 3, cpu_util: 0.95, requests_queued: 150 }
          events: ["scale_up_triggered"]
        - t: 6
          state: { replicas: 6, cpu_util: 0.85, requests_queued: 200 }
          events: ["replicas_added: 3"]
        - t: 10
          state: { replicas: 12, cpu_util: 0.75, requests_queued: 50 }
        - t: 15
          state: { replicas: 15, cpu_util: 0.70, requests_queued: 0 }
      final_state: { replicas: 8, cpu_util: 0.55, requests_queued: 0 }
      metrics:
        - name: "max_cpu_utilization"
          value: 0.95
        - name: "max_queue_depth"
          value: 250
          unit: "requests"
        - name: "time_to_stable"
          value: 15
          unit: "minutes"
        - name: "scaling_events"
          value: 4
      outcome: "System scaled to handle spike, stabilized after 15 minutes"
    - id: "slow_scale"
      type: intervention
      description: "What if scaling is slower?"
      parameters: { scale_up_delay: 300 }
      trajectory:
        - t: 5
          state: { replicas: 3, cpu_util: 0.95, requests_queued: 150 }
          events: ["scale_up_triggered"]
        - t: 10
          state: { replicas: 3, cpu_util: 0.99, requests_queued: 500 }
          events: ["approaching_capacity"]
        - t: 15
          state: { replicas: 6, cpu_util: 0.92, requests_queued: 800 }
          events: ["replicas_added: 3", "request_timeouts_started"]
      final_state: { replicas: 12, cpu_util: 0.70, requests_queued: 0 }
      metrics:
        - name: "max_queue_depth"
          value: 1200
          unit: "requests"
        - name: "timeout_errors"
          value: 340
        - name: "time_to_stable"
          value: 35
          unit: "minutes"
      outcome: "Slow scaling caused significant request timeouts"
  comparison:
    baseline_scenario: "baseline"
    differences:
      - scenario: "traffic_spike"
        variable: "max_queue_depth"
        baseline_value: 0
        scenario_value: 250
        percent_change: null
      - scenario: "slow_scale"
        variable: "timeout_errors"
        baseline_value: 0
        scenario_value: 340
        percent_change: null
sensitivity:
  - parameter: "scale_up_delay"
    impact: high
    direction: positive
    threshold: 120  # Beyond 2 min, errors start occurring
  - parameter: "traffic_multiplier"
    impact: high
    direction: positive
    threshold: 5  # Below 5x, no scaling needed
  - parameter: "max_replicas"
    impact: low
    direction: "n/a"
    threshold: null  # Never hit the limit
validation:
  calibrated: false
  validation_data: null
  anomalies:
    - "Queue drain rate faster than expected - may need tuning"
confidence: 0.75
evidence_anchors:
  - "k8s_hpa_config:autoscaler.yaml"
  - "historical_traffic:traffic_patterns.json"
assumptions:
  - "Linear scaling of capacity with replicas"
  - "Traffic spike is instantaneous (worst case)"
  - "No pod startup delays beyond scale_up_delay"
```

**Evidence pattern:** Ran discrete event simulation using state-transition rules, compared scenarios to understand parameter sensitivity.

---

### Example 2: Monte Carlo Risk Simulation

**Input:**
```yaml
model:
  world_state_ref: "ws_project_schedule"
  causal_model_ref: "cg_task_dependencies"
scenarios:
  - id: "monte_carlo"
    type: monte_carlo
    description: "1000 runs with uncertain task durations"
    runs: 1000
time_steps: 100
seed: 12345
```

**Output:**
```yaml
simulation:
  id: "sim_monte_carlo_schedule"
  model_ref: "ws_project_schedule"
  time_steps: 100
  seed: 12345
results:
  scenarios:
    - id: "monte_carlo"
      type: monte_carlo
      description: "1000 runs with uncertain task durations"
      parameters: { runs: 1000 }
      trajectory: null  # Aggregated across runs
      final_state: null
      metrics:
        - name: "completion_time_p50"
          value: 45
          unit: "days"
        - name: "completion_time_p90"
          value: 62
          unit: "days"
        - name: "completion_time_p99"
          value: 78
          unit: "days"
        - name: "on_time_probability"
          value: 0.72
          unit: "probability"
        - name: "critical_path_stability"
          value: 0.65
          unit: "probability"
      outcome: "72% chance of on-time delivery, critical path varies in 35% of runs"
confidence: 0.85
evidence_anchors:
  - "task_estimates:project_plan.csv"
  - "historical_data:past_project_durations.json"
assumptions:
  - "Task durations follow triangular distributions based on estimates"
  - "No resource contention between tasks"
```

## Verification

- [ ] Simulation respects model constraints (no impossible states)
- [ ] Results are reproducible with same seed
- [ ] Trajectories are monotonic where physics requires
- [ ] No numerical instabilities (NaN, Inf)
- [ ] Aggregate metrics computed correctly from trajectories

**Verification tools:** Trajectory validators, conservation checks

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not execute real-world actions - only simulate
- Flag simulations that reach impossible states
- When results diverge significantly from expectations, investigate before reporting
- Clearly label simulated vs. real outcomes

## Composition Patterns

**Commonly follows:**
- `world-state` - Initial conditions for simulation
- `state-transition` - Rules for state evolution
- `causal-model` - Mechanisms for cause-effect propagation
- `uncertainty-model` - Distributions for Monte Carlo

**Commonly precedes:**
- `forecast-outcome` - Use simulation results for predictions
- `plan` - Test plans before execution
- `critique` - Identify edge cases and failure modes
- `summarize` - Report simulation findings

**Anti-patterns:**
- Never trust simulation results without sensitivity analysis
- Avoid simulating without validating against historical data when available

**Workflow references:**
- See `composition_patterns.md#world-model-build` for model construction
- See `composition_patterns.md#digital-twin-sync-loop` for live simulation
