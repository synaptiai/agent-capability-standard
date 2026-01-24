---
name: identify-world
description: Identify and classify the current world state, environmental context, or system configuration. Use when determining environment type, classifying system state, identifying deployment context, or resolving runtime configuration.
argument-hint: "[target-context] [state-category] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and fully characterize the world state or environmental context based on available evidence. This answers "what is the complete state of this environment?" including environment type, configuration, health status, and relevant metadata.

**Success criteria:**
- Complete world state identification with environment classification
- Match quality assessment (exact, probable, possible, no match)
- Configuration details and runtime characteristics
- Alternative state interpretations when uncertain

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The context to identify (project path, system, deployment, environment) |
| `state_category` | No | string | Category to identify: environment, deployment, health, configuration (default: all) |
| `constraints` | No | object | Identification parameters: include_secrets=false, depth, scope |

## Procedure

1) **Gather environment signals**: Collect indicators of world state
   - Environment variables: NODE_ENV, RAILS_ENV, ENVIRONMENT
   - Configuration files: .env, config/*.yaml, settings.json
   - System metadata: hostname, domain, cloud provider
   - Runtime indicators: log levels, feature flags, debug modes

2) **Classify environment type**: Determine the primary environment category
   - Production: live customer-facing system
   - Staging: pre-production testing environment
   - Development: local or shared development environment
   - Test: automated testing environment
   - CI/CD: continuous integration environment

3) **Extract configuration state**: Identify key configuration values
   - Database connections (without credentials)
   - API endpoints and versions
   - Feature toggles and experiments
   - Integration settings

4) **Assess system health**: Determine operational status
   - Healthy: all systems nominal
   - Degraded: partial functionality
   - Maintenance: planned downtime
   - Failed: critical issues

5) **Determine deployment context**: Identify deployment characteristics
   - Version: deployed software version
   - Region: geographic or logical region
   - Scale: instance count, capacity
   - Last deployed: deployment timestamp

6) **Assess identification confidence**: Determine match quality
   - Exact: consistent signals across multiple sources
   - Probable: primary signals agree, minor inconsistencies
   - Possible: conflicting signals or limited evidence
   - No match: cannot determine state

7) **Ground claims**: Attach evidence anchors to identification
   - Format: `config:path`, `env:VAR`, or `system:attribute`
   - Quote specific values supporting classification

8) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Environment identifier
  type: string  # environment, deployment, runtime
  canonical_name: string  # Environment name (e.g., "Production US-East")
  attributes:
    environment: string  # production, staging, development, test
    region: string | null  # Geographic or logical region
    version: string | null  # Deployed version
    health: healthy | degraded | maintenance | failed
    cloud_provider: string | null  # aws, gcp, azure, on-prem
    configuration:
      key_settings: object  # Important non-sensitive config
      feature_flags: object | null  # Active feature toggles
    last_deployed: string | null  # ISO timestamp
  namespace: string | null  # Organization or project context
match_quality: exact | probable | possible | no_match
alternatives:
  - entity:
      id: string
      canonical_name: string
      attributes: object
    probability: number  # 0.0-1.0
disambiguation_signals: array[string]  # Why this identification
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified world state with full context |
| `match_quality` | enum | Confidence category for the identification |
| `alternatives` | array | Other possible state interpretations |
| `disambiguation_signals` | array | Reasons supporting the identification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to state evidence |
| `assumptions` | array[string] | Stated assumptions about environment |

## Examples

### Example 1: Identifying Production Environment

**Input:**
```yaml
target: "/app/"
state_category: "all"
```

**Output:**
```yaml
entity:
  id: "prod-us-east-1"
  type: environment
  canonical_name: "Production US-East-1"
  attributes:
    environment: "production"
    region: "us-east-1"
    version: "v2.4.1"
    health: healthy
    cloud_provider: "aws"
    configuration:
      key_settings:
        log_level: "warn"
        cache_enabled: true
        rate_limit: 1000
      feature_flags:
        new_checkout: true
        beta_dashboard: false
    last_deployed: "2024-01-15T10:30:00Z"
  namespace: "company/main-app"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "RAILS_ENV=production in environment config"
  - "Database URL contains 'prod-db.internal'"
  - "AWS region detected from instance metadata"
  - "Version v2.4.1 from deployed manifest"
  - "All health checks passing"
confidence: 0.96
evidence_anchors:
  - "config/environment.yaml:3"
  - "config/database.yaml:5"
  - "aws:instance-metadata"
  - "manifest.json:version"
  - "health:endpoint"
assumptions:
  - "Configuration files reflect actual runtime state"
  - "Health endpoint is authoritative for status"
```

**Evidence pattern:** Multi-source environment identification with health verification.

---

### Example 2: Identifying Development Environment

**Input:**
```yaml
target: "/project/"
state_category: "environment"
```

**Output:**
```yaml
entity:
  id: "local-dev"
  type: environment
  canonical_name: "Local Development"
  attributes:
    environment: "development"
    region: null
    version: "local-uncommitted"
    health: healthy
    cloud_provider: null
    configuration:
      key_settings:
        log_level: "debug"
        cache_enabled: false
        hot_reload: true
      feature_flags:
        all_features: true
    last_deployed: null
  namespace: "local"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "NODE_ENV=development in .env.local"
  - "localhost URLs in API configuration"
  - "Debug mode enabled"
  - "Hot reload active"
  - "Git shows uncommitted changes"
confidence: 0.94
evidence_anchors:
  - ".env.local:1"
  - "config/api.yaml:3"
  - "config/debug.yaml:1"
assumptions:
  - ".env.local takes precedence over .env"
  - "Local development indicated by localhost URLs"
```

**Evidence pattern:** Local environment detection with development indicators.

---

### Example 3: Identifying CI/CD Environment

**Input:**
```yaml
target: "current execution context"
state_category: "deployment"
```

**Output:**
```yaml
entity:
  id: "github-actions-run-12345"
  type: deployment
  canonical_name: "GitHub Actions CI Run"
  attributes:
    environment: "ci"
    region: "github-hosted"
    version: "pr-456"
    health: healthy
    cloud_provider: "github"
    configuration:
      key_settings:
        runner: "ubuntu-latest"
        node_version: "18"
        test_parallelism: 4
      feature_flags: null
    last_deployed: null
  namespace: "github/org/repo"
match_quality: exact
alternatives:
  - entity:
      canonical_name: "Self-Hosted Runner"
      attributes:
        cloud_provider: "self-hosted"
    probability: 0.05
disambiguation_signals:
  - "GITHUB_ACTIONS=true environment variable"
  - "CI=true standard indicator"
  - "GITHUB_RUN_ID=12345 identifies run"
  - "GITHUB_REF=refs/pull/456 indicates PR context"
confidence: 0.98
evidence_anchors:
  - "env:GITHUB_ACTIONS"
  - "env:CI"
  - "env:GITHUB_RUN_ID"
  - ".github/workflows/ci.yml"
assumptions:
  - "GitHub Actions environment variables are authoritative"
  - "Workflow file reflects actual configuration"
```

**Evidence pattern:** CI environment detection from environment variables.

---

### Example 4: Identifying Degraded State

**Input:**
```yaml
target: "production system"
state_category: "health"
```

**Output:**
```yaml
entity:
  id: "prod-degraded-2024-01-15"
  type: runtime
  canonical_name: "Production (Degraded)"
  attributes:
    environment: "production"
    region: "us-west-2"
    version: "v2.4.1"
    health: degraded
    cloud_provider: "aws"
    configuration:
      key_settings:
        circuit_breaker: "open:payment-service"
        fallback_mode: true
      feature_flags:
        checkout_disabled: true
    last_deployed: "2024-01-14T18:00:00Z"
  namespace: "company/main-app"
match_quality: exact
alternatives:
  - entity:
      canonical_name: "Production (Maintenance)"
      attributes:
        health: maintenance
    probability: 0.15
disambiguation_signals:
  - "Circuit breaker OPEN for payment-service"
  - "Fallback mode enabled"
  - "Checkout feature flag disabled (degraded response)"
  - "Error rate elevated but not critical"
  - "Not in scheduled maintenance window"
confidence: 0.88
evidence_anchors:
  - "health:circuit-breakers:payment-service"
  - "config/runtime-flags.yaml"
  - "metrics:error_rate"
  - "maintenance-schedule.json"
assumptions:
  - "Circuit breaker OPEN indicates service issue"
  - "Not maintenance since no scheduled window"
next_actions:
  - "Monitor for recovery of payment-service"
  - "Check incident status for root cause"
```

**Evidence pattern:** Health status identification with degradation signals.

---

### Example 5: Conflicting State Signals

**Input:**
```yaml
target: "/project/"
state_category: "environment"
```

**Output:**
```yaml
entity:
  id: "ambiguous-state"
  type: environment
  canonical_name: "Development (with Production Database)"
  attributes:
    environment: "development"
    region: null
    version: "local"
    health: healthy
    cloud_provider: null
    configuration:
      key_settings:
        log_level: "debug"
        database_warning: "PRODUCTION DATABASE CONFIGURED"
      feature_flags: null
    last_deployed: null
  namespace: "local"
match_quality: possible
alternatives:
  - entity:
      canonical_name: "Misconfigured Development"
      attributes:
        environment: "misconfigured"
    probability: 0.40
disambiguation_signals:
  - "NODE_ENV=development indicates development"
  - "WARNING: Database URL contains 'prod-db'"
  - "Conflicting signals between env and database"
  - "Likely configuration error"
confidence: 0.55
evidence_anchors:
  - ".env:NODE_ENV"
  - ".env:DATABASE_URL"
assumptions:
  - "Development environment should not use production database"
  - "This is likely a dangerous misconfiguration"
next_actions:
  - "URGENT: Verify database configuration"
  - "Confirm this is intentional before proceeding"
  - "Check for .env.local override"
```

**Evidence pattern:** Conflict detection with warning.

## Verification

- [ ] Environment classification is accurate and consistent
- [ ] Health status reflects actual system state
- [ ] Configuration is extracted without exposing secrets
- [ ] Conflicts between signals are explicitly reported
- [ ] Evidence anchors reference actual state sources

**Verification tools:** Read (for configuration inspection), Grep (for indicator search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never expose credentials, API keys, or secrets in output
- Flag production environment identification prominently
- Warn if conflicting environment signals detected (potential misconfiguration)
- Note when identification could inform destructive operations
- If production database in development context, issue urgent warning

## Composition Patterns

**Commonly follows:**
- `detect-world` - After confirming a state exists, fully identify it
- `inspect` - After examining project structure

**Commonly precedes:**
- `constrain` - When applying environment-appropriate constraints
- `verify` - When validating operations are appropriate for environment
- `act` - When environment context affects action behavior

**Anti-patterns:**
- Never use to identify state then proceed with production changes without confirmation
- Avoid identifying environments with insufficient signals

**Workflow references:**
- See `workflow_catalog.json#deployment-safety` for environment-aware deployments
- See `workflow_catalog.json#incident-context` for runtime state identification
