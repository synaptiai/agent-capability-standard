---
name: causal-model
description: Build causal graphs (DAGs) representing cause-effect relationships, mechanisms, confounders, and intervention effects. Use when analyzing root causes, predicting intervention outcomes, or explaining why things happen.
argument-hint: "[world_state] [hypothesis|observations] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Construct a **causal model** that captures cause-effect relationships in a domain. This goes beyond correlation to model interventions and counterfactuals: "If we change X, what happens to Y?"

**Success criteria:**
- Causal graph is a valid DAG (no cycles)
- Causal directions are justified with evidence or domain knowledge
- Confounders are identified and represented
- Intervention effects can be estimated from the model
- Assumptions (causal Markov, faithfulness) are explicit

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

**Hard dependencies:**
- Requires `world-state` - Must have entities and variables defined

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `world_state` | Yes | object | Reference to world-state with entities/variables |
| `hypothesis` | No | string | Specific causal question to investigate |
| `observations` | No | array | Observational data for causal discovery |
| `domain_knowledge` | No | array | Known causal relationships from domain expertise |
| `constraints` | No | object | Forbidden edges, required edges, time ordering |

## Procedure

1) **Identify variables**: From world-state, select causally relevant variables
   - Focus on variables that can cause or be affected by others
   - Include potential confounders (common causes)
   - Distinguish between treatment, outcome, and covariate variables
   - Note which variables are observable vs. latent

2) **Establish causal ordering**: Determine which variables can cause which
   - Temporal precedence: causes must precede effects
   - Physical/logical constraints: code can't cause its own writing
   - Domain knowledge: known mechanisms
   - Experimental evidence: interventions and their effects

3) **Build causal graph**: Construct directed acyclic graph (DAG)
   - Nodes: variables from step 1
   - Edges: direct causal relationships (A -> B means A directly causes B)
   - Validate: no cycles (would violate causality)
   - Add latent variables if needed for confounding

4) **Classify edge types**: For each edge, identify the relationship
   - **Direct cause**: A changes B directly
   - **Mediated**: A causes B through intermediate variable M
   - **Confounded**: A and B share common cause C
   - **Collider**: A and B both cause C (conditioning on C introduces bias)

5) **Specify mechanisms**: Describe how causes produce effects
   - Functional form if known (linear, threshold, etc.)
   - Direction of effect (positive, negative, non-monotonic)
   - Strength estimate (strong, moderate, weak)
   - Time lag between cause and effect

6) **Analyze interventions**: For key relationships, describe intervention effects
   - Do(X=x): What happens if we force X to value x?
   - Identify backdoor paths that need blocking
   - Identify front-door paths for indirect effects
   - Note when causal effect is not identifiable

7) **Document assumptions**: Causal inference requires strong assumptions
   - Causal Markov: No direct effect without edge
   - Faithfulness: Dependencies in data reflect causal structure
   - No unmeasured confounders (for specific claims)
   - Positivity: All treatments have non-zero probability

8) **Ground causal claims**: Every edge needs justification
   - Experimental evidence (strongest)
   - Strong domain theory
   - Temporal precedence + correlation
   - Statistical methods (with uncertainty)

## Output Contract

Return a structured object:

```yaml
causal_graph:
  id: string  # Unique model ID
  world_state_ref: string
  nodes:
    - id: string  # Variable ID
      type: treatment | outcome | covariate | confounder | mediator | collider
      description: string
      observable: boolean
      domain: string | array  # Variable domain
  edges:
    - id: string  # Edge ID
      from: string  # Source node ID
      to: string  # Target node ID
      type: causes | correlates | mediates | confounds
      strength: weak | moderate | strong
      direction: positive | negative | non_monotonic
      mechanism: string | null  # How the cause produces effect
      time_lag: string | null  # e.g., "immediate", "1-5 days"
      evidence_quality: experimental | observational | theoretical
interventions:
  - target: string  # Node to intervene on
    intervention: string  # do(X=x) notation
    effect_on: string  # Outcome variable
    estimated_effect: string | object  # Qualitative or quantitative
    confidence: number  # 0.0-1.0
    identification_strategy: string  # How effect is identified
confounders:
  - nodes: array[string]  # Variables confounded
    confounder: string  # Common cause
    adjustment_needed: boolean
assumptions:
  - assumption: string
    testable: boolean
    test_method: string | null
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `nodes` | array | Variables in the causal model |
| `edges` | array | Causal relationships between variables |
| `interventions` | array | Analyzed intervention effects |
| `confounders` | array | Identified confounding relationships |
| `assumptions` | array | Causal assumptions with testability |

## Examples

### Example 1: Deployment Causes Error Rate

**Input:**
```yaml
world_state_ref: "ws_production_system_20250124"
hypothesis: "Does code deployment cause increased error rates?"
observations:
  - "deployment_log.json"
  - "error_metrics.json"
```

**Output:**
```yaml
causal_graph:
  id: "cg_deployment_errors_20250124"
  world_state_ref: "ws_production_system_20250124"
  nodes:
    - id: "deployment"
      type: treatment
      description: "Code deployment event"
      observable: true
      domain: ["deployed", "not_deployed"]
    - id: "error_rate"
      type: outcome
      description: "Application error rate (errors/min)"
      observable: true
      domain: "continuous [0, inf)"
    - id: "code_quality"
      type: mediator
      description: "Quality of deployed code (bugs, complexity)"
      observable: false
      domain: ["low", "medium", "high"]
    - id: "traffic_load"
      type: confounder
      description: "User traffic volume"
      observable: true
      domain: "continuous [0, inf)"
    - id: "time_of_day"
      type: confounder
      description: "Time when deployment occurs"
      observable: true
      domain: "24h clock"
  edges:
    - id: "e1"
      from: "deployment"
      to: "code_quality"
      type: causes
      strength: strong
      direction: "varies"
      mechanism: "Deployment introduces new code which may have bugs"
      time_lag: "immediate"
      evidence_quality: theoretical
    - id: "e2"
      from: "code_quality"
      to: "error_rate"
      type: causes
      strength: strong
      direction: negative  # low quality -> high errors
      mechanism: "Buggy code throws more exceptions"
      time_lag: "0-5 minutes"
      evidence_quality: observational
    - id: "e3"
      from: "traffic_load"
      to: "error_rate"
      type: causes
      strength: moderate
      direction: positive
      mechanism: "Higher load exposes edge cases and resource limits"
      time_lag: "immediate"
      evidence_quality: observational
    - id: "e4"
      from: "time_of_day"
      to: "deployment"
      type: correlates
      strength: moderate
      direction: "n/a"
      mechanism: "Deployments tend to happen during business hours"
      evidence_quality: observational
    - id: "e5"
      from: "time_of_day"
      to: "traffic_load"
      type: causes
      strength: strong
      direction: "varies by hour"
      mechanism: "Traffic follows diurnal patterns"
      evidence_quality: observational
interventions:
  - target: "deployment"
    intervention: "do(deployment=true)"
    effect_on: "error_rate"
    estimated_effect: "Expected increase of 15-30% in first hour post-deployment"
    confidence: 0.7
    identification_strategy: "Control for time_of_day and traffic_load via regression"
  - target: "code_quality"
    intervention: "do(code_quality=high) via code review + testing"
    effect_on: "error_rate"
    estimated_effect: "Reduces error rate increase by 60-80%"
    confidence: 0.6
    identification_strategy: "Compare deployment cohorts with/without reviews"
confounders:
  - nodes: ["deployment", "error_rate"]
    confounder: "traffic_load"
    adjustment_needed: true
  - nodes: ["deployment", "error_rate"]
    confounder: "time_of_day"
    adjustment_needed: true
assumptions:
  - assumption: "No unmeasured confounders between deployment and error_rate"
    testable: false
    test_method: null
  - assumption: "Traffic load is accurately measured"
    testable: true
    test_method: "Compare multiple traffic metrics"
  - assumption: "Error rate metric captures all relevant errors"
    testable: true
    test_method: "Audit error logging completeness"
confidence: 0.75
evidence_anchors:
  - "deployment_log.json:deployment_timestamps"
  - "error_metrics.json:error_rate_timeseries"
  - "traffic_metrics.json:requests_per_minute"
```

**Evidence pattern:** Built DAG from temporal precedence (deployment before errors), identified confounders from domain knowledge, validated with observational correlation.

---

### Example 2: Feature Flag Causal Model

**Input:**
```yaml
world_state_ref: "ws_ab_test_20250124"
hypothesis: "Does new checkout flow increase conversion?"
```

**Output:**
```yaml
causal_graph:
  id: "cg_checkout_conversion"
  nodes:
    - id: "feature_flag"
      type: treatment
      description: "New checkout flow enabled"
      observable: true
      domain: ["control", "treatment"]
    - id: "conversion"
      type: outcome
      description: "User completes purchase"
      observable: true
      domain: ["converted", "not_converted"]
    - id: "page_load_time"
      type: mediator
      description: "Checkout page load latency"
      observable: true
    - id: "user_segment"
      type: confounder
      description: "User type (new vs returning)"
      observable: true
  edges:
    - id: "e1"
      from: "feature_flag"
      to: "page_load_time"
      type: causes
      strength: moderate
      direction: positive  # new flow slightly slower
      mechanism: "New flow has additional JS bundle"
    - id: "e2"
      from: "feature_flag"
      to: "conversion"
      type: causes
      strength: moderate
      direction: positive
      mechanism: "Streamlined UX reduces friction"
    - id: "e3"
      from: "page_load_time"
      to: "conversion"
      type: causes
      strength: moderate
      direction: negative
      mechanism: "Slower pages increase abandonment"
interventions:
  - target: "feature_flag"
    intervention: "do(feature_flag=treatment)"
    effect_on: "conversion"
    estimated_effect: "+2.5% conversion rate (net of load time effect)"
    confidence: 0.85
    identification_strategy: "Randomized A/B test with sufficient sample size"
assumptions:
  - assumption: "Random assignment eliminates confounding"
    testable: true
    test_method: "Balance check on user_segment"
confidence: 0.85
evidence_anchors:
  - "ab_test_results:experiment_123"
  - "analytics:conversion_funnel"
```

## Verification

- [ ] Graph is acyclic (no directed cycles)
- [ ] All edges have justification (evidence or domain knowledge)
- [ ] Confounders are identified for treatment-outcome pairs
- [ ] Intervention effects are consistent with graph structure
- [ ] Assumptions are explicit and testability noted

**Verification tools:** DAG validation, d-separation tests

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not claim causation from correlation alone without explicit caveats
- Flag when causal effect is not identifiable from observational data
- Mark all latent/unobserved confounders
- Distinguish experimental from observational evidence clearly

## Composition Patterns

**Commonly follows:**
- `world-state` - REQUIRED: Must have variables defined
- `state-transition` - Transitions inform causal dynamics
- `temporal-reasoning` - Temporal order constrains causal direction
- `grounding` - Evidence for causal claims

**Commonly precedes:**
- `simulation` - Run causal model forward
- `forecast-outcome` - Predict effects of interventions
- `explain` - Explain outcomes via causal paths
- `plan` - Plan interventions to achieve goals

**Anti-patterns:**
- Never claim causation without addressing confounding
- Avoid cycles in causal graphs (use equilibrium models for feedback)

**Workflow references:**
- See `composition_patterns.md#world-model-build` for full workflow
- See `composition_patterns.md#debug-code-change` for root cause analysis
