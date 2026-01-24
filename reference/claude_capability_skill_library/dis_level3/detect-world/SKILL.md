---
name: detect-world
description: Detect whether a specific world state, environmental condition, or system context exists. Use when checking environment status, validating system state, confirming deployment context, or verifying runtime conditions.
argument-hint: "[target-context] [world-state] [detection-scope]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine whether specific world states, environmental conditions, or system contexts exist. This is an existence check that answers "is the system/environment in this state?" rather than classifying what state it is in.

**Success criteria:**
- Binary detection result (detected/not detected) for queried world state
- Evidence anchors pointing to state indicators
- Clear environmental context and scope boundaries

**Compatible schemas:**
- `docs/schemas/detect_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The context to examine (environment, system, deployment, configuration) |
| `world_state` | No | string | Specific state to detect: production, development, degraded, maintenance, healthy |
| `state_indicators` | No | array | Custom indicators that signal the target state |
| `constraints` | No | object | Detection parameters: scope, include_transient, confidence_threshold |

## Procedure

1) **Define state signatures**: Establish indicators for the target world state
   - Environment variables: NODE_ENV, RAILS_ENV, DEPLOYMENT_ENV
   - Configuration flags: feature toggles, environment-specific settings
   - System markers: hostnames, domain patterns, resource endpoints
   - Runtime indicators: log levels, debug flags, monitoring status

2) **Scan for state indicators**: Search for evidence of the target state
   - Check environment configuration files
   - Examine runtime environment variables
   - Inspect deployment metadata
   - Analyze system health endpoints

3) **Validate state consistency**: Confirm multiple indicators agree
   - Cross-reference multiple state signals
   - Detect conflicting indicators (e.g., prod config with debug=true)
   - Note partial or transitional states

4) **Assess state stability**: Determine if state is stable or transient
   - Check for maintenance mode indicators
   - Look for state transition markers
   - Identify temporary overrides

5) **Ground claims**: Attach evidence anchors to state indicators
   - Format: `file:line`, `env:VAR_NAME`, or `endpoint:path`
   - Quote the specific indicator values

6) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
detected: boolean  # True if world state is confirmed
target_type: world
instances:
  - id: string  # State identifier (e.g., "production", "maintenance")
    type: string  # environment, deployment, runtime, infrastructure
    attributes:
      environment: string | null  # prod, staging, dev, test
      region: string | null  # Geographic or logical region
      version: string | null  # Deployed version if detectable
      stability: stable | transitional | degraded
    location: string  # Primary evidence location
    confidence: number  # 0.0-1.0 for this state
signals:
  - signal: string  # State indicator found
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
| `detected` | boolean | Whether the target world state was confirmed |
| `instances` | array | Detected world state details |
| `signals` | array | Raw indicators of world state |
| `false_positive_risk` | enum | Risk that state detection is incorrect |
| `confidence` | number | 0.0-1.0 based on indicator consistency |
| `evidence_anchors` | array[string] | References to state indicators |
| `assumptions` | array[string] | Stated assumptions about state signals |

## Examples

### Example 1: Detecting Production Environment

**Input:**
```yaml
target: "/app/config/"
world_state: "production"
```

**Output:**
```yaml
detected: true
target_type: world
instances:
  - id: "production"
    type: environment
    attributes:
      environment: "production"
      region: "us-east-1"
      version: "v2.4.1"
      stability: stable
    location: "config/environment.yaml"
    confidence: 0.95
signals:
  - signal: "RAILS_ENV=production in environment.yaml"
    strength: high
    location: "config/environment.yaml:3"
  - signal: "Database URL points to prod-db.internal"
    strength: high
    location: "config/database.yaml:5"
  - signal: "LOG_LEVEL=warn (production default)"
    strength: medium
    location: "config/logging.yaml:2"
  - signal: "Feature flag 'debug_mode' is false"
    strength: medium
    location: "config/features.yaml:15"
false_positive_risk: low
confidence: 0.94
evidence_anchors:
  - "config/environment.yaml:3"
  - "config/database.yaml:5"
  - "config/logging.yaml:2"
  - "config/features.yaml:15"
assumptions:
  - "Configuration files reflect actual runtime environment"
  - "Production indicated by RAILS_ENV value"
```

**Evidence pattern:** Multi-signal environment detection from configuration files.

---

### Example 2: Detecting Degraded System State

**Input:**
```yaml
target: "system health and logs"
world_state: "degraded"
state_indicators:
  - "error rate > 5%"
  - "response time > 2s"
  - "circuit breaker open"
```

**Output:**
```yaml
detected: true
target_type: world
instances:
  - id: "degraded-partial"
    type: runtime
    attributes:
      environment: "production"
      region: "us-west-2"
      version: "v2.4.1"
      stability: degraded
    location: "metrics/dashboard"
    confidence: 0.88
signals:
  - signal: "Error rate: 8.3% (threshold: 5%)"
    strength: high
    location: "metrics/errors.json:latest"
  - signal: "P99 response time: 3.2s (threshold: 2s)"
    strength: high
    location: "metrics/latency.json:latest"
  - signal: "Circuit breaker 'payment-service': OPEN"
    strength: high
    location: "health/circuit-breakers:payment-service"
  - signal: "Downstream dependency 'payment-api' returning 503"
    strength: high
    location: "logs/app.log:45231"
false_positive_risk: low
confidence: 0.92
evidence_anchors:
  - "metrics/errors.json:latest"
  - "metrics/latency.json:latest"
  - "health/circuit-breakers:payment-service"
  - "logs/app.log:45231"
assumptions:
  - "Metrics are current (within last 5 minutes)"
  - "Circuit breaker OPEN state indicates active degradation"
```

**Evidence pattern:** Multi-indicator health assessment from metrics and logs.

---

### Example 3: Detecting Maintenance Mode

**Input:**
```yaml
target: "/etc/app/flags/"
world_state: "maintenance"
```

**Output:**
```yaml
detected: false
target_type: world
instances: []
signals:
  - signal: "maintenance_mode flag file not present"
    strength: high
    location: "/etc/app/flags/"
  - signal: "No scheduled maintenance in cron"
    strength: medium
    location: "/etc/cron.d/maintenance"
  - signal: "Health endpoint returns 200 OK"
    strength: high
    location: "health:endpoint"
false_positive_risk: low
confidence: 0.90
evidence_anchors:
  - "/etc/app/flags/"
  - "/etc/cron.d/maintenance"
assumptions:
  - "Maintenance mode indicated by flag file"
  - "System is operational if health check passes"
```

**Evidence pattern:** Flag file and health check inspection.

---

### Example 4: Detecting Development Environment with Conflicts

**Input:**
```yaml
target: "/project/"
world_state: "development"
```

**Output:**
```yaml
detected: true
target_type: world
instances:
  - id: "development"
    type: environment
    attributes:
      environment: "development"
      region: null
      version: "local"
      stability: stable
    location: ".env.local"
    confidence: 0.75
signals:
  - signal: "NODE_ENV=development in .env.local"
    strength: high
    location: ".env.local:1"
  - signal: "localhost URLs in configuration"
    strength: high
    location: "config/api.yaml:3"
  - signal: "WARNING: Production database URL also present"
    strength: high
    location: "config/database.yaml:8"
false_positive_risk: high
confidence: 0.75
evidence_anchors:
  - ".env.local:1"
  - "config/api.yaml:3"
  - "config/database.yaml:8"
assumptions:
  - "Development indicated by NODE_ENV value"
  - "Production DB URL is likely a configuration error"
next_actions:
  - "Verify database.yaml is not accidentally pointing to production"
  - "Ensure .env.local overrides take precedence"
```

**Evidence pattern:** Environment detection with conflicting indicator flagged.

## Verification

- [ ] Output contains `detected` boolean field
- [ ] State indicators are consistent (or conflicts noted)
- [ ] Evidence anchors reference actual configuration/environment sources
- [ ] Stability assessment reflects detected state consistency
- [ ] Conflicting signals are explicitly reported

**Verification tools:** Read (for config inspection), Grep (for indicator search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive environment variables (API keys, secrets) in output
- Note when production state is detected to prevent accidental modifications
- If detecting security-relevant states (debug mode in prod), flag as warning
- Do not execute commands to query system state; use only static analysis

## Composition Patterns

**Commonly follows:**
- `inspect` - After examining project structure to locate config files
- `retrieve` - After fetching environment or deployment metadata

**Commonly precedes:**
- `identify-world` - When detection confirms a state, identify its full context
- `constrain` - When applying state-specific constraints to operations
- `verify` - When validating operations are appropriate for the detected state

**Anti-patterns:**
- Never use to detect state then proceed with production operations without confirmation
- Avoid combining with `act` before verifying state is appropriate

**Workflow references:**
- See `workflow_catalog.json#environment-gate` for deployment safety checks
- See `workflow_catalog.json#incident-response` for degraded state detection
