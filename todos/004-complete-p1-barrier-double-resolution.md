---
status: complete
priority: p1
issue_id: "004"
tags: [coordination, synchronization, data-integrity, concurrency]
dependencies: []
---

# Prevent barrier double-resolution and add cleanup

## Problem Statement

`SyncBarrier` can be resolved multiple times — `resolve()` does not mark the barrier as consumed. Each call produces a new `SyncResult` with potentially different outcomes (if proposals were modified between calls), creates duplicate evidence anchors and audit events, and the barrier is never removed from `_barriers` after resolution.

## Findings

- `synchronization.py:179-289` — `resolve()` has no "already resolved" guard
- `synchronization.py:124` — Resolved barriers remain in `_barriers` dict forever
- `synchronization.py:55` — `timeout_seconds` field is informational only, never enforced
- `synchronization.py:60` — `required_state` field is dead (never validated)
- Concurrent contribute() + resolve() can interleave: Thread B contributes while Thread A is merging (lock released during merge)
- Flagged by: Security (SEC-07 MEDIUM), Data Integrity (Finding 4 HIGH, Finding 10 MEDIUM, Finding 13 LOW)

## Proposed Solutions

### Option 1: Add resolved flag + remove after resolution

**Approach:** Add `resolved: bool = False` to `SyncBarrier`. Set it `True` under the lock in `resolve()`. Reject `contribute()` and `resolve()` on resolved barriers. Remove from `_barriers` after successful resolution.

**Pros:**
- Prevents all double-resolution and post-resolution contribution
- Automatically bounds memory by removing resolved barriers
- Simple implementation

**Cons:**
- Barrier metadata is lost after resolution (mitigated by evidence anchors + audit events)

**Effort:** Small

**Risk:** Low

## Recommended Action

Implement Option 1. Add `resolved: bool = False` to `SyncBarrier`. In `resolve()`, set `resolved = True` under the lock BEFORE releasing it for merge computation. Reject `contribute()` and `resolve()` on already-resolved barriers with `ValueError`. Remove the barrier from `_barriers` dict after successful resolution. This also solves the memory leak aspect for barriers (complementing Todo 001).

## Technical Details

**Affected files:**
- `grounded_agency/coordination/synchronization.py:40-60` — `SyncBarrier` dataclass
- `grounded_agency/coordination/synchronization.py:154-177` — `contribute()` method
- `grounded_agency/coordination/synchronization.py:179-289` — `resolve()` method

## Resources

- **PR:** #98
- **Related:** SEC-07, Finding 4, Finding 10, Finding 13

## Acceptance Criteria

- [ ] `SyncBarrier` has a `resolved: bool` field defaulting to `False`
- [ ] `resolve()` sets `resolved = True` under the lock before releasing it
- [ ] `resolve()` raises on already-resolved barriers
- [ ] `contribute()` rejects contributions to resolved barriers
- [ ] Resolved barriers are removed from `_barriers` dict
- [ ] Tests cover: double-resolve, contribute-after-resolve, cleanup verification

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Identified barrier double-resolution vulnerability
- Confirmed resolve() releases lock before merge, creating interleave window
- Verified barriers are never cleaned up from _barriers dict

**Learnings:**
- The snapshot approach in resolve() (dict(barrier.proposals)) is safe for the merge itself, but the lack of a resolved flag allows the entire operation to repeat

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
- This also handles barrier cleanup for Todo 001 memory concerns

**Learnings:**
- Data integrity rated this the #2 most dangerous concurrency scenario
