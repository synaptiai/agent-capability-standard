---
name: detect-activity
description: Detect whether an activity, event, or process is occurring or has occurred in the given data. Use when searching for actions, checking for events, monitoring processes, or validating activity patterns.
argument-hint: "[target-data] [activity-type] [time-window]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine whether specific activities, events, or processes have occurred or are occurring based on evidence in the target data. This is an existence check that answers "did this activity happen?" rather than classifying the activity type.

**Success criteria:**
- Binary detection result (detected/not detected) with temporal context
- Evidence anchors pointing to specific activity indicators
- Activity instances with timing information when available

**Compatible schemas:**
- `docs/schemas/detect_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The data to scan for activity evidence (logs, events, audit trails, git history) |
| `activity_type` | No | string | Type of activity: commit, deploy, login, purchase, build, test, any (default: any) |
| `activity_pattern` | No | string | Specific activity pattern or keyword to detect |
| `constraints` | No | object | Detection parameters: time_window, min_occurrences, actor_filter |

## Procedure

1) **Define activity signatures**: Establish what constitutes the target activity
   - Log patterns: timestamps, action verbs, status codes
   - Event markers: event types, trigger indicators
   - Process signals: start/stop markers, state transitions

2) **Scan for activity indicators**: Search for evidence of activities
   - Timestamp patterns indicating when activities occurred
   - Action keywords: "created", "deleted", "updated", "deployed", "built"
   - Status indicators: success/failure markers, completion signals
   - Actor associations: who/what performed the activity

3) **Correlate activity signals**: Group related indicators into activity instances
   - Match start events with end events
   - Associate actors with actions
   - Link cause and effect patterns

4) **Apply temporal constraints**: Filter by time window if specified
   - Parse timestamps from various formats
   - Exclude activities outside the specified window
   - Note timezone assumptions

5) **Ground claims**: Attach evidence anchors to detected activities
   - Format: `file:line` or `log:timestamp`
   - Quote the specific log entry or event record

6) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
detected: boolean  # True if activity evidence found
target_type: activity
instances:
  - id: string | null  # Activity identifier (event ID, commit hash)
    type: string  # commit, deploy, login, build, etc.
    attributes:
      actor: string | null  # Who/what performed it
      timestamp: string | null  # When it occurred (ISO 8601)
      duration: string | null  # How long it took
      status: string | null  # success, failure, in_progress
    location: string  # Log file:line or event source
    confidence: number  # 0.0-1.0 for this instance
signals:
  - signal: string  # Activity indicator found
    strength: low | medium | high
    location: string
false_positive_risk: low | medium | high
confidence: number  # 0.0-1.0 overall
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `detected` | boolean | Whether activity evidence was found |
| `instances` | array | List of detected activity instances |
| `signals` | array | Raw indicators suggesting activity occurred |
| `false_positive_risk` | enum | Risk that detection is incorrect |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | References to activity evidence |
| `assumptions` | array[string] | Stated assumptions about activity patterns |

## Examples

### Example 1: Detecting Deployment Activity in CI/CD Logs

**Input:**
```yaml
target: "/var/log/ci/deploy.log"
activity_type: "deploy"
constraints:
  time_window: "last_24h"
```

**Output:**
```yaml
detected: true
target_type: activity
instances:
  - id: "deploy-2024-01-15-001"
    type: deploy
    attributes:
      actor: "github-actions"
      timestamp: "2024-01-15T14:32:00Z"
      duration: "4m23s"
      status: "success"
    location: "deploy.log:1542"
    confidence: 0.95
  - id: "deploy-2024-01-15-002"
    type: deploy
    attributes:
      actor: "github-actions"
      timestamp: "2024-01-15T18:45:00Z"
      duration: "3m58s"
      status: "success"
    location: "deploy.log:2891"
    confidence: 0.95
signals:
  - signal: "[2024-01-15T14:32:00Z] Deployment started: v2.3.1"
    strength: high
    location: "deploy.log:1542"
  - signal: "[2024-01-15T14:36:23Z] Deployment completed successfully"
    strength: high
    location: "deploy.log:1698"
  - signal: "[2024-01-15T18:45:00Z] Deployment started: v2.3.2"
    strength: high
    location: "deploy.log:2891"
false_positive_risk: low
confidence: 0.94
evidence_anchors:
  - "deploy.log:1542"
  - "deploy.log:1698"
  - "deploy.log:2891"
  - "deploy.log:3047"
assumptions:
  - "Log timestamps are in UTC"
  - "'Deployment started/completed' messages indicate actual deployments"
```

**Evidence pattern:** Log parsing with deployment keyword matching and timestamp extraction.

---

### Example 2: Detecting Build Failures in GitHub Actions

**Input:**
```yaml
target: ".github/workflows/build.yml and recent runs"
activity_type: "build"
activity_pattern: "failure"
```

**Output:**
```yaml
detected: true
target_type: activity
instances:
  - id: "run-7823456"
    type: build
    attributes:
      actor: "dependabot[bot]"
      timestamp: "2024-01-14T09:15:00Z"
      duration: "2m12s"
      status: "failure"
    location: "gh:actions:run:7823456"
    confidence: 0.92
signals:
  - signal: "Build step 'npm test' exited with code 1"
    strength: high
    location: "gh:actions:run:7823456:step:4"
  - signal: "Workflow conclusion: failure"
    strength: high
    location: "gh:actions:run:7823456"
false_positive_risk: low
confidence: 0.91
evidence_anchors:
  - "gh:actions:run:7823456"
  - ".github/workflows/build.yml:45"
assumptions:
  - "GitHub Actions run data is current"
  - "Exit code 1 indicates failure"
```

**Evidence pattern:** GitHub Actions API query combined with workflow file analysis.

---

### Example 3: No Recent Activity Detected

**Input:**
```yaml
target: "/var/log/app/auth.log"
activity_type: "login"
constraints:
  time_window: "last_1h"
  actor_filter: "admin*"
```

**Output:**
```yaml
detected: false
target_type: activity
instances: []
signals:
  - signal: "No login events matching admin* in last hour"
    strength: high
    location: "auth.log"
  - signal: "Last admin login was 6 hours ago"
    strength: medium
    location: "auth.log:4521"
false_positive_risk: low
confidence: 0.88
evidence_anchors:
  - "auth.log:4521"
  - "tool:Grep:admin.*login:auth.log"
assumptions:
  - "Log file contains complete authentication records"
  - "Time window is relative to current time"
next_actions:
  - "Expand time window to find last admin activity"
  - "Check if admin accounts are disabled or renamed"
```

**Evidence pattern:** Time-bounded log search with negative result.

## Verification

- [ ] Output contains `detected` boolean field
- [ ] Activity instances include timestamp when available
- [ ] Time window constraints are properly applied
- [ ] Evidence anchors reference actual log entries or event records
- [ ] Actor filter correctly applied when specified

**Verification tools:** Read (for log inspection), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not execute processes to detect their activity; use only log/event analysis
- Respect log rotation and archival boundaries
- Do not expose sensitive activity details (passwords, tokens) in output
- If detecting security-sensitive activities (login attempts), note elevated scrutiny

## Composition Patterns

**Commonly follows:**
- `retrieve` - After fetching logs or event data
- `detect-person` - After confirming person presence, detect their activities

**Commonly precedes:**
- `identify-activity` - When detection confirms activity, classify its type
- `estimate-impact` - When assessing the impact of detected activities
- `audit` - When creating audit records of detected activities

**Anti-patterns:**
- Never use to monitor individuals without proper authorization
- Avoid detecting activities in real-time streaming logs (use monitoring tools)

**Workflow references:**
- See `workflow_catalog.json#incident-timeline` for activity reconstruction
- See `workflow_catalog.json#audit-trail` for compliance activity detection
