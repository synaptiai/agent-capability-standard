---
status: complete
priority: p1
issue_id: "003"
tags: [coordination, delegation, data-integrity]
dependencies: []
---

# Add state machine validation to delegation lifecycle

## Problem Statement

`DelegationResult` has no explicit status field and no state transition validation. Tasks can be completed multiple times (silently overwriting `output_data`), rejected tasks can be "completed", and there is no way to distinguish in-progress from completed tasks. Each spurious `complete_task()` call creates duplicate evidence anchors and audit events.

## Findings

- `delegation.py:323-355` — `complete_task()` has no guard against double-completion or completing rejected tasks
- `delegation.py:339` — Evidence anchors accumulate with each call: `result.evidence_anchors = result.evidence_anchors + list(evidence_anchors)`
- No `status` field on `DelegationResult` — only `accepted: bool`
- Data Integrity Finding 3 (HIGH): "the most likely source of data corruption in normal operation"
- Python Review P1-3: Union type issue also relates to task lifecycle

## Proposed Solutions

### Option 1: Add explicit status field with transition guards

**Approach:** Add `status: str` field to `DelegationResult` (values: "pending", "accepted", "rejected", "completed", "failed"). Guard `complete_task()` to only accept "accepted" tasks and transition them to "completed" exactly once.

**Pros:**
- Clear lifecycle semantics
- Prevents all double-completion and reject-then-complete scenarios
- Enables future state queries (e.g., "list all in-progress tasks")

**Cons:**
- API change — callers checking `result.accepted` need updating

**Effort:** Small

**Risk:** Low

## Recommended Action

Add `status: str` field to `DelegationResult` with values `"accepted"`, `"rejected"`, `"completed"`. In `delegate()`, set status to `"accepted"` or `"rejected"` based on capability check. In `complete_task()`, guard with `if result.status != "accepted": raise ValueError(...)` and transition to `"completed"` exactly once. Keep `accepted` property as a convenience (`return self.status == "accepted"`).

## Technical Details

**Affected files:**
- `grounded_agency/coordination/delegation.py:42-75` — `DelegationResult` dataclass
- `grounded_agency/coordination/delegation.py:323-355` — `complete_task()` method
- `tests/test_coordination.py` — Add lifecycle validation tests

## Resources

- **PR:** #98
- **Related:** Data Integrity Finding 3

## Acceptance Criteria

- [ ] `DelegationResult` has a `status` field with defined lifecycle states
- [ ] `complete_task()` raises `ValueError` if task is not in "accepted" state
- [ ] `complete_task()` transitions status to "completed" and rejects subsequent calls
- [ ] Rejected tasks cannot be completed
- [ ] Tests cover: double-completion, reject-then-complete, normal lifecycle

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Identified missing state machine in DelegationResult
- Verified complete_task() silently overwrites output_data on re-call
- Confirmed evidence_anchors list grows with each complete_task() call

**Learnings:**
- The accumulating evidence_anchors is particularly dangerous — it creates phantom provenance

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
- Keep `accepted` property for backwards compat, add `status` field for full lifecycle

**Learnings:**
- Data integrity agent rated this the #1 most likely data corruption source
