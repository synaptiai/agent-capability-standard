---
name: identify-activity
description: Identify and classify an activity, event, or process from available evidence. Use when determining what type of action occurred, categorizing events, classifying operations, or naming processes.
argument-hint: "[target-activity] [classification-context] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and name an activity based on available evidence, determining what type of action or event it represents. This answers "what kind of activity is this?" rather than just confirming activity presence.

**Success criteria:**
- Clear activity classification with canonical type name
- Match quality assessment (exact, probable, possible, no match)
- Alternative classifications with probabilities when uncertain
- Disambiguation signals explaining the classification rationale

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The activity reference to identify (log entry, event record, action trace) |
| `context` | No | string\|object | Context for classification (system type, event taxonomy, domain) |
| `constraints` | No | object | Classification parameters: taxonomy, max_alternatives, granularity |

## Procedure

1) **Extract activity signals**: Gather all available indicators from the target
   - Action verbs: created, deleted, modified, deployed, executed
   - Timestamps: start/end times, duration
   - Actors: who/what performed the activity
   - Targets: what was affected by the activity
   - Status: success, failure, in-progress, cancelled

2) **Match against activity taxonomy**: Classify into known activity types
   - CRUD operations: create, read, update, delete
   - Lifecycle events: start, stop, restart, deploy, rollback
   - Security actions: login, logout, grant, revoke, audit
   - Development activities: commit, push, merge, review, release

3) **Determine activity granularity**: Identify hierarchical classification
   - High-level: "deployment" vs specific "blue-green deployment"
   - Domain-specific: "API call" vs specific "user authentication"
   - Composite: activities that combine multiple sub-activities

4) **Assess classification confidence**: Determine match quality
   - Exact: clear activity type with unambiguous signals
   - Probable: strong classification with minor ambiguities
   - Possible: weak signals or overlapping categories
   - No match: activity type cannot be determined

5) **Generate alternatives**: List other possible classifications
   - Overlapping activity types
   - Different granularity levels
   - Domain-specific vs generic classifications

6) **Ground claims**: Attach evidence anchors to classification
   - Format: `log:timestamp` or `event:id`
   - Quote the specific evidence supporting classification

7) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Activity identifier (event ID, log reference)
  type: string  # Activity type classification
  canonical_name: string  # Human-readable activity name
  attributes:
    category: string  # crud, lifecycle, security, development, etc.
    action_verb: string  # create, deploy, login, etc.
    actor: string | null  # Who performed it
    target: string | null  # What was affected
    status: string | null  # success, failure, in_progress
    timestamp: string | null  # When it occurred
  namespace: string | null  # System or domain context
match_quality: exact | probable | possible | no_match
alternatives:
  - entity:
      id: string
      type: string
      canonical_name: string
      attributes: object
    probability: number  # 0.0-1.0
disambiguation_signals: array[string]  # Why this classification
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified activity with attributes |
| `match_quality` | enum | Confidence category for the classification |
| `alternatives` | array | Other possible classifications with probabilities |
| `disambiguation_signals` | array | Reasons supporting the classification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to activity evidence |
| `assumptions` | array[string] | Stated assumptions about activity patterns |

## Examples

### Example 1: Identifying Deployment Activity

**Input:**
```yaml
target:
  log_entry: "[2024-01-15T14:32:00Z] Starting deployment of v2.3.1 to production"
  source: "deploy.log:1542"
context: "CI/CD system"
```

**Output:**
```yaml
entity:
  id: "deploy-2024-01-15-v2.3.1"
  type: production_deployment
  canonical_name: "Production Deployment v2.3.1"
  attributes:
    category: "lifecycle"
    action_verb: "deploy"
    actor: "github-actions"
    target: "production environment"
    status: "started"
    timestamp: "2024-01-15T14:32:00Z"
  namespace: "ci-cd/deployments"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Keywords 'deployment' and 'production' indicate production deployment"
  - "Version string v2.3.1 indicates release deployment"
  - "Starting indicates activity initiation"
confidence: 0.96
evidence_anchors:
  - "deploy.log:1542"
assumptions:
  - "Log format is standard CI/CD deployment log"
  - "'production' keyword indicates production environment"
```

**Evidence pattern:** Log parsing with deployment keyword matching.

---

### Example 2: Identifying Security Event

**Input:**
```yaml
target:
  event: "Failed password attempt for user admin from IP 192.168.1.100"
  timestamp: "2024-01-15T10:23:45Z"
context: "security audit log"
constraints:
  taxonomy: "security_events"
```

**Output:**
```yaml
entity:
  id: "auth-fail-2024-01-15T10:23:45Z"
  type: authentication_failure
  canonical_name: "Failed Login Attempt"
  attributes:
    category: "security"
    action_verb: "authenticate"
    actor: "192.168.1.100"
    target: "user:admin"
    status: "failure"
    timestamp: "2024-01-15T10:23:45Z"
  namespace: "security/authentication"
match_quality: exact
alternatives:
  - entity:
      id: "auth-fail-2024-01-15T10:23:45Z"
      type: brute_force_attempt
      canonical_name: "Potential Brute Force Attempt"
      attributes:
        category: "security_threat"
        action_verb: "attack"
    probability: 0.30
disambiguation_signals:
  - "'Failed password attempt' indicates authentication failure"
  - "Single event, not classified as brute force without pattern"
  - "Admin account target increases security significance"
confidence: 0.92
evidence_anchors:
  - "auth.log:event"
assumptions:
  - "Single failure is auth_failure, not attack"
  - "Need pattern analysis for brute_force classification"
next_actions:
  - "Check for repeated failures from same IP (brute force pattern)"
  - "Verify if admin account lockout was triggered"
```

**Evidence pattern:** Security event classification with threat context.

---

### Example 3: Identifying Ambiguous Database Activity

**Input:**
```yaml
target:
  query: "UPDATE users SET last_login = NOW() WHERE id = 123"
  duration: "15ms"
context: "database query log"
```

**Output:**
```yaml
entity:
  id: "query-update-users-123"
  type: record_update
  canonical_name: "User Record Update"
  attributes:
    category: "crud"
    action_verb: "update"
    actor: null
    target: "users.123"
    status: "success"
    timestamp: null
  namespace: "database/users"
match_quality: probable
alternatives:
  - entity:
      id: "query-update-users-123"
      type: login_tracking
      canonical_name: "Login Activity Tracking"
      attributes:
        category: "audit"
        action_verb: "track"
    probability: 0.40
  - entity:
      id: "query-update-users-123"
      type: session_update
      canonical_name: "Session Update"
      attributes:
        category: "session_management"
        action_verb: "refresh"
    probability: 0.25
disambiguation_signals:
  - "UPDATE statement indicates record modification"
  - "last_login field suggests login tracking purpose"
  - "Cannot determine if part of login flow or standalone update"
confidence: 0.65
evidence_anchors:
  - "database:query_log"
assumptions:
  - "Query executed successfully (no error in log)"
  - "Activity purpose inferred from field name"
next_actions:
  - "Check application context to determine if login-related"
  - "Review surrounding queries for transaction context"
```

**Evidence pattern:** SQL query classification with semantic inference.

---

### Example 4: Composite Activity Identification

**Input:**
```yaml
target:
  events:
    - "PR #456 merged to main"
    - "CI pipeline triggered"
    - "Deployment to staging started"
    - "Deployment to staging completed"
context: "development workflow"
```

**Output:**
```yaml
entity:
  id: "release-flow-pr-456"
  type: continuous_deployment
  canonical_name: "Continuous Deployment Flow"
  attributes:
    category: "development"
    action_verb: "release"
    actor: "automated"
    target: "staging environment"
    status: "completed"
    timestamp: null
  namespace: "devops/cd"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Sequence: merge -> CI -> deploy indicates CD flow"
  - "All events related to same PR (#456)"
  - "Staging deployment completes the flow"
confidence: 0.94
evidence_anchors:
  - "github:pr:456"
  - "ci:pipeline:run"
  - "deploy.log:staging"
assumptions:
  - "Events are chronologically ordered"
  - "Events are causally related"
```

**Evidence pattern:** Multi-event correlation for composite activity.

## Verification

- [ ] Activity type classification is from valid taxonomy
- [ ] Match quality accurately reflects evidence strength
- [ ] Category and action_verb are consistent with type
- [ ] Alternatives listed when match_quality is not "exact"
- [ ] Disambiguation signals explain the classification rationale

**Verification tools:** Read (for log inspection), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive activity details (credentials, PII) in output
- Note when activity classification has security implications
- If identifying potentially malicious activity, flag for security review
- Do not classify activities in ways that could enable evasion

## Composition Patterns

**Commonly follows:**
- `detect-activity` - After confirming activity presence, classify its type
- `retrieve` - After fetching activity logs or event streams

**Commonly precedes:**
- `estimate-impact` - When assessing impact of classified activities
- `audit` - When creating audit records of classified activities
- `compare-entities` - When comparing activities across systems

**Anti-patterns:**
- Never use to classify activities for unauthorized monitoring
- Avoid classifying activities without sufficient context

**Workflow references:**
- See `workflow_catalog.json#incident-analysis` for security activity classification
- See `workflow_catalog.json#audit-trail` for compliance activity classification
