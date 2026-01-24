---
name: discover-activity
description: Discover activities, events, or processes implicitly present in data through pattern analysis. Use when reconstructing timelines, finding hidden workflows, or understanding user/system behavior.
argument-hint: "[data_source] [activity_type] [actors]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Uncover activities, processes, and events that are not explicitly documented but can be inferred from traces, logs, artifacts, and other evidence in the data.

**Success criteria:**
- Activities are reconstructed with temporal ordering
- Actors and their roles are identified
- Implicit workflows are made explicit
- Evidence supports each discovered activity

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data_source` | Yes | string\|object | Data to analyze (logs, commits, records) |
| `activity_type` | No | string | Type of activity to discover (user, system, process) |
| `actors` | No | array[string] | Specific actors to focus on |
| `time_range` | No | object | Period to analyze |
| `granularity` | No | string | Detail level: coarse, medium, fine (default: medium) |

## Procedure

1) **Identify activity traces**: Find evidence of activities
   - Timestamps and sequence markers
   - State changes and transitions
   - Actor identifiers and actions
   - Artifacts created or modified

2) **Reconstruct timelines**: Order events chronologically
   - Absolute timestamps when available
   - Relative ordering from causality
   - Gap detection and interpolation

3) **Identify actors**: Determine who/what performed activities
   - User identifiers
   - System components
   - Automated processes
   - External entities

4) **Detect patterns**: Find recurring activity sequences
   - Workflows and processes
   - Rituals and routines
   - Anomalous sequences

5) **Infer implicit activities**: Fill gaps in the record
   - Activities implied by state changes
   - Missing steps in known workflows
   - Hidden intermediate states

6) **Map interactions**: Understand activity relationships
   - Parallel vs sequential activities
   - Dependent activities
   - Triggering relationships

## Output Contract

Return a structured object:

```yaml
discoveries:
  - id: string
    type: activity | workflow | interaction | routine
    description: string
    actors: array[string]
    timeline:
      start: string  # timestamp or relative marker
      end: string
      duration: string
    steps:
      - sequence: integer
        action: string
        actor: string
        timestamp: string | null
        evidence_anchor: string
    significance: low | medium | high
    novelty: known | suspected | surprising
    evidence:
      - type: direct | inferred | pattern
        location: string
        description: string
actors_identified:
  - id: string
    type: user | system | external | automated
    activity_count: integer
    first_seen: string
    last_seen: string
    primary_activities: array[string]
workflows_discovered:
  - id: string
    name: string
    steps: array[string]
    frequency: integer
    average_duration: string
    variations: array[object]
temporal_analysis:
  time_range: object
  activity_distribution: object  # by hour, day, etc.
  peak_periods: array[string]
  quiet_periods: array[string]
interactions:
  - actor_a: string
    actor_b: string
    interaction_type: string
    frequency: integer
    pattern: string
gaps_identified:
  - description: string
    expected_activity: string
    time_range: string
    possible_explanations: array[string]
recommendations:
  - action: string
    rationale: string
    priority: low | medium | high
methodology: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `discoveries` | array | Individual activities/workflows found |
| `actors_identified` | array | Actors performing activities |
| `workflows_discovered` | array | Recurring activity patterns |
| `temporal_analysis` | object | Time-based activity distribution |
| `interactions` | array | Actor-to-actor relationships |
| `gaps_identified` | array | Missing or unexplained periods |
| `recommendations` | array | Suggested follow-up actions |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | All evidence locations |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Discovering Developer Workflow Patterns

**Input:**
```yaml
data_source: "git_logs/"
activity_type: "development_workflow"
actors:
  - "alice@example.com"
  - "bob@example.com"
  - "carol@example.com"
time_range:
  start: "2024-01-01"
  end: "2024-01-31"
granularity: "medium"
```

**Output:**
```yaml
discoveries:
  - id: "act-001"
    type: workflow
    description: "Feature branch development cycle: create branch -> commits -> PR -> merge"
    actors: ["alice@example.com", "bob@example.com", "carol@example.com"]
    timeline:
      start: "2024-01-01"
      end: "2024-01-31"
      duration: "ongoing pattern"
    steps:
      - sequence: 1
        action: "Create feature branch from main"
        actor: "developer"
        timestamp: null
        evidence_anchor: "git_logs/branches.log:pattern"
      - sequence: 2
        action: "Initial commit with scaffolding"
        actor: "developer"
        timestamp: null
        evidence_anchor: "git_logs/commits.log:pattern"
      - sequence: 3
        action: "Multiple commits (avg 4.2 per feature)"
        actor: "developer"
        timestamp: null
        evidence_anchor: "git_logs/commits.log:statistics"
      - sequence: 4
        action: "Open pull request"
        actor: "developer"
        timestamp: null
        evidence_anchor: "git_logs/prs.log:pattern"
      - sequence: 5
        action: "Code review comments"
        actor: "reviewer"
        timestamp: null
        evidence_anchor: "git_logs/reviews.log:pattern"
      - sequence: 6
        action: "Address review feedback (avg 1.3 rounds)"
        actor: "developer"
        timestamp: null
        evidence_anchor: "git_logs/commits.log:pattern"
      - sequence: 7
        action: "Merge to main"
        actor: "developer"
        timestamp: null
        evidence_anchor: "git_logs/merges.log:pattern"
    significance: high
    novelty: known
    evidence:
      - type: pattern
        location: "git_logs/workflow_analysis.json"
        description: "87% of features follow this pattern"
  - id: "act-002"
    type: activity
    description: "Hotfix bypass workflow: direct commit to main without PR"
    actors: ["bob@example.com"]
    timeline:
      start: "2024-01-15T03:45:00Z"
      end: "2024-01-15T04:12:00Z"
      duration: "27 minutes"
    steps:
      - sequence: 1
        action: "Direct commit to main: 'hotfix: critical auth bypass'"
        actor: "bob@example.com"
        timestamp: "2024-01-15T03:45:00Z"
        evidence_anchor: "git_logs/commits.log:15678"
      - sequence: 2
        action: "Force push to main"
        actor: "bob@example.com"
        timestamp: "2024-01-15T03:47:00Z"
        evidence_anchor: "git_logs/pushes.log:892"
      - sequence: 3
        action: "Post-hoc PR created for documentation"
        actor: "bob@example.com"
        timestamp: "2024-01-15T04:12:00Z"
        evidence_anchor: "git_logs/prs.log:234"
    significance: high
    novelty: surprising
    evidence:
      - type: direct
        location: "git_logs/commits.log:15678"
        description: "Commit directly to main without branch"
      - type: direct
        location: "git_logs/pushes.log:892"
        description: "Force push flag detected"
  - id: "act-003"
    type: routine
    description: "Morning sync routine: alice reviews overnight PRs before starting new work"
    actors: ["alice@example.com"]
    timeline:
      start: "08:00-09:30 daily"
      end: "recurring"
      duration: "~90 minutes"
    steps:
      - sequence: 1
        action: "Review pending PRs from overnight"
        actor: "alice@example.com"
        timestamp: "typically 08:15-08:45"
        evidence_anchor: "git_logs/reviews.log:pattern"
      - sequence: 2
        action: "Respond to review comments on own PRs"
        actor: "alice@example.com"
        timestamp: "typically 08:45-09:00"
        evidence_anchor: "git_logs/comments.log:pattern"
      - sequence: 3
        action: "First commit of new work"
        actor: "alice@example.com"
        timestamp: "typically 09:15-09:30"
        evidence_anchor: "git_logs/commits.log:pattern"
    significance: medium
    novelty: known
    evidence:
      - type: pattern
        location: "git_logs/alice_activity_times.json"
        description: "Consistent pattern on 18 of 22 working days"
actors_identified:
  - id: "alice@example.com"
    type: user
    activity_count: 156
    first_seen: "2024-01-02T08:23:00Z"
    last_seen: "2024-01-31T17:45:00Z"
    primary_activities:
      - "Code commits (67)"
      - "PR reviews (45)"
      - "Review comments (44)"
  - id: "bob@example.com"
    type: user
    activity_count: 203
    first_seen: "2024-01-02T09:12:00Z"
    last_seen: "2024-01-31T23:45:00Z"
    primary_activities:
      - "Code commits (112)"
      - "PR reviews (52)"
      - "Branch operations (39)"
  - id: "carol@example.com"
    type: user
    activity_count: 98
    first_seen: "2024-01-03T10:00:00Z"
    last_seen: "2024-01-31T16:30:00Z"
    primary_activities:
      - "Code commits (45)"
      - "PR reviews (28)"
      - "Documentation updates (25)"
  - id: "github-actions[bot]"
    type: automated
    activity_count: 287
    first_seen: "2024-01-02T08:25:00Z"
    last_seen: "2024-01-31T17:47:00Z"
    primary_activities:
      - "CI checks (145)"
      - "Auto-merge (89)"
      - "Release tags (53)"
workflows_discovered:
  - id: "wf-001"
    name: "Standard feature development"
    steps: ["branch", "commit", "pr", "review", "merge"]
    frequency: 34
    average_duration: "2.3 days"
    variations:
      - name: "Fast-track (no review comments)"
        frequency: 8
        duration: "4 hours"
      - name: "Extended review (2+ rounds)"
        frequency: 6
        duration: "5.1 days"
  - id: "wf-002"
    name: "Documentation update"
    steps: ["branch", "commit", "pr", "auto-merge"]
    frequency: 12
    average_duration: "45 minutes"
    variations: []
  - id: "wf-003"
    name: "Dependency update"
    steps: ["dependabot-pr", "ci-check", "human-approve", "auto-merge"]
    frequency: 23
    average_duration: "6 hours"
    variations: []
temporal_analysis:
  time_range:
    start: "2024-01-01"
    end: "2024-01-31"
  activity_distribution:
    by_hour: { "08": 45, "09": 78, "10": 112, "11": 98, "14": 89, "15": 102, "16": 87, "17": 45 }
    by_day: { "Mon": 98, "Tue": 112, "Wed": 134, "Thu": 89, "Fri": 67 }
  peak_periods:
    - "Tuesday-Wednesday 10:00-11:00"
    - "Wednesday 15:00-16:00"
  quiet_periods:
    - "Friday after 15:00"
    - "Daily 12:00-14:00 (lunch)"
interactions:
  - actor_a: "alice@example.com"
    actor_b: "bob@example.com"
    interaction_type: "code_review"
    frequency: 23
    pattern: "alice reviews bob's PRs (15), bob reviews alice's (8)"
  - actor_a: "bob@example.com"
    actor_b: "carol@example.com"
    interaction_type: "code_review"
    frequency: 18
    pattern: "primarily bob reviewing carol (14/18)"
  - actor_a: "all_developers"
    actor_b: "github-actions[bot]"
    interaction_type: "ci_feedback"
    frequency: 287
    pattern: "automated checks on all PRs"
gaps_identified:
  - description: "No activity from carol@example.com Jan 8-12"
    expected_activity: "Regular commits and reviews"
    time_range: "2024-01-08 to 2024-01-12"
    possible_explanations:
      - "PTO or sick leave"
      - "Off-site work not captured in git"
      - "Non-coding tasks (meetings, planning)"
  - description: "Unusually low activity on Jan 22 (Monday)"
    expected_activity: "~98 activities (Monday average)"
    time_range: "2024-01-22"
    possible_explanations:
      - "Holiday (MLK Day observed)"
      - "Company event"
recommendations:
  - action: "Investigate hotfix bypass workflow (act-002) for process improvement"
    rationale: "Direct commits to main bypass review safeguards"
    priority: high
  - action: "Document alice's morning routine as team best practice"
    rationale: "Consistent pattern leads to faster PR turnaround"
    priority: medium
  - action: "Consider Friday deployment freeze given activity patterns"
    rationale: "Low Friday afternoon activity means less support capacity"
    priority: medium
methodology: "Git log analysis: commit parsing, branch tracking, PR correlation, temporal pattern detection"
confidence: 0.85
evidence_anchors:
  - "git_logs/commits.log"
  - "git_logs/branches.log"
  - "git_logs/prs.log"
  - "git_logs/reviews.log"
  - "git_logs/pushes.log"
  - "git_logs/workflow_analysis.json"
  - "git_logs/alice_activity_times.json"
assumptions:
  - "Git logs are complete and timestamps accurate"
  - "All development activity goes through git"
  - "Actor email addresses are consistent identifiers"
  - "Working hours are approximately 08:00-18:00 local"
```

**Evidence pattern:** Log analysis + temporal pattern detection + actor correlation

## Verification

- [ ] Activity sequences are chronologically consistent
- [ ] Actor identification is unambiguous
- [ ] Inferred activities are clearly marked
- [ ] Gaps are identified and explained
- [ ] Workflow patterns have sufficient frequency support

**Verification tools:** Read (for log inspection), Grep (for pattern searching)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Mark inferred activities distinctly from observed ones
- Do not make claims about actor intent without evidence
- Respect privacy - avoid inferring personal information
- Flag when activity gaps may indicate data issues

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather activity logs
- `search` - to locate relevant data sources
- `identify-entity` - to identify actors

**Commonly precedes:**
- `discover-relationship` - to find relationships between actors
- `generate-plan` - to plan process improvements
- `summarize` - to create activity report

**Anti-patterns:**
- Never claim complete activity coverage (always sampling)
- Avoid over-interpreting gaps in data

**Workflow references:**
- See `workflow_catalog.json#process_mining` for workflow discovery
- See `workflow_catalog.json#user_research` for behavior analysis
