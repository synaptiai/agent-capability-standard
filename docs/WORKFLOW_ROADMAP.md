# Workflow Roadmap

This document tracks the current state and future plans for workflow development in the Agent Capability Standard.

## Current Workflows (5)

The following workflows are fully defined in `schemas/workflow_catalog.json`:

### 1. `debug_code_change`
- **Goal:** Safely diagnose and fix a bug/regression in a codebase.
- **Risk:** High (includes mutation steps)
- **Steps:** inspect → search → map-relationships → model-schema → critique → plan → act-plan → verify → audit → rollback

### 2. `world_model_build`
- **Goal:** Construct a structured world model for a domain with dynamics and uncertainty.
- **Risk:** Low (read-only)
- **Steps:** retrieve → inspect → identity-resolution → world-state → state-transition → causal-model → uncertainty-model → provenance → grounding → simulation → summarize

### 3. `capability_gap_analysis`
- **Goal:** Assess a project/system to identify missing capabilities and propose new skills.
- **Risk:** Medium
- **Steps:** inspect → map-relationships → discover-relationship → compare-plans → prioritize → generate-plan → audit

### 4. `digital_twin_sync_loop`
- **Goal:** Synchronize digital twin state with incoming signals, detect drift, decide and execute safe actions.
- **Risk:** High (includes mutation with rollback)
- **Features:** Parallel groups, gates, recovery loops, input bindings
- **Steps:** receive → search → transform → integrate → identity-resolution → world-state → diff-world-state → state-transition → detect-anomaly → estimate-risk → forecast-risk → plan → constrain → checkpoint → act-plan → verify → audit → rollback → summarize

### 5. `digital_twin_bootstrap`
- **Goal:** Initialize a digital twin from scratch then run a first sync loop.
- **Risk:** High
- **Steps:** invoke-workflow(world_model_build) → invoke-workflow(digital_twin_sync_loop)

## Workflow Skill Directories

Each workflow has a corresponding skill directory in `skills/workflows/`:

| Workflow | Skill Directory |
|----------|-----------------|
| `debug_code_change` | `skills/workflows/debug-workflow/` |
| `capability_gap_analysis` | `skills/workflows/gap-analysis-workflow/` |
| `digital_twin_sync_loop` | `skills/workflows/digital-twin-sync-workflow/` |
| `world_model_build` | `skills/workflows/world-model-workflow/` |

## Future Workflow Candidates

The following workflows could extend the standard based on capability coverage:

### High Priority

| Workflow | Goal | Key Capabilities |
|----------|------|------------------|
| `security_audit` | Audit codebase for security vulnerabilities | inspect, search, detect-vulnerability, estimate-risk, generate-plan |
| `code_review` | Systematic code review with verification | inspect, critique, compare-options, verify, summarize |
| `api_integration` | Integrate with external APIs safely | retrieve, transform, verify, checkpoint, act-api |
| `data_migration` | Migrate data with validation and rollback | inspect, transform, checkpoint, verify, rollback |

### Medium Priority

| Workflow | Goal | Key Capabilities |
|----------|------|------------------|
| `test_generation` | Generate comprehensive test suites | inspect, model-schema, generate-code, verify |
| `documentation_sync` | Keep docs synchronized with code | inspect, diff-world-state, generate-text, verify |
| `dependency_update` | Safely update project dependencies | search, estimate-risk, checkpoint, act-plan, verify |
| `refactoring` | Systematic codebase refactoring | inspect, plan, checkpoint, act-plan, verify, rollback |

### Specialized

| Workflow | Goal | Key Capabilities |
|----------|------|------------------|
| `incident_response` | Respond to production incidents | receive, detect-anomaly, prioritize, plan, act-plan, audit |
| `compliance_check` | Verify regulatory compliance | inspect, verify, audit, summarize |
| `performance_optimization` | Identify and fix performance issues | inspect, detect-anomaly, estimate-risk, plan, verify |

## Contributing New Workflows

To propose a new workflow:

1. Open an RFC issue with:
   - Goal and success criteria
   - Step sequence with capabilities
   - Risk assessment
   - Input/output schemas

2. Follow the structure in `schemas/workflow_catalog.json`

3. Create corresponding skill directory in `skills/workflows/`

4. Add conformance tests

See `spec/GOVERNANCE.md` for the full RFC process.
