---
status: complete
priority: p2
issue_id: "009"
tags: [coordination, agent-native, api]
dependencies: []
---

# Add missing enumeration APIs for agent-native access

## Problem Statement

The coordination runtime is missing several enumeration and query APIs that agents need for programmatic access. Currently 24/30 operations are agent-accessible, but 6 key operations are missing. Error responses are human-readable strings rather than typed exceptions that agents can parse.

## Findings

- Missing: `list_tasks()`, `list_results()` on DelegationProtocol
- Missing: `list_barriers()` on SyncPrimitive
- Missing: `update_trust()` on AgentRegistry (trust scores are immutable after registration)
- Missing: time-range queries on audit log (`get_events_between(start, end)`)
- No typed exception hierarchy — errors are generic `ValueError` with string messages
- Agent-native review: 24/30 operations accessible, verdict "NEEDS WORK"

## Proposed Solutions

### Option 1: Add enumeration methods + typed exceptions

**Approach:** Add `list_tasks()`, `list_results()`, `list_barriers()` methods. Create `CoordinationError` hierarchy for typed error handling.

**Pros:**
- Enables agents to discover and enumerate runtime state
- Typed exceptions allow programmatic error handling

**Cons:**
- Increases API surface area

**Effort:** Medium

**Risk:** Low

## Recommended Action

Add `list_tasks(status_filter: str | None = None)` and `list_results(accepted_filter: bool | None = None)` to `DelegationProtocol`. Add `list_barriers()` to `SyncPrimitive`. Create `grounded_agency/coordination/exceptions.py` with `CoordinationError(Exception)` base and subclasses: `AgentNotRegisteredError`, `CapabilityMismatchError`, `BarrierResolvedError`, `TaskLifecycleError`. Defer `update_trust()` and time-range audit queries to a separate PR.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/delegation.py` — Add `list_tasks()`, `list_results()`
- `grounded_agency/coordination/synchronization.py` — Add `list_barriers()`
- `grounded_agency/coordination/registry.py` — Add `update_trust()` or re-register pattern
- New file: `grounded_agency/coordination/exceptions.py` — Typed exception hierarchy

## Acceptance Criteria

- [ ] `list_tasks()` returns all tasks (optionally filtered by status)
- [ ] `list_results()` returns all results (optionally filtered by accepted/completed)
- [ ] `list_barriers()` returns all active barriers
- [ ] Error responses use typed exceptions from CoordinationError hierarchy
- [ ] Tests cover enumeration and error type assertions

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Audited all coordination APIs for agent accessibility
- Identified 6 missing enumeration/query operations
- Confirmed error responses are human-only strings

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
- Scoped down: defer update_trust and time-range queries to separate PR
