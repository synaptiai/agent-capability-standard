---
status: complete
priority: p3
issue_id: "011"
tags: [coordination, code-quality, cleanup]
dependencies: []
---

# Remove dead code and unnecessary abstractions

## Problem Statement

Several code artifacts exist that serve no functional purpose: dead enum, unused fields, backwards-compatibility aliases for new code, unused `to_dict()` methods, duplicate topological sort logic, and overly broad type unions. Approximately 371 lines (10.8%) could be removed.

## Findings

- `audit.py` — `EventType` enum defined but never used for validation (dead code)
- `synchronization.py` — `STRATEGY_*` module-level aliases unnecessary (new code, no backwards compat needed)
- `synchronization.py:55` — `required_state` field dead (never validated)
- `synchronization.py:56` — `timeout_seconds` informational only (never enforced)
- `orchestrator.py:225-291` — Topological sort duplicates existing WorkflowEngine logic
- `orchestrator.py:275` — `agent_pool` parameter on `orchestrate()` never used
- `delegation.py` — `set[str] | frozenset[str] | list[str]` union should be `Iterable[str]`
- 5 of 9 `to_dict()` methods have no production consumers
- `orchestrator.py:460` — Deferred `StepStatus` import should be module-level
- `tests/test_coordination.py` — Duplicate `_make_step` helpers in two test classes
- `tests/test_coordination.py` — `TestOrchestrateWiring` is white-box test of implementation detail
- Simplicity review: ~371 lines removable, including `resolve()` accepting `str` instead of `SyncStrategy` enum

## Proposed Solutions

### Option 1: Systematic cleanup pass

**Approach:** Remove dead code items one category at a time: dead enum, unused fields, unnecessary aliases, then consolidate type signatures.

**Pros:**
- Reduces maintenance burden
- Clearer API surface
- Better IDE support (unused code warnings eliminated)

**Cons:**
- Some items (like `EventType` enum) may be intended for future use

**Effort:** Small

**Risk:** Low

## Recommended Action

Focus on high-confidence removals only: (1) Remove `EventType` enum (zero consumers), (2) Remove `STRATEGY_*` module-level aliases (new code, no backwards compat), (3) Move deferred `StepStatus` import to module level, (4) Remove unused `agent_pool` parameter, (5) Consolidate duplicate `_make_step` test helpers. Leave topological sort and `to_dict()` methods in place — they may be used by future features or consumers.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/audit.py` — Remove or use EventType enum
- `grounded_agency/coordination/synchronization.py` — Remove STRATEGY_* aliases, dead fields
- `grounded_agency/coordination/orchestrator.py` — Move StepStatus import, remove agent_pool param
- `grounded_agency/coordination/delegation.py` — Simplify capability type to `Iterable[str]`
- `tests/test_coordination.py` — Consolidate _make_step helpers, review TestOrchestrateWiring

## Acceptance Criteria

- [ ] `EventType` enum either removed or used for validation
- [ ] `STRATEGY_*` aliases removed
- [ ] Dead `SyncBarrier` fields documented or removed
- [ ] `StepStatus` import moved to module level
- [ ] Duplicate test helpers consolidated
- [ ] All existing tests pass

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Catalogued all dead code via simplicity and pattern reviews
- Measured ~371 lines of removable code (10.8% of PR additions)
- Identified items that may be intentional for future use vs truly dead

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
- Scoped down: only remove high-confidence dead code, leave potentially intentional items
