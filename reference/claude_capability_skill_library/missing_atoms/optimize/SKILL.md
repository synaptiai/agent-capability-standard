---
name: optimize
description: Tune parameters or choices to improve an objective under constraints. Use when improving performance, reducing costs, maximizing throughput, or finding optimal configurations.
argument-hint: "[target] [objective] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash
context: fork
agent: general-purpose
---

## Intent

Improve a system, process, or configuration by adjusting parameters to optimize for a defined objective while respecting constraints. Produce measurable improvements with documented trade-offs.

**Success criteria:**
- Objective function improved measurably
- Constraints respected
- Changes are reversible or documented
- Trade-offs understood
- Results reproducible

**Compatible schemas:**
- `docs/schemas/optimization_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string or object | What to optimize (config, algorithm, process) |
| `objective` | Yes | string | What to maximize/minimize (latency, cost, throughput) |
| `constraints` | No | object | Hard limits that cannot be violated |
| `parameters` | No | array | Tunable parameters and their ranges |
| `baseline` | No | object | Current performance to improve upon |
| `budget` | No | object | Time/resource limits for optimization |

## Procedure

1) **Understand the target**: Analyze what is being optimized
   - Identify the system/process structure
   - Map dependencies and interactions
   - Find tunable parameters
   - Understand current configuration

2) **Define objective function**: Clarify optimization goal
   - Single objective or multi-objective
   - Maximize or minimize
   - How to measure
   - Acceptable improvement threshold

3) **Identify constraints**: Establish boundaries
   - Hard constraints (must not violate)
   - Soft constraints (prefer not to violate)
   - Resource limits
   - Time limits for optimization itself

4) **Establish baseline**: Measure current performance
   - Run baseline measurement if not provided
   - Ensure reproducibility
   - Document measurement methodology
   - Note variance in measurements

5) **Explore parameter space**: Find improvement opportunities
   - List all tunable parameters
   - Define valid ranges for each
   - Identify parameter interactions
   - Prioritize high-impact parameters

6) **Apply optimization strategy**: Systematically improve
   - Grid search for small spaces
   - Gradient-based for continuous
   - Heuristics for large spaces
   - A/B testing for production

7) **Measure improvements**: Quantify results
   - Compare to baseline
   - Calculate improvement percentage
   - Verify constraints still satisfied
   - Test edge cases

8) **Document trade-offs**: Note side effects
   - What got worse (if anything)
   - Resource consumption changes
   - Complexity changes
   - Maintainability impact

## Output Contract

Return a structured object:

```yaml
optimization:
  target: string  # What was optimized
  objective: string  # What was improved
  direction: maximize | minimize
  strategy: string  # Approach used
baseline:
  value: number
  unit: string
  measured_at: string
  methodology: string
result:
  value: number
  improvement: number  # Percentage
  improvement_absolute: number
  constraints_satisfied: boolean
parameters_changed:
  - name: string
    before: any
    after: any
    impact: number  # Contribution to improvement
trade_offs:
  - benefit: string
    cost: string
    acceptable: boolean
constraints_status:
  - constraint: string
    satisfied: boolean
    margin: number | null  # How close to limit
recommendations:
  - parameter: string
    action: string
    expected_impact: string
confidence: 0..1
evidence_anchors: ["benchmark:id", "config:path"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `optimization` | object | Summary of optimization approach |
| `baseline` | object | Starting performance |
| `result` | object | Achieved performance |
| `parameters_changed` | array | What was tuned |
| `trade_offs` | array | Benefits vs costs |
| `constraints_status` | array | Constraint satisfaction |
| `recommendations` | array | Further optimization opportunities |
| `confidence` | number | 0.0-1.0 based on measurement quality |

## Examples

### Example 1: Database Query Optimization

**Input:**
```yaml
target:
  type: "database_query"
  query: "SELECT * FROM orders WHERE customer_id = ? AND status = 'active'"
  table: "orders"
  rows: 10000000
objective: "minimize response_time"
constraints:
  max_memory: "256MB"
  max_cpu: "50%"
baseline:
  response_time_ms: 450
```

**Output:**
```yaml
optimization:
  target: "orders query by customer_id and status"
  objective: "response_time"
  direction: minimize
  strategy: "index analysis and query rewriting"
baseline:
  value: 450
  unit: "ms"
  measured_at: "2024-01-15T10:00:00Z"
  methodology: "Average of 100 queries with cold cache"
result:
  value: 12
  improvement: 97.3
  improvement_absolute: 438
  constraints_satisfied: true
parameters_changed:
  - name: "index_customer_status"
    before: null
    after: "CREATE INDEX idx_orders_customer_status ON orders(customer_id, status)"
    impact: 90
  - name: "query_select"
    before: "SELECT *"
    after: "SELECT id, customer_id, status, total, created_at"
    impact: 10
trade_offs:
  - benefit: "97% faster query response"
    cost: "Additional index storage (~500MB)"
    acceptable: true
  - benefit: "Reduced data transfer"
    cost: "Must update app to use specific columns"
    acceptable: true
constraints_status:
  - constraint: "max_memory"
    satisfied: true
    margin: "180MB remaining"
  - constraint: "max_cpu"
    satisfied: true
    margin: "35% remaining"
recommendations:
  - parameter: "connection_pool_size"
    action: "Increase from 10 to 25"
    expected_impact: "Handle more concurrent queries"
  - parameter: "query_cache"
    action: "Enable for this query pattern"
    expected_impact: "Further 20-50% improvement for repeated queries"
confidence: 0.95
evidence_anchors:
  - "benchmark:query-perf-2024-01-15"
  - "explain:query-plan-before-after"
assumptions:
  - "Query pattern is representative of production load"
  - "10M row count is accurate"
  - "Customer_id has high cardinality"
```

**Evidence pattern:** Baseline and result measured with same methodology, EXPLAIN plans compared.

---

### Example 2: Configuration Optimization

**Input:**
```yaml
target:
  type: "web_server"
  config: "nginx.conf"
objective: "maximize requests_per_second"
constraints:
  max_memory: "4GB"
  max_latency_p99: "100ms"
budget:
  max_time: "1 hour"
```

**Output:**
```yaml
optimization:
  target: "nginx web server"
  objective: "requests_per_second"
  direction: maximize
  strategy: "systematic parameter tuning with load testing"
baseline:
  value: 5000
  unit: "requests/second"
  measured_at: "2024-01-15T14:00:00Z"
  methodology: "wrk benchmark, 10 threads, 100 connections, 60s"
result:
  value: 12500
  improvement: 150
  improvement_absolute: 7500
  constraints_satisfied: true
parameters_changed:
  - name: "worker_processes"
    before: 1
    after: 4
    impact: 60
  - name: "worker_connections"
    before: 512
    after: 2048
    impact: 25
  - name: "keepalive_timeout"
    before: 65
    after: 30
    impact: 10
  - name: "gzip"
    before: "off"
    after: "on"
    impact: 5
trade_offs:
  - benefit: "150% more throughput"
    cost: "Higher CPU utilization"
    acceptable: true
  - benefit: "Reduced connection overhead"
    cost: "More open file descriptors"
    acceptable: true
constraints_status:
  - constraint: "max_memory"
    satisfied: true
    margin: "2.1GB remaining"
  - constraint: "max_latency_p99"
    satisfied: true
    margin: "35ms margin (65ms actual)"
recommendations:
  - parameter: "worker_processes"
    action: "Match to CPU cores (currently 4, server has 8)"
    expected_impact: "Potential 50% additional improvement"
  - parameter: "tcp_nodelay"
    action: "Enable for low-latency responses"
    expected_impact: "5-10ms latency reduction"
confidence: 0.85
evidence_anchors:
  - "benchmark:nginx-load-test-2024-01-15"
  - "config:nginx.conf.optimized"
assumptions:
  - "Load test represents production traffic patterns"
  - "Server has no other significant workloads"
  - "Network bandwidth is not the bottleneck"
```

## Verification

- [ ] Baseline measurement is reproducible
- [ ] Result measurement uses same methodology
- [ ] All constraints verified
- [ ] Trade-offs documented
- [ ] Changes are reversible

**Verification tools:** Bash (for running benchmarks), Read (for config analysis)

## Safety Constraints

- `mutation`: false (planning only; changes require act-plan)
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- Always establish reproducible baseline first
- Never claim improvements without measurement
- Document methodology for reproducibility
- Note if improvements are environment-specific
- Highlight any regression in other metrics

## Composition Patterns

**Commonly follows:**
- `evaluate` - Measure current performance
- `inspect` - Understand system before optimizing
- `detect-anomaly` - Find performance issues

**Commonly precedes:**
- `plan` - Plan implementation of optimizations
- `act-plan` - Apply optimization changes
- `verify` - Confirm improvements hold

**Anti-patterns:**
- Never optimize without baseline
- Never claim improvement without measurement
- Never ignore constraints for better numbers

**Workflow references:**
- Performance tuning workflows
- Cost optimization workflows
