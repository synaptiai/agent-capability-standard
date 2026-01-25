---
name: schedule
description: Order work under deadlines, resource constraints, and dependencies to produce a timeline or runbook. Use when creating project schedules, sprint plans, or deployment timelines.
argument-hint: "[tasks] [resources] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Arrange prioritized tasks into a timeline that respects deadlines, resource availability, dependencies, and constraints. Produce an executable schedule with clear milestones.

**Success criteria:**
- All tasks scheduled within available time
- Dependencies respected (no task before its prerequisites)
- Resource conflicts resolved
- Deadlines met or flagged
- Buffer time for contingencies included

**Compatible schemas:**
- `docs/schemas/schedule_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `tasks` | Yes | array | Tasks to schedule with durations |
| `resources` | No | array | Available resources (people, machines) |
| `constraints` | No | object | Deadlines, dependencies, blockers |
| `start_date` | No | string | Schedule start date |
| `end_date` | No | string | Hard deadline for all work |
| `buffer_percent` | No | number | Contingency buffer (default: 20%) |

## Procedure

1) **Inventory tasks**: Understand what needs scheduling
   - List all tasks with durations
   - Note dependencies between tasks
   - Identify critical path candidates
   - Flag tasks with hard deadlines

2) **Map dependencies**: Build task graph
   - Create directed acyclic graph (DAG)
   - Identify parallel-safe tasks
   - Find blocking dependencies
   - Detect cycles (error if present)

3) **Assess resources**: Understand capacity
   - List available resources
   - Note resource capabilities
   - Identify shared resources
   - Calculate total capacity

4) **Calculate critical path**: Find longest path
   - Identify tasks that cannot slip
   - Calculate minimum project duration
   - Note slack for non-critical tasks
   - Flag if critical path exceeds deadline

5) **Schedule tasks**: Assign to timeline
   - Start with critical path
   - Schedule parallel tasks when resources allow
   - Respect resource constraints
   - Add buffer after high-risk tasks

6) **Resolve conflicts**: Handle resource contention
   - When two tasks need same resource, prioritize
   - Consider task priority and deadlines
   - Move lower-priority tasks if needed
   - Document trade-offs made

7) **Add milestones**: Mark significant points
   - Phase completions
   - Integration points
   - Review gates
   - Deadline markers

8) **Validate schedule**: Check feasibility
   - All deadlines met?
   - All resources within capacity?
   - Buffer included?
   - Dependencies respected?

## Output Contract

Return a structured object:

```yaml
schedule:
  start_date: string  # Schedule start
  end_date: string  # Scheduled completion
  total_duration: string  # Total time span
  buffer_included: number  # Percentage
scheduled_tasks:
  - id: string
    name: string
    start: string  # Start date/time
    end: string  # End date/time
    duration: string
    resource: string | null
    depends_on: array[string]
    on_critical_path: boolean
    slack: string | null  # Available slack time
    milestone: string | null
timeline:
  - date: string
    events:
      - type: start | end | milestone | deadline
        task_id: string | null
        description: string
critical_path:
  tasks: array[string]  # Task IDs on critical path
  duration: string
  risk_level: low | medium | high
resources_used:
  - resource: string
    utilization: number  # Percentage
    tasks: array[string]
milestones:
  - name: string
    date: string
    tasks_complete: array[string]
    gate: review | approval | integration | deployment
risks:
  - risk: string
    impact: string
    mitigation: string
confidence: 0..1
evidence_anchors: ["source:ref"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `schedule` | object | Overall schedule metadata |
| `scheduled_tasks` | array | Each task with timing |
| `timeline` | array | Chronological event list |
| `critical_path` | object | Longest dependency chain |
| `resources_used` | array | Resource allocation |
| `milestones` | array | Significant checkpoints |
| `risks` | array | Scheduling risks identified |
| `confidence` | number | 0.0-1.0 based on estimate quality |

## Examples

### Example 1: Sprint Schedule

**Input:**
```yaml
tasks:
  - id: "T1"
    name: "Design API endpoints"
    duration: "2d"
    resource: "alice"
  - id: "T2"
    name: "Implement endpoints"
    duration: "3d"
    depends_on: ["T1"]
    resource: "bob"
  - id: "T3"
    name: "Write tests"
    duration: "2d"
    depends_on: ["T2"]
    resource: "carol"
  - id: "T4"
    name: "Documentation"
    duration: "1d"
    depends_on: ["T2"]
    resource: "alice"
  - id: "T5"
    name: "Code review"
    duration: "1d"
    depends_on: ["T2", "T3"]
    resource: "bob"
resources:
  - id: "alice"
    capacity: "8h/day"
  - id: "bob"
    capacity: "8h/day"
  - id: "carol"
    capacity: "8h/day"
start_date: "2024-01-15"
end_date: "2024-01-26"
buffer_percent: 20
```

**Output:**
```yaml
schedule:
  start_date: "2024-01-15"
  end_date: "2024-01-24"
  total_duration: "8 working days"
  buffer_included: 20
scheduled_tasks:
  - id: "T1"
    name: "Design API endpoints"
    start: "2024-01-15"
    end: "2024-01-16"
    duration: "2d"
    resource: "alice"
    depends_on: []
    on_critical_path: true
    slack: null
    milestone: null
  - id: "T2"
    name: "Implement endpoints"
    start: "2024-01-17"
    end: "2024-01-19"
    duration: "3d"
    resource: "bob"
    depends_on: ["T1"]
    on_critical_path: true
    slack: null
    milestone: null
  - id: "T3"
    name: "Write tests"
    start: "2024-01-22"
    end: "2024-01-23"
    duration: "2d"
    resource: "carol"
    depends_on: ["T2"]
    on_critical_path: true
    slack: null
    milestone: null
  - id: "T4"
    name: "Documentation"
    start: "2024-01-22"
    end: "2024-01-22"
    duration: "1d"
    resource: "alice"
    depends_on: ["T2"]
    on_critical_path: false
    slack: "1d"
    milestone: null
  - id: "T5"
    name: "Code review"
    start: "2024-01-24"
    end: "2024-01-24"
    duration: "1d"
    resource: "bob"
    depends_on: ["T2", "T3"]
    on_critical_path: true
    slack: null
    milestone: "Sprint Complete"
timeline:
  - date: "2024-01-15"
    events:
      - type: start
        task_id: "T1"
        description: "Design begins"
  - date: "2024-01-17"
    events:
      - type: start
        task_id: "T2"
        description: "Implementation begins"
  - date: "2024-01-22"
    events:
      - type: start
        task_id: "T3"
        description: "Testing begins"
      - type: start
        task_id: "T4"
        description: "Documentation begins (parallel)"
  - date: "2024-01-24"
    events:
      - type: end
        task_id: "T5"
        description: "Code review complete"
      - type: milestone
        task_id: null
        description: "Sprint Complete"
critical_path:
  tasks: ["T1", "T2", "T3", "T5"]
  duration: "8d"
  risk_level: medium
resources_used:
  - resource: "alice"
    utilization: 37.5
    tasks: ["T1", "T4"]
  - resource: "bob"
    utilization: 50
    tasks: ["T2", "T5"]
  - resource: "carol"
    utilization: 25
    tasks: ["T3"]
milestones:
  - name: "Sprint Complete"
    date: "2024-01-24"
    tasks_complete: ["T1", "T2", "T3", "T4", "T5"]
    gate: review
risks:
  - risk: "No slack on critical path"
    impact: "Any delay pushes end date"
    mitigation: "Daily standups to catch blockers early"
  - risk: "Bob has 2 back-to-back critical tasks"
    impact: "Bob absence delays project"
    mitigation: "Cross-train Carol on implementation"
confidence: 0.85
evidence_anchors:
  - "tasks:duration-estimates"
assumptions:
  - "No holidays or PTO during sprint"
  - "Duration estimates are accurate"
  - "Resources available full-time"
```

**Evidence pattern:** Critical path calculated, resource utilization tracked, risks identified.

## Verification

- [ ] All tasks scheduled
- [ ] Dependencies respected
- [ ] Deadlines met or flagged
- [ ] Resources not over-allocated
- [ ] Critical path identified

**Verification tools:** Read (for task details)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always identify critical path
- Flag impossible schedules
- Include buffer for uncertainty
- Note resource conflicts
- Highlight deadline risks

## Composition Patterns

**Commonly follows:**
- `prioritize` - Schedule prioritized items
- `decompose` - Break down before scheduling
- `estimate` - Get task durations

**Commonly precedes:**
- `plan` - Include schedule in plan
- `delegate` - Assign scheduled work
- `send` - Share schedule with team

**Anti-patterns:**
- Never schedule without dependencies
- Never ignore resource conflicts
- Never hide critical path risks

**Workflow references:**
- Project planning workflows
- Sprint planning workflows
