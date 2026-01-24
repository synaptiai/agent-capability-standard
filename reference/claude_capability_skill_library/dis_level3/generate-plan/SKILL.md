---
name: generate-plan
description: Generate action plans with steps, dependencies, verification criteria, and rollback options. Use when creating implementation plans, project plans, or multi-step execution strategies.
argument-hint: "[goal] [constraints] [context]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create structured, executable plans with clear steps, dependencies, verification criteria, and risk mitigation strategies that can be reviewed, modified, and executed.

**Success criteria:**
- Plan achieves stated goal
- Steps are concrete and actionable
- Dependencies and ordering are explicit
- Verification criteria enable progress tracking
- Rollback options address failure scenarios

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `goal` | Yes | string | What the plan should achieve |
| `constraints` | No | object | Limitations: time, resources, permissions |
| `context` | No | string\|object | Current state and background |
| `preferences` | No | object | Style preferences: detailed vs high-level, risk tolerance |
| `available_resources` | No | array | Tools, people, systems available |

## Procedure

1) **Clarify goal and constraints**: Understand the target
   - What does success look like?
   - What are the hard constraints?
   - What is the current starting state?
   - Who/what is executing the plan?

2) **Decompose into steps**: Break down the goal
   - Identify major phases
   - Break phases into actionable steps
   - Ensure steps are appropriately sized
   - Define clear boundaries between steps

3) **Map dependencies**: Understand ordering
   - Which steps depend on others?
   - What can be parallelized?
   - What are the critical path items?
   - External dependencies and blockers

4) **Add verification criteria**: Define success
   - How do we know each step succeeded?
   - What are the acceptance criteria?
   - What tests or checks validate progress?

5) **Plan for failure**: Risk mitigation
   - What could go wrong at each step?
   - What is the rollback procedure?
   - Where are checkpoints needed?
   - How do we detect and recover from failures?

6) **Estimate and schedule**: Time and resources
   - Duration estimates per step
   - Resource requirements
   - Total timeline
   - Buffer for uncertainty

## Output Contract

Return a structured object:

```yaml
artifact:
  type: plan
  content: object  # The structured plan
  format: yaml | json
  metadata:
    goal: string
    total_steps: integer
    estimated_duration: string
    risk_level: low | medium | high
plan:
  id: string
  goal: string
  preconditions: array[string]
  steps:
    - id: string
      action: string
      target: string
      description: string
      dependencies: array[string]
      estimated_duration: string
      verification_criteria: string
      rollback_action: string | null
      checkpoint: boolean
      risk_notes: string | null
  checkpoints:
    - after_step: string
      type: git_stash | file_backup | state_snapshot | approval_gate
      description: string
  success_criteria: array[string]
  estimated_total_duration: string
  estimated_risk: low | medium | high
parallel_opportunities:
  - steps: array[string]
    reason: string
critical_path:
  - step_id: string
    reason: string
risk_analysis:
  - risk: string
    probability: low | medium | high
    impact: low | medium | high
    mitigation: string
    affected_steps: array[string]
alternatives_considered: array[string]
constraints_used:
  - constraint: string
    satisfied: boolean
    notes: string | null
rationale: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `artifact` | object | The complete plan |
| `plan` | object | Structured plan with steps |
| `parallel_opportunities` | array | Steps that can run concurrently |
| `critical_path` | array | Steps that determine minimum duration |
| `risk_analysis` | array | Identified risks and mitigations |
| `alternatives_considered` | array | Other approaches evaluated |
| `confidence` | number | 0.0-1.0 confidence in plan feasibility |
| `evidence_anchors` | array[string] | Sources informing the plan |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Execution safety considerations |
| `next_actions` | array[string] | Immediate next steps |

## Examples

### Example 1: Generating Database Migration Plan

**Input:**
```yaml
goal: "Migrate PostgreSQL database from version 12 to version 15"
constraints:
  max_downtime: "4 hours"
  data_loss_tolerance: "zero"
  maintenance_window: "Saturday 2am-6am"
context:
  current_version: "PostgreSQL 12.8"
  database_size: "500GB"
  application: "Production e-commerce platform"
  replication: "Primary with 2 read replicas"
preferences:
  risk_tolerance: "low"
  detail_level: "high"
available_resources:
  - "DBA team (2 people)"
  - "DevOps engineer"
  - "Staging environment"
  - "AWS infrastructure"
```

**Output:**
```yaml
artifact:
  type: plan
  content: "See plan object below"
  format: yaml
  metadata:
    goal: "Migrate PostgreSQL 12 to 15"
    total_steps: 12
    estimated_duration: "3-4 hours (within maintenance window)"
    risk_level: medium
plan:
  id: "pg-migration-2024-01"
  goal: "Migrate PostgreSQL database from version 12 to 15 with zero data loss"
  preconditions:
    - "Staging migration completed successfully"
    - "Full backup verified within 24 hours"
    - "Application tested against PG15 in staging"
    - "Rollback procedure documented and tested"
    - "Monitoring and alerting configured"
  steps:
    - id: "step-01"
      action: "verify_prerequisites"
      target: "all systems"
      description: "Confirm all preconditions are met before starting migration"
      dependencies: []
      estimated_duration: "15 minutes"
      verification_criteria: "Checklist complete, team confirms ready"
      rollback_action: "Abort migration, reschedule"
      checkpoint: false
      risk_notes: null
    - id: "step-02"
      action: "create_backup"
      target: "production database"
      description: "Create final pg_dump backup before any changes"
      dependencies: ["step-01"]
      estimated_duration: "45 minutes"
      verification_criteria: "Backup file exists, size matches expected, restore test on empty instance succeeds"
      rollback_action: null
      checkpoint: true
      risk_notes: "Long backup time due to database size"
    - id: "step-03"
      action: "enable_maintenance_mode"
      target: "application"
      description: "Enable application maintenance mode, stop accepting new orders"
      dependencies: ["step-02"]
      estimated_duration: "5 minutes"
      verification_criteria: "Health check returns maintenance status, no new connections"
      rollback_action: "Disable maintenance mode"
      checkpoint: false
      risk_notes: "Downtime begins here"
    - id: "step-04"
      action: "stop_replicas"
      target: "read replicas"
      description: "Stop read replicas to prevent split-brain during migration"
      dependencies: ["step-03"]
      estimated_duration: "5 minutes"
      verification_criteria: "Replicas stopped, no replication lag alerts"
      rollback_action: "Restart replicas pointing to original primary"
      checkpoint: false
      risk_notes: null
    - id: "step-05"
      action: "stop_application_connections"
      target: "application servers"
      description: "Drain and close all database connections from application"
      dependencies: ["step-04"]
      estimated_duration: "5 minutes"
      verification_criteria: "Zero active connections from application, only DBA connections remain"
      rollback_action: "Allow application reconnection"
      checkpoint: true
      risk_notes: null
    - id: "step-06"
      action: "run_pg_upgrade"
      target: "primary database"
      description: "Execute pg_upgrade --link from PG12 to PG15"
      dependencies: ["step-05"]
      estimated_duration: "30-60 minutes"
      verification_criteria: "pg_upgrade completes without errors, log shows success"
      rollback_action: "Restore from step-02 backup"
      checkpoint: true
      risk_notes: "Most critical step - cannot partially rollback"
    - id: "step-07"
      action: "verify_upgrade"
      target: "upgraded database"
      description: "Run verification queries and check data integrity"
      dependencies: ["step-06"]
      estimated_duration: "15 minutes"
      verification_criteria: "Row counts match, critical tables validated, indexes present"
      rollback_action: "If verification fails, restore from backup"
      checkpoint: false
      risk_notes: null
    - id: "step-08"
      action: "update_configuration"
      target: "postgresql.conf"
      description: "Apply PG15-optimized configuration settings"
      dependencies: ["step-07"]
      estimated_duration: "10 minutes"
      verification_criteria: "pg_reload_conf() succeeds, SHOW commands confirm settings"
      rollback_action: "Revert to previous config and restart"
      checkpoint: false
      risk_notes: "Tune parameters for PG15 features"
    - id: "step-09"
      action: "run_analyze"
      target: "all tables"
      description: "Update statistics for query planner"
      dependencies: ["step-08"]
      estimated_duration: "20 minutes"
      verification_criteria: "ANALYZE completes on all tables, pg_stat_user_tables shows recent analyze"
      rollback_action: null
      checkpoint: false
      risk_notes: "Can run with application up if needed"
    - id: "step-10"
      action: "restore_replicas"
      target: "read replicas"
      description: "Rebuild replicas from upgraded primary using pg_basebackup"
      dependencies: ["step-09"]
      estimated_duration: "60 minutes"
      verification_criteria: "Replicas streaming, replication lag < 1 second"
      rollback_action: null
      checkpoint: false
      risk_notes: "Application can come up before replicas are ready"
    - id: "step-11"
      action: "enable_application"
      target: "application"
      description: "Disable maintenance mode, allow traffic"
      dependencies: ["step-09"]
      estimated_duration: "5 minutes"
      verification_criteria: "Health checks pass, orders processing, no errors in logs"
      rollback_action: "Re-enable maintenance mode, investigate"
      checkpoint: true
      risk_notes: "Monitor closely for first 30 minutes"
    - id: "step-12"
      action: "post_migration_monitoring"
      target: "all systems"
      description: "Monitor performance, errors, and replication for 2 hours"
      dependencies: ["step-11"]
      estimated_duration: "120 minutes"
      verification_criteria: "No performance degradation, no errors, replicas caught up"
      rollback_action: "Engage incident response if issues"
      checkpoint: false
      risk_notes: "Keep DBA on call"
  checkpoints:
    - after_step: "step-02"
      type: file_backup
      description: "Full database backup available for restore"
    - after_step: "step-05"
      type: state_snapshot
      description: "Clean shutdown state, can restart PG12 if needed"
    - after_step: "step-06"
      type: approval_gate
      description: "DBA verifies upgrade success before proceeding"
    - after_step: "step-11"
      type: approval_gate
      description: "Team confirms application healthy before ending maintenance"
  success_criteria:
    - "Database running PostgreSQL 15"
    - "All data intact and verified"
    - "Application functional with no errors"
    - "Replication active to all replicas"
    - "Performance equal or better than before"
    - "Downtime within 4-hour window"
  estimated_total_duration: "3.5 hours (plus 2-hour monitoring)"
  estimated_risk: medium
parallel_opportunities:
  - steps: ["step-10"]
    reason: "Replica rebuild can continue after application is up (step-11)"
critical_path:
  - step_id: "step-02"
    reason: "Backup duration is fixed by database size"
  - step_id: "step-06"
    reason: "pg_upgrade duration depends on database complexity"
risk_analysis:
  - risk: "pg_upgrade fails mid-process"
    probability: low
    impact: high
    mitigation: "Full backup at step-02 enables complete restore"
    affected_steps: ["step-06"]
  - risk: "Backup takes longer than expected"
    probability: medium
    impact: medium
    mitigation: "Start 30 minutes early, have incremental backup as fallback"
    affected_steps: ["step-02"]
  - risk: "Application incompatibility discovered in production"
    probability: low
    impact: high
    mitigation: "Thorough staging testing, quick rollback procedure"
    affected_steps: ["step-11"]
  - risk: "Maintenance window exceeded"
    probability: low
    impact: medium
    mitigation: "Clear go/no-go decision points, prepared communication"
    affected_steps: ["all"]
alternatives_considered:
  - "Logical replication migration - rejected due to complexity and longer transition period"
  - "Blue-green deployment with new database - rejected due to data sync complexity"
  - "pg_upgrade without --link - rejected due to longer duration and more disk space"
constraints_used:
  - constraint: "max_downtime: 4 hours"
    satisfied: true
    notes: "Estimated 3.5 hours within window"
  - constraint: "data_loss_tolerance: zero"
    satisfied: true
    notes: "Full backup before changes, verification after"
  - constraint: "maintenance_window: Saturday 2am-6am"
    satisfied: true
    notes: "Plan fits within window with buffer"
rationale: "pg_upgrade --link is the fastest in-place upgrade method for large databases. The plan includes comprehensive checkpoints and rollback procedures to ensure zero data loss. Application downtime is minimized by allowing application restart before replica rebuild completes."
confidence: 0.85
evidence_anchors:
  - "input:context"
  - "input:constraints"
  - "postgresql:upgrade_documentation"
assumptions:
  - "pg_upgrade compatible between PG12 and PG15"
  - "Sufficient disk space for upgrade process"
  - "Network bandwidth adequate for replica rebuild"
  - "No major schema changes blocking upgrade"
safety_notes:
  - "Never skip the backup step"
  - "Test rollback procedure before migration day"
  - "Have DBA available throughout migration"
  - "Document any deviations from plan"
  - "Do not force completion if issues arise"
next_actions:
  - "Review plan with DBA team"
  - "Schedule staging rehearsal"
  - "Prepare communication templates"
  - "Create monitoring dashboards"
  - "Document rollback procedure details"
```

**Evidence pattern:** Goal decomposition + dependency mapping + risk analysis

## Verification

- [ ] Plan achieves stated goal
- [ ] All steps have verification criteria
- [ ] Dependencies form valid DAG
- [ ] Rollback options cover failure scenarios
- [ ] Time estimates sum to within constraints

**Verification tools:** Read (for context and constraints)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Plans for mutations should include rollback options
- Flag irreversible steps clearly
- Include verification criteria for all critical steps
- Do not generate plans that bypass safety measures
- Recommend checkpoints for high-risk operations

## Composition Patterns

**Commonly follows:**
- `compare-plans` - after choosing approach
- `critique` - to address plan weaknesses
- `estimate-risk` - to inform risk mitigation

**Commonly precedes:**
- `act-plan` - to execute the plan
- `verify` - to validate plan steps
- `checkpoint` - to create restore points

**Anti-patterns:**
- Never generate plans without rollback considerations
- Avoid over-detailed plans that become unmaintainable

**Workflow references:**
- See `workflow_catalog.json#project_execution` for implementation workflows
- See `workflow_catalog.json#change_management` for operational changes
