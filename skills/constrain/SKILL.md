---
name: constrain
description: Enforce policies, guardrails, and permission boundaries; refuse unsafe actions and apply least privilege. Use when evaluating actions against policies, checking permissions, or reducing scope to safe boundaries.
argument-hint: "[target] [constraints] [action_on_violation]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Execute **constrain** to evaluate proposed actions against defined policies, enforce permission boundaries, and reduce scope to the minimum required for safe operation. This is the gatekeeper that prevents unsafe actions before they execute.

**Success criteria:**
- All relevant policies evaluated for the proposed action
- Clear allow/deny decision with rationale
- Scope reduced to minimum necessary permissions
- Violation actions documented (block, warn, log)

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | any | What to constrain |
| `constraints` | Yes | array | Constraints to enforce |
| `action_on_violation` | No | string | What to do on a violation: `block`, `warn`, or `log` |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

In a workflow, a constrain step that blocks can count independent reviews
with a `quorum` (Standard v1.1 `quorum@1`): earlier `delegate` steps are
the reviewers, and the output gains a `tally` of passes, blocks,
abstentions, full-sweep passes and voters. See
[ORCHESTRATION_EXTENSIONS.md](../../docs/guides/ORCHESTRATION_EXTENSIONS.md).

## Procedure

1) **Identify applicable policies**: Find all policies relevant to the action
   - Load policy definitions from `.policies/` or policy registry
   - Match action type to policy triggers
   - Consider context (user role, environment, time) for policy selection

2) **Evaluate preconditions**: Check if action meets basic safety requirements
   - Is action within workspace boundaries?
   - Does action target sensitive resources (.env, credentials)?
   - Is checkpoint required but missing?
   - Is approval required but not obtained?

3) **Apply policy rules**: Evaluate each policy condition
   - Parse policy conditions (AND/OR/NOT expressions)
   - Check each condition against the target action's parameters
   - Record which conditions pass and which fail
   - Determine overall policy verdict (allow/deny/conditional)

4) **Reduce scope**: Apply least privilege principle
   - Identify minimum permissions needed for action
   - Remove unnecessary permissions from scope
   - Document removed permissions and rationale

5) **Determine enforcement action**: Based on policy verdict
   - `block`: Prevent action from executing
   - `warn`: Allow but alert user to risk
   - `log`: Record violation but allow action

6) **Ground claims**: Document policy evaluation evidence
   - Format: `policy:<policy_id>:<condition>`, decision rationale
   - Include any scope reductions applied

## Output Contract

Return a structured object:

```yaml
constraints_applied:
  - name: string  # Policy or constraint name
    type: policy | permission | rate_limit | scope
    target: string  # What the constraint applies to
    enforced: boolean  # Whether constraint was enforced
    violation_action: block | warn | log
policy_evaluation:
  policy_id: string  # Which policy was evaluated
  result: allow | deny | conditional
  conditions_met: array[string]  # Conditions that passed
  conditions_failed: array[string]  # Conditions that failed
scope_reduction:
  original_scope: object  # Permissions before constraining
  constrained_scope: object  # Permissions after constraining
  removed_permissions: array[string]  # What was removed
compliant: boolean  # Overall go/no-go: false when any violation is enforced with `block`
violations:  # Constraint violations (any enforcement level)
  - constraint: string  # Which constraint was violated
    detail: string  # What failed
    action: block | warn | log  # Enforcement applied
actions_taken: array[string]  # Enforcement actions performed (block, warn, log, scope reduction)
tally:  # Only when the step has a quorum (quorum@1)
  passes: integer
  blocks: integer
  abstains: integer
  full_passes: integer
  voters: array[string]
blocked_reason: string | null  # Why blocked (if applicable)
confidence: number  # 0.0-1.0
evidence_anchors: ["policy:...", "file:..."]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `constraints_applied` | array | List of constraints evaluated and their enforcement |
| `policy_evaluation` | object | Result of primary policy evaluation |
| `scope_reduction` | object | How permissions were reduced |
| `compliant` | boolean | Overall decision: true when no violation is enforced with `block`, so the action can proceed (workflows gate on `${<step>.compliant}`) |
| `violations` | array | Constraint violations, each with the enforcement applied; `warn`/`log` violations leave `compliant` true |
| `actions_taken` | array | Enforcement actions performed |
| `tally` | object | Review quorum count (passes, blocks, abstains, full_passes, voters); present only when the step has a `quorum` |
| `blocked_reason` | string | Explanation if action is blocked |
| `confidence` | number | 0.0-1.0 based on policy coverage |
| `evidence_anchors` | array | References to policies evaluated |
| `assumptions` | array | Policy assumptions made |

## Examples

### Example 1: Constrain File Access to Safe Boundaries

**Input:**
```yaml
target:
  capability: "mutate"
  target: "/etc/passwd"
  parameters:
    content: "..."
constraints: ["workspace_boundary", "sensitive_file_protection"]
action_on_violation: block
```

**Output:**
```yaml
constraints_applied:
  - name: "workspace_boundary"
    type: scope
    target: "/etc/passwd"
    enforced: true
    violation_action: block
  - name: "sensitive_file_protection"
    type: policy
    target: "/etc/passwd"
    enforced: true
    violation_action: block
policy_evaluation:
  policy_id: "sys_file_protection"
  result: deny
  conditions_met: []
  conditions_failed:
    - "path must be within workspace"
    - "system files are read-only"
scope_reduction:
  original_scope:
    paths: ["/**"]
  constrained_scope:
    paths: ["/workspace/**"]
  removed_permissions:
    - "write to system paths"
compliant: false
violations:
  - constraint: "workspace_boundary"
    detail: "path must be within workspace"
    action: block
  - constraint: "sensitive_file_protection"
    detail: "system files are read-only"
    action: block
actions_taken:
  - "block: mutate /etc/passwd"
  - "scope reduced to /workspace/**"
blocked_reason: "Action targets system file outside workspace boundary. Editing /etc/passwd is prohibited."
confidence: 1.0
evidence_anchors:
  - "policy:workspace_boundary:path_check"
  - "policy:sys_file_protection:sensitive_paths"
assumptions: []
```

**Evidence pattern:** Policy definitions, path matching against workspace boundary.

---

### Example 2: Constrain API Call with Rate Limiting

**Input:**
```yaml
target:
  capability: "send"
  target: "https://api.external.com/data"
  parameters:
    method: "POST"
    payload: {...}
constraints: ["external_api_rate_limit", "checkpoint_before_send"]
action_on_violation: warn
```

Session `abc123` has already made 95 requests this hour.

**Output:**
```yaml
constraints_applied:
  - name: "external_api_rate_limit"
    type: rate_limit
    target: "api.external.com"
    enforced: true
    violation_action: warn
  - name: "checkpoint_before_send"
    type: policy
    target: "send capability"
    enforced: true
    violation_action: block
policy_evaluation:
  policy_id: "external_communication"
  result: conditional
  conditions_met:
    - "destination is allowed domain"
    - "payload size within limits"
  conditions_failed:
    - "approaching rate limit (95/100 this hour)"
scope_reduction:
  original_scope:
    rate_limit: 100
    burst_allowed: true
  constrained_scope:
    rate_limit: 5
    burst_allowed: false
  removed_permissions:
    - "burst requests"
compliant: true
violations:
  - constraint: "external_api_rate_limit"
    detail: "approaching rate limit (95/100 this hour)"
    action: warn
actions_taken:
  - "warn: 95/100 requests used this hour"
  - "scope reduced: rate limit 5, no burst"
blocked_reason: null
confidence: 0.9
evidence_anchors:
  - "policy:external_api_rate_limit:hourly_quota"
  - "context:requests_this_hour:95"
assumptions:
  - "Rate limit counter is accurate"
  - "Hour boundary resets at :00"
```

---

### Example 3: Constrain Before Execute

**Input:**
```yaml
target:
  capability: "execute"
  target: "refactor_handlers_plan"
  parameters:
    plan_id: "plan_20240115_refactor"
constraints: ["checkpoint_required"]
action_on_violation: block
```

**Output:**
```yaml
constraints_applied:
  - name: "checkpoint_required"
    type: policy
    target: "execute"
    enforced: true
    violation_action: block
policy_evaluation:
  policy_id: "mutation_safety"
  result: conditional
  conditions_met:
    - "plan exists and is valid"
    - "files in scope are editable"
  conditions_failed:
    - "checkpoint not found for scope"
scope_reduction:
  original_scope:
    mutation_allowed: true
  constrained_scope:
    mutation_allowed: false
  removed_permissions:
    - "file mutation (pending checkpoint)"
compliant: false
violations:
  - constraint: "checkpoint_required"
    detail: "checkpoint not found for scope"
    action: block
actions_taken:
  - "block: execute refactor_handlers_plan until checkpoint exists"
blocked_reason: "This execute step mutates files (requires_checkpoint: true). Call 'checkpoint' first with scope matching the plan."
confidence: 1.0
evidence_anchors:
  - "policy:mutation_safety:checkpoint_gate"
  - "composition_patterns.md:CAVR"
assumptions: []
```

## Verification

Apply the following verification patterns:

- [ ] **Policy Coverage**: All applicable policies were evaluated
- [ ] **Evidence Grounding**: Decisions linked to specific policy conditions
- [ ] **Scope Reduction Valid**: Constrained scope is subset of original
- [ ] **Safety Boundary Check**: No sensitive files in allowed scope

**Verification tools:** Read (for policy files), Grep (for policy search)

## Safety Constraints

- `mutation`: false (constrain is evaluation only)
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always evaluate workspace boundary policy
- Always check for sensitive file patterns (.env, credentials, secrets, .pem, .key)
- Apply strictest enforcement when ambiguous
- Never downgrade enforcement level silently
- Log all policy evaluations for audit

## Composition Patterns

**Commonly follows:**
- `plan` - Constrain the planned actions before checkpoint
- `critique` - After identifying risks, constrain to mitigate

**Commonly precedes:**
- `checkpoint` - After constrain approves, create checkpoint
- `send` - REQUIRED: constrain before any external communication
- `execute` / `mutate` - Constrain as part of pre-execution checks (constrain must precede them)

**Anti-patterns:**
- CRITICAL: Never skip constrain before send (no unchecked external comms)
- Never ignore blocked_reason and proceed anyway
- Never silently weaken policy enforcement
- Never evaluate constrain after mutation has begun

**Workflow references:**
- See `reference/composition_patterns.md#digital-twin-sync-loop` for constrain-before-act
- See `reference/composition_patterns.md#risk-assessment` for constrain placement
- See `reference/verification_patterns.md#pattern-6-safety-boundary-check` for boundary checks
