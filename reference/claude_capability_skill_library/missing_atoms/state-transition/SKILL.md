---
name: state-transition
description: Define state machines, transition rules, triggers, guards, and actions that govern how world state changes over time. Use when modeling workflows, lifecycle events, protocol states, or any system with discrete state changes.
argument-hint: "[world_state] [transitions|triggers] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Build a **state transition model** that captures how a system moves between states. This defines the dynamics layer of world modeling - the rules governing change.

**Success criteria:**
- All valid states are enumerated
- Transitions have explicit triggers and guard conditions
- Actions associated with transitions are specified
- Probability and reversibility are captured where applicable
- Model is deterministic or explicitly probabilistic

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

**Hard dependencies:**
- Requires `world-state` - Must have a defined state space first

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `world_state` | Yes | object | Reference to world-state output (entities and state variables) |
| `focus_entities` | No | array | Specific entities to model transitions for (default: all) |
| `transition_sources` | No | array | Documentation, logs, or specs describing state changes |
| `constraints` | No | object | Allowed/forbidden transitions, timing constraints |

## Procedure

1) **Identify state space**: From world-state, enumerate discrete states
   - Extract state variables that have finite domains
   - Identify composite states (combinations of variables)
   - Define initial and terminal states if applicable
   - Mark absorbing states (no outgoing transitions)

2) **Extract transitions**: For each state, identify possible next states
   - From documentation: explicit state diagrams, workflow specs
   - From logs: observed state change sequences
   - From code: switch statements, state pattern implementations
   - From domain knowledge: standard lifecycle patterns

3) **Define triggers**: What causes each transition to fire
   - Events: external signals, user actions, messages
   - Conditions: time elapsed, threshold crossed, resource available
   - Internal: computation complete, error occurred

4) **Specify guards**: Conditions that must be true for transition to proceed
   - Preconditions on source state
   - Resource availability
   - Permission/authorization checks
   - Timing constraints (cooldowns, deadlines)

5) **Define actions**: What happens during/after transition
   - Side effects: notifications, logging, resource allocation
   - State updates: variable changes, entity modifications
   - Downstream triggers: cascading transitions

6) **Assess transition properties**:
   - **Probability**: For non-deterministic transitions, assign probabilities
   - **Reversibility**: Can this transition be undone? How?
   - **Duration**: Instantaneous or has duration
   - **Idempotency**: Multiple triggers = same result?

7) **Validate completeness**: Check for modeling gaps
   - Unreachable states
   - States with no outgoing transitions (deadlocks)
   - Missing error/exception paths
   - Unhandled events in certain states

8) **Ground all claims**: Attach evidence for each transition rule
   - Reference source documentation
   - Link to observed state changes in logs

## Output Contract

Return a structured object:

```yaml
transition:
  id: string  # Unique transition model ID
  world_state_ref: string  # Reference to world-state this builds on
  state_space:
    variables:
      - name: string
        domain: array[string] | object  # Enumerated values or range
    states:
      - id: string  # Unique state ID
        label: string  # Human-readable name
        type: initial | normal | terminal | absorbing
        variable_values: object  # {var_name: value}
  transitions:
    - id: string  # Transition ID
      from_state: string  # Source state ID
      to_state: string  # Target state ID
      trigger:
        type: event | condition | internal
        description: string
        event_name: string | null
      guard_conditions: array[string]  # Conditions that must be true
      actions: array[string]  # Effects of the transition
      probability: number | null  # 0.0-1.0 for probabilistic transitions
      reversible: boolean
      reverse_transition: string | null  # ID of reverse transition if exists
      duration_estimate: string | null  # e.g., "instant", "5s", "1-5m"
affected_entities:
  - entity_id: string
    changes: object  # Attribute changes during transitions
side_effects: array[string]  # External effects
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `state_space.variables` | array | State variables with their domains |
| `state_space.states` | array | All possible states |
| `transitions` | array | All valid state transitions |
| `affected_entities` | array | Entities modified by transitions |
| `side_effects` | array | External effects (notifications, etc.) |

## Examples

### Example 1: Pull Request Lifecycle

**Input:**
```yaml
world_state_ref: "ws_github_repo_20250124"
focus_entities: ["pull_request"]
transition_sources:
  - "GitHub PR documentation"
  - ".github/workflows/ci.yml"
```

**Output:**
```yaml
transition:
  id: "tr_pr_lifecycle_20250124"
  world_state_ref: "ws_github_repo_20250124"
  state_space:
    variables:
      - name: "pr_status"
        domain: ["draft", "open", "review_requested", "changes_requested", "approved", "merged", "closed"]
      - name: "ci_status"
        domain: ["pending", "running", "passed", "failed"]
    states:
      - id: "draft"
        label: "Draft PR"
        type: initial
        variable_values: { pr_status: "draft", ci_status: "pending" }
      - id: "open_pending"
        label: "Open, CI pending"
        type: normal
        variable_values: { pr_status: "open", ci_status: "pending" }
      - id: "open_passed"
        label: "Open, CI passed"
        type: normal
        variable_values: { pr_status: "open", ci_status: "passed" }
      - id: "approved"
        label: "Approved"
        type: normal
        variable_values: { pr_status: "approved", ci_status: "passed" }
      - id: "merged"
        label: "Merged"
        type: terminal
        variable_values: { pr_status: "merged" }
      - id: "closed"
        label: "Closed without merge"
        type: terminal
        variable_values: { pr_status: "closed" }
  transitions:
    - id: "t_ready_for_review"
      from_state: "draft"
      to_state: "open_pending"
      trigger:
        type: event
        description: "Author marks PR ready for review"
        event_name: "ready_for_review"
      guard_conditions:
        - "PR has at least one commit"
        - "Author is not blocked"
      actions:
        - "Trigger CI workflow"
        - "Notify reviewers"
      probability: null
      reversible: true
      reverse_transition: "t_convert_to_draft"
      duration_estimate: "instant"
    - id: "t_ci_pass"
      from_state: "open_pending"
      to_state: "open_passed"
      trigger:
        type: event
        description: "CI workflow completes successfully"
        event_name: "ci_success"
      guard_conditions:
        - "All required checks pass"
      actions:
        - "Update status badge"
      probability: 0.85
      reversible: false
      duration_estimate: "5-15m"
    - id: "t_approve"
      from_state: "open_passed"
      to_state: "approved"
      trigger:
        type: event
        description: "Reviewer approves PR"
        event_name: "review_approved"
      guard_conditions:
        - "Required number of approvals met"
        - "No blocking reviews"
      actions:
        - "Enable merge button"
        - "Notify author"
      probability: null
      reversible: true
      reverse_transition: "t_request_changes"
      duration_estimate: "instant"
    - id: "t_merge"
      from_state: "approved"
      to_state: "merged"
      trigger:
        type: event
        description: "Author or maintainer merges PR"
        event_name: "merge"
      guard_conditions:
        - "No merge conflicts"
        - "Branch protection rules satisfied"
      actions:
        - "Merge commits to base branch"
        - "Delete source branch (if configured)"
        - "Close linked issues"
      probability: null
      reversible: false
      duration_estimate: "instant"
affected_entities:
  - entity_id: "pull_request"
    changes:
      status: "transitions through pr_status"
      ci_status: "updates based on workflow"
side_effects:
  - "Email notifications to watchers"
  - "Slack integration posts"
  - "CI/CD pipeline triggers"
confidence: 0.9
evidence_anchors:
  - "github_docs:pull_request_lifecycle"
  - ".github/workflows/ci.yml:1-50"
  - "repo_settings:branch_protection"
assumptions:
  - "Standard GitHub workflow without custom actions"
  - "CI passes in typical case (85% success rate from historical data)"
```

**Evidence pattern:** Extracted state machine from GitHub documentation, correlated with repository workflow files.

---

### Example 2: Order Fulfillment State Machine

**Input:**
```yaml
world_state_ref: "ws_ecommerce_20250124"
focus_entities: ["order"]
```

**Output:**
```yaml
transition:
  id: "tr_order_fulfillment"
  world_state_ref: "ws_ecommerce_20250124"
  state_space:
    variables:
      - name: "order_status"
        domain: ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"]
    states:
      - id: "pending"
        type: initial
        variable_values: { order_status: "pending" }
      - id: "confirmed"
        type: normal
        variable_values: { order_status: "confirmed" }
      - id: "processing"
        type: normal
        variable_values: { order_status: "processing" }
      - id: "shipped"
        type: normal
        variable_values: { order_status: "shipped" }
      - id: "delivered"
        type: terminal
        variable_values: { order_status: "delivered" }
      - id: "cancelled"
        type: terminal
        variable_values: { order_status: "cancelled" }
  transitions:
    - id: "t_confirm"
      from_state: "pending"
      to_state: "confirmed"
      trigger:
        type: event
        description: "Payment confirmed"
        event_name: "payment_success"
      guard_conditions:
        - "Valid payment method"
        - "Items in stock"
      actions:
        - "Reserve inventory"
        - "Send confirmation email"
      probability: 0.95
      reversible: false
    - id: "t_cancel_pending"
      from_state: "pending"
      to_state: "cancelled"
      trigger:
        type: event
        description: "Customer cancels or payment fails"
        event_name: "cancel_or_payment_fail"
      guard_conditions: []
      actions:
        - "Release any holds"
        - "Send cancellation notice"
      probability: 0.05
      reversible: false
confidence: 0.85
evidence_anchors:
  - "order_service/state_machine.rb:10-80"
  - "docs/order_lifecycle.md"
assumptions:
  - "Happy path probability based on last quarter's conversion rate"
```

## Verification

- [ ] Every state has at least one outgoing transition (except terminal/absorbing)
- [ ] Initial states are reachable from nothing
- [ ] Terminal states have no outgoing transitions
- [ ] Guard conditions are evaluable boolean expressions
- [ ] Probabilities from a state sum to 1.0 (for probabilistic models)
- [ ] No orphan states (unreachable from initial)

**Verification tools:** State machine validators, graph reachability analysis

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not execute transitions - only model them
- Flag potential infinite loops (cycles with no exit path)
- Mark destructive transitions (data loss, irreversible operations)
- When confidence < 0.5 on a transition, suggest validation approaches

## Composition Patterns

**Commonly follows:**
- `world-state` - REQUIRED: Must have state space defined first
- `temporal-reasoning` - Time-based triggers and durations
- `inspect` - Observe current state before modeling transitions

**Commonly precedes:**
- `causal-model` - Transitions inform causal relationships
- `simulation` - Run state machine forward in time
- `plan` - Plan sequences of transitions to reach goals
- `diff-world-state` - Compare states after transitions

**Anti-patterns:**
- Never define transitions without a `world-state` reference
- Avoid modeling transitions for continuously-valued state (use differential equations instead)

**Workflow references:**
- See `composition_patterns.md#world-model-build` for full workflow
- See `composition_patterns.md#digital-twin-sync-loop` for applying transitions
