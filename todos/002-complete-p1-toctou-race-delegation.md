---
status: complete
priority: p1
issue_id: "002"
tags: [coordination, concurrency, security, delegation]
dependencies: []
---

# Fix TOCTOU race condition in delegation protocol

## Problem Statement

`DelegationProtocol.delegate()` performs a registry lookup and capability check **outside** the delegation lock, then stores the result **inside** the lock. Between these two operations, another thread could unregister or re-register the agent with different capabilities, allowing delegation to be accepted based on stale data.

## Findings

- `delegation.py:201` — `get_agent()` acquires/releases registry lock
- `delegation.py:209` — Capability check happens with no lock held
- `delegation.py:234-236` — Result stored under delegation lock (different lock)
- Same pattern in `auto_delegate()` — `discover_by_capabilities()` returns a snapshot that can become stale
- CWE-367: Time-of-Check Time-of-Use
- Flagged by: Security (SEC-02 HIGH), Data Integrity (Finding 6 HIGH)

## Proposed Solutions

### Option 1: Re-verify under delegation lock

**Approach:** After acquiring `self._lock`, re-call `self._agent_registry.get_agent()` and verify the agent still exists and has the required capabilities before storing.

**Pros:**
- Minimal change — add ~5 lines inside the existing `with self._lock` block
- No lock coupling between modules

**Cons:**
- Double registry lookup (minor overhead)
- Still not fully atomic (agent could be unregistered between re-check and store)

**Effort:** Small

**Risk:** Low

---

### Option 2: Hold a single lock spanning check and store

**Approach:** Introduce a coordination-level lock or use the delegation lock to span both the registry lookup and result storage.

**Pros:**
- True atomicity — no window for race conditions

**Cons:**
- Lock coupling between modules increases deadlock risk
- Requires careful lock ordering documentation

**Effort:** Medium

**Risk:** Medium

## Recommended Action

Implement Option 1 (re-verify under delegation lock). Inside the `with self._lock` block in `delegate()`, re-call `self._agent_registry.get_agent(target_agent_id)` and verify it is not None and still has required capabilities. If stale, set `result.accepted = False` with rejection reason. Apply same pattern to `auto_delegate()`. Add a concurrent delegate+unregister test.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/delegation.py:190-253` — `delegate()` method
- `grounded_agency/coordination/delegation.py:256-311` — `auto_delegate()` method

## Resources

- **PR:** #98
- **Related:** SEC-02, Finding 6

## Acceptance Criteria

- [ ] Agent existence is re-verified under the delegation lock before storing accepted results
- [ ] Test added for concurrent delegate + unregister scenario
- [ ] No deadlocks introduced (lock ordering documented)

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Identified TOCTOU race between registry lookup (line 201) and result storage (line 234)
- Confirmed locks are independent (registry._lock vs delegation._lock)
- Verified the race window exists in both delegate() and auto_delegate()

**Learnings:**
- Current code acquires/releases locks sequentially (not nested), which is good for deadlock avoidance but creates TOCTOU windows
- The re-verify approach is simpler and safer than lock coupling

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
- Recommended: Option 1 (re-verify under lock), not Option 2 (lock coupling)

**Learnings:**
- CWE-367 race — flagged by both security and data integrity agents
