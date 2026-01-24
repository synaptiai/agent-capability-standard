---
name: identify-anomaly
description: Identify and classify an anomaly, determining its type, category, and characteristics. Use when categorizing deviations, classifying outliers, naming violations, or determining anomaly types.
argument-hint: "[target-anomaly] [classification-context] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and name an anomaly based on available evidence, determining what type of deviation or violation it represents. This answers "what kind of anomaly is this?" rather than just confirming anomaly presence.

**Success criteria:**
- Clear anomaly classification with type and category
- Match quality assessment (exact, probable, possible, no match)
- Alternative classifications with probabilities when uncertain
- Root cause indicators when identifiable

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The anomaly to identify (data point, pattern, violation) |
| `context` | No | string\|object | Context for classification (expected behavior, baseline, domain) |
| `constraints` | No | object | Classification parameters: taxonomy, include_severity, max_alternatives |

## Procedure

1) **Extract anomaly characteristics**: Gather attributes of the deviation
   - Magnitude: how far from normal (percentage, std deviations)
   - Pattern: sudden, gradual, cyclical, random
   - Scope: isolated, widespread, correlated
   - Duration: momentary, persistent, recurring

2) **Classify anomaly type**: Determine the category of anomaly
   - Statistical: outlier, distribution shift, trend break
   - Structural: schema violation, missing field, type mismatch
   - Behavioral: sequence violation, timing anomaly, rate anomaly
   - Semantic: invalid value, constraint violation, logic error

3) **Assess anomaly severity**: Determine impact level
   - Critical: system failure, data corruption, security breach
   - High: service degradation, data quality issue
   - Medium: performance impact, minor deviation
   - Low: cosmetic issue, acceptable variation

4) **Identify potential root causes**: Suggest underlying reasons
   - Configuration errors
   - Code bugs
   - External factors (load, dependencies)
   - Data quality issues

5) **Assess classification confidence**: Determine match quality
   - Exact: clear anomaly type with unambiguous characteristics
   - Probable: strong classification with minor ambiguities
   - Possible: multiple plausible types or weak signals
   - No match: anomaly cannot be classified

6) **Ground claims**: Attach evidence anchors to classification
   - Format: `data:location` or `metric:name:timestamp`
   - Include both the anomaly and the baseline comparison

7) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Anomaly identifier
  type: string  # Anomaly type classification
  canonical_name: string  # Human-readable anomaly name
  attributes:
    category: string  # statistical, structural, behavioral, semantic
    severity: low | medium | high | critical
    pattern: string  # sudden, gradual, cyclical, persistent
    magnitude: string  # Deviation description
    scope: string  # isolated, correlated, widespread
    probable_cause: string | null  # Root cause if identifiable
  namespace: string | null  # System or data context
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
| `entity` | object | The identified anomaly with attributes |
| `match_quality` | enum | Confidence category for the classification |
| `alternatives` | array | Other possible classifications with probabilities |
| `disambiguation_signals` | array | Reasons supporting the classification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to anomaly evidence |
| `assumptions` | array[string] | Stated assumptions about anomaly type |

## Examples

### Example 1: Identifying Performance Anomaly

**Input:**
```yaml
target:
  metric: "response_time_p99"
  value: 4500
  baseline_mean: 200
  baseline_std: 50
  timestamp: "2024-01-15T14:32:00Z"
context: "API performance metrics"
```

**Output:**
```yaml
entity:
  id: "perf-anomaly-2024-01-15T14:32"
  type: latency_spike
  canonical_name: "Response Time Spike"
  attributes:
    category: "statistical"
    severity: critical
    pattern: "sudden"
    magnitude: "86 standard deviations above mean"
    scope: "widespread"
    probable_cause: "Resource exhaustion or downstream dependency failure"
  namespace: "api/performance"
match_quality: exact
alternatives:
  - entity:
      type: system_overload
      canonical_name: "System Overload"
      attributes:
        category: "behavioral"
        severity: critical
    probability: 0.35
disambiguation_signals:
  - "P99 latency 22.5x above baseline mean"
  - "Sudden spike suggests trigger event, not gradual degradation"
  - "86 std dev indicates extreme outlier, not normal variation"
confidence: 0.94
evidence_anchors:
  - "metrics:response_time_p99:2024-01-15T14:32"
  - "baseline:response_time:last_7d"
assumptions:
  - "Baseline represents normal operation"
  - "Single metric spike, not examining correlated metrics"
next_actions:
  - "Check CPU/memory metrics for resource exhaustion"
  - "Examine downstream service health"
  - "Review error logs around timestamp"
```

**Evidence pattern:** Statistical deviation analysis with severity assessment.

---

### Example 2: Identifying Schema Anomaly

**Input:**
```yaml
target:
  field: "user.age"
  value: "twenty-five"
  expected_type: "integer"
context: "User data validation"
```

**Output:**
```yaml
entity:
  id: "schema-anomaly-user-age"
  type: type_mismatch
  canonical_name: "Type Mismatch Error"
  attributes:
    category: "structural"
    severity: medium
    pattern: "persistent"
    magnitude: "string instead of integer"
    scope: "isolated"
    probable_cause: "Data entry error or API contract violation"
  namespace: "data/users"
match_quality: exact
alternatives:
  - entity:
      type: format_violation
      canonical_name: "Format Violation"
      attributes:
        category: "semantic"
    probability: 0.20
disambiguation_signals:
  - "Value 'twenty-five' is string, expected integer"
  - "Structural type mismatch, not just format issue"
  - "Could be parsed if format validation (age spelled out)"
confidence: 0.92
evidence_anchors:
  - "data:user.age"
  - "schema:user.json:age"
assumptions:
  - "Schema is authoritative definition"
  - "Value should not be text representation of number"
```

**Evidence pattern:** Type system validation with schema reference.

---

### Example 3: Identifying Behavioral Anomaly

**Input:**
```yaml
target:
  pattern: "User logged in 47 times in 1 minute"
  actor: "user_12345"
  baseline: "Normal: 1-3 logins per day"
context: "Security monitoring"
```

**Output:**
```yaml
entity:
  id: "behavior-anomaly-user-12345"
  type: rate_anomaly
  canonical_name: "Abnormal Login Rate"
  attributes:
    category: "behavioral"
    severity: high
    pattern: "sudden"
    magnitude: "1000x normal rate"
    scope: "isolated"
    probable_cause: "Automated script, credential stuffing, or session bug"
  namespace: "security/authentication"
match_quality: probable
alternatives:
  - entity:
      type: credential_stuffing_attack
      canonical_name: "Credential Stuffing Attack"
      attributes:
        category: "security"
        severity: critical
    probability: 0.40
  - entity:
      type: session_loop_bug
      canonical_name: "Session Loop Bug"
      attributes:
        category: "application_error"
        severity: medium
    probability: 0.25
disambiguation_signals:
  - "47 logins/minute vs 1-3 logins/day is extreme deviation"
  - "Could be attack or application bug"
  - "Need additional context (IP, success/fail ratio) to confirm attack"
confidence: 0.75
evidence_anchors:
  - "auth.log:user_12345"
  - "baseline:login_rate"
assumptions:
  - "All 47 logins are from same user account"
  - "Baseline represents legitimate user behavior"
next_actions:
  - "Check if logins are successes or failures"
  - "Examine source IP addresses for bot pattern"
  - "Review application logs for session errors"
```

**Evidence pattern:** Rate analysis with security context.

---

### Example 4: Identifying Data Quality Anomaly

**Input:**
```yaml
target:
  field: "order.total"
  value: -500.00
  constraint: "total >= 0"
context: "Order processing system"
```

**Output:**
```yaml
entity:
  id: "data-anomaly-negative-total"
  type: constraint_violation
  canonical_name: "Negative Order Total"
  attributes:
    category: "semantic"
    severity: high
    pattern: "isolated"
    magnitude: "Negative value where positive expected"
    scope: "isolated"
    probable_cause: "Refund processing error or calculation bug"
  namespace: "orders/validation"
match_quality: exact
alternatives:
  - entity:
      type: refund_record
      canonical_name: "Misclassified Refund"
      attributes:
        category: "data_classification"
        severity: low
    probability: 0.30
disambiguation_signals:
  - "Order total cannot be negative by business rule"
  - "May be refund incorrectly stored as order"
  - "Constraint violation is definitive anomaly"
confidence: 0.88
evidence_anchors:
  - "orders:123456:total"
  - "schema:order:constraints"
assumptions:
  - "This is an order record, not a refund"
  - "Constraint total >= 0 is correct business rule"
next_actions:
  - "Check if this should be a refund record instead"
  - "Review calculation logic for rounding errors"
```

**Evidence pattern:** Constraint validation with business rule context.

## Verification

- [ ] Anomaly type classification is from valid taxonomy
- [ ] Severity rating is justified by impact assessment
- [ ] Category accurately reflects anomaly nature
- [ ] Alternatives listed when match_quality is not "exact"
- [ ] Probable cause is grounded in evidence

**Verification tools:** Read (for data inspection), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive data values when describing anomalies
- Flag security-related anomalies for immediate review
- Note when anomaly classification has compliance implications
- If anomaly indicates data breach, follow incident response procedures

## Composition Patterns

**Commonly follows:**
- `detect-anomaly` - After confirming anomaly presence, classify its type
- `retrieve` - After fetching data containing anomalies

**Commonly precedes:**
- `critique` - When assessing anomaly risk and impact
- `mitigate` - When determining remediation for classified anomalies
- `audit` - When documenting anomalies for compliance

**Anti-patterns:**
- Never use to classify anomalies without understanding baseline
- Avoid classifying anomalies in domains without expertise

**Workflow references:**
- See `workflow_catalog.json#incident-triage` for anomaly classification in incidents
- See `workflow_catalog.json#data-quality` for data anomaly classification
