---
name: estimate-world
description: Approximate the current state of a world or system from partial observations. Use when inferring system state, reconstructing situations, or filling in unobserved variables.
argument-hint: "[world] [--observations <data>] [--variables <list>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce an estimate of a world's or system's current state based on partial, noisy, or indirect observations. This skill answers "given what we can observe, what is the approximate complete state of the world/system?" It performs state estimation, filling in unobserved or hidden variables.

**Success criteria:**
- Observable and unobservable state variables are distinguished
- State estimates include uncertainty for each variable
- Consistency between estimated variables is maintained
- The observation-to-state inference is explicit

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`
- `docs/schemas/world_state.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `world` | Yes | string | The world or system to estimate (e.g., "production environment", "user session", "market") |
| `observations` | No | array | Available measurements or signals |
| `variables` | No | array | Specific state variables to estimate |
| `model` | No | string | Reference to world model or schema |

## Procedure

1) **Define the world and its state space**: Clarify what system is being modeled.
   - What is the scope of the world? (application, environment, domain)
   - What are the key state variables?
   - Which variables are observable vs. hidden?

2) **Catalog available observations**: List what can be directly measured.
   - Current measurements and their timestamps
   - Observation quality and potential noise
   - Coverage: which state variables do observations inform?

3) **Identify state estimation approach**: Choose inference method.
   - **Direct mapping**: Observation directly equals state
   - **Sensor fusion**: Combine multiple noisy observations
   - **Bayesian inference**: Update prior beliefs with observations
   - **Constraint satisfaction**: Find state consistent with all observations
   - **Model-based**: Use system dynamics to infer hidden state

4) **Estimate each state variable**: Derive values for all variables.
   - Observed variables: apply noise/error bounds
   - Hidden variables: infer from related observations
   - Derived variables: compute from other state values
   - Unknown variables: flag as uncertain with priors

5) **Check state consistency**: Ensure estimates don't contradict.
   - Do variable values respect known constraints?
   - Are there incompatible observations?
   - What is the overall state probability?

6) **Quantify uncertainty**: Assess confidence in the state estimate.
   - Observation-backed variables: higher confidence
   - Inferred variables: lower confidence based on inference chain length
   - Unknown variables: express as distribution or bounds

7) **Format output**: Structure complete world state per contract.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: world
  world_id: string        # Identifier for the world/system
  timestamp: string       # When this state estimate applies
  state_variables:
    - name: string        # Variable name
      value: any          # Estimated value
      status: observed | inferred | unknown
      confidence: number  # 0.0-1.0 for this variable
      source: string      # How value was determined
  range:                  # Overall state uncertainty
    completeness: number  # Fraction of state that is known
    consistency: number   # How well variables agree
methodology: string       # State estimation approach
observations_used:
  - observation: string   # What was observed
    timestamp: string     # When
    quality: low | medium | high
sensitivity:
  - variable: string
    impact: low | medium | high
confidence: number        # Overall state estimate confidence
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.world_id` | string | Identifier for the estimated world/system |
| `state_variables` | array | List of state variable estimates with individual confidence |
| `range.completeness` | number | Fraction of state space that is estimated (0-1) |
| `observations_used` | array | Raw observations that informed the estimate |
| `confidence` | number | Overall certainty in the complete state estimate |

## Examples

### Example 1: Estimating Production System State

**Input:**
```yaml
world: "production-kubernetes-cluster"
observations:
  - "pod count: 47 running, 3 pending"
  - "CPU utilization: 62% average"
  - "memory utilization: 78% average"
  - "error rate: 0.3% (last 5 minutes)"
  - "last deployment: 2 hours ago"
variables:
  - "health_status"
  - "capacity_headroom"
  - "stability"
```

**Output:**
```yaml
estimate:
  target_type: world
  world_id: "production-kubernetes-cluster"
  timestamp: "2024-01-15T14:30:00Z"
  state_variables:
    - name: "health_status"
      value: "healthy"
      status: inferred
      confidence: 0.85
      source: "Low error rate (0.3%) and no crash loops indicate healthy state"
    - name: "capacity_headroom"
      value: "moderate"
      status: inferred
      confidence: 0.72
      source: "CPU at 62%, memory at 78%. Memory is limiting factor with ~22% headroom"
    - name: "stability"
      value: "stable"
      status: inferred
      confidence: 0.80
      source: "2 hours since last deployment, no pending pods increasing, error rate flat"
    - name: "pod_state"
      value: {"running": 47, "pending": 3, "failed": 0}
      status: observed
      confidence: 0.95
      source: "Direct observation from kubectl/API"
    - name: "resource_utilization"
      value: {"cpu_pct": 62, "memory_pct": 78}
      status: observed
      confidence: 0.90
      source: "Metrics API, 5-minute average"
    - name: "deployment_state"
      value: "idle"
      status: inferred
      confidence: 0.88
      source: "No active rollouts, last deployment completed 2 hours ago"
  range:
    completeness: 0.75
    consistency: 0.92
methodology: "State inference from Kubernetes metrics and events. Observed metrics mapped to categorical states using operational thresholds. Hidden states (health, stability) inferred from observable indicators."
observations_used:
  - observation: "pod count and status"
    timestamp: "2024-01-15T14:30:00Z"
    quality: high
  - observation: "resource utilization"
    timestamp: "2024-01-15T14:30:00Z"
    quality: high
  - observation: "error rate"
    timestamp: "2024-01-15T14:28:00Z"
    quality: medium
sensitivity:
  - variable: "health_status"
    impact: high
  - variable: "capacity_headroom"
    impact: medium
confidence: 0.78
evidence_anchors:
  - "k8s/pod_status.json"
  - "prometheus/cluster_metrics:14:30"
  - "deployments/history.log"
assumptions:
  - "Metrics are current and accurate"
  - "No silent failures undetected by monitoring"
  - "Thresholds for categorical states are correctly calibrated"
```

**Evidence pattern:** Kubernetes metrics mapped to operational state categories.

---

### Example 2: Estimating User Session State

**Input:**
```yaml
world: "user_session_12345"
observations:
  - "pages_viewed: 7"
  - "time_on_site: 4 minutes"
  - "cart_items: 2"
  - "last_action: 45 seconds ago"
variables:
  - "engagement_level"
  - "purchase_intent"
  - "session_phase"
```

**Output:**
```yaml
estimate:
  target_type: world
  world_id: "user_session_12345"
  timestamp: "2024-01-15T14:35:00Z"
  state_variables:
    - name: "engagement_level"
      value: "high"
      status: inferred
      confidence: 0.82
      source: "7 pages in 4 minutes indicates active browsing, above 75th percentile"
    - name: "purchase_intent"
      value: 0.65
      status: inferred
      confidence: 0.68
      source: "Cart with 2 items is strong signal; browsing pattern suggests comparison shopping"
    - name: "session_phase"
      value: "consideration"
      status: inferred
      confidence: 0.75
      source: "Post-cart-add behavior without checkout initiation"
    - name: "activity_status"
      value: "active"
      status: observed
      confidence: 0.90
      source: "Last action 45 seconds ago, within active threshold"
    - name: "cart_state"
      value: {"items": 2, "value": "unknown"}
      status: observed
      confidence: 0.95
      source: "Direct from session data"
  range:
    completeness: 0.60
    consistency: 0.88
methodology: "User behavior signals mapped to engagement model. Purchase intent from conversion funnel position and behavioral indicators. Session phase from journey stage analysis."
observations_used:
  - observation: "page view count"
    timestamp: "accumulated"
    quality: high
  - observation: "cart contents"
    timestamp: "current"
    quality: high
  - observation: "last action timestamp"
    timestamp: "2024-01-15T14:34:15Z"
    quality: high
sensitivity:
  - variable: "purchase_intent"
    impact: high
  - variable: "session_phase"
    impact: medium
confidence: 0.72
evidence_anchors:
  - "analytics/session_12345:events"
  - "cart/session_12345:state"
assumptions:
  - "User behavior patterns match historical models"
  - "No multi-tab or multi-device session"
  - "Cart items indicate genuine interest"
```

**Evidence pattern:** Behavioral signals mapped to user state model.

## Verification

- [ ] All requested variables have estimates
- [ ] Observable vs. inferred status is correctly labeled
- [ ] Individual variable confidence is justified
- [ ] State variables are mutually consistent
- [ ] Completeness reflects coverage of state space

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Clearly distinguish observed from inferred state
- Do not present inferred state as certain fact
- If observations are stale, note timestamp concerns

## Composition Patterns

**Commonly follows:**
- `retrieve` - To gather current observations
- `inspect` - To understand world structure
- `detect-anomaly` - When anomaly triggers state investigation

**Commonly precedes:**
- `forecast-world` - To project future world state
- `plan` - When current state informs action planning
- `compare` - To compare world states across time or scenarios

**Anti-patterns:**
- Never use for future state predictions (use forecast-world instead)
- Avoid when observations are too stale to represent current state

**Workflow references:**
- See `workflow_catalog.json#situation_assessment` for world estimation context
