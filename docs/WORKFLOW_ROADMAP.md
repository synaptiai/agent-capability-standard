# Workflow Roadmap

This document tracks the current state and future plans for workflow development in the Agent Capability Standard.

## Current Workflows (12)

The reference catalog, `schemas/workflow_catalog.yaml`, defines these
workflows (step capabilities in order; a domain in brackets):

### 1. `monitor_and_replan`
- **Goal:** Detect world changes that invalidate the current plan and trigger replanning when needed.
- **Declared risk:** medium
- **Steps:** observe → state → compare[assumption_validation] → detect[plan-invalidation] → critique → plan → audit

### 2. `clarify_intent`
- **Goal:** Resolve ambiguous user requests through targeted clarification questions.
- **Declared risk:** low
- **Steps:** critique → inquire → receive → integrate → audit

### 3. `debug_code_change`
- **Goal:** Safely diagnose and fix a bug/regression in a codebase.
- **Declared risk:** medium
- **Steps:** observe → search → attribute[dependencies] → constrain → critique → plan → checkpoint → execute → verify → rollback → audit

### 4. `world_model_build`
- **Goal:** Construct a structured world model for a domain (real or digital) with dynamics and uncertainty.
- **Declared risk:** low
- **Steps:** retrieve → observe → detect[entity] → classify → integrate → state → transition → attribute[causation] → measure[uncertainty] → audit → ground → simulate → explain

### 5. `capability_gap_analysis`
- **Goal:** Assess a project/system to identify missing capabilities and propose new skills.
- **Declared risk:** low
- **Steps:** observe → attribute[dependencies] → discover → compare[architecture] → compare[priority] → generate[plan] → audit

### 6. `digital_twin_sync_loop`
- **Goal:** Synchronize digital twin state with incoming signals, detect drift, decide and execute safe actions, and record provenance.
- **Declared risk:** high
- **Steps:** receive → search → transform → integrate → detect[entity] → classify → state → compare[state_diff] → transition → detect[anomaly] → measure[risk] → predict[risk] → plan → constrain → checkpoint → mutate → execute → verify → rollback → audit → explain

### 7. `digital_twin_bootstrap`
- **Goal:** Initialize a digital twin from scratch then run a first sync loop.
- **Declared risk:** high
- **Steps:** invoke(world_model_build) → invoke(digital_twin_sync_loop) → invoke(digital_twin_sync_loop)

### 8. `rag_pipeline`
- **Goal:** Retrieve relevant information and generate a grounded, evidence-cited response.
- **Declared risk:** low
- **Steps:** search → retrieve → detect[relevance] → generate → ground → explain → audit

### 9. `security_assessment`
- **Goal:** Identify and assess security vulnerabilities with risk scoring and mitigation recommendations.
- **Declared risk:** low
- **Steps:** search → detect[vulnerability] → measure[severity] → attribute[causation] → critique → generate[report] → audit

### 10. `multi_agent_orchestration`
- **Goal:** Coordinate multiple agents to execute a complex task through decomposition, delegation, and result integration.
- **Declared risk:** medium
- **Steps:** decompose → plan → delegate → synchronize → verify → integrate → audit

### 11. `data_quality_pipeline`
- **Goal:** Examine, detect, classify, measure, clean, verify, and audit data quality issues.
- **Declared risk:** low
- **Steps:** observe → detect[data_issue] → classify → measure[quality] → transform → verify → audit

### 12. `model_deployment`
- **Goal:** Safely deploy an ML model to production with validation, policy checks, and rollback capability.
- **Declared risk:** high
- **Steps:** constrain → constrain → checkpoint → execute → verify → measure[performance] → rollback → audit

## Workflow Skill Directories

Four workflows have a skill that runs them step by step:

| Workflow | Skill Directory | Skill name |
|----------|-----------------|------------|
| `debug_code_change` | `skills/debug-workflow/` | `debug-workflow` |
| `capability_gap_analysis` | `skills/capability-gap-analysis/` | `gap-analysis-workflow` |
| `digital_twin_sync_loop` | `skills/digital-twin-sync-loop/` | `digital-twin-sync-workflow` |
| `digital_twin_bootstrap` | `skills/digital-twin-bootstrap/` | `digital-twin-bootstrap` |

`world_model_build` has no skill of its own: `digital-twin-bootstrap` runs it
as its first step when no world state is given.

## Future Workflow Candidates

The following workflows could extend the standard based on capability coverage:

### High Priority

| Workflow | Goal | Key Capabilities |
|----------|------|------------------|
| `code_review` | Systematic code review with verification | observe, critique, compare, verify, explain |
| `api_integration` | Integrate with external APIs safely | retrieve, transform, verify, checkpoint, invoke |
| `data_migration` | Migrate data with validation and rollback | observe, transform, checkpoint, verify, rollback |

### Medium Priority

| Workflow | Goal | Key Capabilities |
|----------|------|------------------|
| `test_generation` | Generate comprehensive test suites | observe, constrain, generate[code], verify |
| `documentation_sync` | Keep docs synchronized with code | observe, compare[state], generate, verify |
| `dependency_update` | Safely update project dependencies | search, measure[risk], checkpoint, execute, verify |
| `refactoring` | Systematic codebase refactoring | observe, plan, checkpoint, execute, verify, rollback |

### Specialized

| Workflow | Goal | Key Capabilities |
|----------|------|------------------|
| `incident_response` | Respond to production incidents | receive, detect[anomaly], compare[priority], plan, execute, audit |
| `compliance_check` | Verify regulatory compliance | observe, verify, audit, explain |
| `performance_optimization` | Identify and fix performance issues | observe, detect[anomaly], measure[risk], plan, verify |

## Contributing New Workflows

To propose a new workflow:

1. Open an RFC issue with:
   - Goal and success criteria
   - Step sequence with capabilities
   - Risk assessment
   - Input/output schemas

2. Follow the structure in `schemas/workflow_catalog.yaml`

3. Optionally, create a skill that runs it in `skills/`

4. Add conformance tests

See `spec/GOVERNANCE.md` for the full RFC process.
