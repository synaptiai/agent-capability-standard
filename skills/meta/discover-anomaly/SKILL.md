---
name: discover-anomaly
description: Discover anomalies, outliers, or unexpected patterns without predefined expectations. Use when exploring data for irregularities, finding unusual behaviors, or detecting deviations from norms.
argument-hint: "[data_source] [baseline] [sensitivity]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Identify unexpected patterns, outliers, or deviations in data without requiring predefined rules or thresholds, using statistical analysis, pattern recognition, and domain-aware heuristics.

**Success criteria:**
- Anomalies are identified with evidence and context
- Each finding is assessed for significance and potential cause
- False positive likelihood is evaluated
- Actionable next steps are provided for investigation

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data_source` | Yes | string\|object | Data to analyze (file, directory, dataset) |
| `baseline` | No | object | Expected normal behavior for comparison |
| `sensitivity` | No | string | Detection sensitivity: low, medium, high (default: medium) |
| `domain_context` | No | string | Domain knowledge to inform anomaly detection |
| `focus_areas` | No | array[string] | Specific attributes or patterns to examine |

## Procedure

1) **Establish context**: Understand the data domain
   - Identify data type and structure
   - Note expected patterns and distributions
   - Define what "normal" looks like (explicit or inferred)

2) **Statistical analysis**: Quantitative anomaly detection
   - Distribution analysis (outliers beyond 2-3 sigma)
   - Time series analysis (trend breaks, seasonality violations)
   - Frequency analysis (rare values, unexpected patterns)

3) **Pattern analysis**: Structural anomaly detection
   - Sequence anomalies (unexpected order, missing steps)
   - Structural anomalies (malformed records, schema violations)
   - Relationship anomalies (unexpected associations)

4) **Domain-aware heuristics**: Context-specific checks
   - Business rule violations
   - Common error patterns in the domain
   - Impossible or implausible values

5) **Assess each anomaly**: Evaluate significance
   - Severity: How far from normal?
   - Impact: What could this indicate?
   - False positive risk: How likely is this benign?

6) **Generate hypotheses**: Explain possible causes
   - Data quality issues
   - Process failures
   - Genuine exceptional events
   - Security/integrity concerns

## Output Contract

Return a structured object:

```yaml
discoveries:
  - id: string
    type: statistical | structural | behavioral | domain_specific
    subtype: string  # outlier, sequence_break, schema_violation, etc.
    description: string
    location: string  # Where found
    observed_value: string | number | object
    expected_value: string | number | object | null
    deviation: string  # How far from normal
    significance: low | medium | high | critical
    novelty: known | suspected | surprising
    false_positive_risk: low | medium | high
    evidence:
      - type: string
        location: string
        details: string
    hypotheses:
      - explanation: string
        likelihood: low | medium | high
        investigation_steps: array[string]
analysis_context:
  data_summary:
    total_records: integer
    date_range: string | null
    key_attributes: array[string]
  baseline_used: string  # Explicit, inferred, or none
  detection_methods: array[string]
anomaly_summary:
  total_found: integer
  by_severity:
    critical: integer
    high: integer
    medium: integer
    low: integer
  by_type: object
patterns_observed:
  - pattern: string
    affected_anomalies: array[string]  # IDs of related anomalies
    interpretation: string
recommendations:
  - action: string
    target_anomaly: string | null  # null if general
    priority: low | medium | high | critical
    rationale: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `discoveries` | array | Individual anomalies found |
| `analysis_context` | object | Data and methodology context |
| `anomaly_summary` | object | Aggregate statistics |
| `patterns_observed` | array | Cross-anomaly patterns |
| `recommendations` | array | Suggested investigation steps |
| `confidence` | number | 0.0-1.0 based on detection reliability |
| `evidence_anchors` | array[string] | All evidence locations |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Discovering Log Anomalies

**Input:**
```yaml
data_source: "logs/application-2024-01.log"
sensitivity: "medium"
domain_context: "Web application access logs"
focus_areas:
  - "response_times"
  - "error_rates"
  - "user_behavior"
```

**Output:**
```yaml
discoveries:
  - id: "anom-001"
    type: statistical
    subtype: "outlier"
    description: "Response times spike to 15-30 seconds between 02:00-02:45 UTC on Jan 15"
    location: "logs/application-2024-01.log:45892-46234"
    observed_value: "avg 22.3s (peak 31.2s)"
    expected_value: "avg 0.3s (p99 1.2s)"
    deviation: "74x baseline average"
    significance: high
    novelty: surprising
    false_positive_risk: low
    evidence:
      - type: "statistical"
        location: "logs/application-2024-01.log:45892"
        details: "342 requests with response time > 10s in 45-minute window"
    hypotheses:
      - explanation: "Database connection pool exhaustion"
        likelihood: high
        investigation_steps:
          - "Check database metrics for Jan 15 02:00 UTC"
          - "Review connection pool configuration"
          - "Look for long-running queries"
      - explanation: "External service dependency timeout"
        likelihood: medium
        investigation_steps:
          - "Check external service logs"
          - "Review timeout configurations"
  - id: "anom-002"
    type: behavioral
    subtype: "unusual_sequence"
    description: "User ID 8847 made 2,847 API calls in 10 minutes with sequential resource IDs"
    location: "logs/application-2024-01.log:78234-78956"
    observed_value: "284.7 requests/minute"
    expected_value: "5-20 requests/minute for active users"
    deviation: "14-57x normal activity"
    significance: critical
    novelty: surprising
    false_positive_risk: low
    evidence:
      - type: "pattern"
        location: "logs/application-2024-01.log:78234"
        details: "Sequential GET /api/resources/{id} from id=1 to id=2847"
      - type: "behavioral"
        location: "logs/application-2024-01.log:78500"
        details: "No pause between requests, automated pattern"
    hypotheses:
      - explanation: "Automated data scraping attack"
        likelihood: high
        investigation_steps:
          - "Block user ID 8847 pending investigation"
          - "Review data accessed for sensitivity"
          - "Check for rate limiting bypass"
      - explanation: "Legitimate bulk export by authorized user"
        likelihood: low
        investigation_steps:
          - "Verify user 8847 role and permissions"
          - "Check for approved bulk operations"
  - id: "anom-003"
    type: statistical
    subtype: "frequency_anomaly"
    description: "404 errors increased 340% on Jan 20, concentrated on /api/v2/* endpoints"
    location: "logs/application-2024-01.log:112000-115000"
    observed_value: "1,247 404 errors (34% of requests)"
    expected_value: "~280 404 errors (8% baseline)"
    deviation: "4.4x baseline error rate"
    significance: medium
    novelty: suspected
    false_positive_risk: medium
    evidence:
      - type: "statistical"
        location: "logs/application-2024-01.log:112000"
        details: "Error rate jumped from 8% to 34% at 14:00 UTC"
      - type: "pattern"
        location: "logs/application-2024-01.log:113500"
        details: "89% of 404s are for /api/v2/users/* endpoints"
    hypotheses:
      - explanation: "API endpoint renamed or removed in deployment"
        likelihood: high
        investigation_steps:
          - "Check deployment history for Jan 20"
          - "Compare v2 endpoints before/after"
          - "Review API documentation updates"
      - explanation: "Client using deprecated endpoint version"
        likelihood: medium
        investigation_steps:
          - "Identify which clients are hitting v2"
          - "Check client version distribution"
  - id: "anom-004"
    type: structural
    subtype: "schema_violation"
    description: "23 log entries have malformed JSON in request body field"
    location: "scattered (see evidence)"
    observed_value: "23 malformed entries"
    expected_value: "0 (all entries should be valid JSON)"
    deviation: "any non-zero is anomalous"
    significance: low
    novelty: known
    false_positive_risk: high
    evidence:
      - type: "structural"
        location: "logs/application-2024-01.log:5432"
        details: "request_body: '{\"user\": \"test' (truncated)"
      - type: "structural"
        location: "logs/application-2024-01.log:67891"
        details: "request_body: 'null' (string instead of null)"
    hypotheses:
      - explanation: "Log truncation at buffer boundary"
        likelihood: high
        investigation_steps:
          - "Check log buffer configuration"
          - "Verify log rotation settings"
      - explanation: "Application logging bug"
        likelihood: medium
        investigation_steps:
          - "Review logging library version"
          - "Check for known issues"
analysis_context:
  data_summary:
    total_records: 2847563
    date_range: "2024-01-01 to 2024-01-31"
    key_attributes: ["timestamp", "response_time", "status_code", "user_id", "endpoint"]
  baseline_used: "Inferred from first 7 days of January (stable period)"
  detection_methods:
    - "Statistical: Z-score analysis for response times"
    - "Behavioral: Request frequency per user"
    - "Pattern: Sequential ID detection"
    - "Structural: JSON validation"
anomaly_summary:
  total_found: 4
  by_severity:
    critical: 1
    high: 1
    medium: 1
    low: 1
  by_type:
    statistical: 2
    behavioral: 1
    structural: 1
patterns_observed:
  - pattern: "All high-severity anomalies occurred during off-hours (02:00-03:00 UTC)"
    affected_anomalies: ["anom-001"]
    interpretation: "May indicate automated processes or attacks during low-traffic periods"
  - pattern: "Anomalies cluster around mid-month"
    affected_anomalies: ["anom-001", "anom-002"]
    interpretation: "Possible correlation with deployment or maintenance schedule"
recommendations:
  - action: "Immediately investigate user 8847 activity for potential data breach"
    target_anomaly: "anom-002"
    priority: critical
    rationale: "Pattern strongly suggests automated scraping of sequential resources"
  - action: "Review database performance for Jan 15 incident"
    target_anomaly: "anom-001"
    priority: high
    rationale: "Prolonged response time degradation affects user experience and SLAs"
  - action: "Implement rate limiting if not present"
    target_anomaly: null
    priority: high
    rationale: "Multiple anomalies could have been prevented or detected earlier with rate limits"
  - action: "Audit API v2 deprecation communication"
    target_anomaly: "anom-003"
    priority: medium
    rationale: "High 404 rate suggests clients were not properly notified of changes"
confidence: 0.8
evidence_anchors:
  - "logs/application-2024-01.log:45892"
  - "logs/application-2024-01.log:46234"
  - "logs/application-2024-01.log:78234"
  - "logs/application-2024-01.log:78956"
  - "logs/application-2024-01.log:112000"
  - "logs/application-2024-01.log:115000"
  - "logs/application-2024-01.log:5432"
  - "logs/application-2024-01.log:67891"
assumptions:
  - "Log timestamps are accurate and in UTC"
  - "First 7 days represent normal baseline behavior"
  - "User IDs are unique and consistent"
  - "Response times are measured in seconds"
```

**Evidence pattern:** Statistical analysis + behavioral pattern matching + structural validation

## Verification

- [ ] Each anomaly has evidence with specific locations
- [ ] Hypotheses are plausible given the evidence
- [ ] False positive risk assessment is realistic
- [ ] Severity ratings align with potential impact
- [ ] Recommendations are actionable

**Verification tools:** Read (for data inspection), Grep (for pattern searching)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Mark automated detection distinctly from manual analysis
- Include false positive assessment for all findings
- Do not access data outside specified search scope
- Flag potential security/privacy implications immediately

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather data for analysis
- `search` - to locate relevant data sources
- `identify-entity` - to understand data structure

**Commonly precedes:**
- `identify-anomaly` - to classify specific anomalies
- `critique` - to evaluate anomaly implications
- `generate-plan` - to plan investigation or remediation

**Anti-patterns:**
- Never claim comprehensive anomaly detection (always bounded)
- Avoid single-method detection (combine approaches)

**Workflow references:**
- See `workflow_catalog.json#incident_investigation` for security workflows
- See `workflow_catalog.json#data_quality_audit` for data analysis
