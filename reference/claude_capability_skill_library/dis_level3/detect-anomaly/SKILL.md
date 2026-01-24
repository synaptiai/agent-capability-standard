---
name: detect-anomaly
description: Detect whether anomalies, outliers, or violations exist in the given data relative to expected patterns. Use when checking for deviations, identifying outliers, validating conformance, or finding irregularities.
argument-hint: "[target-data] [baseline-pattern] [anomaly-threshold]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine whether anomalies, outliers, or deviations from expected patterns exist in the target data. This is an existence check that answers "is there something unusual here?" rather than classifying what type of anomaly it is.

**Success criteria:**
- Binary detection result (detected/not detected) with deviation metrics
- Evidence anchors pointing to specific anomalous data points
- Clear comparison between expected baseline and observed values

**Compatible schemas:**
- `docs/schemas/detect_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The data to scan for anomalies (metrics, logs, code, configuration) |
| `baseline` | No | string\|object | Expected pattern, normal range, or reference for comparison |
| `anomaly_type` | No | string | Type of anomaly: statistical, semantic, structural, behavioral, any (default: any) |
| `constraints` | No | object | Detection parameters: threshold, sensitivity, ignore_patterns |

## Procedure

1) **Establish baseline expectations**: Define what "normal" looks like
   - Statistical: mean, median, standard deviation, expected ranges
   - Semantic: expected values, valid enumerations, format patterns
   - Structural: expected schema, valid relationships, hierarchy
   - Behavioral: typical patterns, expected sequences, timing

2) **Scan for deviations**: Compare target data against baseline
   - Numeric outliers: values beyond N standard deviations
   - Format violations: unexpected data types, malformed entries
   - Missing elements: gaps in sequences, absent required fields
   - Unexpected patterns: spikes, drops, inversions, duplicates

3) **Assess anomaly significance**: Evaluate whether deviations are meaningful
   - Calculate deviation magnitude (how far from normal)
   - Consider context (is this deviation expected given circumstances?)
   - Check for known exceptions or acceptable variations

4) **Filter noise and false positives**: Exclude expected variations
   - Apply ignore_patterns for known acceptable deviations
   - Consider seasonal or cyclical patterns
   - Account for measurement precision limits

5) **Ground claims**: Attach evidence anchors to detected anomalies
   - Format: `file:line` or `data:index`
   - Include both the anomalous value and the expected value

6) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
detected: boolean  # True if anomaly/anomalies found
target_type: anomaly
instances:
  - id: string | null  # Anomaly identifier
    type: string  # statistical, semantic, structural, behavioral
    attributes:
      observed: string | number  # What was found
      expected: string | number  # What was expected
      deviation: string | number  # Magnitude of deviation
      severity: low | medium | high | critical
    location: string  # Where the anomaly was found
    confidence: number  # 0.0-1.0 for this instance
signals:
  - signal: string  # Anomaly indicator
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
| `detected` | boolean | Whether any anomaly was found |
| `instances` | array | List of detected anomalies with details |
| `signals` | array | Raw indicators suggesting anomalous behavior |
| `false_positive_risk` | enum | Risk that detection is incorrect |
| `confidence` | number | 0.0-1.0 based on deviation clarity |
| `evidence_anchors` | array[string] | References to anomalous data points |
| `assumptions` | array[string] | Stated assumptions about baseline expectations |

## Examples

### Example 1: Detecting Performance Anomaly in Metrics

**Input:**
```yaml
target: "/metrics/response_times.csv"
baseline:
  mean: 150
  std_dev: 25
  unit: "ms"
anomaly_type: "statistical"
constraints:
  threshold: 3  # standard deviations
```

**Output:**
```yaml
detected: true
target_type: anomaly
instances:
  - id: "metric-2024-01-15T14:32:00Z"
    type: statistical
    attributes:
      observed: 450
      expected: "150 +/- 75 (3 std dev)"
      deviation: "12 std deviations"
      severity: critical
    location: "response_times.csv:1542"
    confidence: 0.98
  - id: "metric-2024-01-15T14:33:00Z"
    type: statistical
    attributes:
      observed: 380
      expected: "150 +/- 75 (3 std dev)"
      deviation: "9.2 std deviations"
      severity: high
    location: "response_times.csv:1543"
    confidence: 0.97
signals:
  - signal: "Response time 450ms at 14:32:00, 12 std dev above mean"
    strength: high
    location: "response_times.csv:1542"
  - signal: "Consecutive anomalies suggest incident, not random spike"
    strength: high
    location: "response_times.csv:1542-1543"
false_positive_risk: low
confidence: 0.96
evidence_anchors:
  - "response_times.csv:1542"
  - "response_times.csv:1543"
assumptions:
  - "Baseline mean and std_dev represent normal operation"
  - "Anomalies beyond 3 std dev are significant"
```

**Evidence pattern:** Statistical comparison against provided baseline.

---

### Example 2: Detecting Schema Violation in Configuration

**Input:**
```yaml
target: "/config/database.yaml"
baseline: "Expected schema: host (string), port (integer 1-65535), ssl (boolean)"
anomaly_type: "structural"
```

**Output:**
```yaml
detected: true
target_type: anomaly
instances:
  - id: "schema-violation-port"
    type: structural
    attributes:
      observed: "port: 'not-a-number'"
      expected: "port: integer 1-65535"
      deviation: "type mismatch: string vs integer"
      severity: high
    location: "database.yaml:5"
    confidence: 0.99
  - id: "schema-violation-ssl"
    type: structural
    attributes:
      observed: "ssl: 'yes'"
      expected: "ssl: boolean (true/false)"
      deviation: "type mismatch: string vs boolean"
      severity: medium
    location: "database.yaml:7"
    confidence: 0.95
signals:
  - signal: "Field 'port' has string value, expected integer"
    strength: high
    location: "database.yaml:5"
  - signal: "Field 'ssl' has string 'yes', expected boolean"
    strength: high
    location: "database.yaml:7"
false_positive_risk: low
confidence: 0.94
evidence_anchors:
  - "database.yaml:5"
  - "database.yaml:7"
assumptions:
  - "Provided schema is the authoritative expected structure"
  - "YAML 'yes' without quotes should be boolean, with quotes is string"
```

**Evidence pattern:** Schema validation against expected structure.

---

### Example 3: Detecting Behavioral Anomaly in Git History

**Input:**
```yaml
target: "git log --oneline -50"
anomaly_type: "behavioral"
constraints:
  sensitivity: "high"
```

**Output:**
```yaml
detected: true
target_type: anomaly
instances:
  - id: "commit-abc123"
    type: behavioral
    attributes:
      observed: "45 files changed in single commit"
      expected: "average 3-5 files per commit"
      deviation: "10x typical commit size"
      severity: medium
    location: "git:commit:abc123"
    confidence: 0.85
signals:
  - signal: "Commit abc123 modifies 45 files, 10x average"
    strength: high
    location: "git:commit:abc123"
  - signal: "Commit message 'WIP' suggests incomplete work"
    strength: medium
    location: "git:commit:abc123"
false_positive_risk: medium
confidence: 0.80
evidence_anchors:
  - "git:commit:abc123"
  - "git:log:HEAD~20..HEAD~19"
assumptions:
  - "Average commit size derived from recent history"
  - "Large commits may be legitimate (refactoring, migrations)"
next_actions:
  - "Review commit abc123 for code quality"
  - "Check if large commit is intentional refactoring"
```

**Evidence pattern:** Git history analysis with statistical comparison.

---

### Example 4: No Anomalies Detected

**Input:**
```yaml
target: "/logs/access.log"
baseline: "HTTP status codes: 200, 201, 204, 301, 302, 304, 400, 401, 403, 404"
anomaly_type: "semantic"
```

**Output:**
```yaml
detected: false
target_type: anomaly
instances: []
signals:
  - signal: "All HTTP status codes within expected set"
    strength: high
    location: "access.log:1-5000"
  - signal: "No unusual response codes found"
    strength: high
    location: "access.log"
false_positive_risk: low
confidence: 0.92
evidence_anchors:
  - "tool:Grep:HTTP/[0-9]:access.log"
assumptions:
  - "Expected status codes list is complete"
  - "5xx errors would be anomalies but none found"
```

**Evidence pattern:** Log parsing with valid value enumeration check.

## Verification

- [ ] Output contains `detected` boolean field
- [ ] Anomaly instances include observed vs. expected comparison
- [ ] Severity ratings are consistent with deviation magnitude
- [ ] Evidence anchors reference specific anomalous data points
- [ ] Baseline assumptions are clearly stated

**Verification tools:** Read (for data inspection), Grep (for pattern validation)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive data values when reporting anomalies (redact if needed)
- Note when anomaly detection has limited statistical validity (small samples)
- If detecting security-related anomalies, flag for security review
- Do not trigger alerts or notifications; only report findings

## Composition Patterns

**Commonly follows:**
- `retrieve` - After fetching data for anomaly analysis
- `inspect` - After examining data structure to establish baseline

**Commonly precedes:**
- `identify-anomaly` - When detection confirms anomaly, classify its type
- `critique` - When assessing anomaly impact and risk
- `mitigate` - When addressing detected anomalies

**Anti-patterns:**
- Never use as sole basis for automated remediation without confirmation
- Avoid detecting anomalies in highly variable data without robust baseline

**Workflow references:**
- See `workflow_catalog.json#incident-detection` for anomaly-triggered incidents
- See `workflow_catalog.json#data-quality` for schema anomaly detection
