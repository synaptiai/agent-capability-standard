---
name: forecast-world
description: Predict the future state of a world or system over a specified horizon. Use when projecting system evolution, anticipating state changes, or modeling future scenarios.
argument-hint: "[world] [--horizon <period>] [--scenarios]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Predict how a world's or system's state will evolve over a specified time horizon. This skill answers "what will the state of the world/system be in the future?" Unlike estimate-world (current state), this projects the complete system state forward in time, considering multiple state variables and their interactions.

**Success criteria:**
- Future state of key variables is predicted
- State transitions and their triggers are identified
- Scenarios explore different future world states
- Dependencies between state variables are considered

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`
- `docs/schemas/world_state.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `world` | Yes | string | The world or system to forecast (e.g., "production environment", "market segment", "project state") |
| `time_horizon` | Yes | string | How far ahead to forecast |
| `current_state` | No | object | Current state estimate |
| `known_events` | No | array | Scheduled events that will affect state |
| `variables` | No | array | Specific state variables to forecast |

## Procedure

1) **Define the world and key state variables**: Clarify what system is being modeled.
   - What is the scope of the world?
   - What are the key state variables?
   - How do variables relate to each other?

2) **Establish current state**: Starting point for projection.
   - Current value of each state variable
   - Current trends and momentum
   - Recent state transitions

3) **Identify state transition dynamics**: Model how state changes.
   - What triggers state transitions?
   - How do variables influence each other?
   - What are the stable states (attractors)?
   - What feedback loops exist?

4) **Map known future events**: Plot scheduled changes.
   - Planned interventions
   - Scheduled deployments or changes
   - External events with known timing

5) **Project state evolution**: Forecast each variable over time.
   - Apply dynamics rules
   - Apply event effects
   - Check variable consistency
   - Identify cascade effects

6) **Generate scenario worlds**: Create alternative future states.
   - Baseline: current trajectory continues
   - Optimistic: favorable events, positive transitions
   - Pessimistic: adverse events, negative transitions
   - Black swan: unlikely but high-impact changes

7) **Format output**: Structure with multi-variable state forecasts.

## Output Contract

Return a structured object:

```yaml
forecast:
  target_type: world
  world_id: string          # Identifier for the world/system
  prediction: string        # Summary of predicted future state
  time_horizon: string      # Forecast period
  probability: number       # Confidence in primary prediction (0-1)
  state_trajectory:
    - timestamp: string     # Point in time
      variables:
        - name: string      # Variable name
          value: any        # Predicted value
          confidence: number
      overall_state: string # Summary of state at this point
      transitions: array    # State changes occurring
  scenarios:
    - name: string
      probability: number
      outcome:
        description: string
        key_variables: object
        trigger_path: string  # What leads to this scenario
drivers:
  - factor: string          # What influences world evolution
    affects: array[string]  # Which variables
    direction: positive | negative | neutral
    magnitude: low | medium | high
critical_transitions:
  - from_state: string
    to_state: string
    trigger: string
    probability: number
    timing: string
confidence: number          # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.state_trajectory` | array | Complete world state at multiple time points |
| `scenarios` | array | Alternative future world states |
| `critical_transitions` | array | Key state changes that could occur |
| `drivers` | array | Factors shaping world evolution |
| `confidence` | number | Overall certainty in world state forecast |

## Examples

### Example 1: Forecasting Production System State

**Input:**
```yaml
world: "e-commerce-platform"
time_horizon: "Q2 2024"
current_state:
  traffic: "1.2M daily users"
  infrastructure: "80% capacity"
  tech_debt: "medium (score 42)"
  team: "stable (12 engineers)"
known_events:
  - "Black Friday sale planning (mid-Q2)"
  - "Infrastructure upgrade (month 2)"
  - "New feature launch (month 3)"
variables:
  - "system_stability"
  - "capacity_headroom"
  - "development_velocity"
```

**Output:**
```yaml
forecast:
  target_type: world
  world_id: "e-commerce-platform"
  prediction: "System reaches healthy state by Q2 end with improved capacity and stable performance"
  time_horizon: "Q2 2024"
  probability: 0.62
  state_trajectory:
    - timestamp: "Q2 start"
      variables:
        - name: "system_stability"
          value: "stable"
          confidence: 0.85
        - name: "capacity_headroom"
          value: "20%"
          confidence: 0.80
        - name: "development_velocity"
          value: "45 points/sprint"
          confidence: 0.82
        - name: "traffic"
          value: "1.2M daily"
          confidence: 0.90
      overall_state: "Operating normally; capacity concerns for growth"
      transitions: []
    - timestamp: "month 1 end"
      variables:
        - name: "system_stability"
          value: "stable"
          confidence: 0.80
        - name: "capacity_headroom"
          value: "15%"
          confidence: 0.75
        - name: "development_velocity"
          value: "42 points/sprint"
          confidence: 0.78
      overall_state: "Velocity dip as team preps for infrastructure upgrade"
      transitions:
        - "development_velocity: normal -> reduced (prep work)"
    - timestamp: "month 2 (infrastructure upgrade)"
      variables:
        - name: "system_stability"
          value: "degraded during migration"
          confidence: 0.70
        - name: "capacity_headroom"
          value: "50%"
          confidence: 0.72
        - name: "development_velocity"
          value: "38 points/sprint"
          confidence: 0.75
      overall_state: "Transition period; new capacity but migration risk"
      transitions:
        - "capacity_headroom: 15% -> 50% (upgrade complete)"
        - "system_stability: stable -> degraded (migration)"
    - timestamp: "Q2 end"
      variables:
        - name: "system_stability"
          value: "stable"
          confidence: 0.65
        - name: "capacity_headroom"
          value: "45%"
          confidence: 0.68
        - name: "development_velocity"
          value: "50 points/sprint"
          confidence: 0.62
      overall_state: "Healthy with capacity for Black Friday; velocity improved"
      transitions:
        - "system_stability: degraded -> stable (settled)"
        - "development_velocity: reduced -> improved (new tooling)"
  scenarios:
    - name: "smooth_execution"
      probability: 0.35
      outcome:
        description: "All upgrades execute successfully; team gains efficiency"
        key_variables:
          stability: "robust"
          capacity: "55% headroom"
          velocity: "55 points/sprint"
        trigger_path: "Infrastructure upgrade smooth, feature launch well-received"
    - name: "typical"
      probability: 0.45
      outcome:
        description: "Upgrades complete with minor issues; steady improvement"
        key_variables:
          stability: "stable"
          capacity: "45% headroom"
          velocity: "50 points/sprint"
        trigger_path: "Normal execution with expected challenges"
    - name: "complications"
      probability: 0.20
      outcome:
        description: "Infrastructure issues persist; velocity impacted"
        key_variables:
          stability: "intermittent issues"
          capacity: "35% headroom"
          velocity: "40 points/sprint"
        trigger_path: "Migration problems require extended remediation"
drivers:
  - factor: "infrastructure upgrade"
    affects: ["capacity_headroom", "system_stability"]
    direction: positive
    magnitude: high
  - factor: "feature launch complexity"
    affects: ["development_velocity", "system_stability"]
    direction: negative
    magnitude: medium
  - factor: "Black Friday preparation"
    affects: ["development_velocity"]
    direction: negative
    magnitude: medium
  - factor: "team stability"
    affects: ["development_velocity", "system_stability"]
    direction: positive
    magnitude: medium
critical_transitions:
  - from_state: "stable system"
    to_state: "degraded during migration"
    trigger: "infrastructure upgrade execution"
    probability: 0.90
    timing: "month 2"
  - from_state: "degraded"
    to_state: "stable"
    trigger: "migration settling period complete"
    probability: 0.75
    timing: "month 2 + 2 weeks"
  - from_state: "degraded"
    to_state: "unstable"
    trigger: "migration complications compound"
    probability: 0.20
    timing: "month 2 + 3 weeks"
confidence: 0.58
evidence_anchors:
  - "infrastructure/upgrade_plan.md"
  - "project/q2_roadmap.md"
  - "monitoring/capacity_trends:90d"
  - "jira/velocity_history:6_sprints"
assumptions:
  - "Infrastructure upgrade proceeds as planned"
  - "Team composition remains stable"
  - "Traffic growth follows historical pattern"
  - "No major external market disruptions"
```

**Evidence pattern:** Multi-variable state evolution with planned event integration.

---

### Example 2: Forecasting Market Position

**Input:**
```yaml
world: "saas-product-market-position"
time_horizon: "12 months"
current_state:
  market_share: "12%"
  customer_base: "2,400"
  nps: 42
  feature_parity: "behind leader"
known_events:
  - "major feature launch (Q2)"
  - "competitor funding announcement expected"
  - "pricing restructure (Q3)"
```

**Output:**
```yaml
forecast:
  target_type: world
  world_id: "saas-product-market-position"
  prediction: "Improved market position to 14-16% share with stronger NPS"
  time_horizon: "12 months"
  probability: 0.55
  state_trajectory:
    - timestamp: "current"
      variables:
        - name: "market_share"
          value: "12%"
          confidence: 0.90
        - name: "customer_base"
          value: 2400
          confidence: 0.95
        - name: "nps"
          value: 42
          confidence: 0.85
        - name: "competitive_position"
          value: "challenger"
          confidence: 0.82
      overall_state: "Established challenger with room to grow"
      transitions: []
    - timestamp: "Q2 (feature launch)"
      variables:
        - name: "market_share"
          value: "13%"
          confidence: 0.72
        - name: "customer_base"
          value: 2750
          confidence: 0.75
        - name: "nps"
          value: 48
          confidence: 0.70
        - name: "competitive_position"
          value: "strong challenger"
          confidence: 0.68
      overall_state: "Momentum from feature launch; closing gap with leader"
      transitions:
        - "competitive_position: challenger -> strong challenger"
        - "feature_parity: behind -> at parity"
    - timestamp: "Q3 (pricing restructure)"
      variables:
        - name: "market_share"
          value: "14.5%"
          confidence: 0.62
        - name: "customer_base"
          value: 3100
          confidence: 0.65
        - name: "nps"
          value: 45
          confidence: 0.60
      overall_state: "Expansion segment growth; some NPS impact from change"
      transitions:
        - "pricing: premium tier -> tiered structure"
    - timestamp: "12 months"
      variables:
        - name: "market_share"
          value: "15.5%"
          confidence: 0.52
        - name: "customer_base"
          value: 3600
          confidence: 0.55
        - name: "nps"
          value: 50
          confidence: 0.50
        - name: "competitive_position"
          value: "strong #2"
          confidence: 0.48
      overall_state: "Established as clear #2; sustainable growth trajectory"
      transitions:
        - "competitive_position: strong challenger -> established #2"
  scenarios:
    - name: "breakthrough"
      probability: 0.20
      outcome:
        description: "Feature launch creates buzz; competitor stumbles"
        key_variables:
          market_share: "20%"
          nps: 55
          position: "challenging for #1"
        trigger_path: "Feature resonates strongly + competitor missteps"
    - name: "steady_growth"
      probability: 0.50
      outcome:
        description: "Planned trajectory executes; gradual improvement"
        key_variables:
          market_share: "15.5%"
          nps: 50
          position: "strong #2"
        trigger_path: "Plans execute as expected"
    - name: "competitive_pressure"
      probability: 0.30
      outcome:
        description: "Well-funded competitor accelerates; share gains modest"
        key_variables:
          market_share: "13%"
          nps: 44
          position: "maintained challenger"
        trigger_path: "Competitor funding enables aggressive response"
drivers:
  - factor: "major feature launch"
    affects: ["market_share", "nps", "competitive_position"]
    direction: positive
    magnitude: high
  - factor: "competitor funding"
    affects: ["market_share", "competitive_position"]
    direction: negative
    magnitude: medium
  - factor: "pricing restructure"
    affects: ["customer_base", "market_share", "nps"]
    direction: mixed
    magnitude: medium
  - factor: "market growth"
    affects: ["customer_base"]
    direction: positive
    magnitude: low
critical_transitions:
  - from_state: "challenger"
    to_state: "strong #2"
    trigger: "feature parity achieved + growth maintained"
    probability: 0.55
    timing: "within 9 months"
  - from_state: "challenger"
    to_state: "declining challenger"
    trigger: "competitor response overwhelming"
    probability: 0.15
    timing: "if competitor launches major initiative"
confidence: 0.52
evidence_anchors:
  - "analytics/market_share_trends.csv"
  - "product/feature_roadmap.md"
  - "competitive/funding_tracker.md"
  - "customer/nps_surveys:4_quarters"
assumptions:
  - "Feature launch delivers expected value"
  - "Competitor funding doesn't dramatically shift landscape"
  - "Market growth continues at current rate"
  - "Pricing restructure is well-received"
```

**Evidence pattern:** Multi-stakeholder world state with competitive dynamics.

## Verification

- [ ] All key state variables have trajectories
- [ ] Critical transitions are identified with triggers
- [ ] Scenarios cover range of possible world states
- [ ] Variable dependencies are considered
- [ ] Confidence decreases over longer horizons

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Consider interactions between state variables
- Note when world state depends on external factors outside control
- Distinguish between likely and possible states

## Composition Patterns

**Commonly follows:**
- `estimate-world` - Current state is baseline for projection
- `retrieve` - Historical world state data
- `forecast-attribute` - Individual variable forecasts inform world state

**Commonly precedes:**
- `plan` - Future state informs strategic planning
- `compare` - To compare future world states across options
- `forecast-risk` - When world state affects risk exposure

**Anti-patterns:**
- Never forecast world state without considering variable interactions
- Avoid single-variable focus (use forecast-attribute instead)

**Workflow references:**
- See `workflow_catalog.json#strategic_planning` for world state forecasting context
