---
status: complete
priority: p1
issue_id: "001"
tags: [coordination, memory, security, performance, dos]
dependencies: []
---

# Add bounded size limits to all unbounded collections

## Problem Statement

Four coordination modules use unbounded `dict` or `defaultdict(list)` collections that grow without limit. In a long-running orchestration session, these will exhaust process memory (OOM). The audit log correctly uses `deque(maxlen=N)` and the evidence store has `max_anchors`, but delegation, sync, evidence bridge, and registry have no bounds.

## Findings

- `delegation.py:114-115` — `_tasks: dict` and `_results: dict` grow with every delegation, never evicted
- `synchronization.py:124` — `_barriers: dict` never cleaned up after resolution
- `evidence_bridge.py:84` — `_shared: defaultdict(list)` grows per target agent per share
- `registry.py:70` — `_agents: dict` unbounded (lower risk but still uncapped)
- Flagged by: Security (SEC-01 HIGH), Performance (SIG-1/2/3), Data Integrity (Finding 14/15), Simplicity review
- CWE-400: Uncontrolled Resource Consumption

## Proposed Solutions

### Option 1: Add max_size parameters with FIFO eviction

**Approach:** Add `max_tasks`, `max_barriers`, `max_shared_per_agent` parameters to constructors. Use `OrderedDict` with FIFO eviction for tasks/results, remove resolved barriers, cap per-agent evidence lists.

**Pros:**
- Consistent with existing pattern (audit log `maxlen`, evidence store `max_anchors`)
- Minimal API change — new optional constructor params with sensible defaults

**Cons:**
- Silent data loss (same tradeoff as audit log)

**Effort:** Small

**Risk:** Low

---

### Option 2: TTL-based cleanup with periodic sweep

**Approach:** Add timestamps to stored items and a `cleanup(max_age)` method that evicts expired entries.

**Pros:**
- Retains recent data regardless of volume
- More predictable behavior under burst loads

**Cons:**
- Requires caller to invoke cleanup (or a background thread)
- More complex implementation

**Effort:** Medium

**Risk:** Low

## Recommended Action

Implement Option 1 (max_size with FIFO eviction). Add `max_tasks=10000` default to `DelegationProtocol`, `max_shared_per_agent=1000` to `CrossAgentEvidenceBridge`, `max_agents=1000` to `AgentRegistry`. For barriers, rely on Todo 004's resolved-barrier removal for natural cleanup. Use `OrderedDict` with FIFO eviction for `_tasks`/`_results`, evicting only completed tasks.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/delegation.py:114-115` — `_tasks`, `_results` dicts
- `grounded_agency/coordination/synchronization.py:124` — `_barriers` dict
- `grounded_agency/coordination/evidence_bridge.py:84` — `_shared` defaultdict
- `grounded_agency/coordination/registry.py:70` — `_agents` dict

## Resources

- **PR:** #98
- **Issue:** #76
- **Related:** SEC-01, SIG-1/2/3, Finding 14/15

## Acceptance Criteria

- [ ] `DelegationProtocol` accepts `max_tasks` parameter, evicts oldest completed tasks
- [ ] `SyncPrimitive` removes resolved barriers from `_barriers` dict
- [ ] `CrossAgentEvidenceBridge` caps per-agent shared evidence list size
- [ ] `AgentRegistry` accepts `max_agents` parameter
- [ ] Existing tests still pass
- [ ] New tests verify eviction behavior

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Identified 4 unbounded collections across coordination modules
- Compared against bounded patterns in audit.py and evidence_store.py
- Cross-referenced findings from 5 review agents (security, performance, data integrity, simplicity, python quality)

**Learnings:**
- The audit log and evidence store already demonstrate the correct bounded pattern
- Priority-based eviction in evidence_store is more sophisticated than needed here — simple FIFO or remove-on-complete suffices

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session — address with rigor
- Status changed from pending to ready
- Recommended Action: Option 1 with FIFO eviction + sensible defaults

**Learnings:**
- This is the highest-impact P1: flagged by 5 of 9 review agents independently
