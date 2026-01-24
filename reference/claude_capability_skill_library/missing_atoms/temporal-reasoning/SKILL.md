---
name: temporal-reasoning
description: Reason over time dimensions including ordering, duration, periodicity, intervals, and temporal constraints. Use when analyzing sequences, scheduling, detecting time-based patterns, or validating temporal invariants.
argument-hint: "[events] [query: ordering|duration|periodicity|window] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Perform **temporal analysis** on events, states, or processes to answer questions about time: what happened when, how long did it take, does it recur, what overlaps or conflicts.

**Success criteria:**
- Temporal relationships are correctly identified (before, after, during, overlaps)
- Durations and intervals are calculated accurately
- Periodic patterns are detected with confidence scores
- Time windows are properly bounded
- Allen's interval algebra relations are applied where relevant

**Compatible schemas:**
- `docs/schemas/event_schema.yaml`
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `events` | Yes | array | Events/states with timestamps to analyze |
| `query` | Yes | string | Type of temporal analysis: `ordering`, `duration`, `periodicity`, `window`, `conflict` |
| `reference_time` | No | string | Reference timestamp for relative calculations (default: now) |
| `constraints` | No | object | Time bounds, granularity, tolerance for pattern matching |

## Procedure

1) **Parse temporal data**: Extract and normalize timestamps
   - Identify timestamp format (ISO 8601, Unix epoch, relative)
   - Convert all timestamps to consistent format (UTC ISO 8601)
   - Handle missing timestamps (mark as unknown, use bounds if available)
   - Detect timezone inconsistencies

2) **Build temporal model**: Organize events on timeline
   - For point events: place at exact timestamp
   - For interval events: establish start and end bounds
   - For unbounded intervals: identify open ends (ongoing, unknown start)
   - Create interval representation for Allen's algebra if needed

3) **Apply query-specific analysis**:

   For `ordering`:
   - Sort events chronologically
   - Identify causal chains (A must happen before B)
   - Detect violations of expected ordering
   - Compute partial orders where total order is uncertain

   For `duration`:
   - Calculate elapsed time between events
   - Compute statistics (min, max, mean, p50, p95)
   - Identify outliers in duration
   - Account for gaps and pauses

   For `periodicity`:
   - Detect recurring patterns (daily, weekly, custom)
   - Calculate period and phase
   - Measure regularity/jitter
   - Identify missed or extra occurrences

   For `window`:
   - Define time window bounds
   - Filter events within window
   - Aggregate events by time bucket
   - Compute window-based metrics

   For `conflict`:
   - Apply Allen's interval relations (overlaps, meets, during, etc.)
   - Detect scheduling conflicts
   - Identify resource contention periods
   - Suggest resolution strategies

4) **Quantify temporal uncertainty**: Assess confidence in temporal claims
   - Clock skew and synchronization issues
   - Missing or interpolated timestamps
   - Granularity limitations (day vs. millisecond)

5) **Ground findings**: Attach evidence for each temporal relationship
   - Reference specific timestamps from source data
   - Show calculation methodology

## Output Contract

Return a structured object:

```yaml
temporal_analysis:
  query_type: string  # ordering, duration, periodicity, window, conflict
  reference_time: string  # ISO 8601 timestamp used as reference
  timeline:
    events:
      - id: string
        timestamp: string  # ISO 8601
        timestamp_end: string | null  # For intervals
        type: point | interval
        label: string
    span:
      start: string  # Earliest timestamp
      end: string  # Latest timestamp
      duration_seconds: number
  results:
    # Query-specific results (see examples below)
    ordering: object | null  # If query=ordering
    duration: object | null  # If query=duration
    periodicity: object | null  # If query=periodicity
    window: object | null  # If query=window
    conflicts: array | null  # If query=conflict
  temporal_relations:
    - event_a: string
      relation: string  # before, after, meets, overlaps, during, starts, finishes, equals
      event_b: string
      confidence: number
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `timeline.events` | array | Normalized event list with timestamps |
| `timeline.span` | object | Overall time range covered |
| `results` | object | Query-specific analysis results |
| `temporal_relations` | array | Pairwise temporal relationships (Allen's algebra) |
| `confidence` | number | Based on timestamp quality and coverage |

## Examples

### Example 1: Event Ordering Analysis

**Input:**
```yaml
events:
  - id: "deploy_v2"
    timestamp: "2025-01-24T10:30:00Z"
    label: "Deployed version 2.0"
  - id: "error_spike"
    timestamp: "2025-01-24T10:35:00Z"
    label: "Error rate increased 500%"
  - id: "rollback"
    timestamp: "2025-01-24T10:45:00Z"
    label: "Rolled back to version 1.9"
query: ordering
```

**Output:**
```yaml
temporal_analysis:
  query_type: "ordering"
  reference_time: "2025-01-24T12:00:00Z"
  timeline:
    events:
      - id: "deploy_v2"
        timestamp: "2025-01-24T10:30:00Z"
        timestamp_end: null
        type: point
        label: "Deployed version 2.0"
      - id: "error_spike"
        timestamp: "2025-01-24T10:35:00Z"
        timestamp_end: null
        type: point
        label: "Error rate increased 500%"
      - id: "rollback"
        timestamp: "2025-01-24T10:45:00Z"
        timestamp_end: null
        type: point
        label: "Rolled back to version 1.9"
    span:
      start: "2025-01-24T10:30:00Z"
      end: "2025-01-24T10:45:00Z"
      duration_seconds: 900
  results:
    ordering:
      sequence:
        - deploy_v2
        - error_spike
        - rollback
      causal_candidates:
        - cause: "deploy_v2"
          effect: "error_spike"
          delay_seconds: 300
          plausibility: high
        - cause: "error_spike"
          effect: "rollback"
          delay_seconds: 600
          plausibility: high
  temporal_relations:
    - event_a: "deploy_v2"
      relation: "before"
      event_b: "error_spike"
      confidence: 1.0
    - event_a: "error_spike"
      relation: "before"
      event_b: "rollback"
      confidence: 1.0
confidence: 0.95
evidence_anchors:
  - "deployment_log:2025-01-24T10:30:00Z"
  - "monitoring_alert:2025-01-24T10:35:00Z"
  - "deployment_log:2025-01-24T10:45:00Z"
assumptions:
  - "All timestamps are from synchronized clocks"
  - "No intermediate events were missed"
```

**Evidence pattern:** Extracted timestamps from deployment logs and monitoring alerts, verified clock synchronization.

---

### Example 2: Periodicity Detection

**Input:**
```yaml
events:
  - { id: "job_1", timestamp: "2025-01-20T02:00:00Z" }
  - { id: "job_2", timestamp: "2025-01-21T02:00:00Z" }
  - { id: "job_3", timestamp: "2025-01-22T02:05:00Z" }
  - { id: "job_4", timestamp: "2025-01-23T02:00:00Z" }
  - { id: "job_5", timestamp: "2025-01-24T02:00:00Z" }
query: periodicity
```

**Output:**
```yaml
temporal_analysis:
  query_type: "periodicity"
  reference_time: "2025-01-24T12:00:00Z"
  timeline:
    events: [...]  # As above
    span:
      start: "2025-01-20T02:00:00Z"
      end: "2025-01-24T02:00:00Z"
      duration_seconds: 345600
  results:
    periodicity:
      detected: true
      pattern:
        period_seconds: 86400
        period_human: "daily"
        phase: "02:00:00 UTC"
      regularity:
        mean_interval_seconds: 86380
        std_deviation_seconds: 75
        jitter_ratio: 0.001
      anomalies:
        - event_id: "job_3"
          expected: "2025-01-22T02:00:00Z"
          actual: "2025-01-22T02:05:00Z"
          deviation_seconds: 300
          severity: low
      next_expected: "2025-01-25T02:00:00Z"
confidence: 0.92
evidence_anchors:
  - "cron_log:job_history"
assumptions:
  - "Jobs represent complete executions, not partial runs"
```

## Verification

- [ ] All timestamps are valid ISO 8601 format
- [ ] Timeline span correctly bounds all events
- [ ] Temporal relations are consistent (no A before B and B before A)
- [ ] Periodicity detection has sufficient samples (>3 for pattern)
- [ ] Duration calculations account for timezone correctly

**Verification tools:** Date parsing libraries, interval arithmetic validation

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not assume timestamps are accurate without evidence of clock sync
- Flag events with suspicious timestamp patterns (exact duplicates, impossible gaps)
- When periodicity confidence < 0.5, suggest collecting more data points
- Handle DST transitions and leap seconds for high-precision analysis

## Composition Patterns

**Commonly follows:**
- `world-state` - Temporal reasoning often operates on state snapshots
- `retrieve` - Get event logs before temporal analysis
- `inspect` - Observe systems to collect timestamped events

**Commonly precedes:**
- `state-transition` - Temporal order informs transition sequencing
- `causal-model` - Temporal precedence is necessary for causality
- `forecast-time` - Periodicity enables time predictions
- `detect-anomaly` - Temporal patterns establish baselines

**Anti-patterns:**
- Never assume causation from temporal correlation alone
- Avoid temporal reasoning on unsynchronized clock sources without flagging uncertainty

**Workflow references:**
- See `composition_patterns.md#world-model-build` for state-time integration
- See `composition_patterns.md#digital-twin-sync-loop` for real-time temporal tracking
